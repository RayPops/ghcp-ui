"""Pure translator: SchedulingDecision + WorkOrder + coordinates -> PSO XML.

This module performs **no I/O** — it does not read CSVs, geocode postcodes, or
make HTTP calls. That keeps it trivially unit-testable and snapshot-friendly.

Output XML follows the ``07 - Add Tasks`` shape from the IFS Postman
collection. The namespace is ``http://360Scheduling.com/Schema/dsScheduleData.xsd``.

All datetimes are emitted in UTC with explicit ``+00:00`` offset, matching
every example in the Postman collection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Optional
from xml.etree import ElementTree as ET

from app.models import SchedulingDecision, WorkOrder
from app.sla_guardrail import apply_sla_guardrail

from . import mappings

PSO_NAMESPACE = "http://360Scheduling.com/Schema/dsScheduleData.xsd"
DEFAULT_DATASET_ID = "CC_LIVE"

# Working day window used for the SLA bracket when no narrower constraint
# is available.
_DEFAULT_DAY_START_HOUR = 9
_DEFAULT_DAY_END_HOUR = 17


# --------------------------------------------------------------------------- #
# Inputs container
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PsoTaskInputs:
    """The fully-resolved set of fields needed to render a PSO Activity.

    Built by :func:`build_pso_inputs` and consumed by
    :func:`render_add_tasks_xml`. Pulled out as its own type so callers
    (and tests) can inspect or override individual fields without poking
    at the XML.
    """

    order_id: str
    latitude: float
    longitude: float
    task_type: str
    soonest_start: datetime
    latest_start: datetime
    duration_minutes: int
    required_skills: list[str]
    postcode: str
    text_description: str
    value: int
    region: str | None
    availability_window: tuple[datetime, datetime] | None


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #


def _next_working_day(d: date) -> date:
    """Advance ``d`` to the next Mon-Fri date if it lands on a weekend."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _at_utc(d: date, hour: int) -> datetime:
    return datetime.combine(d, time(hour=hour, tzinfo=timezone.utc))


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"  # ellipsis


def build_pso_inputs(
    decision: SchedulingDecision,
    order: WorkOrder,
    coordinates: tuple[float, float],
    *,
    today: Optional[date] = None,
) -> PsoTaskInputs:
    """Compose a :class:`PsoTaskInputs` from a decision + the source order.

    ``coordinates`` must be ``(latitude, longitude)`` in WGS84.

    ``today`` (default :func:`datetime.date.today`) drives the SLA guardrail
    (see ``app.sla_guardrail``): any committed delivery date in the past is
    rolled forward to ``today + 1 business day`` so PSO never receives an
    Activity whose soonest/latest start times are in the past.
    """
    if today is None:
        today = date.today()

    latitude, longitude = coordinates

    # SLA guardrail: shift past committed dates before any planning math.
    guardrail = apply_sla_guardrail(order.committed_delivery_date, today)
    effective_committed = guardrail.effective_date

    # Planned date: prefer the decision's planned_visit_date; fall back to
    # the (guardrail-adjusted) committed delivery date. If the decision's
    # planned date is itself in the past, the guardrail also shifts it so
    # PSO never sees a stale SLA.
    planned = decision.planned_visit_date or effective_committed
    if planned < today:
        planned = apply_sla_guardrail(planned, today).effective_date
    planned = _next_working_day(planned)

    soonest = _at_utc(planned, _DEFAULT_DAY_START_HOUR)
    latest_day = _next_working_day(planned + timedelta(days=1))
    latest = _at_utc(latest_day, _DEFAULT_DAY_END_HOUR)

    # Task type
    task_type = mappings.map_task_type(order.service_type, order.job_type)

    # Duration
    duration_minutes = 60
    if decision.visit_readiness and decision.visit_readiness.estimated_duration_minutes:
        duration_minutes = int(decision.visit_readiness.estimated_duration_minutes)

    # Skills
    required_tools: list[str] = []
    safety_equipment: list[str] = []
    safety_risks: list[str] = []
    if decision.visit_readiness:
        required_tools = list(decision.visit_readiness.required_tools or [])
    if decision.safety_assessment:
        safety_equipment = list(decision.safety_assessment.safety_equipment or [])
        safety_risks = list(decision.safety_assessment.safety_risks or [])

    skills = mappings.derive_skill_ids(
        service_type=order.service_type,
        required_tools=required_tools,
        safety_equipment=safety_equipment,
        safety_risks=safety_risks,
        exchange_visit_flag=order.exchange_visit_flag,
    )

    # Value: bumped when a human needs to review (nudges PSO to prioritise).
    value = (
        mappings.HUMAN_REVIEW_VALUE
        if decision.recommended_action == "needs-human-review"
        else mappings.DEFAULT_VALUE
    )

    # Optional Availability window from the customer-availability label.
    availability_window: tuple[datetime, datetime] | None = None
    if decision.constraints and decision.constraints.customer_availability_window:
        label = decision.constraints.customer_availability_window.lower().strip()
        slot = mappings.AVAILABILITY_WINDOW_TABLE.get(label)
        if slot is not None:
            start_hour, end_hour = slot
            availability_window = (
                _at_utc(planned, start_hour),
                _at_utc(planned, end_hour),
            )

    text_description = _truncate(
        order.unstructured_customer_notes or "",
        mappings.TEXT_DESCRIPTION_MAX_LEN,
    )

    return PsoTaskInputs(
        order_id=order.order_id,
        latitude=latitude,
        longitude=longitude,
        task_type=task_type,
        soonest_start=soonest,
        latest_start=latest,
        duration_minutes=duration_minutes,
        required_skills=skills,
        postcode=order.postcode or "",
        text_description=text_description,
        value=value,
        region=None,  # Not derived; see Open Questions for Federico.
        availability_window=availability_window,
    )


# --------------------------------------------------------------------------- #
# XML rendering
# --------------------------------------------------------------------------- #


def _iso_utc(dt: datetime) -> str:
    """Format a tz-aware datetime as ``YYYY-MM-DDTHH:MM:SS+00:00``."""
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    dt = dt.astimezone(timezone.utc)
    # PSO examples use no microseconds.
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def _iso_duration_minutes(minutes: int) -> str:
    """Format an integer minute count as an ISO 8601 duration ``PT{N}M``."""
    return f"PT{int(minutes)}M"


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    elem = ET.SubElement(parent, tag)
    if text is not None:
        elem.text = text
    return elem


def render_add_tasks_xml(
    inputs: PsoTaskInputs,
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    input_type: str = "CHANGE",
    description: str | None = None,
    now: datetime | None = None,
    uuid_factory: Callable[[], str] | None = None,
) -> str:
    """Render the full ``<dsScheduleData>`` XML body for ``07 - Add Tasks``.

    Parameters
    ----------
    inputs:
        The resolved task fields.
    dataset_id:
        Target PSO dataset; defaults to ``CC_LIVE``.
    input_type:
        ``"CHANGE"`` for incremental adds (the normal case) or ``"LOAD"``
        for an initial bulk load.
    description:
        Optional ``<Input_Reference><description>`` text.
    now:
        Override "now" for snapshot tests. Defaults to the current UTC time.
    uuid_factory:
        Override the input-reference id generator for snapshot tests.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if uuid_factory is None:
        uuid_factory = lambda: uuid.uuid4().hex  # noqa: E731

    ET.register_namespace("", PSO_NAMESPACE)
    root = ET.Element(f"{{{PSO_NAMESPACE}}}dsScheduleData")

    # --- Input_Reference -------------------------------------------------- #
    # Minimal envelope shape, matching the Postman collection's `02 - Add a
    # new resource` and `07 - Add Tasks` requests (incremental CHANGE inputs).
    # The longer envelope from `01 - First Dataset CC Load` is only required
    # for the initial bulk LOAD and is intentionally not emitted here.
    input_ref = ET.SubElement(root, "Input_Reference")
    _sub(input_ref, "datetime", _iso_utc(now))
    _sub(input_ref, "id", uuid_factory())
    _sub(
        input_ref,
        "description",
        description or f"BT Openreach push: {inputs.order_id}",
    )
    _sub(input_ref, "input_type", input_type)
    _sub(input_ref, "dataset_id", dataset_id)

    # --- Activity --------------------------------------------------------- #
    activity = ET.SubElement(root, "Activity")
    _sub(activity, "id", inputs.order_id)
    _sub(activity, "activity_class_id", mappings.ACTIVITY_CLASS_ID)
    _sub(activity, "activity_type_id", inputs.task_type)
    _sub(activity, "location_id", inputs.order_id)
    _sub(activity, "do_on_site", "false")
    _sub(activity, "duration", _iso_duration_minutes(inputs.duration_minutes))
    _sub(activity, "base_value", str(inputs.value))

    # --- Activity_SLA (Soonest / Lastest we can Start) ------------------- #
    sla = ET.SubElement(root, "Activity_SLA")
    _sub(sla, "sla_type_id", mappings.DEFAULT_SLA_TYPE)
    _sub(sla, "activity_id", inputs.order_id)
    _sub(sla, "datetime_start", _iso_utc(inputs.soonest_start))
    _sub(sla, "datetime_end", _iso_utc(inputs.latest_start))
    _sub(sla, "priority", "1")
    _sub(sla, "start_based", "true")

    # --- Activity_Status -------------------------------------------------- #
    status = ET.SubElement(root, "Activity_Status")
    _sub(status, "activity_id", inputs.order_id)
    _sub(status, "status_id", "0")
    _sub(status, "date_time_status", _iso_utc(inputs.soonest_start))
    _sub(status, "visit_id", "1")
    _sub(status, "fixed", "false")
    _sub(status, "date_time_stamp", _iso_utc(inputs.soonest_start))

    # --- Location --------------------------------------------------------- #
    location = ET.SubElement(root, "Location")
    _sub(location, "id", inputs.order_id)
    _sub(location, "latitude", f"{inputs.latitude}")
    _sub(location, "longitude", f"{inputs.longitude}")

    # --- Activity_Skill (one per derived skill) -------------------------- #
    for skill_id in inputs.required_skills:
        skill_elem = ET.SubElement(root, "Activity_Skill")
        _sub(skill_elem, "skill_id", skill_id)
        _sub(skill_elem, "activity_id", inputs.order_id)

    # --- Availability (optional, only when a window was resolved) -------- #
    if inputs.availability_window is not None:
        win_start, win_end = inputs.availability_window
        avail = ET.SubElement(root, "Availability")
        _sub(avail, "id", inputs.order_id)
        _sub(avail, "datetime_start", _iso_utc(win_start))
        _sub(avail, "datetime_end", _iso_utc(win_end))
        _sub(avail, "activity_id", inputs.order_id)

    # Pretty-print so humans (and snapshot diffs) can read it.
    ET.indent(root, space="  ")
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")

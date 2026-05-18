"""Bulk PSO XML payload exporter.

Renders every work order in a CSV to its own ``<order_id>.xml`` file under a
target folder, and writes a combined ``_all_orders.xml`` for convenience.
No network call. Used to share the 12 sample payloads with IFS for
test-dataset construction.

Determinism
-----------
The body of every ``<dsScheduleData>`` is already deterministic by design
(see ``translator.py`` and the snapshot tests). To make the *whole* file
deterministic we additionally freeze the two fields that normally vary at
request time:

* ``Input_Reference.datetime`` -> a fixed UTC instant.
* ``Input_Reference.id`` -> a deterministic per-order hash, not a fresh UUID.

This means re-running ``--export-payloads`` produces the same bytes every
time, so IFS can diff cleanly between revisions.

The frozen "today" used for the SLA guardrail is exposed as a function
argument so the demo run can pin it to the actual demo day.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from app.csv_loader import load_work_orders
from app.integrations.pso.translator import build_pso_inputs, render_add_tasks_xml
from app.orchestrator import process_work_order

logger = logging.getLogger(__name__)

# Frozen "now" used in every emitted Input_Reference. The choice of value is
# arbitrary; what matters is that it does not change between runs.
_FROZEN_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
# Frozen "today" for the SLA guardrail so re-exporting produces the same
# bytes even after time passes. Picked to match _FROZEN_NOW's date.
_FROZEN_TODAY = _FROZEN_NOW.date()

_COMBINED_FILENAME = "_all_orders.xml"


def _frozen_uuid_for(order_id: str) -> str:
    """Deterministic 32-char hex id derived from the order id."""
    digest = hashlib.sha256(f"pso-payload:{order_id}".encode("utf-8")).hexdigest()
    return digest[:32]


def export_payloads(
    csv_path: Path,
    output_dir: Path,
    *,
    today: Optional[date] = None,
    now: Optional[datetime] = None,
) -> tuple[int, Path]:
    """Render every order in ``csv_path`` to its own XML file under ``output_dir``.

    Also writes a combined ``_all_orders.xml`` that concatenates every payload
    inside a single ``<pso_payloads>`` root element (the file is not a valid
    PSO request on its own — it is a viewing convenience for reviewers).

    Returns ``(count_written, output_dir)`` where ``count_written`` is the
    number of per-order files written (the combined file is not counted).

    ``today`` and ``now`` override the frozen demo defaults. Pass them when
    you want the SLA guardrail and ``Input_Reference.datetime`` to reflect
    a live run instead of the snapshot constants.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    today = today or _FROZEN_TODAY
    now = now or _FROZEN_NOW

    output_dir.mkdir(parents=True, exist_ok=True)
    orders = load_work_orders(csv_path)

    # Build the geocoder once; pgeocode loads a CSV in its constructor.
    try:
        from app.integrations.pso.pgeocode_geocoder import PgeocodeGeocoder

        geocoder: object | None = PgeocodeGeocoder()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not build PgeocodeGeocoder: %s; using (0,0) fallback for all rows", exc)
        geocoder = None

    written = 0
    rendered_xml: list[tuple[str, str]] = []
    for order in orders:
        decision = process_work_order(order)

        if geocoder is None:
            coords = (0.0, 0.0)
        else:
            try:
                coords = geocoder.lookup(order.postcode)  # type: ignore[attr-defined]
            except ValueError as exc:
                logger.warning(
                    "Geocoding failed for %s (%r): %s; defaulting to (0,0)",
                    order.order_id, order.postcode, exc,
                )
                coords = (0.0, 0.0)

        inputs = build_pso_inputs(decision, order, coords, today=today)
        order_uuid = _frozen_uuid_for(order.order_id)
        xml = render_add_tasks_xml(
            inputs,
            now=now,
            uuid_factory=lambda fixed=order_uuid: fixed,
            description=f"BT Openreach sample payload: {order.order_id}",
        )

        target = output_dir / f"{order.order_id}.xml"
        target.write_text(xml, encoding="utf-8")
        rendered_xml.append((order.order_id, xml))
        written += 1

    _write_combined(output_dir / _COMBINED_FILENAME, rendered_xml)

    logger.info(
        "Wrote %d PSO XML payloads (+ combined) to %s", written, output_dir
    )
    return written, output_dir


def _write_combined(target: Path, rendered: list[tuple[str, str]]) -> None:
    """Concatenate every per-order XML under a single wrapper for viewing.

    The wrapper exists purely so reviewers can grep one file instead of
    twelve. It is not a valid PSO request body.
    """
    parts = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<pso_payloads>",
    ]
    for order_id, xml in rendered:
        parts.append(f"  <!-- {order_id} -->")
        # Strip the XML declaration from each child if present so the combined
        # file does not have stray <?xml ?> tags interleaved.
        body = xml.lstrip()
        if body.startswith("<?xml"):
            body = body.split("?>", 1)[1].lstrip()
        parts.append(body)
    parts.append("</pso_payloads>")
    target.write_text("\n".join(parts) + "\n", encoding="utf-8")

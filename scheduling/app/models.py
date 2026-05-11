"""Data models for the BT Openreach Scheduling Copilot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class ExtractionTrace:
    """One audit-trail entry: which skill rule fired and what it found.

    Used by the cleaning pipeline to populate ``agent_actions.jsonl``. Strictly
    additive on the skill output models — older callers ignore it harmlessly.
    """

    field: str               # the SchedulingDecision-side field this contributes to
    value: Any               # the extracted value (date, str, bool, list, ...)
    pattern: str             # rule / regex constant name, e.g. "_NOT_BEFORE_PATTERN"
    source_excerpt: str = ""  # verbatim substring of the note that triggered it ("" when flag-only)


@dataclass
class WorkOrder:
    """A single work order loaded from CSV."""

    order_id: str
    order_source: str
    service_type: str
    job_type: str
    requested_start_date: date
    requested_end_date: date
    committed_delivery_date: date
    postcode: str
    customer_ready_status: str
    access_issue_flag: bool
    customer_delay_flag: bool
    driveway_surface_hint: str
    photo_provided_flag: bool
    dog_on_site_flag: bool
    exchange_visit_flag: bool
    heavy_ppe_hint: str
    unstructured_customer_notes: str


@dataclass
class SchedulingConstraints:
    """Output of Skill A: extracted scheduling constraints."""

    earliest_allowed_date: Optional[date] = None
    customer_availability_window: str = ""
    special_instructions: list[str] = field(default_factory=list)
    trace: list[ExtractionTrace] = field(default_factory=list)


@dataclass
class DeliveryDateRisk:
    """Output of Skill B: delivery date risk assessment."""

    date_change_recommended: bool = False
    reason_code: str = ""
    revised_delivery_date: Optional[date] = None
    explanation: str = ""


@dataclass
class VisitReadiness:
    """Output of Skill C: visit readiness assessment."""

    required_tools: list[str] = field(default_factory=list)
    required_materials: list[str] = field(default_factory=list)
    estimated_duration_minutes: int = 60
    confidence: str = "medium"
    explanation: str = ""
    trace: list[ExtractionTrace] = field(default_factory=list)


@dataclass
class SafetyAssessment:
    """Output of Skill D: safety and feasibility assessment."""

    safety_equipment: list[str] = field(default_factory=lambda: ["standard PPE"])
    extra_engineer_required: bool = False
    safety_risks: list[str] = field(default_factory=list)
    explanation: str = ""
    trace: list[ExtractionTrace] = field(default_factory=list)


@dataclass
class DelayRecord:
    """A single delay record from the delay history data."""

    project_name: str
    task_name: str
    holding_reason: str
    delay_start_date: str
    delay_end_date: str
    status: str
    delay_type: str
    delay_summary: str
    ccd_impact_days: str


@dataclass
class DelayHistory:
    """Output of Skill E: delay history lookup."""

    project_name: str
    total_delays: int = 0
    ongoing_delays: int = 0
    resolved_delays: int = 0
    delay_types: dict = field(default_factory=dict)
    top_reasons: list[str] = field(default_factory=list)
    records: list[DelayRecord] = field(default_factory=list)
    explanation: str = ""


@dataclass
class SchedulingDecision:
    """Final composed decision for a work order."""

    order_id: str
    recommended_action: str  # "schedule", "reschedule", "needs-human-review"
    planned_visit_date: Optional[date] = None
    constraints: Optional[SchedulingConstraints] = None
    delivery_date_assessment: Optional[DeliveryDateRisk] = None
    visit_readiness: Optional[VisitReadiness] = None
    safety_assessment: Optional[SafetyAssessment] = None
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a JSON-serialisable dictionary."""
        def _date_str(d: Optional[date]) -> Optional[str]:
            return d.isoformat() if d else None

        result: dict = {
            "order_id": self.order_id,
            "recommended_action": self.recommended_action,
            "planned_visit_date": _date_str(self.planned_visit_date),
        }

        if self.constraints:
            result["constraints"] = {
                "earliest_allowed_date": _date_str(self.constraints.earliest_allowed_date),
                "customer_availability_window": self.constraints.customer_availability_window,
                "special_instructions": self.constraints.special_instructions,
            }

        if self.delivery_date_assessment:
            result["delivery_date_assessment"] = {
                "date_change_recommended": self.delivery_date_assessment.date_change_recommended,
                "reason_code": self.delivery_date_assessment.reason_code,
                "revised_delivery_date": _date_str(self.delivery_date_assessment.revised_delivery_date),
                "explanation": self.delivery_date_assessment.explanation,
            }

        if self.visit_readiness:
            result["visit_readiness"] = {
                "required_tools": self.visit_readiness.required_tools,
                "required_materials": self.visit_readiness.required_materials,
                "estimated_duration_minutes": self.visit_readiness.estimated_duration_minutes,
                "confidence": self.visit_readiness.confidence,
                "explanation": self.visit_readiness.explanation,
            }

        if self.safety_assessment:
            result["safety_assessment"] = {
                "safety_equipment": self.safety_assessment.safety_equipment,
                "extra_engineer_required": self.safety_assessment.extra_engineer_required,
                "safety_risks": self.safety_assessment.safety_risks,
                "explanation": self.safety_assessment.explanation,
            }

        result["rationale"] = self.rationale
        return result

"""Aggregator: SchedulingDecision (+ optional DelayHistory) -> cleaned-CSV row + action log entries.

Pure functions. No I/O. No new domain logic - just a small, documented mapping
from existing skill outputs back into the 17-column cleaned-CSV shape, plus
one ``ExtractionTrace``-shaped action-log entry per recovered field so the
demo can show *why* each value was set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from app.models import (
    DelayHistory,
    ExtractionTrace,
    SchedulingDecision,
    WorkOrder,
)
from app.sla_guardrail import GUARDRAIL_REASON, apply_sla_guardrail

# 17-column header order matching ``data/work_orders.csv`` exactly.
CLEANED_COLUMNS = (
    "order_id",
    "order_source",
    "service_type",
    "job_type",
    "requested_start_date",
    "requested_end_date",
    "committed_delivery_date",
    "postcode",
    "customer_ready_status",
    "access_issue_flag",
    "customer_delay_flag",
    "driveway_surface_hint",
    "photo_provided_flag",
    "dog_on_site_flag",
    "exchange_visit_flag",
    "heavy_ppe_hint",
    "unstructured_customer_notes",
)

# Regex used by the customer_ready_status derivation. Lifted verbatim from
# the prompt so the rule stays auditable.
_BLOCKING_INSTRUCTION_RE = re.compile(r"asbestos|wayleave|civils|permit|do not book", re.IGNORECASE)
# "do not book" is the canonical Skill A "_INSTRUCTION_PATTERNS" hit that
# also signals customer_delay_flag.
_DO_NOT_BOOK_RE = re.compile(r"do\s+not\s+book", re.IGNORECASE)
# Skill A "access" instructions that should set access_issue_flag.
_ACCESS_INSTRUCTION_RE = re.compile(r"access|wayleave|permit|denied|blocked", re.IGNORECASE)


@dataclass
class ActionEntry:
    """One JSON-friendly entry for ``agent_actions.jsonl``.

    For directly extracted values, ``source_excerpt`` is a verbatim copy of
    the note substring that triggered the rule. For derived values, it is
    intentionally empty and ``reasoning`` describes the rule.

    ``extra`` carries entry-type-specific metadata that does not fit the
    standard skill-extraction shape - e.g. the ``sla_guardrail_applied``
    entry uses it to record both the original and shifted committed dates.
    """

    field: str
    value: Any
    skill: str            # human label, e.g. "A: Extract Constraints"
    reasoning: str
    source_excerpt: str = ""
    pattern: Optional[str] = None  # rule / regex name when relevant
    extra: Optional[dict[str, Any]] = None  # entry-type-specific payload

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "field": self.field,
            "value": self.value,
            "skill": self.skill,
            "reasoning": self.reasoning,
            "source_excerpt": self.source_excerpt,
        }
        if self.pattern:
            out["pattern"] = self.pattern
        if self.extra:
            out.update(self.extra)
        return out


@dataclass
class AggregatedOrder:
    """Result of aggregating one work order. Holds both the cleaned row and the action log entry."""

    cleaned_row: dict[str, str]
    extractions: list[ActionEntry] = field(default_factory=list)
    decision_label: str = "NEEDS-HUMAN-REVIEW"
    decision_reasoning: str = ""

    def action_log_entry(self, order: WorkOrder) -> dict[str, Any]:
        """Build the JSONL line for this order in the agreed format."""
        return {
            "order_id": order.order_id,
            "service_type": order.service_type,
            "extractions": [e.to_dict() for e in self.extractions],
            "decision": self.decision_label,
            "decision_reasoning": self.decision_reasoning,
        }


# --------------------------------------------------------------------------- #
# Recovery rules for the six dropped columns
# --------------------------------------------------------------------------- #


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def _recover_dog_on_site(decision: SchedulingDecision) -> tuple[bool, list[ActionEntry]]:
    """Skill D safety_risks containing dog mentions -> True."""
    safety = decision.safety_assessment
    if not safety:
        return False, []
    triggered = any(r.startswith("dog") for r in safety.safety_risks)
    if not triggered:
        return False, []
    # Find the corresponding trace entry to cite
    for t in safety.trace:
        if t.field == "dog_on_site_flag":
            return True, [ActionEntry(
                field="dog_on_site_flag",
                value=True,
                skill="D: Assess Safety",
                reasoning="Skill D detected a dog on site (flag or note mention).",
                source_excerpt=t.source_excerpt,
                pattern=t.pattern,
            )]
    # Triggered but no trace (pre-existing flag with no excerpt) - emit anyway
    return True, [ActionEntry(
        field="dog_on_site_flag",
        value=True,
        skill="D: Assess Safety",
        reasoning="Skill D safety_risks contains a dog entry.",
    )]


def _recover_heavy_ppe(decision: SchedulingDecision) -> tuple[str, list[ActionEntry]]:
    """Confined space wins over overhead (matches existing safety semantics)."""
    safety = decision.safety_assessment
    if not safety:
        return "", []
    risks = safety.safety_risks

    if "confined space working" in risks:
        for t in safety.trace:
            if t.field == "heavy_ppe_hint" and t.value == "confined space":
                return "confined space", [ActionEntry(
                    field="heavy_ppe_hint",
                    value="confined space",
                    skill="D: Assess Safety",
                    reasoning="Skill D flagged confined space working from notes or hint.",
                    source_excerpt=t.source_excerpt,
                    pattern=t.pattern,
                )]
        return "confined space", [ActionEntry(
            field="heavy_ppe_hint", value="confined space",
            skill="D: Assess Safety",
            reasoning="Skill D risks contain 'confined space working'.",
        )]

    if "working at height" in risks:
        for t in safety.trace:
            if t.field == "heavy_ppe_hint" and t.value == "overhead work":
                return "overhead work", [ActionEntry(
                    field="heavy_ppe_hint",
                    value="overhead work",
                    skill="D: Assess Safety",
                    reasoning="Skill D flagged overhead / working-at-height from notes or hint.",
                    source_excerpt=t.source_excerpt,
                    pattern=t.pattern,
                )]
        return "overhead work", [ActionEntry(
            field="heavy_ppe_hint", value="overhead work",
            skill="D: Assess Safety",
            reasoning="Skill D risks contain 'working at height'.",
        )]

    return "", []


def _recover_exchange_visit(
    decision: SchedulingDecision, order: WorkOrder
) -> tuple[bool, list[ActionEntry]]:
    """Skill D mentions exchange access key OR Ethernet service + 'exchange' in notes."""
    safety = decision.safety_assessment
    skill_d_hit = bool(safety and "exchange access key" in (safety.explanation or ""))

    notes = order.unstructured_customer_notes or ""
    is_ethernet = order.service_type.lower().startswith("ethernet")
    notes_mentions_exchange = bool(re.search(r"\bexchange\b", notes, re.IGNORECASE))
    heuristic_hit = is_ethernet and notes_mentions_exchange

    if not (skill_d_hit or heuristic_hit):
        return False, []

    if skill_d_hit:
        return True, [ActionEntry(
            field="exchange_visit_flag", value=True,
            skill="D: Assess Safety",
            reasoning="Skill D added 'exchange access key' to safety equipment, indicating an exchange visit.",
        )]
    # Heuristic: derived from service_type + note mention.
    excerpt_match = re.search(r".{0,40}\bexchange\b.{0,40}", notes, re.IGNORECASE)
    return True, [ActionEntry(
        field="exchange_visit_flag", value=True,
        skill="D: Assess Safety + service_type heuristic",
        reasoning=(
            "Derived from service_type starts with 'Ethernet' and customer notes mention "
            "'exchange'."
        ),
        source_excerpt=excerpt_match.group(0).strip() if excerpt_match else "",
    )]


def _recover_access_issue(
    decision: SchedulingDecision, delays: Optional[DelayHistory]
) -> tuple[bool, list[ActionEntry]]:
    """Skill A access-related instruction OR Skill E ongoing 3xxx delay."""
    constraints = decision.constraints
    skill_a_hit = None
    if constraints:
        for instr in constraints.special_instructions:
            if _ACCESS_INSTRUCTION_RE.search(instr):
                skill_a_hit = instr
                break

    skill_e_hit = False
    if delays:
        for rec in delays.records:
            reason = (rec.holding_reason or "").strip()
            if rec.status == "Ongoing" and reason.startswith("3"):
                skill_e_hit = True
                break

    if not (skill_a_hit or skill_e_hit):
        return False, []

    if skill_a_hit and skill_e_hit:
        return True, [ActionEntry(
            field="access_issue_flag", value=True,
            skill="A: Extract Constraints + E: Delay History",
            reasoning="Skill A found an access-related instruction and Skill E shows an ongoing wayleave / 3rd-party delay.",
            source_excerpt=skill_a_hit,
        )]
    if skill_a_hit:
        return True, [ActionEntry(
            field="access_issue_flag", value=True,
            skill="A: Extract Constraints",
            reasoning="Skill A extracted an access / wayleave / permit instruction from the notes.",
            source_excerpt=skill_a_hit,
        )]
    return True, [ActionEntry(
        field="access_issue_flag", value=True,
        skill="E: Delay History",
        reasoning="Derived from Skill E: an ongoing delay record with a 3xxx (access / wayleave / 3rd-party) reason code.",
    )]


def _recover_customer_ready_status(
    decision: SchedulingDecision, delays: Optional[DelayHistory]
) -> tuple[str, list[ActionEntry]]:
    """C low confidence OR ongoing E -> not ready; C high + no A blockers -> ready; else unknown."""
    readiness = decision.visit_readiness
    constraints = decision.constraints

    has_blocking_instruction = False
    if constraints:
        for instr in constraints.special_instructions:
            if _BLOCKING_INSTRUCTION_RE.search(instr):
                has_blocking_instruction = True
                break

    ongoing = bool(delays and delays.ongoing_delays > 0)
    confidence = readiness.confidence if readiness else "medium"

    if confidence == "low" or ongoing:
        skill_label = []
        if confidence == "low":
            skill_label.append("C: Assess Readiness")
        if ongoing:
            skill_label.append("E: Delay History")
        return "not ready", [ActionEntry(
            field="customer_ready_status", value="not ready",
            skill=" + ".join(skill_label),
            reasoning=(
                "Derived from Skill C confidence='low' and/or Skill E ongoing delays > 0."
            ),
        )]

    if confidence == "high" and not has_blocking_instruction:
        return "ready", [ActionEntry(
            field="customer_ready_status", value="ready",
            skill="C: Assess Readiness + A: Extract Constraints",
            reasoning="Derived from Skill C confidence='high' with no blocking instructions from Skill A.",
        )]

    return "unknown", [ActionEntry(
        field="customer_ready_status", value="unknown",
        skill="C: Assess Readiness + A: Extract Constraints + E: Delay History",
        reasoning="Insufficient signal to confirm ready or not ready; defaulting to 'unknown'.",
    )]


def _recover_customer_delay(
    decision: SchedulingDecision, delays: Optional[DelayHistory]
) -> tuple[bool, list[ActionEntry]]:
    """'do not book'-type instruction OR ongoing 2xxx (CP/customer) delay."""
    constraints = decision.constraints
    do_not_book_excerpt = None
    if constraints:
        for instr in constraints.special_instructions:
            if _DO_NOT_BOOK_RE.search(instr):
                do_not_book_excerpt = instr
                break

    cp_delay = False
    if delays:
        for rec in delays.records:
            reason = (rec.holding_reason or "").strip()
            if rec.status == "Ongoing" and reason.startswith("2"):
                cp_delay = True
                break

    if not (do_not_book_excerpt or cp_delay):
        return False, []

    if do_not_book_excerpt and cp_delay:
        return True, [ActionEntry(
            field="customer_delay_flag", value=True,
            skill="A: Extract Constraints + E: Delay History",
            reasoning="Skill A found a 'do not book' instruction and Skill E shows an ongoing CP-side delay.",
            source_excerpt=do_not_book_excerpt,
        )]
    if do_not_book_excerpt:
        return True, [ActionEntry(
            field="customer_delay_flag", value=True,
            skill="A: Extract Constraints",
            reasoning="Skill A extracted a 'do not book' instruction from the notes.",
            source_excerpt=do_not_book_excerpt,
        )]
    return True, [ActionEntry(
        field="customer_delay_flag", value=True,
        skill="E: Delay History",
        reasoning="Derived from Skill E: an ongoing delay record with a 2xxx (CP / customer) reason code.",
    )]


# --------------------------------------------------------------------------- #
# Extra extractions to surface to the action log (directly traced, not derived)
# --------------------------------------------------------------------------- #


def _extractions_from_traces(decision: SchedulingDecision) -> list[ActionEntry]:
    """Lift every ExtractionTrace from skills A/C/D into ActionEntry shape.

    These describe what the skills *directly* extracted (date, availability
    window, special instructions, tools, equipment, risks). They sit alongside
    the recovery entries above and give Federico the "based on the description,
    it has added this skill to this activity" demo line.
    """
    out: list[ActionEntry] = []

    if decision.constraints:
        for t in decision.constraints.trace:
            out.append(ActionEntry(
                field=t.field, value=t.value,
                skill="A: Extract Constraints",
                reasoning=f"Skill A pattern '{t.pattern}' matched the cited excerpt.",
                source_excerpt=t.source_excerpt,
                pattern=t.pattern,
            ))

    if decision.visit_readiness:
        for t in decision.visit_readiness.trace:
            out.append(ActionEntry(
                field=t.field, value=t.value,
                skill="C: Assess Readiness",
                reasoning=f"Skill C pattern '{t.pattern}' adjusted the visit kit / duration / confidence.",
                source_excerpt=t.source_excerpt,
                pattern=t.pattern,
            ))

    if decision.safety_assessment:
        for t in decision.safety_assessment.trace:
            # The dog/heavy-PPE/exchange traces are already surfaced via the recovery
            # entries below; skipping them here avoids duplicate lines in the log.
            if t.field in {"dog_on_site_flag", "heavy_ppe_hint", "exchange_visit_flag"}:
                continue
            out.append(ActionEntry(
                field=t.field, value=t.value,
                skill="D: Assess Safety",
                reasoning=f"Skill D pattern '{t.pattern}' fired on the cited excerpt.",
                source_excerpt=t.source_excerpt,
                pattern=t.pattern,
            ))

    return out


# --------------------------------------------------------------------------- #
# Top-level aggregation
# --------------------------------------------------------------------------- #


def aggregate(
    order: WorkOrder,
    decision: SchedulingDecision,
    delays: Optional[DelayHistory] = None,
    today: Optional[date] = None,
) -> AggregatedOrder:
    """Combine the original raw row + the decision + optional delay lookup
    into a cleaned-CSV row plus an action-log entry.

    ``today`` controls the SLA guardrail (see ``app.sla_guardrail``). If a
    work order's ``committed_delivery_date`` is strictly before ``today`` we
    write the shifted date into the cleaned row and emit a dedicated
    ``sla_guardrail_applied`` action entry that preserves the original date
    for audit. Defaults to :func:`datetime.date.today` for production use;
    pin it from tests for determinism.
    """
    if today is None:
        today = date.today()

    # SLA guardrail: never let a past committed date flow downstream.
    guardrail = apply_sla_guardrail(order.committed_delivery_date, today)
    sla_entries: list[ActionEntry] = []
    if guardrail.shifted:
        sla_entries.append(ActionEntry(
            field="sla_guardrail_applied",
            value=guardrail.effective_date.isoformat(),
            skill="SLA Guardrail",
            reasoning=GUARDRAIL_REASON,
            extra={
                "original_committed_date": guardrail.original_date.isoformat(),
                "shifted_committed_date": guardrail.effective_date.isoformat(),
                "reason": GUARDRAIL_REASON,
            },
        ))

    # Per-column recoveries
    dog, dog_entries = _recover_dog_on_site(decision)
    ppe, ppe_entries = _recover_heavy_ppe(decision)
    exch, exch_entries = _recover_exchange_visit(decision, order)
    access, access_entries = _recover_access_issue(decision, delays)
    ready, ready_entries = _recover_customer_ready_status(decision, delays)
    delay_flag, delay_entries = _recover_customer_delay(decision, delays)

    # Build the 17-column cleaned row. For columns the raw CSV preserves
    # untouched (postcode, dates, photo flag, etc.) we copy from the order.
    # ``committed_delivery_date`` carries the shifted value when the
    # guardrail fired; the original is preserved in the action log entry.
    cleaned_row: dict[str, str] = {
        "order_id": order.order_id,
        "order_source": order.order_source,
        "service_type": order.service_type,
        "job_type": order.job_type,
        "requested_start_date": order.requested_start_date.isoformat(),
        "requested_end_date": order.requested_end_date.isoformat(),
        "committed_delivery_date": guardrail.effective_date.isoformat(),
        "postcode": order.postcode,
        "customer_ready_status": ready,
        "access_issue_flag": _bool_str(access),
        "customer_delay_flag": _bool_str(delay_flag),
        "driveway_surface_hint": order.driveway_surface_hint,
        "photo_provided_flag": _bool_str(order.photo_provided_flag),
        "dog_on_site_flag": _bool_str(dog),
        "exchange_visit_flag": _bool_str(exch),
        "heavy_ppe_hint": ppe,
        "unstructured_customer_notes": order.unstructured_customer_notes,
    }

    # Action log = direct extractions (from traces) + recovery entries +
    # the SLA guardrail entry (when it fired).
    extractions: list[ActionEntry] = []
    extractions.extend(_extractions_from_traces(decision))
    extractions.extend(dog_entries)
    extractions.extend(ppe_entries)
    extractions.extend(exch_entries)
    extractions.extend(access_entries)
    extractions.extend(ready_entries)
    extractions.extend(delay_entries)
    extractions.extend(sla_entries)

    # Decision summary
    decision_label = (decision.recommended_action or "").upper().replace("_", "-") or "UNKNOWN"
    rationale = decision.rationale or []
    decision_reasoning = " ".join(rationale[:2]).strip()

    return AggregatedOrder(
        cleaned_row=cleaned_row,
        extractions=extractions,
        decision_label=decision_label,
        decision_reasoning=decision_reasoning,
    )

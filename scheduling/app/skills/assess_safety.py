"""Skill D: Assess safety and feasibility."""

from __future__ import annotations

import logging
import re

from app.models import ExtractionTrace, SafetyAssessment

logger = logging.getLogger(__name__)

_STANDARD_PPE = "standard PPE"
_ANTI_STATIC_PPE = "anti-static PPE"
_OVERHEAD_PPE = "hard hat with chin strap"
_CONFINED_SPACE_KIT = "confined space rescue kit"


def assess_safety_and_feasibility(
    dog_on_site_flag: bool,
    heavy_ppe_hint: str,
    exchange_visit_flag: bool,
    customer_notes: str,
) -> SafetyAssessment:
    """Assess safety risks and equipment requirements.

    Args:
        dog_on_site_flag: Whether a dog is reported at the property.
        heavy_ppe_hint: Hints about heavy PPE needs (e.g., "confined space", "overhead work").
        exchange_visit_flag: Whether this visit includes a telephone exchange.
        customer_notes: Free text notes from customer or agent.

    Returns:
        SafetyAssessment with equipment, risks, and extra engineer flag.
    """
    equipment: list[str] = [_STANDARD_PPE]
    risks: list[str] = []
    extra_engineer = False
    explanations: list[str] = []
    trace: list[ExtractionTrace] = []

    notes_lower = customer_notes.lower() if customer_notes else ""
    hint_lower = heavy_ppe_hint.lower() if heavy_ppe_hint else ""

    # Dog on site
    if dog_on_site_flag:
        risks.append("dog on site")
        explanations.append("Dog reported on site. Customer must secure animal before engineer arrives.")
        trace.append(ExtractionTrace(
            field="dog_on_site_flag", value=True,
            pattern="DOG_ON_SITE_FLAG", source_excerpt="",
        ))

    # Check notes for dog mentions even if flag is false
    dog_notes_match = re.search(r"\bdog\b|\bdogs\b|guard\s+dog", notes_lower)
    if not dog_on_site_flag and dog_notes_match:
        risks.append("dog mentioned in notes (flag not set)")
        explanations.append("Dog mentioned in customer notes but flag was not set. Verify before visit.")
        trace.append(ExtractionTrace(
            field="dog_on_site_flag", value=True,
            pattern=r"\bdog\b|\bdogs\b|guard\s+dog",
            source_excerpt=customer_notes[dog_notes_match.start():dog_notes_match.end()] if customer_notes else "",
        ))

    # Confined space
    confined_notes_match = re.search(r"confined\s+space|low\s+ceiling|basement|crawl", notes_lower)
    if "confined space" in hint_lower or confined_notes_match:
        equipment.append(_CONFINED_SPACE_KIT)
        risks.append("confined space working")
        extra_engineer = True
        explanations.append("Confined space working identified. Two-person team required per safety policy.")
        excerpt = (
            customer_notes[confined_notes_match.start():confined_notes_match.end()]
            if confined_notes_match and customer_notes
            else heavy_ppe_hint
        )
        trace.append(ExtractionTrace(
            field="heavy_ppe_hint", value="confined space",
            pattern=r"confined\s+space|low\s+ceiling|basement|crawl|HINT=confined space",
            source_excerpt=excerpt or "",
        ))

    # Overhead work
    overhead_notes_match = re.search(r"overhead|cherry\s+picker|scaffolding|3rd\s+floor|roof\s+access", notes_lower)
    if "overhead" in hint_lower or overhead_notes_match:
        equipment.append(_OVERHEAD_PPE)
        risks.append("working at height")
        explanations.append("Working at height identified. Hard hat with chin strap required.")
        excerpt = (
            customer_notes[overhead_notes_match.start():overhead_notes_match.end()]
            if overhead_notes_match and customer_notes
            else heavy_ppe_hint
        )
        trace.append(ExtractionTrace(
            field="heavy_ppe_hint", value="overhead work",
            pattern=r"overhead|cherry\s+picker|scaffolding|3rd\s+floor|roof\s+access|HINT=overhead",
            source_excerpt=excerpt or "",
        ))

    # Check for overhead power lines
    power_match = re.search(r"overhead\s+power\s+lines?|power\s+lines?\s+near", notes_lower)
    if power_match:
        risks.append("proximity to overhead power lines")
        extra_engineer = True
        explanations.append("Overhead power lines near work area. Safe clearance must be maintained.")
        trace.append(ExtractionTrace(
            field="safety_risks", value="proximity to overhead power lines",
            pattern=r"overhead\s+power\s+lines?|power\s+lines?\s+near",
            source_excerpt=customer_notes[power_match.start():power_match.end()] if customer_notes else "",
        ))

    # Anti-static requirements (data centres, server rooms)
    static_match = re.search(r"anti-?static|data\s+centre|server\s+room", notes_lower)
    if static_match:
        equipment.append(_ANTI_STATIC_PPE)
        risks.append("electrostatic discharge risk")
        explanations.append("Anti-static PPE required for data centre environment.")
        trace.append(ExtractionTrace(
            field="safety_risks", value="electrostatic discharge risk",
            pattern=r"anti-?static|data\s+centre|server\s+room",
            source_excerpt=customer_notes[static_match.start():static_match.end()] if customer_notes else "",
        ))

    # Exchange visit
    if exchange_visit_flag:
        equipment.append("exchange access key")
        explanations.append("Exchange visit requires access key and sign-in.")
        trace.append(ExtractionTrace(
            field="exchange_visit_flag", value=True,
            pattern="EXCHANGE_VISIT_FLAG", source_excerpt="",
        ))

    # Asbestos
    asbestos_match = re.search(r"asbestos", notes_lower)
    if asbestos_match:
        risks.append("potential asbestos exposure")
        extra_engineer = True
        equipment.append("asbestos awareness certification")
        explanations.append(
            "Asbestos flagged in notes. Do not access affected area without clearance. "
            "Two-person team required."
        )
        trace.append(ExtractionTrace(
            field="safety_risks", value="potential asbestos exposure",
            pattern=r"asbestos",
            source_excerpt=customer_notes[asbestos_match.start():asbestos_match.end()] if customer_notes else "",
        ))

    # Building being demolished
    demo_match = re.search(r"demolished|demolition", notes_lower)
    if demo_match:
        risks.append("building being demolished")
        explanations.append("Building is scheduled for demolition. Access may become restricted.")
        trace.append(ExtractionTrace(
            field="safety_risks", value="building being demolished",
            pattern=r"demolished|demolition",
            source_excerpt=customer_notes[demo_match.start():demo_match.end()] if customer_notes else "",
        ))

    # Security clearance
    sec_match = re.search(r"security\s+clearance|photo\s+ID", notes_lower)
    if sec_match:
        explanations.append("Security clearance or photo ID required for site access.")
        trace.append(ExtractionTrace(
            field="explanation", value="Security clearance or photo ID required for site access.",
            pattern=r"security\s+clearance|photo\s+ID",
            source_excerpt=customer_notes[sec_match.start():sec_match.end()] if customer_notes else "",
        ))

    # If no specific risks, note that
    if not risks:
        explanations.append("No safety risks identified for this job.")

    explanation = " ".join(explanations)

    logger.info(
        "Safety assessment: %d risks, extra_engineer=%s, %d equipment items",
        len(risks), extra_engineer, len(equipment),
    )

    return SafetyAssessment(
        safety_equipment=equipment,
        extra_engineer_required=extra_engineer,
        safety_risks=risks,
        explanation=explanation,
        trace=trace,
    )

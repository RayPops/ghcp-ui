"""Skill D: Assess safety and feasibility."""

from __future__ import annotations

import logging
import re

from app.models import SafetyAssessment

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

    notes_lower = customer_notes.lower() if customer_notes else ""
    hint_lower = heavy_ppe_hint.lower() if heavy_ppe_hint else ""

    # Dog on site
    if dog_on_site_flag:
        risks.append("dog on site")
        explanations.append("Dog reported on site. Customer must secure animal before engineer arrives.")

    # Check notes for dog mentions even if flag is false
    if not dog_on_site_flag and re.search(r"\bdog\b|\bdogs\b|guard\s+dog", notes_lower):
        risks.append("dog mentioned in notes (flag not set)")
        explanations.append("Dog mentioned in customer notes but flag was not set. Verify before visit.")

    # Confined space
    if "confined space" in hint_lower or re.search(r"confined\s+space|low\s+ceiling|basement|crawl", notes_lower):
        equipment.append(_CONFINED_SPACE_KIT)
        risks.append("confined space working")
        extra_engineer = True
        explanations.append("Confined space working identified. Two-person team required per safety policy.")

    # Overhead work
    if "overhead" in hint_lower or re.search(r"overhead|cherry\s+picker|scaffolding|3rd\s+floor|roof\s+access", notes_lower):
        equipment.append(_OVERHEAD_PPE)
        risks.append("working at height")
        explanations.append("Working at height identified. Hard hat with chin strap required.")

    # Check for overhead power lines
    if re.search(r"overhead\s+power\s+lines?|power\s+lines?\s+near", notes_lower):
        risks.append("proximity to overhead power lines")
        extra_engineer = True
        explanations.append("Overhead power lines near work area. Safe clearance must be maintained.")

    # Anti-static requirements (data centres, server rooms)
    if re.search(r"anti-?static|data\s+centre|server\s+room", notes_lower):
        equipment.append(_ANTI_STATIC_PPE)
        risks.append("electrostatic discharge risk")
        explanations.append("Anti-static PPE required for data centre environment.")

    # Exchange visit
    if exchange_visit_flag:
        equipment.append("exchange access key")
        explanations.append("Exchange visit requires access key and sign-in.")

    # Asbestos
    if re.search(r"asbestos", notes_lower):
        risks.append("potential asbestos exposure")
        extra_engineer = True
        equipment.append("asbestos awareness certification")
        explanations.append(
            "Asbestos flagged in notes. Do not access affected area without clearance. "
            "Two-person team required."
        )

    # Building being demolished
    if re.search(r"demolished|demolition", notes_lower):
        risks.append("building being demolished")
        explanations.append("Building is scheduled for demolition. Access may become restricted.")

    # Security clearance
    if re.search(r"security\s+clearance|photo\s+ID", notes_lower):
        explanations.append("Security clearance or photo ID required for site access.")

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
    )

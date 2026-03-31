"""Skill C: Assess visit readiness - tools, materials, duration."""

from __future__ import annotations

import logging
import re

from app.models import VisitReadiness

logger = logging.getLogger(__name__)

# Base tool/material requirements by service type and job type
_TOOLKITS: dict[str, dict[str, dict]] = {
    "fttp installation": {
        "new line installation": {
            "tools": ["fibre splicer", "cable rod set", "power meter", "fibre cleaver"],
            "materials": ["fibre patch lead", "wall box", "cable clips", "duct tape"],
            "duration": 120,
        },
        "default": {
            "tools": ["fibre splicer", "power meter"],
            "materials": ["fibre patch lead"],
            "duration": 90,
        },
    },
    "ethernet bearer": {
        "provision": {
            "tools": ["fibre splicer", "cable rod set", "power meter", "fibre cleaver", "duct rods"],
            "materials": ["fibre patch lead", "wall box", "cable tray", "fire stop"],
            "duration": 180,
        },
        "cease": {
            "tools": ["screwdriver set", "cable cutters"],
            "materials": ["blanking plates"],
            "duration": 60,
        },
        "default": {
            "tools": ["fibre splicer", "power meter"],
            "materials": ["fibre patch lead"],
            "duration": 120,
        },
    },
    "broadband repair": {
        "repair": {
            "tools": ["cable tester", "tone generator", "cable jointing kit", "hand tools"],
            "materials": ["replacement cable", "joint closure", "cable ties"],
            "duration": 90,
        },
        "default": {
            "tools": ["cable tester", "hand tools"],
            "materials": ["replacement cable"],
            "duration": 60,
        },
    },
}


def _get_base_kit(service_type: str, job_type: str) -> dict:
    """Look up base tools, materials, and duration for a job."""
    service_key = service_type.lower()
    job_key = job_type.lower()

    if service_key in _TOOLKITS:
        service_kits = _TOOLKITS[service_key]
        if job_key in service_kits:
            return service_kits[job_key]
        return service_kits.get("default", {"tools": [], "materials": [], "duration": 60})

    return {"tools": ["general hand tools"], "materials": [], "duration": 60}


def assess_visit_readiness(
    service_type: str,
    job_type: str,
    driveway_surface_hint: str,
    photo_provided_flag: bool,
    customer_notes: str,
) -> VisitReadiness:
    """Assess what tools, materials, and time are needed for a visit.

    Args:
        service_type: Type of service (e.g., "FTTP Installation").
        job_type: Type of work (e.g., "new line installation").
        driveway_surface_hint: Surface type at property.
        photo_provided_flag: Whether customer provided a site photo.
        customer_notes: Free text notes from customer or agent.

    Returns:
        VisitReadiness with tools, materials, duration, and confidence.
    """
    base = _get_base_kit(service_type, job_type)
    tools = list(base["tools"])
    materials = list(base["materials"])
    duration = base["duration"]
    confidence = "high" if photo_provided_flag else "medium"
    explanations: list[str] = []

    notes_lower = customer_notes.lower() if customer_notes else ""

    # Adjust for driveway surface
    surface = driveway_surface_hint.lower() if driveway_surface_hint else ""
    if surface == "gravel":
        tools.append("ground mat")
        explanations.append("Gravel surface may need ground protection.")
        duration += 15
    elif surface == "block paving":
        tools.append("paving lifter")
        explanations.append("Block paving may need careful lifting and replacement.")
        duration += 20

    # Adjust for long cable runs mentioned in notes
    long_run_match = re.search(r"(\d{2,3})\s*m\b", notes_lower)
    if long_run_match:
        run_length = int(long_run_match.group(1))
        if run_length > 50:
            materials.append(f"extended cable run ({run_length}m)")
            duration += 30
            explanations.append(f"Long cable run of approximately {run_length} metres noted.")

    # Check for duct issues
    if re.search(r"duct\s+block", notes_lower):
        tools.append("duct rod set (heavy duty)")
        materials.append("duct bore equipment")
        duration += 60
        confidence = "low"
        explanations.append("Duct blockage reported. May require duct bore.")

    # Check for cherry picker / scaffolding
    if re.search(r"cherry\s+picker|scaffolding", notes_lower):
        tools.append("cherry picker or scaffolding (pre-book)")
        duration += 60
        explanations.append("High-level access equipment needed.")

    # Check for cable jointing kit mentioned
    if re.search(r"jointing\s+kit", notes_lower):
        if "cable jointing kit" not in tools:
            tools.append("cable jointing kit")
        explanations.append("Cable jointing kit specifically requested in notes.")

    # Check for raised floor routing
    if re.search(r"raised\s+floor", notes_lower):
        tools.append("raised floor tile lifter")
        explanations.append("Raised floor cable routing noted.")

    # Check for previous failed attempt
    if re.search(r"previous\s+(?:attempt|visit)\s+failed", notes_lower):
        confidence = "low"
        duration += 30
        explanations.append("Previous attempt failed. Extra time allocated for contingency.")

    # Reduce confidence if no photo and non-trivial job
    if not photo_provided_flag and duration > 90:
        if confidence != "low":
            confidence = "medium"
        explanations.append("No site photo provided. Confidence reduced.")

    # Cap duration at 480 minutes (full day)
    duration = min(duration, 480)

    explanation = " ".join(explanations) if explanations else "Standard job requirements identified."

    logger.info(
        "Visit readiness for %s/%s: %d tools, %d materials, %dmin, confidence=%s",
        service_type, job_type, len(tools), len(materials), duration, confidence,
    )

    return VisitReadiness(
        required_tools=tools,
        required_materials=materials,
        estimated_duration_minutes=duration,
        confidence=confidence,
        explanation=explanation,
    )

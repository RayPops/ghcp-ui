"""Skill C: Assess visit readiness - tools, materials, duration."""

from __future__ import annotations

import logging
import re

from app.models import ExtractionTrace, VisitReadiness

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
    trace: list[ExtractionTrace] = []

    notes_lower = customer_notes.lower() if customer_notes else ""

    # Adjust for driveway surface
    surface = driveway_surface_hint.lower() if driveway_surface_hint else ""
    if surface == "gravel":
        tools.append("ground mat")
        explanations.append("Gravel surface may need ground protection.")
        duration += 15
        trace.append(ExtractionTrace(
            field="required_tools", value="ground mat",
            pattern="DRIVEWAY_SURFACE=gravel", source_excerpt="",
        ))
    elif surface == "block paving":
        tools.append("paving lifter")
        explanations.append("Block paving may need careful lifting and replacement.")
        duration += 20
        trace.append(ExtractionTrace(
            field="required_tools", value="paving lifter",
            pattern="DRIVEWAY_SURFACE=block paving", source_excerpt="",
        ))

    # Adjust for long cable runs mentioned in notes
    long_run_match = re.search(r"(\d{2,3})\s*m\b", notes_lower)
    if long_run_match:
        run_length = int(long_run_match.group(1))
        if run_length > 50:
            materials.append(f"extended cable run ({run_length}m)")
            duration += 30
            explanations.append(f"Long cable run of approximately {run_length} metres noted.")
            trace.append(ExtractionTrace(
                field="required_materials",
                value=f"extended cable run ({run_length}m)",
                pattern=r"(\d{2,3})\s*m\b",
                source_excerpt=long_run_match.group(0),
            ))

    # Check for duct issues
    duct_match = re.search(r"duct\s+block", notes_lower)
    if duct_match:
        tools.append("duct rod set (heavy duty)")
        materials.append("duct bore equipment")
        duration += 60
        confidence = "low"
        explanations.append("Duct blockage reported. May require duct bore.")
        trace.append(ExtractionTrace(
            field="confidence", value="low",
            pattern=r"duct\s+block",
            source_excerpt=customer_notes[duct_match.start():duct_match.end()] if customer_notes else "",
        ))

    # Check for cherry picker / scaffolding
    cherry_match = re.search(r"cherry\s+picker|scaffolding", notes_lower)
    if cherry_match:
        tools.append("cherry picker or scaffolding (pre-book)")
        duration += 60
        explanations.append("High-level access equipment needed.")
        trace.append(ExtractionTrace(
            field="required_tools", value="cherry picker or scaffolding (pre-book)",
            pattern=r"cherry\s+picker|scaffolding",
            source_excerpt=customer_notes[cherry_match.start():cherry_match.end()] if customer_notes else "",
        ))

    # Check for cable jointing kit mentioned
    jointing_match = re.search(r"jointing\s+kit", notes_lower)
    if jointing_match:
        if "cable jointing kit" not in tools:
            tools.append("cable jointing kit")
        explanations.append("Cable jointing kit specifically requested in notes.")
        trace.append(ExtractionTrace(
            field="required_tools", value="cable jointing kit",
            pattern=r"jointing\s+kit",
            source_excerpt=customer_notes[jointing_match.start():jointing_match.end()] if customer_notes else "",
        ))

    # Check for raised floor routing
    raised_match = re.search(r"raised\s+floor", notes_lower)
    if raised_match:
        tools.append("raised floor tile lifter")
        explanations.append("Raised floor cable routing noted.")
        trace.append(ExtractionTrace(
            field="required_tools", value="raised floor tile lifter",
            pattern=r"raised\s+floor",
            source_excerpt=customer_notes[raised_match.start():raised_match.end()] if customer_notes else "",
        ))

    # Check for previous failed attempt
    prev_match = re.search(r"previous\s+(?:attempt|visit)\s+failed", notes_lower)
    if prev_match:
        confidence = "low"
        duration += 30
        explanations.append("Previous attempt failed. Extra time allocated for contingency.")
        trace.append(ExtractionTrace(
            field="confidence", value="low",
            pattern=r"previous\s+(?:attempt|visit)\s+failed",
            source_excerpt=customer_notes[prev_match.start():prev_match.end()] if customer_notes else "",
        ))

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
        trace=trace,
    )

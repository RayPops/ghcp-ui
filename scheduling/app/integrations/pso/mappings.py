"""Lookup tables that translate domain values into PSO vocabulary.

These tables are intentionally separated from translator logic so they can be
tuned without touching the XML builder. All mappings are *initial proposals*
that need to be confirmed with Federico Sensi before going live.

Open questions for Federico:
- Are ``INSTALL``, ``MAINTENANCE``, ``FIX``, ``EMERGENCY`` the canonical
  Activity Type ids in the ``CC_LIVE`` dataset?
- Is the skill vocabulary below correct for ``CC_LIVE``? The simulation
  dataset advertises ``5G``, ``fibre``, and ``network``.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# service_type + job_type -> PSO Activity Type id
# --------------------------------------------------------------------------- #

# Keys are lower-cased for matching. ``"*"`` is the wildcard fallback for the
# job_type slot.
_TASK_TYPE_TABLE: dict[tuple[str, str], str] = {
    ("fttp installation", "new line installation"): "INSTALL",
    ("fttp installation", "repair"): "FIX",
    ("fttp installation", "fault"): "FIX",
    ("fttp installation", "*"): "INSTALL",
    ("ethernet bearer", "provision"): "INSTALL",
    ("ethernet bearer", "repair"): "FIX",
    ("ethernet bearer", "fault"): "FIX",
    ("ethernet bearer", "cease"): "MAINTENANCE",
    ("ethernet bearer", "*"): "INSTALL",
    ("broadband repair", "*"): "FIX",
}

DEFAULT_TASK_TYPE = "INSTALL"


def map_task_type(service_type: str, job_type: str) -> str:
    """Map a service_type + job_type pair to a PSO Activity Type id."""
    service_key = (service_type or "").strip().lower()
    job_key = (job_type or "").strip().lower()
    if (service_key, job_key) in _TASK_TYPE_TABLE:
        return _TASK_TYPE_TABLE[(service_key, job_key)]
    if (service_key, "*") in _TASK_TYPE_TABLE:
        return _TASK_TYPE_TABLE[(service_key, "*")]
    return DEFAULT_TASK_TYPE


# --------------------------------------------------------------------------- #
# Tools / equipment / risk tokens -> PSO Skill ids
# --------------------------------------------------------------------------- #

# A token from a skill output triggers the listed PSO skill_id.
# Matching is substring-based and case-insensitive.
_SKILL_TOKEN_TABLE: list[tuple[str, str]] = [
    # Fibre work
    ("fibre splicer", "fibre"),
    ("fibre cleaver", "fibre"),
    ("fibre patch lead", "fibre"),
    # Network / exchange
    ("exchange access key", "network"),
    # Height / overhead
    ("hard hat with chin strap", "overhead"),
    ("working at height", "overhead"),
    # Confined space
    ("confined space rescue kit", "confined_space"),
    ("confined space working", "confined_space"),
    # Asbestos
    ("asbestos", "asbestos_aware"),
    # ESD / data centre
    ("anti-static ppe", "esd"),
    ("electrostatic discharge risk", "esd"),
]


def derive_skill_ids(
    *,
    service_type: str,
    required_tools: list[str],
    safety_equipment: list[str],
    safety_risks: list[str],
    exchange_visit_flag: bool,
) -> list[str]:
    """Derive a deduplicated list of PSO skill_ids for the activity.

    Order is deterministic: the order in which skills are first added is
    preserved (so snapshot tests are stable).
    """
    seen: dict[str, None] = {}

    # Service-level baseline
    service_lower = (service_type or "").lower()
    if "fttp" in service_lower or "ethernet" in service_lower or "fibre" in service_lower:
        seen.setdefault("fibre", None)

    # Exchange visits always need network skill
    if exchange_visit_flag:
        seen.setdefault("network", None)

    # Token scan over tools, equipment, risks
    haystack: list[str] = []
    haystack.extend(required_tools or [])
    haystack.extend(safety_equipment or [])
    haystack.extend(safety_risks or [])
    haystack_lower = [item.lower() for item in haystack]

    for token, skill_id in _SKILL_TOKEN_TABLE:
        for entry in haystack_lower:
            if token in entry:
                seen.setdefault(skill_id, None)
                break

    return list(seen.keys())


# --------------------------------------------------------------------------- #
# Customer availability window labels -> intra-day time slots
# --------------------------------------------------------------------------- #

# Maps the human label produced by Skill A onto a (start_hour, end_hour) pair
# in the planned-visit-date local timezone (we use UTC throughout).
# Returning ``None`` means "do not emit an <Availability> block".
AVAILABILITY_WINDOW_TABLE: dict[str, tuple[int, int] | None] = {
    "mornings only": (9, 13),
    "afternoons only": (13, 17),
    # The labels below cover the full working day or are too unusual to emit
    # an Availability block for; we let the SLA window do the work instead.
    "any time": None,
    "weekdays only": None,
    "weekdays business hours only": None,
    "night shift only": None,
}


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_VALUE = 3000
HUMAN_REVIEW_VALUE = 10000
DEFAULT_SLA_TYPE = "Normal"
ACTIVITY_CLASS_ID = "CALL"
TEXT_DESCRIPTION_MAX_LEN = 2000

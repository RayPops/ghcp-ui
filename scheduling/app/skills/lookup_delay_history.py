"""Skill E: Look up delay history for a project from BT delay data."""

from __future__ import annotations

import csv
import logging
from collections import Counter
from pathlib import Path

from app.models import DelayHistory, DelayRecord

logger = logging.getLogger(__name__)

# Mapping of numeric holding reason codes to human-readable descriptions.
# Sourced from BT Openreach delay classification codes.
_REASON_DESCRIPTIONS: dict[str, str] = {
    "2002": "CP/end-user assistance or information required",
    "2021": "CP missed appointment or no access",
    "2042": "Incorrect order/information submitted by CP",
    "2047": "Incorrect order/information submitted by CP",
    "2060": "Excess construction charges (ECC) exceeded threshold",
    "2064": "CP consent required for charges",
    "3001": "Wayleave required",
    "3005": "No response after three contact attempts",
    "3007": "Third-party infrastructure blockage",
    "3011": "Traffic management / road permits",
    "3012": "Local authority permit delays",
    "4002": "Equipment or materials unavailable",
    "9581": "Internal Openreach resource issue",
    "9582": "Internal Openreach planning delay",
    "9742": "Civils / ductwork dependency",
}

# Lazy-loaded delay index: PROJECT_NAME -> list of delay rows
_delay_index: dict[str, list[dict]] = {}
_delay_csv_path: str | None = None


def _ensure_delay_data_loaded(csv_path: str | Path) -> dict[str, list[dict]]:
    """Load and index delay data on first access."""
    global _delay_csv_path

    csv_path = Path(csv_path)
    path_str = str(csv_path)

    # Already loaded for this path
    if _delay_index and _delay_csv_path == path_str:
        return _delay_index

    if not csv_path.exists():
        logger.warning("Delay data file not found: %s", csv_path)
        return _delay_index

    logger.info("Loading delay data from %s (this may take a moment)...", csv_path)
    _delay_index.clear()

    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            proj = row.get("PROJECT_NAME", "").strip()
            if proj:
                if proj not in _delay_index:
                    _delay_index[proj] = []
                _delay_index[proj].append(row)
                count += 1

    _delay_csv_path = path_str
    logger.info("Indexed %d delay records across %d projects", count, len(_delay_index))
    return _delay_index


def _describe_reason(code: str) -> str:
    """Turn a holding reason code into a human-readable string."""
    desc = _REASON_DESCRIPTIONS.get(code, "Other/unclassified")
    return f"{code} ({desc})"


def lookup_delay_history(project_name: str, csv_path: str | Path) -> DelayHistory:
    """Look up delay history for a project.

    Args:
        project_name: The PROJECT_NAME / order_id to look up.
        csv_path: Path to the delay_data.csv file.

    Returns:
        DelayHistory with aggregated delay information.
    """
    index = _ensure_delay_data_loaded(csv_path)
    rows = index.get(project_name, [])

    if not rows:
        return DelayHistory(
            project_name=project_name,
            explanation=f"No delay records found for project {project_name}.",
        )

    # Aggregate
    total = len(rows)
    ongoing = sum(1 for r in rows if r.get("Status", "") == "Ongoing")
    resolved = sum(1 for r in rows if r.get("Status", "") == "Resolved")

    delay_type_counts = Counter(r.get("Delay_Type", "") for r in rows)
    reason_counts = Counter(r.get("holding_reason", "") for r in rows)

    # Top reasons with descriptions
    top_reasons = [_describe_reason(code) for code, _ in reason_counts.most_common(5)]

    # Build detail records (cap at 10 most recent for readability)
    records = []
    for row in rows[-10:]:
        summary = row.get("delay_summary", "").strip()
        # Truncate very long summaries
        if len(summary) > 300:
            summary = summary[:297] + "..."
        records.append(DelayRecord(
            project_name=project_name,
            task_name=row.get("task_name", ""),
            holding_reason=_describe_reason(row.get("holding_reason", "")),
            delay_start_date=row.get("Delay_Start_Date", ""),
            delay_end_date=row.get("Delay_End_Date", "") or row.get("Estimated_End_Date", ""),
            status=row.get("Status", ""),
            delay_type=row.get("Delay_Type", ""),
            delay_summary=summary,
            ccd_impact_days=row.get("ccd_impact_days", ""),
        ))

    # Build explanation
    explanations = [
        f"Project {project_name} has {total} delay record(s): "
        f"{ongoing} ongoing, {resolved} resolved.",
    ]

    if delay_type_counts:
        type_parts = [f"{v} {k}" for k, v in delay_type_counts.most_common()]
        explanations.append(f"Delay types: {', '.join(type_parts)}.")

    if ongoing > 0:
        explanations.append(
            f"WARNING: {ongoing} delay(s) are still ongoing. "
            "This order may not be ready to schedule."
        )

    if reason_counts:
        most_common_reason = reason_counts.most_common(1)[0]
        explanations.append(
            f"Most frequent delay reason: {_describe_reason(most_common_reason[0])} "
            f"({most_common_reason[1]} occurrence(s))."
        )

    return DelayHistory(
        project_name=project_name,
        total_delays=total,
        ongoing_delays=ongoing,
        resolved_delays=resolved,
        delay_types=dict(delay_type_counts),
        top_reasons=top_reasons,
        records=records,
        explanation=" ".join(explanations),
    )

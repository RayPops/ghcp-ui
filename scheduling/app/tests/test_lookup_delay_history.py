"""Tests for Skill E: delay history lookup."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from app.skills.lookup_delay_history import lookup_delay_history


@pytest.fixture()
def delay_csv(tmp_path: Path) -> Path:
    """Create a small delay CSV for testing."""
    path = tmp_path / "delay_data.csv"
    rows = [
        {
            "PROJECT_NAME": "ONEA00000001",
            "bundle_id": "100",
            "task_id": "T1",
            "task_name": "Survey - B end",
            "holding_reason": "3001",
            "Delay_Start_Date": "2025-06-01 10:00:00 UTC",
            "Estimated_End_Date": "2025-06-15 23:59:00 UTC",
            "Delay_End_Date": "2025-06-10 12:00:00 UTC",
            "Status": "Resolved",
            "Delay_Type": "DC Delay",
            "target_role": "DEEMEDCONSENTDELAY",
            "delay_summary": "Wayleave required for 1st party onsite duct",
            "clear_notes": "",
            "originator_ein": "12345",
            "clearing_ein": "67890",
            "parallel_delay_details": "",
            "ccd_impact_days": "5",
        },
        {
            "PROJECT_NAME": "ONEA00000001",
            "bundle_id": "100",
            "task_id": "T2",
            "task_name": "Install - A end",
            "holding_reason": "2002",
            "Delay_Start_Date": "2025-07-01 09:00:00 UTC",
            "Estimated_End_Date": "2025-07-10 23:59:00 UTC",
            "Delay_End_Date": "",
            "Status": "Ongoing",
            "Delay_Type": "DC Delay",
            "target_role": "DEEMEDCONSENTDELAY",
            "delay_summary": "CP has not provided site plans",
            "clear_notes": "",
            "originator_ein": "12345",
            "clearing_ein": "",
            "parallel_delay_details": "",
            "ccd_impact_days": "3",
        },
        {
            "PROJECT_NAME": "ONEA00000002",
            "bundle_id": "200",
            "task_id": "T3",
            "task_name": "Survey - A end",
            "holding_reason": "3007",
            "Delay_Start_Date": "2025-05-15 08:00:00 UTC",
            "Estimated_End_Date": "2025-05-30 23:59:00 UTC",
            "Delay_End_Date": "2025-05-25 14:00:00 UTC",
            "Status": "Resolved",
            "Delay_Type": "OR Delay",
            "target_role": "",
            "delay_summary": "Duct blockage on proposed route",
            "clear_notes": "",
            "originator_ein": "11111",
            "clearing_ein": "22222",
            "parallel_delay_details": "",
            "ccd_impact_days": "7",
        },
    ]
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_lookup_finds_delays(delay_csv: Path) -> None:
    result = lookup_delay_history("ONEA00000001", delay_csv)
    assert result.total_delays == 2
    assert result.ongoing_delays == 1
    assert result.resolved_delays == 1
    assert len(result.records) == 2
    assert "WARNING" in result.explanation


def test_lookup_no_delays(delay_csv: Path) -> None:
    result = lookup_delay_history("NONEXISTENT", delay_csv)
    assert result.total_delays == 0
    assert "No delay records found" in result.explanation


def test_lookup_single_resolved(delay_csv: Path) -> None:
    result = lookup_delay_history("ONEA00000002", delay_csv)
    assert result.total_delays == 1
    assert result.ongoing_delays == 0
    assert result.resolved_delays == 1
    assert len(result.top_reasons) == 1
    assert "3007" in result.top_reasons[0]


def test_delay_types_tracked(delay_csv: Path) -> None:
    result = lookup_delay_history("ONEA00000001", delay_csv)
    assert "DC Delay" in result.delay_types
    assert result.delay_types["DC Delay"] == 2

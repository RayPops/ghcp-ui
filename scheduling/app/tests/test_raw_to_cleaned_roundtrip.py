"""Round-trip test: raw CSV (with planted phrases) -> cleaning pipeline -> assertions.

Covers the three acceptance criteria from the deliverable spec:
1. The action log contains a non-empty ``extractions`` list.
2. At least one extraction cites a ``source_excerpt`` copied verbatim from the notes.
3. ``dog_on_site_flag`` and ``heavy_ppe_hint`` round-trip when planted in the raw notes.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.cleaner import run_cleaning


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "raw_orders_sample.csv"


def _write_fixture(tmp_path: Path) -> Path:
    """Write a single-row raw CSV with planted dog + overhead phrases."""
    fixture = tmp_path / "raw_input.csv"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    with open(fixture, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "order_id",
                "order_source",
                "service_type",
                "job_type",
                "requested_start_date",
                "requested_end_date",
                "committed_delivery_date",
                "postcode",
                "driveway_surface_hint",
                "photo_provided_flag",
                "unstructured_customer_notes",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "order_id": "TEST001",
            "order_source": "Home Broadband",
            "service_type": "FTTP Installation",
            "job_type": "new line installation",
            "requested_start_date": "2025-11-01",
            "requested_end_date": "2025-11-30",
            "committed_delivery_date": "2025-11-15",
            "postcode": "EC1A 1BB",
            "driveway_surface_hint": "tarmac",
            "photo_provided_flag": "true",
            "unstructured_customer_notes": (
                "Customer mentioned a dog on site - please ring ahead so it can be secured. "
                "|| Engineer reports overhead pole work required to complete this circuit. "
                "|| Standard FTTP install at the front of the property."
            ),
        })
    return fixture


def test_raw_to_cleaned_roundtrip(tmp_path: Path) -> None:
    raw_csv = _write_fixture(tmp_path)
    out_dir = tmp_path / "out"

    summary = run_cleaning(raw_csv, out_dir, delay_csv=None)

    assert summary.processed == 1
    cleaned_path = out_dir / "work_orders_cleaned.csv"
    action_log_path = out_dir / "agent_actions.jsonl"
    assert cleaned_path.exists()
    assert action_log_path.exists()

    # --- (1) extractions list is non-empty --- #
    lines = action_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "expected one JSONL line per order"
    entry = json.loads(lines[0])
    assert entry["order_id"] == "TEST001"
    assert isinstance(entry["extractions"], list)
    assert len(entry["extractions"]) > 0, "extractions list must not be empty"

    # --- (2) at least one extraction has a verbatim source_excerpt --- #
    notes = (
        "Customer mentioned a dog on site - please ring ahead so it can be secured. "
        "|| Engineer reports overhead pole work required to complete this circuit. "
        "|| Standard FTTP install at the front of the property."
    )
    cited = [
        e for e in entry["extractions"]
        if e.get("source_excerpt") and e["source_excerpt"] in notes
    ]
    assert cited, (
        f"no extraction cited a verbatim source_excerpt; got: "
        f"{[e.get('source_excerpt') for e in entry['extractions']]}"
    )

    # --- (3) dog_on_site_flag and heavy_ppe_hint round-trip --- #
    with open(cleaned_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    cleaned = rows[0]
    assert cleaned["dog_on_site_flag"] == "true", (
        f"dog signal lost; row was: {cleaned}"
    )
    assert cleaned["heavy_ppe_hint"] == "overhead work", (
        f"overhead signal lost; row was: {cleaned}"
    )


def test_raw_to_cleaned_picks_confined_space_over_overhead(tmp_path: Path) -> None:
    """Confined space wins ties (matches existing safety semantics)."""
    raw_csv = tmp_path / "raw.csv"
    with open(raw_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "order_id", "order_source", "service_type", "job_type",
                "requested_start_date", "requested_end_date", "committed_delivery_date",
                "postcode", "driveway_surface_hint", "photo_provided_flag",
                "unstructured_customer_notes",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "order_id": "TEST002",
            "order_source": "Ethernet",
            "service_type": "Ethernet Bearer",
            "job_type": "provision",
            "requested_start_date": "2025-11-01",
            "requested_end_date": "2025-11-30",
            "committed_delivery_date": "2025-11-15",
            "postcode": "EC1A 1BB",
            "driveway_surface_hint": "",
            "photo_provided_flag": "true",
            "unstructured_customer_notes": (
                "Riser cupboard is a confined space - gas monitor needed. "
                "|| Overhead pole route at the kerbside."
            ),
        })

    summary = run_cleaning(raw_csv, tmp_path / "out", delay_csv=None)
    assert summary.processed == 1

    rows = list(csv.DictReader(open(tmp_path / "out" / "work_orders_cleaned.csv", encoding="utf-8")))
    assert rows[0]["heavy_ppe_hint"] == "confined space"

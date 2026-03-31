"""End-to-end test: process a small CSV and verify output structure."""

import csv
import json
import tempfile
from datetime import date
from pathlib import Path

from app.csv_loader import load_work_orders
from app.orchestrator import process_all


_TEST_CSV_ROWS = [
    {
        "order_id": "TEST-001",
        "order_source": "Home Broadband",
        "service_type": "FTTP Installation",
        "job_type": "new line installation",
        "requested_start_date": "2026-04-01",
        "requested_end_date": "2026-04-05",
        "committed_delivery_date": "2026-04-03",
        "postcode": "B1 1BB",
        "customer_ready_status": "ready",
        "access_issue_flag": "false",
        "customer_delay_flag": "false",
        "driveway_surface_hint": "gravel",
        "photo_provided_flag": "true",
        "dog_on_site_flag": "false",
        "exchange_visit_flag": "false",
        "heavy_ppe_hint": "",
        "unstructured_customer_notes": "Standard install. Available any time.",
    },
    {
        "order_id": "TEST-002",
        "order_source": "Ethernet",
        "service_type": "Ethernet Bearer",
        "job_type": "provision",
        "requested_start_date": "2026-04-02",
        "requested_end_date": "2026-04-12",
        "committed_delivery_date": "2026-04-05",
        "postcode": "EC1A 1BB",
        "customer_ready_status": "not ready",
        "access_issue_flag": "true",
        "customer_delay_flag": "false",
        "driveway_surface_hint": "",
        "photo_provided_flag": "false",
        "dog_on_site_flag": "true",
        "exchange_visit_flag": "true",
        "heavy_ppe_hint": "confined space",
        "unstructured_customer_notes": "DO NOT ATTEND before 10th April. Basement access with low ceiling. Guard dog on site.",
    },
]


def _write_test_csv(path: Path) -> None:
    """Write test CSV data to a file."""
    fieldnames = list(_TEST_CSV_ROWS[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_TEST_CSV_ROWS)


def test_end_to_end_pipeline():
    """Full pipeline should produce valid decisions for each work order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test_orders.csv"
        _write_test_csv(csv_path)

        # Load orders
        orders = load_work_orders(csv_path)
        assert len(orders) == 2

        # Process all
        decisions = process_all(orders)
        assert len(decisions) == 2

        # Verify first decision (clean order)
        d1 = decisions[0]
        assert d1.order_id == "TEST-001"
        assert d1.recommended_action in ("schedule", "reschedule", "needs-human-review")
        assert d1.planned_visit_date is not None
        assert d1.rationale is not None
        assert len(d1.rationale) > 0

        # Verify second decision (complex order with many flags)
        d2 = decisions[1]
        assert d2.order_id == "TEST-002"
        assert d2.recommended_action in ("reschedule", "needs-human-review")
        assert d2.planned_visit_date is not None
        assert d2.safety_assessment is not None
        assert d2.safety_assessment.extra_engineer_required is True
        assert len(d2.safety_assessment.safety_risks) > 0

        # Verify JSON serialisation works
        for d in decisions:
            d_dict = d.to_dict()
            json_str = json.dumps(d_dict)
            parsed = json.loads(json_str)
            assert parsed["order_id"] == d.order_id
            assert "recommended_action" in parsed
            assert "planned_visit_date" in parsed
            assert "rationale" in parsed


def test_end_to_end_with_real_csv():
    """Process the real CSV file and verify all orders produce decisions."""
    csv_path = Path(__file__).parent.parent.parent / "data" / "work_orders.csv"
    if not csv_path.exists():
        return  # Skip if CSV not present

    orders = load_work_orders(csv_path)
    assert len(orders) >= 10

    decisions = process_all(orders)
    assert len(decisions) == len(orders)

    for d in decisions:
        assert d.recommended_action in ("schedule", "reschedule", "needs-human-review")
        assert d.rationale is not None
        assert len(d.rationale) > 0
        # Verify JSON round-trip
        d_dict = d.to_dict()
        json.dumps(d_dict)  # should not raise

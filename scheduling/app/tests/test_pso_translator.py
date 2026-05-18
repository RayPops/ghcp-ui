"""Snapshot tests for the PSO XML translator.

Strategy
--------
For three representative orders we:
1. Load the row from ``data/work_orders.csv``.
2. Run it through the existing scheduling pipeline (skills A-D + composer).
3. Translate the resulting decision into PSO XML using a fixed "now" timestamp,
   a fixed Input_Reference id, and static lat/lon (no live geocoding).
4. Compare the canonicalised XML against a committed fixture file.

Set the env var ``UPDATE_PSO_SNAPSHOTS=1`` to (re)write the fixtures after a
deliberate change to the translator or the mapping tables.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from app.csv_loader import load_work_orders
from app.integrations.pso.translator import build_pso_inputs, render_add_tasks_xml
from app.orchestrator import process_work_order

SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / "pso"
CSV_PATH = Path(__file__).parent.parent.parent / "data" / "work_orders.csv"

FROZEN_NOW = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
FROZEN_TODAY = FROZEN_NOW.date()
FROZEN_INPUT_REF_ID = "00000000000000000000000000000000"

# Static coordinates per order so the snapshot is deterministic regardless of
# the geocoder. Approximate UK postcode centroids.
STATIC_COORDINATES: dict[str, tuple[float, float]] = {
    "ONEA92160383": (51.5170, -0.0980),   # EC1A 1BB - City of London (moved from Shetland for demo)
    "ONEA73446139": (51.5135, -0.3045),   # W5 2BJ - Ealing
    "ONEA78030061": (51.5170, -0.0980),   # EC1A 1BB - City of London
}


def _canonical(xml_text: str) -> str:
    return ET.canonicalize(xml_text, strip_text=True)


def _load_order(order_id: str):
    orders = load_work_orders(CSV_PATH)
    by_id = {o.order_id: o for o in orders}
    if order_id not in by_id:
        raise AssertionError(f"Order {order_id} not found in {CSV_PATH}")
    return by_id[order_id]


def _render(order_id: str) -> str:
    order = _load_order(order_id)
    decision = process_work_order(order)
    inputs = build_pso_inputs(
        decision, order, STATIC_COORDINATES[order_id], today=FROZEN_TODAY,
    )
    return render_add_tasks_xml(
        inputs,
        now=FROZEN_NOW,
        uuid_factory=lambda: FROZEN_INPUT_REF_ID,
    )


def _compare_or_update(order_id: str, actual_xml: str) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOT_DIR / f"{order_id}.xml"

    if os.environ.get("UPDATE_PSO_SNAPSHOTS") == "1" or not snapshot_path.exists():
        snapshot_path.write_text(actual_xml, encoding="utf-8")
        pytest.skip(f"Wrote snapshot for {order_id}; rerun without UPDATE_PSO_SNAPSHOTS=1")

    expected_xml = snapshot_path.read_text(encoding="utf-8")
    assert _canonical(actual_xml) == _canonical(expected_xml), (
        f"Snapshot mismatch for {order_id}.\n"
        f"Run with UPDATE_PSO_SNAPSHOTS=1 if the change is intentional."
    )


@pytest.mark.parametrize(
    "order_id",
    [
        "ONEA92160383",  # FTTP installation, overhead work hint
        "ONEA73446139",  # Ethernet Bearer, customer not ready
        "ONEA78030061",  # Ethernet Bearer, confined space hint
    ],
)
def test_translator_snapshot(order_id: str) -> None:
    actual = _render(order_id)
    _compare_or_update(order_id, actual)

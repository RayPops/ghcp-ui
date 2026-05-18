"""Regression test for the dispersed-postcode demo CSV.

Before this change the seed CSV had seven orders sharing ``EC1A 1BB`` which
produced an unrealistic PSO plan (five engineers stacked on one street).
The fix re-spread the seven London orders across distinct outward codes so
PSO shows them across the city. This test pins that intent.
"""

from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path

import pytest

_CSV_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "work_orders.csv"
)


def _load_postcodes() -> list[str]:
    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        return [row["postcode"] for row in csv.DictReader(f)]


def test_every_postcode_is_unique() -> None:
    """No postcode should appear more than once in the demo CSV."""
    postcodes = _load_postcodes()
    counts = Counter(postcodes)
    duplicates = {pc: n for pc, n in counts.items() if n > 1}
    assert not duplicates, (
        f"Found duplicate postcodes in {_CSV_PATH.name}: {duplicates}. "
        "Spread the orders across distinct outward codes — see the "
        "BT demo follow-up brief."
    )


def test_every_postcode_resolves_via_pgeocode() -> None:
    """Every postcode must resolve to a non-null lat/long.

    PSO needs a real coordinate or the activity will not place on the map.
    """
    pgeocode = pytest.importorskip("pgeocode")

    nomi = pgeocode.Nominatim("gb")
    unresolved: list[str] = []
    for postcode in _load_postcodes():
        record = nomi.query_postal_code(postcode)
        if math.isnan(float(record.latitude)) or math.isnan(float(record.longitude)):
            unresolved.append(postcode)

    assert not unresolved, (
        f"pgeocode could not resolve these postcodes to lat/long: {unresolved}"
    )

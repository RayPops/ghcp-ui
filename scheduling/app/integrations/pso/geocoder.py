"""Geocoder protocol and the lightweight static implementation used in tests.

The pgeocode-backed implementation lives in :mod:`pgeocode_geocoder` so that
test environments without ``pgeocode`` installed can still import this module.
"""

from __future__ import annotations

from typing import Protocol


class Geocoder(Protocol):
    """Resolve a UK postcode to a ``(latitude, longitude)`` pair."""

    def lookup(self, postcode: str) -> tuple[float, float]: ...


class StaticGeocoder:
    """Dict-backed geocoder. Useful for tests and offline demo runs."""

    def __init__(self, table: dict[str, tuple[float, float]]) -> None:
        # Normalise keys the same way as ``lookup`` so callers can pass mixed
        # case / whitespace.
        self._table = {self._normalise(k): v for k, v in table.items()}

    @staticmethod
    def _normalise(postcode: str) -> str:
        return (postcode or "").strip().upper().replace("  ", " ")

    def lookup(self, postcode: str) -> tuple[float, float]:
        key = self._normalise(postcode)
        if key not in self._table:
            raise ValueError(
                f"StaticGeocoder has no entry for postcode {postcode!r}. "
                f"Known postcodes: {sorted(self._table.keys())}"
            )
        return self._table[key]

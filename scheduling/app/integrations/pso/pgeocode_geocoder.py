"""pgeocode-backed UK postcode geocoder.

Caveat
------
``pgeocode`` resolves UK postcodes at the **outward-code level only**. For
example ``"EC1A 1BB"`` and ``"EC1A 9XY"`` both resolve to the same coordinate
(the centroid of the EC1A district). Accuracy is roughly 1 km in dense urban
areas, worse in rural ones. Good enough for the IFS PSO demo where PSO uses
the point for travel-time approximation, but **not appropriate for production
field-engineer routing** — for that we would swap in a unit-postcode source
such as the ONS Postcode Directory or postcodes.io behind the same
:class:`Geocoder` Protocol.

The Nominatim instance loads a CSV on first construction, so the geocoder
should be built once and reused, not per-call.
"""

from __future__ import annotations

import math

import pgeocode  # type: ignore[import-untyped]


class PgeocodeGeocoder:
    """UK postcode geocoder backed by ``pgeocode.Nominatim('gb')``."""

    def __init__(self) -> None:
        self._nomi = pgeocode.Nominatim("gb")

    @staticmethod
    def _normalise(postcode: str) -> str:
        return (postcode or "").strip().upper()

    def lookup(self, postcode: str) -> tuple[float, float]:
        normalised = self._normalise(postcode)
        if not normalised:
            raise ValueError("Postcode is empty")

        record = self._nomi.query_postal_code(normalised)
        latitude = float(record.latitude)
        longitude = float(record.longitude)

        if math.isnan(latitude) or math.isnan(longitude):
            raise ValueError(
                f"pgeocode could not resolve postcode {postcode!r} "
                "(unknown or invalid)"
            )

        return latitude, longitude

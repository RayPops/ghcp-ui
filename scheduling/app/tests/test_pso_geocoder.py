"""Tests for the static geocoder used by the test suite."""

from __future__ import annotations

import pytest

from app.integrations.pso.geocoder import StaticGeocoder


def test_static_geocoder_returns_known_coordinates() -> None:
    geo = StaticGeocoder({"EC1A 1BB": (51.517, -0.098)})
    assert geo.lookup("ec1a 1bb") == (51.517, -0.098)


def test_static_geocoder_unknown_postcode_raises_clear_error() -> None:
    geo = StaticGeocoder({"EC1A 1BB": (51.517, -0.098)})

    with pytest.raises(ValueError) as exc_info:
        geo.lookup("ZZ99 9ZZ")

    message = str(exc_info.value)
    assert "ZZ99 9ZZ" in message
    assert "EC1A 1BB" in message  # surfaces what *is* known

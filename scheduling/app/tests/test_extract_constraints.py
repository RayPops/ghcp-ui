"""Unit tests for Skill A: Extract scheduling constraints."""

from datetime import date

from app.skills.extract_constraints import extract_scheduling_constraints


def test_extract_earliest_date_from_do_not_attend():
    """Notes with 'do not attend before' should set earliest_allowed_date."""
    notes = "Customer called. DO NOT ATTEND before 10th April. Will be away."
    result = extract_scheduling_constraints(
        customer_notes=notes,
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 10),
        committed_delivery_date=date(2026, 4, 5),
    )
    assert result.earliest_allowed_date == date(2026, 4, 10)


def test_extract_earliest_date_from_holiday():
    """Notes mentioning holiday until a date should set earliest_allowed_date."""
    notes = "Customer on holiday until 15th April. Please do not visit before then."
    result = extract_scheduling_constraints(
        customer_notes=notes,
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 20),
        committed_delivery_date=date(2026, 4, 8),
    )
    assert result.earliest_allowed_date == date(2026, 4, 15)


def test_extract_afternoon_availability():
    """Notes with 'prefers afternoon' should set availability window."""
    notes = "Intermittent fault. Customer works from home - prefers afternoon slot after 2pm."
    result = extract_scheduling_constraints(
        customer_notes=notes,
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 5),
        committed_delivery_date=date(2026, 4, 3),
    )
    assert result.customer_availability_window == "afternoons only"


def test_extract_morning_availability():
    """Notes with 'only available mornings before 12' should set availability."""
    notes = "Large dog in garden. Notes say customer only available mornings before 12."
    result = extract_scheduling_constraints(
        customer_notes=notes,
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 5),
        committed_delivery_date=date(2026, 4, 3),
    )
    assert result.customer_availability_window == "mornings only"


def test_extract_special_instructions():
    """Notes with access codes and contact info should populate special_instructions."""
    notes = "Rear access only, use side gate code 4821. Contact site manager Dave on 07700 900123."
    result = extract_scheduling_constraints(
        customer_notes=notes,
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 5),
        committed_delivery_date=date(2026, 4, 3),
    )
    assert len(result.special_instructions) >= 1
    combined = " ".join(result.special_instructions).lower()
    assert "gate code 4821" in combined or "side gate" in combined


def test_empty_notes_returns_empty_constraints():
    """Empty notes should return empty constraints."""
    result = extract_scheduling_constraints(
        customer_notes="",
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 5),
        committed_delivery_date=date(2026, 4, 3),
    )
    assert result.earliest_allowed_date is None
    assert result.customer_availability_window == ""
    assert result.special_instructions == []


def test_do_not_book_sets_far_future():
    """Notes with 'do not book' should force a far-future earliest date."""
    notes = "Customer wants to delay. DO NOT book until customer confirms."
    result = extract_scheduling_constraints(
        customer_notes=notes,
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 10),
        committed_delivery_date=date(2026, 4, 6),
    )
    assert result.earliest_allowed_date is not None
    assert result.earliest_allowed_date > date(2026, 4, 10)

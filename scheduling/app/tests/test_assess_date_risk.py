"""Unit tests for Skill B: Assess delivery date risk."""

from datetime import date

from app.models import SchedulingConstraints
from app.skills.assess_date_risk import assess_delivery_date_risk


def test_no_issues_returns_no_change():
    """Clean order with no issues should not recommend date change."""
    result = assess_delivery_date_risk(
        order_source="Home Broadband",
        committed_delivery_date=date(2026, 4, 3),
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 5),
        access_issue_flag=False,
        customer_delay_flag=False,
        customer_ready_status="ready",
    )
    assert result.date_change_recommended is False
    assert result.reason_code == "no_change_needed"


def test_customer_availability_conflict_triggers_reschedule():
    """When earliest_allowed_date is after committed date, should recommend change."""
    constraints = SchedulingConstraints(earliest_allowed_date=date(2026, 4, 10))
    result = assess_delivery_date_risk(
        order_source="Home Broadband",
        committed_delivery_date=date(2026, 4, 5),
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 10),
        access_issue_flag=False,
        customer_delay_flag=False,
        customer_ready_status="ready",
        constraints=constraints,
    )
    assert result.date_change_recommended is True
    assert result.reason_code == "delay_exceeds_allowed_window"


def test_ethernet_allows_longer_delay():
    """Ethernet orders should allow up to 10 days of delay."""
    constraints = SchedulingConstraints(earliest_allowed_date=date(2026, 4, 15))
    result = assess_delivery_date_risk(
        order_source="Ethernet",
        committed_delivery_date=date(2026, 4, 8),
        requested_start_date=date(2026, 4, 5),
        requested_end_date=date(2026, 4, 20),
        access_issue_flag=False,
        customer_delay_flag=False,
        customer_ready_status="ready",
        constraints=constraints,
    )
    assert result.date_change_recommended is True
    assert result.revised_delivery_date is not None
    assert result.revised_delivery_date >= date(2026, 4, 15)


def test_access_issue_triggers_reschedule():
    """Access issue flag should trigger a date change recommendation."""
    result = assess_delivery_date_risk(
        order_source="Home Broadband",
        committed_delivery_date=date(2026, 4, 3),
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 5),
        access_issue_flag=True,
        customer_delay_flag=False,
        customer_ready_status="ready",
    )
    assert result.date_change_recommended is True
    assert result.reason_code == "access_issue"


def test_customer_not_ready():
    """Customer not ready should trigger reschedule."""
    result = assess_delivery_date_risk(
        order_source="Ethernet",
        committed_delivery_date=date(2026, 4, 10),
        requested_start_date=date(2026, 4, 5),
        requested_end_date=date(2026, 4, 15),
        access_issue_flag=False,
        customer_delay_flag=False,
        customer_ready_status="not ready",
    )
    assert result.date_change_recommended is True
    assert result.reason_code == "customer_not_ready"


def test_revised_date_is_working_day():
    """Revised date should always be a working day."""
    # 2026-04-04 is a Saturday
    constraints = SchedulingConstraints(earliest_allowed_date=date(2026, 4, 4))
    result = assess_delivery_date_risk(
        order_source="Home Broadband",
        committed_delivery_date=date(2026, 4, 2),
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 10),
        access_issue_flag=False,
        customer_delay_flag=False,
        customer_ready_status="ready",
        constraints=constraints,
    )
    if result.revised_delivery_date:
        assert result.revised_delivery_date.weekday() < 5  # Monday to Friday

"""Skill B: Assess delivery date risk and recommend date changes."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from app.models import DeliveryDateRisk, SchedulingConstraints

logger = logging.getLogger(__name__)

# Ethernet orders allow date movement within these bounds
_ETHERNET_MAX_DELAY_DAYS = 10
_BROADBAND_MAX_DELAY_DAYS = 3


def _next_working_day(d: date) -> date:
    """Return the next working day on or after the given date (skip weekends)."""
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d += timedelta(days=1)
    return d


def assess_delivery_date_risk(
    order_source: str,
    committed_delivery_date: date,
    requested_start_date: date,
    requested_end_date: date,
    access_issue_flag: bool,
    customer_delay_flag: bool,
    customer_ready_status: str,
    constraints: Optional[SchedulingConstraints] = None,
) -> DeliveryDateRisk:
    """Assess whether a committed delivery date needs to change.

    Applies product-specific delay rules:
    - Ethernet orders allow up to 10 working days of movement
    - Home Broadband orders allow up to 3 days of movement
    - Various flags and constraint outputs can trigger a recommendation to reschedule

    Args:
        order_source: "Ethernet" or "Home Broadband".
        committed_delivery_date: Current contractual delivery date.
        requested_start_date: Start of customer requested window.
        requested_end_date: End of customer requested window.
        access_issue_flag: Whether there is a known access problem.
        customer_delay_flag: Whether the customer requested a delay.
        customer_ready_status: "ready", "not ready", or "unknown".
        constraints: Output from Skill A (scheduling constraints).

    Returns:
        DeliveryDateRisk with recommendation.
    """
    result = DeliveryDateRisk()
    is_ethernet = order_source.lower() == "ethernet"
    max_delay = _ETHERNET_MAX_DELAY_DAYS if is_ethernet else _BROADBAND_MAX_DELAY_DAYS
    reasons: list[str] = []

    # Check if earliest allowed date conflicts with committed date
    if constraints and constraints.earliest_allowed_date:
        if constraints.earliest_allowed_date > committed_delivery_date:
            days_gap = (constraints.earliest_allowed_date - committed_delivery_date).days
            if days_gap <= max_delay:
                result.revised_delivery_date = _next_working_day(constraints.earliest_allowed_date)
                result.date_change_recommended = True
                result.reason_code = "customer_availability_conflict"
                reasons.append(
                    f"Customer is not available until {constraints.earliest_allowed_date.isoformat()}. "
                    f"Committed date of {committed_delivery_date.isoformat()} is {days_gap} day(s) too early."
                )
            else:
                result.date_change_recommended = True
                result.reason_code = "delay_exceeds_allowed_window"
                result.revised_delivery_date = _next_working_day(
                    committed_delivery_date + timedelta(days=max_delay)
                )
                reasons.append(
                    f"Customer availability gap of {days_gap} days exceeds the maximum allowed "
                    f"delay of {max_delay} days for {order_source} orders. Needs human review."
                )

    # Customer delay flag
    if customer_delay_flag and not result.date_change_recommended:
        result.date_change_recommended = True
        result.reason_code = "customer_requested_delay"
        result.revised_delivery_date = _next_working_day(
            committed_delivery_date + timedelta(days=max_delay)
        )
        reasons.append("Customer has requested a delay.")

    # Access issues (Ethernet orders can absorb; broadband less so)
    if access_issue_flag:
        if not result.date_change_recommended:
            result.date_change_recommended = True
            result.reason_code = "access_issue"
            result.revised_delivery_date = _next_working_day(
                committed_delivery_date + timedelta(days=3 if is_ethernet else 2)
            )
        reasons.append("Access issue flagged. Additional time may be needed to resolve.")

    # Customer not ready
    if customer_ready_status == "not ready":
        if not result.date_change_recommended:
            result.date_change_recommended = True
            result.reason_code = "customer_not_ready"
            result.revised_delivery_date = _next_working_day(
                committed_delivery_date + timedelta(days=max_delay)
            )
        reasons.append("Customer is marked as not ready.")

    # If no issues found, confirm the current date
    if not result.date_change_recommended:
        result.reason_code = "no_change_needed"
        result.revised_delivery_date = committed_delivery_date
        reasons.append("No delivery date risks identified. Current committed date is suitable.")

    result.explanation = " ".join(reasons)
    logger.info(
        "Date risk for %s order (committed %s): change=%s, reason=%s",
        order_source,
        committed_delivery_date,
        result.date_change_recommended,
        result.reason_code,
    )
    return result

"""Orchestrator: calls all skills and composes a final scheduling decision."""

from __future__ import annotations

import logging
from datetime import timedelta

from app.models import (
    SchedulingDecision,
    WorkOrder,
)
from app.skills.extract_constraints import extract_scheduling_constraints
from app.skills.assess_date_risk import assess_delivery_date_risk
from app.skills.assess_visit_readiness import assess_visit_readiness
from app.skills.assess_safety import assess_safety_and_feasibility

logger = logging.getLogger(__name__)


def _next_working_day_from(d):
    """Return the next working day on or after the given date."""
    from datetime import timedelta as td
    while d.weekday() >= 5:
        d += td(days=1)
    return d


def process_work_order(order: WorkOrder) -> SchedulingDecision:
    """Process a single work order through all skills and compose a decision.

    Args:
        order: A validated WorkOrder.

    Returns:
        SchedulingDecision with recommendations from all skills.
    """
    logger.info("Processing work order %s", order.order_id)

    # Step 1: Extract scheduling constraints (Skill A)
    constraints = extract_scheduling_constraints(
        customer_notes=order.unstructured_customer_notes,
        requested_start_date=order.requested_start_date,
        requested_end_date=order.requested_end_date,
        committed_delivery_date=order.committed_delivery_date,
    )

    # Step 2: Assess delivery date risk (Skill B)
    date_risk = assess_delivery_date_risk(
        order_source=order.order_source,
        committed_delivery_date=order.committed_delivery_date,
        requested_start_date=order.requested_start_date,
        requested_end_date=order.requested_end_date,
        access_issue_flag=order.access_issue_flag,
        customer_delay_flag=order.customer_delay_flag,
        customer_ready_status=order.customer_ready_status,
        constraints=constraints,
    )

    # Step 3: Assess visit readiness (Skill C)
    readiness = assess_visit_readiness(
        service_type=order.service_type,
        job_type=order.job_type,
        driveway_surface_hint=order.driveway_surface_hint,
        photo_provided_flag=order.photo_provided_flag,
        customer_notes=order.unstructured_customer_notes,
    )

    # Step 4: Assess safety and feasibility (Skill D)
    safety = assess_safety_and_feasibility(
        dog_on_site_flag=order.dog_on_site_flag,
        heavy_ppe_hint=order.heavy_ppe_hint,
        exchange_visit_flag=order.exchange_visit_flag,
        customer_notes=order.unstructured_customer_notes,
    )

    # Step 5: Compose final decision
    rationale: list[str] = []
    recommended_action = "schedule"
    planned_date = order.committed_delivery_date

    # Apply date risk recommendation
    if date_risk.date_change_recommended:
        if date_risk.reason_code == "delay_exceeds_allowed_window":
            recommended_action = "needs-human-review"
            rationale.append(
                f"Delivery date delay exceeds allowed window for {order.order_source} orders"
            )
        else:
            recommended_action = "reschedule"

        if date_risk.revised_delivery_date:
            planned_date = date_risk.revised_delivery_date
            rationale.append(
                f"Delivery date moved from {order.committed_delivery_date.isoformat()} "
                f"to {planned_date.isoformat()} ({date_risk.reason_code})"
            )

    # Apply constraint-based adjustments
    if constraints.earliest_allowed_date and planned_date < constraints.earliest_allowed_date:
        planned_date = _next_working_day_from(constraints.earliest_allowed_date)
        if recommended_action == "schedule":
            recommended_action = "reschedule"
        rationale.append(
            f"Adjusted to {planned_date.isoformat()} based on customer availability constraint"
        )

    if constraints.customer_availability_window:
        rationale.append(
            f"Customer availability: {constraints.customer_availability_window}"
        )

    if constraints.special_instructions:
        rationale.append(
            f"Special instructions: {', '.join(constraints.special_instructions)}"
        )

    # Apply readiness notes
    if readiness.confidence == "low":
        if recommended_action == "schedule":
            recommended_action = "needs-human-review"
        rationale.append("Visit readiness confidence is low - human review recommended")

    rationale.append(
        f"Estimated duration: {readiness.estimated_duration_minutes} minutes "
        f"(confidence: {readiness.confidence})"
    )

    # Apply safety notes
    if safety.safety_risks:
        rationale.append(f"Safety risks: {', '.join(safety.safety_risks)}")

    if safety.extra_engineer_required:
        rationale.append("Extra engineer required for this job")

    # Customer not ready => needs human review
    if order.customer_ready_status == "not ready":
        recommended_action = "needs-human-review"
        rationale.append("Customer marked as not ready")

    # Ensure planned_date is a working day
    planned_date = _next_working_day_from(planned_date)

    decision = SchedulingDecision(
        order_id=order.order_id,
        recommended_action=recommended_action,
        planned_visit_date=planned_date,
        constraints=constraints,
        delivery_date_assessment=date_risk,
        visit_readiness=readiness,
        safety_assessment=safety,
        rationale=rationale,
    )

    logger.info(
        "Decision for %s: %s on %s (%d rationale points)",
        order.order_id,
        recommended_action,
        planned_date,
        len(rationale),
    )

    return decision


def process_all(orders: list[WorkOrder]) -> list[SchedulingDecision]:
    """Process all work orders and return decisions.

    Args:
        orders: List of WorkOrder objects.

    Returns:
        List of SchedulingDecision objects.
    """
    decisions = []
    for order in orders:
        try:
            decision = process_work_order(order)
            decisions.append(decision)
        except Exception as exc:
            logger.error("Failed to process %s: %s", order.order_id, exc)
            decisions.append(
                SchedulingDecision(
                    order_id=order.order_id,
                    recommended_action="needs-human-review",
                    rationale=[f"Processing error: {exc}"],
                )
            )
    return decisions

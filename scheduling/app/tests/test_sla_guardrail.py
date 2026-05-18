"""Unit tests for the SLA guardrail.

Covers all three branches of the rule:
* past committed date -> shifted to today + 1 business day, action entry emitted
* future committed date -> untouched, no action entry
* today's date -> untouched, no action entry

Also exercises the PSO translator path so we know the same shift applies
when an order goes out to PSO, not just to the cleaned CSV.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.aggregator import aggregate
from app.integrations.pso.translator import build_pso_inputs
from app.models import (
    SchedulingConstraints,
    SchedulingDecision,
    VisitReadiness,
    WorkOrder,
)
from app.sla_guardrail import (
    GUARDRAIL_REASON,
    apply_sla_guardrail,
    next_business_day,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_order(committed: date) -> WorkOrder:
    return WorkOrder(
        order_id="TEST-SLA",
        order_source="Home Broadband",
        service_type="FTTP Installation",
        job_type="new line installation",
        requested_start_date=date(2025, 11, 1),
        requested_end_date=date(2025, 11, 30),
        committed_delivery_date=committed,
        postcode="EC1A 1BB",
        customer_ready_status="unknown",
        access_issue_flag=False,
        customer_delay_flag=False,
        driveway_surface_hint="tarmac",
        photo_provided_flag=False,
        dog_on_site_flag=False,
        exchange_visit_flag=False,
        heavy_ppe_hint="",
        unstructured_customer_notes="Standard install.",
    )


def _make_decision(order: WorkOrder) -> SchedulingDecision:
    return SchedulingDecision(
        order_id=order.order_id,
        recommended_action="schedule",
        planned_visit_date=order.committed_delivery_date,
        constraints=SchedulingConstraints(),
        delivery_date_assessment=None,
        visit_readiness=VisitReadiness(estimated_duration_minutes=60),
        safety_assessment=None,
        rationale=[],
    )


def _guardrail_entries(extractions: list[dict]) -> list[dict]:
    return [e for e in extractions if e.get("field") == "sla_guardrail_applied"]


# --------------------------------------------------------------------------- #
# Pure helper
# --------------------------------------------------------------------------- #


def test_next_business_day_skips_weekend() -> None:
    # Fri -> Mon
    assert next_business_day(date(2026, 5, 15)) == date(2026, 5, 18)
    # Sat -> Mon
    assert next_business_day(date(2026, 5, 16)) == date(2026, 5, 18)
    # Sun -> Mon
    assert next_business_day(date(2026, 5, 17)) == date(2026, 5, 18)
    # Wed -> Thu
    assert next_business_day(date(2026, 5, 13)) == date(2026, 5, 14)


def test_apply_sla_guardrail_past_shifts_to_next_business_day() -> None:
    today = date(2026, 5, 13)  # Wednesday
    result = apply_sla_guardrail(date(2025, 11, 15), today)
    assert result.shifted is True
    assert result.original_date == date(2025, 11, 15)
    assert result.effective_date == date(2026, 5, 14)  # Thursday


def test_apply_sla_guardrail_future_passes_through() -> None:
    today = date(2026, 5, 13)
    result = apply_sla_guardrail(date(2026, 6, 1), today)
    assert result.shifted is False
    assert result.effective_date == date(2026, 6, 1)


def test_apply_sla_guardrail_today_passes_through() -> None:
    today = date(2026, 5, 13)
    result = apply_sla_guardrail(today, today)
    assert result.shifted is False
    assert result.effective_date == today


# --------------------------------------------------------------------------- #
# Aggregator integration
# --------------------------------------------------------------------------- #


def test_aggregate_past_committed_date_emits_guardrail_entry() -> None:
    today = date(2026, 5, 13)  # Wednesday
    order = _make_order(committed=date(2025, 11, 15))
    decision = _make_decision(order)

    agg = aggregate(order, decision, delays=None, today=today)
    log_entry = agg.action_log_entry(order)
    guardrail = _guardrail_entries(log_entry["extractions"])

    # One guardrail entry, original preserved, shifted value present.
    assert len(guardrail) == 1
    entry = guardrail[0]
    assert entry["original_committed_date"] == "2025-11-15"
    assert entry["shifted_committed_date"] == "2026-05-14"
    assert entry["reason"] == GUARDRAIL_REASON
    assert entry["skill"] == "SLA Guardrail"

    # Cleaned-row committed_delivery_date carries the shifted value.
    assert agg.cleaned_row["committed_delivery_date"] == "2026-05-14"


def test_aggregate_future_committed_date_no_guardrail() -> None:
    today = date(2026, 5, 13)
    order = _make_order(committed=date(2026, 6, 1))
    decision = _make_decision(order)

    agg = aggregate(order, decision, delays=None, today=today)
    log_entry = agg.action_log_entry(order)
    guardrail = _guardrail_entries(log_entry["extractions"])

    assert guardrail == []
    assert agg.cleaned_row["committed_delivery_date"] == "2026-06-01"


def test_aggregate_today_committed_date_no_guardrail() -> None:
    today = date(2026, 5, 13)
    order = _make_order(committed=today)
    decision = _make_decision(order)

    agg = aggregate(order, decision, delays=None, today=today)
    log_entry = agg.action_log_entry(order)
    guardrail = _guardrail_entries(log_entry["extractions"])

    assert guardrail == []
    assert agg.cleaned_row["committed_delivery_date"] == today.isoformat()


# --------------------------------------------------------------------------- #
# Translator integration - PSO must receive the shifted date
# --------------------------------------------------------------------------- #


def test_translator_past_committed_date_uses_shifted_sla() -> None:
    today = date(2026, 5, 13)  # Wednesday -> guardrail target is Thu 14th
    order = _make_order(committed=date(2025, 11, 15))
    decision = _make_decision(order)

    inputs = build_pso_inputs(decision, order, (51.5, -0.1), today=today)

    # soonest_start lands on the shifted business day (Thu 2026-05-14).
    assert inputs.soonest_start.date() == date(2026, 5, 14)
    # latest_start is the working day after (Fri 2026-05-15).
    assert inputs.latest_start.date() == date(2026, 5, 15)


def test_translator_future_committed_date_unchanged() -> None:
    today = date(2026, 5, 13)
    future = date(2026, 6, 1)  # Monday
    order = _make_order(committed=future)
    decision = _make_decision(order)

    inputs = build_pso_inputs(decision, order, (51.5, -0.1), today=today)

    assert inputs.soonest_start.date() == future


@pytest.mark.parametrize(
    "today_d, expected_target",
    [
        (date(2026, 5, 13), date(2026, 5, 14)),  # Wed -> Thu
        (date(2026, 5, 15), date(2026, 5, 18)),  # Fri -> Mon
        (date(2026, 5, 16), date(2026, 5, 18)),  # Sat -> Mon
    ],
)
def test_aggregate_guardrail_target_respects_weekends(
    today_d: date, expected_target: date,
) -> None:
    order = _make_order(committed=date(2025, 11, 15))
    decision = _make_decision(order)
    agg = aggregate(order, decision, delays=None, today=today_d)
    assert agg.cleaned_row["committed_delivery_date"] == expected_target.isoformat()

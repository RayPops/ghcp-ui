"""SLA guardrail: keep PSO from receiving a committed delivery date in the past.

Federico (IFS) flagged that several seed work orders carry an SLA dated 17 or
18 November 2025 - in the past relative to the agent's run date. When PSO
ingests an Activity with both ``soonest`` and ``latest`` start times in the
past it refuses to schedule it. The guardrail is a small, deterministic rule:

* If ``committed_delivery_date < today``, the effective SLA date becomes
  ``today + 1 business day`` (Mon-Fri only).
* If ``committed_delivery_date >= today`` it is passed through untouched.

Both the cleaning pipeline (``aggregator.aggregate``) and the PSO push path
(``translator.build_pso_inputs``) call into this module so the cleaned CSV
row, the action log, and the PSO XML all agree on the shifted date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


GUARDRAIL_REASON = "committed_delivery_date in the past at run time"


def next_business_day(d: date) -> date:
    """Return the next Mon-Fri date strictly after ``d``.

    Saturday and Sunday are skipped, so a Friday rolls over to the following
    Monday and a Saturday/Sunday also lands on the following Monday.
    """
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:  # 5 = Sat, 6 = Sun
        nxt += timedelta(days=1)
    return nxt


@dataclass(frozen=True)
class GuardrailResult:
    """Outcome of applying the guardrail to a single committed date."""

    effective_date: date
    shifted: bool
    original_date: date


def apply_sla_guardrail(committed_date: date, today: date) -> GuardrailResult:
    """Apply the past-date guardrail.

    Returns a :class:`GuardrailResult` where ``effective_date`` is what
    callers should use as the SLA date going forward. ``shifted`` is true iff
    the input was strictly before ``today`` and was rolled forward.
    """
    if committed_date < today:
        return GuardrailResult(
            effective_date=next_business_day(today),
            shifted=True,
            original_date=committed_date,
        )
    return GuardrailResult(
        effective_date=committed_date,
        shifted=False,
        original_date=committed_date,
    )

"""Cleaning pipeline: raw CSV -> cleaned CSV + per-order action log.

For each row in the raw CSV (missing the six dropped flag columns):
1. Load it as a WorkOrder with safe defaults for the missing flags.
2. Run ``process_work_order`` (which calls Skills A + B + C + D).
3. Run ``aggregator.aggregate`` to map skill outputs back into the cleaned
   17-column row plus an action-log entry.
4. Optionally enrich with Skill E (delay history).
5. Write ``output/work_orders_cleaned.csv`` and ``output/agent_actions.jsonl``.

The original ``data/work_orders.csv`` is **never overwritten**.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from app.aggregator import CLEANED_COLUMNS, aggregate
from app.models import DelayHistory, WorkOrder
from app.orchestrator import process_work_order
from app.skills.lookup_delay_history import lookup_delay_history

logger = logging.getLogger(__name__)


def _parse_date(value: str):
    from datetime import date
    return date.fromisoformat(value.strip())


def _load_raw_orders(csv_path: Path) -> list[WorkOrder]:
    """Read the raw CSV (missing 6 flag columns) and build WorkOrders.

    Defaults for the missing columns are deliberately *neutral* so the skills
    have to recover the signal from the notes themselves - which is the whole
    point of the demo. The cleaning pipeline can then check whether the
    recovery matches the original cleaned CSV.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Raw CSV not found: {csv_path}")

    orders: list[WorkOrder] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            try:
                orders.append(WorkOrder(
                    order_id=row["order_id"].strip(),
                    order_source=row.get("order_source", "").strip(),
                    service_type=row.get("service_type", "").strip(),
                    job_type=row.get("job_type", "").strip(),
                    requested_start_date=_parse_date(row["requested_start_date"]),
                    requested_end_date=_parse_date(row["requested_end_date"]),
                    committed_delivery_date=_parse_date(row["committed_delivery_date"]),
                    postcode=row.get("postcode", "").strip(),
                    # The six recovered columns - all default to neutral so the
                    # skills have to extract them from the notes.
                    customer_ready_status="unknown",
                    access_issue_flag=False,
                    customer_delay_flag=False,
                    driveway_surface_hint=row.get("driveway_surface_hint", "").strip(),
                    photo_provided_flag=row.get("photo_provided_flag", "").strip().lower() == "true",
                    dog_on_site_flag=False,
                    exchange_visit_flag=False,
                    heavy_ppe_hint="",
                    unstructured_customer_notes=row.get("unstructured_customer_notes", "").strip(),
                ))
            except Exception as exc:
                logger.warning("Skipping invalid raw row %d: %s", row_num, exc)
    logger.info("Loaded %d raw orders from %s", len(orders), csv_path)
    return orders


def _try_lookup_delays(order_id: str, delay_csv: Optional[Path]) -> Optional[DelayHistory]:
    """Best-effort Skill E lookup. Missing CSV is non-fatal - we just skip enrichment."""
    if delay_csv is None or not delay_csv.exists():
        return None
    try:
        return lookup_delay_history(order_id, delay_csv)
    except Exception as exc:
        logger.warning("Skill E lookup failed for %s: %s", order_id, exc)
        return None


@dataclass
class CleaningSummary:
    processed: int
    cleaned_csv_path: Path
    action_log_path: Path
    decisions_breakdown: dict[str, int]


def run_cleaning(
    input_csv: Path,
    output_dir: Path,
    delay_csv: Optional[Path] = None,
    today: Optional[date] = None,
) -> CleaningSummary:
    """End-to-end raw -> cleaned + action log. Pure orchestration, no CLI parsing.

    ``today`` is threaded into :func:`aggregator.aggregate` so the SLA
    guardrail can shift any committed delivery dates that are in the past.
    Defaults to :func:`datetime.date.today`.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cleaned_csv_path = output_dir / "work_orders_cleaned.csv"
    action_log_path = output_dir / "agent_actions.jsonl"

    orders = _load_raw_orders(input_csv)

    decisions_breakdown: Counter[str] = Counter()

    with (
        open(cleaned_csv_path, "w", newline="", encoding="utf-8") as cleaned_f,
        open(action_log_path, "w", encoding="utf-8") as action_f,
    ):
        writer = csv.DictWriter(cleaned_f, fieldnames=list(CLEANED_COLUMNS))
        writer.writeheader()

        for order in orders:
            decision = process_work_order(order)
            delays = _try_lookup_delays(order.order_id, delay_csv)
            agg = aggregate(order, decision, delays, today=today)

            writer.writerow(agg.cleaned_row)
            # Newline-delimited JSON: one object per line, no array wrapper.
            action_f.write(json.dumps(agg.action_log_entry(order), ensure_ascii=False))
            action_f.write("\n")

            decisions_breakdown[agg.decision_label] += 1

    logger.info(
        "Cleaning complete: %d orders -> %s, %s",
        len(orders), cleaned_csv_path, action_log_path,
    )
    return CleaningSummary(
        processed=len(orders),
        cleaned_csv_path=cleaned_csv_path,
        action_log_path=action_log_path,
        decisions_breakdown=dict(decisions_breakdown),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cleaner",
        description="Clean a raw work-orders CSV by recovering structured signal from notes.",
    )
    parser.add_argument(
        "--input",
        default="data/work_orders_raw.csv",
        help="Path to the raw input CSV (default: data/work_orders_raw.csv).",
    )
    parser.add_argument(
        "--output-dir",
        default="out",
        help="Directory for output files (default: out).",
    )
    parser.add_argument(
        "--delay-csv",
        default="data/bt_real_data/delay_data.csv",
        help="Path to the BT delay history CSV used by Skill E (optional).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    delay_csv = Path(args.delay_csv) if args.delay_csv else None

    try:
        summary = run_cleaning(Path(args.input), Path(args.output_dir), delay_csv)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1

    print(f"Processed {summary.processed} orders")
    print(f"  Cleaned CSV : {summary.cleaned_csv_path}")
    print(f"  Action log  : {summary.action_log_path}")
    print("Decision breakdown:")
    for label, count in sorted(summary.decisions_breakdown.items()):
        print(f"  {label}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

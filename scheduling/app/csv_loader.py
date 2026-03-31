"""Load and validate work orders from CSV."""

from __future__ import annotations

import csv
import logging
from datetime import date
from pathlib import Path

from app.models import WorkOrder

logger = logging.getLogger(__name__)


def _parse_bool(value: str) -> bool:
    """Parse a boolean value from CSV text."""
    return value.strip().lower() in ("true", "1", "yes")


def _parse_date(value: str) -> date:
    """Parse an ISO-format date string."""
    return date.fromisoformat(value.strip())


def load_work_orders(csv_path: str | Path) -> list[WorkOrder]:
    """Load work orders from a CSV file.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of validated WorkOrder objects. Invalid rows are logged and skipped.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    orders: list[WorkOrder] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):  # row 1 is header
            try:
                order = WorkOrder(
                    order_id=row["order_id"].strip(),
                    order_source=row["order_source"].strip(),
                    service_type=row["service_type"].strip(),
                    job_type=row["job_type"].strip(),
                    requested_start_date=_parse_date(row["requested_start_date"]),
                    requested_end_date=_parse_date(row["requested_end_date"]),
                    committed_delivery_date=_parse_date(row["committed_delivery_date"]),
                    postcode=row["postcode"].strip(),
                    customer_ready_status=row["customer_ready_status"].strip(),
                    access_issue_flag=_parse_bool(row["access_issue_flag"]),
                    customer_delay_flag=_parse_bool(row["customer_delay_flag"]),
                    driveway_surface_hint=row.get("driveway_surface_hint", "").strip(),
                    photo_provided_flag=_parse_bool(row["photo_provided_flag"]),
                    dog_on_site_flag=_parse_bool(row["dog_on_site_flag"]),
                    exchange_visit_flag=_parse_bool(row["exchange_visit_flag"]),
                    heavy_ppe_hint=row.get("heavy_ppe_hint", "").strip(),
                    unstructured_customer_notes=row.get("unstructured_customer_notes", "").strip(),
                )
                orders.append(order)
                logger.debug("Loaded work order %s", order.order_id)
            except Exception as exc:
                logger.warning("Skipping invalid row %d: %s", row_num, exc)

    logger.info("Loaded %d work orders from %s", len(orders), csv_path)
    return orders

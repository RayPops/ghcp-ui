"""End-to-end orchestrator: order_id (or decision) -> PSO Activity.

This module wires the per-step components (loader, orchestrator, geocoder,
translator, client) together so callers (CLI, MCP tool) only have to hand
us an order id.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import httpx

from app.csv_loader import load_work_orders
from app.models import SchedulingDecision, WorkOrder
from app.orchestrator import process_work_order

from .client import PsoClient
from .geocoder import Geocoder
from .translator import build_pso_inputs, render_add_tasks_xml

logger = logging.getLogger(__name__)


@dataclass
class PsoPushResult:
    """Outcome of a push attempt. Always populated, even on failure."""

    order_id: str
    success: bool
    http_status: Optional[int] = None
    pso_response_body: str = ""
    xml_sent: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _load_order(order_id: str, csv_path: Path) -> WorkOrder:
    orders = load_work_orders(csv_path)
    for order in orders:
        if order.order_id == order_id:
            return order
    raise ValueError(f"Order {order_id!r} not found in {csv_path}")


def _default_geocoder() -> Geocoder:
    """Lazy import so test environments don't need pgeocode installed."""
    from .pgeocode_geocoder import PgeocodeGeocoder

    return PgeocodeGeocoder()


def push_order_to_pso(
    order_id: str,
    *,
    csv_path: Path,
    decision: Optional[SchedulingDecision] = None,
    order: Optional[WorkOrder] = None,
    geocoder: Optional[Geocoder] = None,
    client: Optional[PsoClient] = None,
) -> PsoPushResult:
    """Run the full push pipeline for a single order.

    Parameters
    ----------
    order_id:
        The work order identifier (matches ``WorkOrder.order_id``).
    csv_path:
        Path to ``work_orders.csv``. Used when ``order`` is not supplied.
    decision:
        Optional pre-computed decision. If omitted, ``process_work_order``
        is run on the fly.
    order:
        Optional pre-loaded :class:`WorkOrder`. If omitted, loaded from CSV.
    geocoder:
        Optional :class:`Geocoder` implementation. Defaults to
        :class:`PgeocodeGeocoder`.
    client:
        Optional :class:`PsoClient`. Defaults to one built from env vars.
    """
    # 1. Order
    if order is None:
        try:
            order = _load_order(order_id, csv_path)
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Failed to load order %s: %s", order_id, exc)
            return PsoPushResult(
                order_id=order_id, success=False, error=f"order_lookup_failed: {exc}"
            )

    # 2. Decision
    if decision is None:
        decision = process_work_order(order)

    # 3. Geocode
    geo = geocoder or _default_geocoder()
    try:
        coordinates = geo.lookup(order.postcode)
    except ValueError as exc:
        logger.error("Geocoding failed for %s: %s", order_id, exc)
        return PsoPushResult(
            order_id=order_id, success=False, error=f"geocoding_failed: {exc}"
        )

    # 4. Translate to XML
    inputs = build_pso_inputs(decision, order, coordinates)
    xml_body = render_add_tasks_xml(inputs)

    # 5. POST
    if client is None:
        from .client import PsoConfig  # local import keeps env var read lazy

        try:
            config = PsoConfig.from_env()
        except RuntimeError as exc:
            logger.error("PSO config missing: %s", exc)
            return PsoPushResult(
                order_id=order_id,
                success=False,
                xml_sent=xml_body,
                error=f"config_missing: {exc}",
            )
        client = PsoClient(config)

    try:
        response = client.add_tasks(xml_body)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "PSO rejected push for %s: status=%s", order_id, exc.response.status_code
        )
        return PsoPushResult(
            order_id=order_id,
            success=False,
            http_status=exc.response.status_code,
            pso_response_body=exc.response.text,
            xml_sent=xml_body,
            error=f"pso_http_error: {exc.response.status_code}",
        )
    except httpx.HTTPError as exc:
        # Network-level error (timeout, DNS, etc.).
        logger.error("PSO request failed for %s: %s", order_id, exc)
        return PsoPushResult(
            order_id=order_id,
            success=False,
            xml_sent=xml_body,
            error=f"pso_request_error: {exc}",
        )

    return PsoPushResult(
        order_id=order_id,
        success=True,
        http_status=response.status_code,
        pso_response_body=response.body,
        xml_sent=xml_body,
    )

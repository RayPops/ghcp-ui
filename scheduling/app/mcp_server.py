"""MCP server exposing scheduling skills as tools for ghcp-ui integration.

Run with: python -m app.mcp_server
Exposes tools via HTTP+SSE on port 3002 (configurable via MCP_PORT env var).
"""

from __future__ import annotations

import json
import os
import logging
import sys
from datetime import date
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.csv_loader import load_work_orders
from app.models import WorkOrder
from app.skills.extract_constraints import extract_scheduling_constraints
from app.skills.assess_date_risk import assess_delivery_date_risk
from app.skills.assess_visit_readiness import assess_visit_readiness
from app.skills.assess_safety import assess_safety_and_feasibility
from app.orchestrator import process_work_order
from app.render import render_decision_markdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s - %(message)s")
logger = logging.getLogger(__name__)

_mcp_port = int(os.environ.get("MCP_PORT", "3002"))

mcp = FastMCP(
    "BT Openreach Scheduling Copilot",
    instructions="Scheduling decision intelligence for BT Openreach field engineer visits",
    host="0.0.0.0",
    port=_mcp_port,
)

# Cache loaded work orders
_orders_cache: dict[str, WorkOrder] = {}
_csv_path = os.environ.get("SCHEDULING_CSV_PATH", "data/work_orders.csv")


def _ensure_loaded() -> dict[str, WorkOrder]:
    """Load work orders on first access."""
    if not _orders_cache:
        path = Path(_csv_path)
        if not path.is_absolute():
            # Resolve relative to the scheduling directory
            scheduling_dir = Path(__file__).parent.parent
            path = scheduling_dir / path
        orders = load_work_orders(path)
        for o in orders:
            _orders_cache[o.order_id] = o
    return _orders_cache


def _order_to_dict(order: WorkOrder) -> dict:
    """Convert a WorkOrder to a JSON-friendly dict."""
    return {
        "order_id": order.order_id,
        "order_source": order.order_source,
        "service_type": order.service_type,
        "job_type": order.job_type,
        "requested_start_date": order.requested_start_date.isoformat(),
        "requested_end_date": order.requested_end_date.isoformat(),
        "committed_delivery_date": order.committed_delivery_date.isoformat(),
        "postcode": order.postcode,
        "customer_ready_status": order.customer_ready_status,
        "access_issue_flag": order.access_issue_flag,
        "customer_delay_flag": order.customer_delay_flag,
        "driveway_surface_hint": order.driveway_surface_hint,
        "photo_provided_flag": order.photo_provided_flag,
        "dog_on_site_flag": order.dog_on_site_flag,
        "exchange_visit_flag": order.exchange_visit_flag,
        "heavy_ppe_hint": order.heavy_ppe_hint,
        "unstructured_customer_notes": order.unstructured_customer_notes,
    }


@mcp.tool()
def list_work_orders() -> str:
    """List all work orders from the CSV data file.

    Returns a JSON array of work order summaries with order_id, service_type,
    job_type, committed_delivery_date, and customer_ready_status.
    """
    orders = _ensure_loaded()
    summaries = []
    for o in orders.values():
        summaries.append({
            "order_id": o.order_id,
            "order_source": o.order_source,
            "service_type": o.service_type,
            "job_type": o.job_type,
            "committed_delivery_date": o.committed_delivery_date.isoformat(),
            "customer_ready_status": o.customer_ready_status,
            "postcode": o.postcode,
        })
    return json.dumps(summaries, indent=2)


@mcp.tool()
def get_work_order(order_id: str) -> str:
    """Get full details for a specific work order.

    Args:
        order_id: The work order identifier (e.g., "WO-001").

    Returns a JSON object with all work order fields.
    """
    orders = _ensure_loaded()
    order = orders.get(order_id)
    if not order:
        return json.dumps({"error": f"Work order {order_id} not found"})
    return json.dumps(_order_to_dict(order), indent=2)


@mcp.tool()
def extract_constraints_tool(order_id: str) -> str:
    """Extract scheduling constraints from a work order's unstructured notes.

    Parses customer notes to find hidden scheduling constraints such as:
    - Earliest allowed visit date
    - Customer availability windows (mornings, afternoons, weekdays)
    - Special instructions (access codes, contact details, restrictions)

    Args:
        order_id: The work order identifier.

    Returns JSON with extracted constraints.
    """
    orders = _ensure_loaded()
    order = orders.get(order_id)
    if not order:
        return json.dumps({"error": f"Work order {order_id} not found"})

    result = extract_scheduling_constraints(
        customer_notes=order.unstructured_customer_notes,
        requested_start_date=order.requested_start_date,
        requested_end_date=order.requested_end_date,
        committed_delivery_date=order.committed_delivery_date,
    )
    return json.dumps({
        "order_id": order_id,
        "earliest_allowed_date": result.earliest_allowed_date.isoformat() if result.earliest_allowed_date else None,
        "customer_availability_window": result.customer_availability_window,
        "special_instructions": result.special_instructions,
    }, indent=2)


@mcp.tool()
def assess_date_risk_tool(order_id: str) -> str:
    """Assess delivery date risk for a work order.

    Evaluates whether the committed delivery date needs to change based on:
    - Customer availability conflicts
    - Access issues
    - Customer delay requests
    - Product-specific delay rules (Ethernet allows more flexibility)

    Args:
        order_id: The work order identifier.

    Returns JSON with date risk assessment and recommendation.
    """
    orders = _ensure_loaded()
    order = orders.get(order_id)
    if not order:
        return json.dumps({"error": f"Work order {order_id} not found"})

    constraints = extract_scheduling_constraints(
        customer_notes=order.unstructured_customer_notes,
        requested_start_date=order.requested_start_date,
        requested_end_date=order.requested_end_date,
        committed_delivery_date=order.committed_delivery_date,
    )

    result = assess_delivery_date_risk(
        order_source=order.order_source,
        committed_delivery_date=order.committed_delivery_date,
        requested_start_date=order.requested_start_date,
        requested_end_date=order.requested_end_date,
        access_issue_flag=order.access_issue_flag,
        customer_delay_flag=order.customer_delay_flag,
        customer_ready_status=order.customer_ready_status,
        constraints=constraints,
    )
    return json.dumps({
        "order_id": order_id,
        "date_change_recommended": result.date_change_recommended,
        "reason_code": result.reason_code,
        "revised_delivery_date": result.revised_delivery_date.isoformat() if result.revised_delivery_date else None,
        "explanation": result.explanation,
    }, indent=2)


@mcp.tool()
def assess_readiness_tool(order_id: str) -> str:
    """Assess visit readiness for a work order.

    Determines what tools, materials, and time are needed based on:
    - Service type and job type
    - Driveway surface conditions
    - Site photo availability
    - Information in customer notes

    Args:
        order_id: The work order identifier.

    Returns JSON with tools, materials, estimated duration, and confidence level.
    """
    orders = _ensure_loaded()
    order = orders.get(order_id)
    if not order:
        return json.dumps({"error": f"Work order {order_id} not found"})

    result = assess_visit_readiness(
        service_type=order.service_type,
        job_type=order.job_type,
        driveway_surface_hint=order.driveway_surface_hint,
        photo_provided_flag=order.photo_provided_flag,
        customer_notes=order.unstructured_customer_notes,
    )
    return json.dumps({
        "order_id": order_id,
        "required_tools": result.required_tools,
        "required_materials": result.required_materials,
        "estimated_duration_minutes": result.estimated_duration_minutes,
        "confidence": result.confidence,
        "explanation": result.explanation,
    }, indent=2)


@mcp.tool()
def assess_safety_tool(order_id: str) -> str:
    """Assess safety and feasibility for a work order.

    Evaluates safety requirements based on:
    - Dog on site flag
    - Heavy PPE requirements
    - Exchange visit requirements
    - Hazards mentioned in customer notes

    Args:
        order_id: The work order identifier.

    Returns JSON with safety equipment, risks, and extra engineer requirements.
    """
    orders = _ensure_loaded()
    order = orders.get(order_id)
    if not order:
        return json.dumps({"error": f"Work order {order_id} not found"})

    result = assess_safety_and_feasibility(
        dog_on_site_flag=order.dog_on_site_flag,
        heavy_ppe_hint=order.heavy_ppe_hint,
        exchange_visit_flag=order.exchange_visit_flag,
        customer_notes=order.unstructured_customer_notes,
    )
    return json.dumps({
        "order_id": order_id,
        "safety_equipment": result.safety_equipment,
        "extra_engineer_required": result.extra_engineer_required,
        "safety_risks": result.safety_risks,
        "explanation": result.explanation,
    }, indent=2)


@mcp.tool()
def compose_scheduling_decision(order_id: str) -> str:
    """Run the full scheduling analysis pipeline for a work order.

    Calls all four skills in sequence:
    1. Extract scheduling constraints from notes
    2. Assess delivery date risk
    3. Assess visit readiness (tools, materials, duration)
    4. Assess safety and feasibility

    Then composes a final scheduling decision with a recommended action.

    Args:
        order_id: The work order identifier.

    Returns JSON with the complete scheduling decision including recommended action,
    planned visit date, required equipment, safety assessment, and rationale.
    """
    orders = _ensure_loaded()
    order = orders.get(order_id)
    if not order:
        return json.dumps({"error": f"Work order {order_id} not found"})

    decision = process_work_order(order)
    result = decision.to_dict()

    # Also include the markdown summary
    result["markdown_summary"] = render_decision_markdown(decision)

    return json.dumps(result, indent=2)


if __name__ == "__main__":
    logger.info("Starting MCP server on port %d", _mcp_port)
    mcp.run(transport="sse")

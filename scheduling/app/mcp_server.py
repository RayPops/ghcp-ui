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
from app.skills.lookup_delay_history import lookup_delay_history
from app.orchestrator import process_work_order
from app.render import render_decision_markdown
from app.integrations.pso.push import push_order_to_pso
from app.cleaner import run_cleaning

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
_delay_csv_path = os.environ.get("DELAY_CSV_PATH", "data/bt_real_data/delay_data.csv")


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


@mcp.tool()
def lookup_delay_history_tool(order_id: str) -> str:
    """Look up the delay history for a work order from BT Openreach delay records.

    Queries historical delay data to find:
    - How many times this order has been delayed
    - Whether delays are ongoing or resolved
    - The reasons for delays (wayleave, access, CP information, civils, etc.)
    - CCD (Customer Committed Date) impact in days
    - Detailed delay summaries with dates

    This is useful for understanding why an order may be at risk and whether
    it has a pattern of delays that could affect future scheduling.

    Args:
        order_id: The work order / project identifier (e.g., "ONEA92160383").

    Returns JSON with delay history summary and individual delay records.
    """
    scheduling_dir = Path(__file__).parent.parent
    delay_path = Path(_delay_csv_path)
    if not delay_path.is_absolute():
        delay_path = scheduling_dir / delay_path

    result = lookup_delay_history(order_id, delay_path)

    records_out = []
    for rec in result.records:
        records_out.append({
            "task_name": rec.task_name,
            "holding_reason": rec.holding_reason,
            "delay_start_date": rec.delay_start_date,
            "delay_end_date": rec.delay_end_date,
            "status": rec.status,
            "delay_type": rec.delay_type,
            "delay_summary": rec.delay_summary,
            "ccd_impact_days": rec.ccd_impact_days,
        })

    return json.dumps({
        "order_id": order_id,
        "total_delays": result.total_delays,
        "ongoing_delays": result.ongoing_delays,
        "resolved_delays": result.resolved_delays,
        "delay_types": result.delay_types,
        "top_reasons": result.top_reasons,
        "records": records_out,
        "explanation": result.explanation,
    }, indent=2)


@mcp.tool()
def push_to_pso_tool(order_id: str) -> str:
    """Push a scheduling decision for a work order into IFS PSO as a new Activity.

    Runs the full pipeline:
    1. Loads the work order from the CSV.
    2. Runs ``compose_scheduling_decision`` to get a fresh decision.
    3. Geocodes the postcode (UK outward-code accuracy).
    4. Translates the decision into a PSO ``07 - Add Tasks`` XML payload.
    5. POSTs the payload to PSO using credentials from PSO_URL / PSO_USER / PSO_PWD.

    The chat path always runs live (no dry-run). On failure the returned JSON has
    ``success=false`` and an ``error`` field; surface that verbatim and stop.

    Args:
        order_id: The work order identifier (e.g. "ONEA92160383").

    Returns JSON with: order_id, success, http_status, pso_response_body,
    xml_sent (the full XML for audit), error (only when success=false).
    """
    csv_path = Path(_csv_path)
    if not csv_path.is_absolute():
        csv_path = Path(__file__).parent.parent / csv_path

    result = push_order_to_pso(order_id, csv_path=csv_path)
    return json.dumps(result.to_dict(), indent=2)


@mcp.tool()
def clean_work_orders_tool(
    input_csv_path: str = "data/work_orders_raw.csv",
    output_dir: str = "out",
) -> str:
    """Clean a raw work-orders CSV by recovering structured signal from notes.

    Runs the same Skills A + B + C + D pipeline used by
    ``compose_scheduling_decision`` over every row in the raw CSV, then maps
    the results back into the cleaned 17-column shape and writes a per-order
    action log explaining what was recovered and why.

    Args:
        input_csv_path: Path to the raw input CSV (default: data/work_orders_raw.csv).
        output_dir: Directory for output files (default: out).

    Returns JSON with: processed (int), cleaned_csv (path), action_log (path),
    decisions (mapping of decision label -> count).
    """
    scheduling_dir = Path(__file__).parent.parent
    in_path = Path(input_csv_path)
    if not in_path.is_absolute():
        in_path = scheduling_dir / in_path
    out_path = Path(output_dir)
    if not out_path.is_absolute():
        out_path = scheduling_dir / out_path

    delay_path = Path(_delay_csv_path)
    if not delay_path.is_absolute():
        delay_path = scheduling_dir / delay_path

    summary = run_cleaning(in_path, out_path, delay_path if delay_path.exists() else None)
    return json.dumps({
        "processed": summary.processed,
        "cleaned_csv": str(summary.cleaned_csv_path),
        "action_log": str(summary.action_log_path),
        "decisions": summary.decisions_breakdown,
    }, indent=2)


if __name__ == "__main__":
    logger.info("Starting MCP server on port %d", _mcp_port)
    mcp.run(transport="sse")

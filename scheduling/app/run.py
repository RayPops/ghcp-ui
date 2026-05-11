"""CLI entrypoint for the BT Openreach Scheduling Copilot."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.csv_loader import load_work_orders
from app.integrations.pso.push import push_order_to_pso
from app.orchestrator import process_all
from app.render import render_decision_markdown


def _run_push_to_pso(order_id: str, csv_path: Path, *, live: bool, logger: logging.Logger) -> int:
    """Run the single-order PSO push pipeline.

    Defaults to dry-run: build and print the XML, but do not POST.
    Pass ``live=True`` to actually fire the request to PSO.
    """
    if live:
        result = push_order_to_pso(order_id, csv_path=csv_path)
    else:
        result = _dry_run_push(order_id, csv_path)

    print("--- PSO XML payload ---")
    print(result.xml_sent or "(no payload generated; pipeline failed before render)")
    print("--- end payload ---\n")

    if not live:
        if result.error:
            print(f"\u274c dry-run failed: {result.error}")
            return 1
        print("\u2705 dry-run OK \u2014 rerun with --live to POST to PSO")
        return 0

    print(f"PSO HTTP status: {result.http_status}")
    print("--- PSO response body ---")
    print(result.pso_response_body or "(empty)")
    print("--- end response ---\n")

    if result.success:
        print(f"\u2705 pushed {order_id} to PSO")
        return 0

    print(f"\u274c failed: {result.error}")
    return 1


def _dry_run_push(order_id: str, csv_path: Path):
    """Build the XML without instantiating a live PsoClient.

    Mirrors :func:`push_order_to_pso` up to (but not including) the POST.
    Returns the same :class:`PsoPushResult` shape so the caller can format
    the result uniformly.
    """
    from app.integrations.pso.push import PsoPushResult, _default_geocoder, _load_order
    from app.integrations.pso.translator import build_pso_inputs, render_add_tasks_xml
    from app.orchestrator import process_work_order

    try:
        order = _load_order(order_id, csv_path)
    except (FileNotFoundError, ValueError) as exc:
        return PsoPushResult(
            order_id=order_id, success=False, error=f"order_lookup_failed: {exc}"
        )

    decision = process_work_order(order)

    try:
        coordinates = _default_geocoder().lookup(order.postcode)
    except ValueError as exc:
        return PsoPushResult(
            order_id=order_id, success=False, error=f"geocoding_failed: {exc}"
        )

    inputs = build_pso_inputs(decision, order, coordinates)
    xml_body = render_add_tasks_xml(inputs)
    return PsoPushResult(order_id=order_id, success=True, xml_sent=xml_body)


def main(argv: list[str] | None = None) -> int:
    """Run the scheduling copilot on a CSV file of work orders.

    Args:
        argv: Command line arguments. Defaults to sys.argv[1:].

    Returns:
        Exit code (0 for success).
    """
    parser = argparse.ArgumentParser(
        prog="scheduling-copilot",
        description="BT Openreach Scheduling Copilot - analyse work orders and recommend scheduling decisions",
    )
    parser.add_argument(
        "--csv",
        default="data/work_orders.csv",
        help="Path to the work orders CSV file (default: data/work_orders.csv)",
    )
    parser.add_argument(
        "--out",
        default="out",
        help="Output directory (default: out)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--push-to-pso",
        metavar="ORDER_ID",
        help="Push a single order to IFS PSO instead of running the batch. "
             "Defaults to dry-run (prints the XML, does not POST).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Used with --push-to-pso. Actually POST to PSO instead of dry-run.",
    )
    parser.add_argument(
        "--generate-raw",
        action="store_true",
        help="Generate data/work_orders_raw.csv from the cleaned source. "
             "Use --raw-output and --seed to customise.",
    )
    parser.add_argument(
        "--raw-output",
        default="data/work_orders_raw.csv",
        help="Where --generate-raw writes the raw CSV (default: data/work_orders_raw.csv).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic seed for --generate-raw (default: 42).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Run the cleaning pipeline: raw CSV -> cleaned CSV + agent_actions.jsonl. "
             "Reads --clean-input, writes into --out.",
    )
    parser.add_argument(
        "--clean-input",
        default="data/work_orders_raw.csv",
        help="Raw CSV consumed by --clean (default: data/work_orders_raw.csv).",
    )
    parser.add_argument(
        "--delay-csv",
        default="data/bt_real_data/delay_data.csv",
        help="Optional Skill E delay history CSV used by --clean.",
    )

    args = parser.parse_args(argv)

    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("scheduling-copilot")

    csv_path = Path(args.csv)

    # Generate the raw CSV (pre-demo step).
    if args.generate_raw:
        from app.raw_generator import generate_raw_csv

        try:
            written = generate_raw_csv(csv_path, Path(args.raw_output), args.seed)
        except FileNotFoundError as exc:
            logger.error(str(exc))
            return 1
        print(f"Wrote {written} raw rows to {args.raw_output} (seed={args.seed})")
        return 0

    # Cleaning pipeline (raw CSV -> cleaned CSV + action log).
    if args.clean:
        from app.cleaner import run_cleaning

        try:
            summary = run_cleaning(
                Path(args.clean_input),
                Path(args.out),
                Path(args.delay_csv) if args.delay_csv else None,
            )
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

    # PSO push branch
    if args.push_to_pso:
        if not csv_path.exists():
            logger.error("CSV file not found: %s", csv_path)
            return 1
        return _run_push_to_pso(
            args.push_to_pso, csv_path, live=args.live, logger=logger
        )

    if args.live:
        logger.warning("--live has no effect without --push-to-pso")

    # Existing batch mode
    logger.info("Loading work orders from %s", csv_path)

    try:
        orders = load_work_orders(csv_path)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1

    if not orders:
        logger.error("No valid work orders found in %s", csv_path)
        return 1

    logger.info("Loaded %d work orders", len(orders))

    # Process all orders
    decisions = process_all(orders)
    logger.info("Processed %d decisions", len(decisions))

    # Write output
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_decisions: list[dict] = []

    for decision in decisions:
        decision_dict = decision.to_dict()
        all_decisions.append(decision_dict)

        # Write individual JSON
        json_path = out_dir / f"{decision.order_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(decision_dict, f, indent=2)
        logger.info("Wrote %s", json_path)

        # Write individual Markdown
        md_path = out_dir / f"{decision.order_id}.md"
        md_content = render_decision_markdown(decision)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info("Wrote %s", md_path)

    # Write combined decisions
    combined_path = out_dir / "decisions.json"
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_decisions, f, indent=2)
    logger.info("Wrote combined decisions to %s", combined_path)

    # Print summary
    action_counts: dict[str, int] = {}
    for d in decisions:
        action = d.recommended_action
        action_counts[action] = action_counts.get(action, 0) + 1

    print(f"\nProcessed {len(decisions)} work orders:")
    for action, count in sorted(action_counts.items()):
        print(f"  {action}: {count}")
    print(f"\nOutput written to {out_dir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())

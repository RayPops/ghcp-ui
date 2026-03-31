"""CLI entrypoint for the BT Openreach Scheduling Copilot."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.csv_loader import load_work_orders
from app.orchestrator import process_all
from app.render import render_decision_markdown


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
        required=True,
        help="Path to the work orders CSV file",
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

    args = parser.parse_args(argv)

    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("scheduling-copilot")

    # Load work orders
    csv_path = Path(args.csv)
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

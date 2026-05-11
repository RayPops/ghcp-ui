"""Generate a *raw* (pre-cleaning) work-orders CSV for the demo.

The cleaned ``data/work_orders.csv`` already has six structured flag columns
that, in the real Openreach world, a dispatcher would have to extract from
free-text notes themselves. This script goes backwards: it drops those six
columns and splices a short, dispatcher-style sentence carrying the same
signal into ``unstructured_customer_notes`` so the cleaning pipeline can
recover it.

Determinism: a single ``--seed`` (default 42) plus a per-order salt
(``hash(order_id)``) chooses the paraphrase template and the splice
position. Same seed + same input -> same output, byte for byte.

The original phrasing of the notes is preserved untouched so the existing
Skill A regex anchors keep firing on legitimate signal already present.
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Columns dropped from the raw CSV (the six the demo recovers from notes).
DROPPED_COLUMNS = (
    "customer_ready_status",
    "access_issue_flag",
    "customer_delay_flag",
    "dog_on_site_flag",
    "exchange_visit_flag",
    "heavy_ppe_hint",
)

# Column order preserved for the surviving columns. ``unstructured_customer_notes``
# stays last to match the cleaned CSV.
RAW_COLUMNS = (
    "order_id",
    "order_source",
    "service_type",
    "job_type",
    "requested_start_date",
    "requested_end_date",
    "committed_delivery_date",
    "postcode",
    "driveway_surface_hint",
    "photo_provided_flag",
    "unstructured_customer_notes",
)

# Paraphrase templates per dropped flag. Each list provides several phrasings
# so different orders don't all read identically. Phrases are written in the
# voice of an Openreach scheduler / engineer note, in British English, and use
# vocabulary that the existing skill regex matches.
_PARAPHRASES: dict[str, list[str]] = {
    "dog_on_site_flag.true": [
        "Customer mentioned a dog on site - please ring ahead so it can be secured.",
        "Note from CP: dogs at the property, must be secured before engineer attends.",
        "Site contact has a dog in the back garden; needs to be put away before access.",
    ],
    "exchange_visit_flag.true": [
        "Job involves a visit to the local exchange building - access key required.",
        "Engineer will need to attend the exchange as part of this circuit build.",
        "Exchange visit confirmed; sign-in required at the front desk.",
    ],
    "heavy_ppe_hint.confined space": [
        "Riser cupboard is a confined space - gas monitor needed.",
        "Work is in a basement plant room; treat as confined space working.",
        "Low-ceiling crawl run noted - confined space PPE required.",
    ],
    "heavy_ppe_hint.overhead work": [
        "Engineer reports overhead pole work required to complete this circuit.",
        "Cable will be routed via the overhead pole at the kerbside; cherry picker pre-book.",
        "Working at height on the rear wall - overhead access kit needed.",
    ],
    "access_issue_flag.true": [
        "Wayleave still pending with the building owner - access blocked until signed.",
        "Permit not yet granted by local authority; access on hold.",
        "Site access denied at the last visit pending grantor approval.",
    ],
    "customer_delay_flag.true": [
        "CP has asked us not to book until they confirm next steps.",
        "Customer requested we hold the appointment - they are not ready to receive engineer.",
        "Hold this order at customer's request; do not book yet.",
    ],
    "customer_ready_status.not ready": [
        "Customer flagged as not ready - escort access still being arranged.",
        "Site contact confirmed building works incomplete; not ready for install.",
        "Civils and wayleave outstanding; customer not ready.",
    ],
    "customer_ready_status.ready": [
        "Customer confirmed ready and waiting for the engineer.",
        "All site prep complete per CP; ready to proceed.",
    ],
    # No paraphrase for "unknown" - that is the default state when nothing is said.
}


def _splice_into_notes(notes: str, sentences: list[str], rng: random.Random) -> str:
    """Insert each sentence at a deterministic position between ``||`` separators.

    The original notes already use ``||`` as a section break (see
    ``data/work_orders.csv``). We pick existing break positions when possible
    so the new sentence reads as a fresh dispatcher annotation rather than
    being shoved into the middle of someone else's paragraph.
    """
    if not sentences:
        return notes

    # Split, splice, rejoin. Each new sentence becomes its own ``|| ... ||``
    # section to read as a separate dispatcher note.
    segments = [seg.strip() for seg in notes.split("||")]
    for sentence in sentences:
        # Pick an insertion index inclusive of both ends.
        idx = rng.randint(0, len(segments))
        segments.insert(idx, sentence)
    return " || ".join(seg for seg in segments if seg)


def _paraphrases_for_row(row: dict[str, str]) -> list[str]:
    """Choose paraphrase keys based on the dropped-flag values in this row."""
    keys: list[str] = []

    if row.get("dog_on_site_flag", "").strip().lower() == "true":
        keys.append("dog_on_site_flag.true")

    if row.get("exchange_visit_flag", "").strip().lower() == "true":
        keys.append("exchange_visit_flag.true")

    hint = row.get("heavy_ppe_hint", "").strip().lower()
    if hint == "confined space":
        keys.append("heavy_ppe_hint.confined space")
    elif hint == "overhead work":
        keys.append("heavy_ppe_hint.overhead work")

    if row.get("access_issue_flag", "").strip().lower() == "true":
        keys.append("access_issue_flag.true")

    if row.get("customer_delay_flag", "").strip().lower() == "true":
        keys.append("customer_delay_flag.true")

    status = row.get("customer_ready_status", "").strip().lower()
    if status == "not ready":
        keys.append("customer_ready_status.not ready")
    elif status == "ready":
        keys.append("customer_ready_status.ready")
    # "unknown" -> no paraphrase

    return keys


def generate_raw_row(row: dict[str, str], seed: int) -> dict[str, str]:
    """Build one raw-CSV row from one cleaned-CSV row.

    The RNG is seeded with ``seed + hash(order_id)`` so each row is independent
    and the whole file is reproducible.
    """
    order_id = row["order_id"]
    rng = random.Random(f"{seed}:{order_id}")

    notes = row.get("unstructured_customer_notes", "")
    sentences: list[str] = []
    for key in _paraphrases_for_row(row):
        choices = _PARAPHRASES.get(key, [])
        if choices:
            sentences.append(rng.choice(choices))

    new_notes = _splice_into_notes(notes, sentences, rng)

    return {col: (new_notes if col == "unstructured_customer_notes" else row.get(col, "")) for col in RAW_COLUMNS}


def generate_raw_csv(input_csv: Path, output_csv: Path, seed: int) -> int:
    """Read ``input_csv`` (cleaned shape) and write ``output_csv`` (raw shape).

    Returns the number of rows written.
    """
    if not input_csv.exists():
        raise FileNotFoundError(f"Cleaned CSV not found: {input_csv}")

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with (
        open(input_csv, newline="", encoding="utf-8") as in_f,
        open(output_csv, "w", newline="", encoding="utf-8") as out_f,
    ):
        reader = csv.DictReader(in_f)
        writer = csv.DictWriter(out_f, fieldnames=list(RAW_COLUMNS))
        writer.writeheader()
        for row in reader:
            writer.writerow(generate_raw_row(row, seed))
            written += 1

    logger.info("Wrote %d raw rows to %s", written, output_csv)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="raw_generator",
        description="Generate the raw (pre-cleaning) work-orders CSV from the cleaned source.",
    )
    parser.add_argument(
        "--input",
        default="data/work_orders.csv",
        help="Path to the cleaned source CSV (default: data/work_orders.csv).",
    )
    parser.add_argument(
        "--output",
        default="data/work_orders_raw.csv",
        help="Path for the generated raw CSV (default: data/work_orders_raw.csv).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42).")
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

    try:
        written = generate_raw_csv(Path(args.input), Path(args.output), args.seed)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1

    print(f"Wrote {written} raw rows to {args.output} (seed={args.seed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

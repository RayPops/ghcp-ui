---
name: extract-scheduling-constraints
description: >
  Extracts hidden scheduling constraints from unstructured customer notes.
  Identifies earliest allowed dates, customer availability windows, and
  special instructions that are buried in free text.
---

# Extract Scheduling Constraints

## Purpose

Field scheduling systems often contain critical constraints in unstructured notes
rather than structured fields. This skill parses free text customer notes to
extract actionable scheduling information.

## When to Use

Call this skill when you have a work order with `unstructured_customer_notes`
and need to understand what scheduling constraints exist before making a
scheduling decision.

## Inputs

| Field | Type | Description |
|-------|------|-------------|
| `customer_notes` | string | Free text notes from customer or agent |
| `requested_start_date` | date (ISO format) | Start of customer requested window |
| `requested_end_date` | date (ISO format) | End of customer requested window |
| `committed_delivery_date` | date (ISO format) | Contractual delivery date |

## Outputs

Returns a JSON object:

```json
{
  "earliest_allowed_date": "2026-04-10",
  "customer_availability_window": "afternoons only",
  "special_instructions": [
    "use rear access gate code 4821",
    "call daughter on 07700 112233 when on way"
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `earliest_allowed_date` | date or null | Earliest date the customer allows a visit |
| `customer_availability_window` | string | Time of day / day of week preference |
| `special_instructions` | string[] | Access codes, contact details, restrictions |

## Extraction Rules

- "do not attend before X" sets `earliest_allowed_date`
- "holiday until X" / "away until X" sets `earliest_allowed_date`
- "only available mornings/afternoons" sets `customer_availability_window`
- "prefers afternoon" / "after 2pm" sets `customer_availability_window`
- Gate codes, contact numbers, access instructions go to `special_instructions`
- "do not book until customer confirms" sets a far-future earliest date to force review

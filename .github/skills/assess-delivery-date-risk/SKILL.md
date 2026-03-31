---
name: assess-delivery-date-risk
description: >
  Evaluates whether a committed delivery date needs to change based on
  access issues, customer delays, availability conflicts, and product-specific
  delay rules. Ethernet orders allow more date movement than Home Broadband.
---

# Assess Delivery Date Risk

## Purpose

Committed delivery dates have contractual implications. This skill determines
whether a date change is needed and calculates a revised date within allowed
product rules.

## When to Use

Call this skill after extracting scheduling constraints (Skill A). It uses the
constraint output plus work order flags to assess date risk.

## Inputs

| Field | Type | Description |
|-------|------|-------------|
| `order_source` | string | "Ethernet" or "Home Broadband" |
| `committed_delivery_date` | date | Current contractual delivery date |
| `requested_start_date` | date | Start of customer requested window |
| `requested_end_date` | date | End of customer requested window |
| `access_issue_flag` | boolean | Known access problem |
| `customer_delay_flag` | boolean | Customer requested delay |
| `customer_ready_status` | string | "ready", "not ready", or "unknown" |
| `constraints` | object | Output from extract-scheduling-constraints |

## Outputs

Returns a JSON object:

```json
{
  "date_change_recommended": true,
  "reason_code": "customer_availability_conflict",
  "revised_delivery_date": "2026-04-10",
  "explanation": "Customer is not available until 10th April..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `date_change_recommended` | boolean | Whether the date should change |
| `reason_code` | string | Machine-readable reason |
| `revised_delivery_date` | date or null | New suggested date |
| `explanation` | string | Human-readable explanation |

## Reason Codes

- `no_change_needed` - Current date is fine
- `customer_availability_conflict` - Customer not available on committed date
- `customer_requested_delay` - Customer explicitly asked for delay
- `access_issue` - Access problem requires extra time
- `customer_not_ready` - Customer marked as not ready
- `delay_exceeds_allowed_window` - Delay too large, needs human review

## Delay Rules

- **Ethernet orders**: Up to 10 working days of date movement allowed
- **Home Broadband orders**: Up to 3 days of date movement allowed
- Revised dates always land on a working day (Monday to Friday)

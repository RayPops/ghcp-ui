# BT Openreach Scheduling Copilot - Requirements

## Problem Statement

BT Openreach manages thousands of engineer field visits daily for broadband and Ethernet installations. Missed appointments carry financial penalties, customer dissatisfaction, and wasted engineer time. Root causes include:

- **Poor data quality**: scheduling constraints are buried in unstructured customer notes rather than structured fields
- **Rigid delivery dates**: committed delivery dates follow complex movement rules (especially for Ethernet orders) that schedulers must apply manually
- **Incomplete preparation**: engineers arrive on-site without the right tools, materials, or safety equipment
- **Safety gaps**: hazards like dogs on site, confined spaces, or heavy equipment requirements are missed until the engineer is at the door

This demo shows how a scheduling copilot can extract, assess, and structure this information before a human scheduler makes the final call.

## In Scope

- Parse unstructured customer notes to extract scheduling constraints
- Apply simplified delivery date movement rules (inspired by Ethernet delay logic)
- Predict visit readiness: tools, materials, estimated duration
- Flag safety constraints and extra engineer requirements
- Output structured JSON decisions and readable Markdown summaries
- Local CSV as the only data source (no databases, no external systems)
- CLI batch processing mode
- MCP server integration with ghcp-ui chat interface

## Out of Scope

- Real customer data or PII
- Live integration with Openreach scheduling systems (Siebel, GPON, etc.)
- Route optimisation or geographic clustering
- Engineer skill matching or availability calendars
- SLA calculation or penalty costing
- Authentication or multi-tenancy

## User Stories

1. **As a scheduler**, I want the system to extract hidden constraints from customer notes so I do not miss availability windows.
2. **As a scheduler**, I want to know if a committed delivery date should be moved, and why, so I can act before a breach occurs.
3. **As a field engineer**, I want a pre-visit checklist of tools, materials, and safety equipment so I arrive prepared.
4. **As a team leader**, I want safety risks flagged before dispatch so I can assign the right team and equipment.
5. **As a planning manager**, I want structured decision outputs per job so I can feed them into downstream scheduling tools.
6. **As a scheduler**, I want a clear recommended action (schedule, reschedule, or needs human review) with a rationale so I can make fast, confident decisions.
7. **As a demo presenter**, I want realistic messy data so the audience sees how the system handles real-world ambiguity.

## Functional Requirements

| ID | Requirement | Acceptance Criteria |
|----|------------|---------------------|
| FR-01 | System shall load work orders from a CSV file | CSV with 10-15 rows loads without error; invalid rows are logged and skipped |
| FR-02 | System shall extract scheduling constraints from unstructured notes | Given notes containing "only available after 3pm", output includes `customer_availability_window` |
| FR-03 | System shall detect earliest allowed dates from notes | Given "do not attend before 15th March", output includes `earliest_allowed_date` |
| FR-04 | System shall assess delivery date movement risk | Given an Ethernet order with access issues, output recommends reschedule with reason |
| FR-05 | System shall apply product-specific delay rules | Ethernet orders allow date movement; Home Broadband orders are more constrained |
| FR-06 | System shall predict required tools and materials | Given job type "new line installation" and driveway hint "gravel", output includes relevant tools |
| FR-07 | System shall estimate visit duration | Output includes `estimated_duration_minutes` between 30 and 480 |
| FR-08 | System shall flag safety risks | Given `dog_on_site_flag=true`, output includes "dog on site" in safety risks |
| FR-09 | System shall determine if extra engineer is required | Given heavy equipment or confined space, output sets `extra_engineer_required=true` |
| FR-10 | System shall produce a recommended action per job | Output is one of: "schedule", "reschedule", "needs-human-review" |
| FR-11 | System shall write JSON output per job | Each job produces `out/<order_id>.json` |
| FR-12 | System shall write Markdown summary per job | Each job produces `out/<order_id>.md` |
| FR-13 | System shall write combined decisions file | `out/decisions.json` contains all job decisions |

## Non-Functional Requirements

| ID | Requirement |
|----|------------|
| NFR-01 | All skill functions must be deterministic given the same input |
| NFR-02 | Processing 15 work orders must complete in under 5 seconds (excluding LLM calls) |
| NFR-03 | All functions must include type hints and docstrings |
| NFR-04 | Logging must use Python `logging` module at INFO level by default |
| NFR-05 | No secrets or API keys in source code |
| NFR-06 | No em dashes in any text output |
| NFR-07 | Output text must use plain English, no abbreviations |
| NFR-08 | MCP server must expose tools via HTTP/SSE on a configurable port |

## Data Contract: CSV Schema

| Column | Type | Required | Description | Example Values |
|--------|------|----------|-------------|----------------|
| `order_id` | string | yes | Unique work order identifier | "WO-001" |
| `order_source` | string | yes | Originating system | "Home Broadband", "Ethernet" |
| `service_type` | string | yes | Service being delivered | "FTTP Installation", "Ethernet Bearer", "Broadband Repair" |
| `job_type` | string | yes | Type of work | "new line installation", "repair", "provision", "cease" |
| `requested_start_date` | date (YYYY-MM-DD) | yes | Start of customer requested window | "2026-04-01" |
| `requested_end_date` | date (YYYY-MM-DD) | yes | End of customer requested window | "2026-04-05" |
| `committed_delivery_date` | date (YYYY-MM-DD) | yes | Contractual delivery date | "2026-04-03" |
| `postcode` | string | yes | Site postcode | "B1 1BB" |
| `customer_ready_status` | string | yes | Whether customer is ready | "ready", "not ready", "unknown" |
| `access_issue_flag` | boolean | yes | Known access problems | true, false |
| `customer_delay_flag` | boolean | yes | Customer requested delay | true, false |
| `driveway_surface_hint` | string | no | Surface type at property | "tarmac", "gravel", "block paving", "" |
| `photo_provided_flag` | boolean | yes | Customer provided site photo | true, false |
| `dog_on_site_flag` | boolean | yes | Dog reported at property | true, false |
| `exchange_visit_flag` | boolean | yes | Visit to telephone exchange needed | true, false |
| `heavy_ppe_hint` | string | no | Heavy PPE requirement hints | "confined space", "overhead work", "" |
| `unstructured_customer_notes` | string | no | Free text notes from customer/agent | See examples below |

## Output Contract: JSON Schema

Each job produces a `SchedulingDecision` object:

```json
{
  "order_id": "WO-001",
  "recommended_action": "reschedule",
  "planned_visit_date": "2026-04-07",
  "constraints": {
    "earliest_allowed_date": "2026-04-05",
    "customer_availability_window": "afternoons only",
    "special_instructions": ["use rear access gate"]
  },
  "delivery_date_assessment": {
    "date_change_recommended": true,
    "reason_code": "customer_availability_conflict",
    "revised_delivery_date": "2026-04-07",
    "explanation": "Customer notes indicate availability only after 5th April. Current committed date of 3rd April conflicts."
  },
  "visit_readiness": {
    "required_tools": ["fibre splicer", "cable rod set"],
    "required_materials": ["fibre patch lead", "wall box"],
    "estimated_duration_minutes": 120,
    "confidence": "medium",
    "explanation": "New FTTP installation on gravel driveway. No photo provided, reducing confidence."
  },
  "safety_assessment": {
    "safety_equipment": ["standard PPE"],
    "extra_engineer_required": false,
    "safety_risks": [],
    "explanation": "No safety flags raised for this job."
  },
  "rationale": [
    "Customer notes indicate they are only available after 5th April",
    "Committed delivery date of 3rd April conflicts with customer availability",
    "Recommending reschedule to 7th April (next working day after constraint window)",
    "Standard FTTP installation kit required",
    "No safety concerns identified"
  ]
}
```

## Markdown Summary Format

Each job produces a Markdown file:

```markdown
# Scheduling Decision: WO-001

## Recommended Action: RESCHEDULE

**Planned Visit Date:** 2026-04-07

## Rationale
- Customer notes indicate they are only available after 5th April
- Committed delivery date of 3rd April conflicts with customer availability
- Recommending reschedule to 7th April (next working day after constraint window)

## Scheduling Constraints
- **Earliest Allowed Date:** 2026-04-05
- **Customer Availability:** afternoons only
- **Special Instructions:** use rear access gate

## Visit Preparation
- **Tools:** fibre splicer, cable rod set
- **Materials:** fibre patch lead, wall box
- **Estimated Duration:** 120 minutes
- **Confidence:** medium

## Safety
- **Equipment:** standard PPE
- **Extra Engineer Required:** No
- **Risks:** None
```

## Skill Definitions

### Skill A: Extract Scheduling Constraints
- **Input:** customer notes (free text), requested date range, committed delivery date
- **Output:** earliest allowed date, customer availability window, special instructions list
- **Logic:** Regex and keyword extraction from unstructured notes

### Skill B: Assess Delivery Date Risk
- **Input:** committed delivery date, delay indicators (access issue, customer delayed, dependency failure), constraint output from Skill A
- **Output:** date change recommended (boolean), reason code, revised delivery date suggestion, explanation
- **Logic:** Product-specific rules. Ethernet orders have more flexible date movement. Home Broadband orders are more constrained.

### Skill C: Assess Visit Readiness
- **Input:** job type, service type, driveway surface hint, photo provided flag, customer notes
- **Output:** required tools list, required materials list, estimated duration in minutes, confidence level, explanation
- **Logic:** Lookup tables keyed by service type and job type, adjusted by site conditions

### Skill D: Assess Safety and Feasibility
- **Input:** dog on site flag, heavy PPE requirement hints, exchange visit flag, customer notes
- **Output:** safety equipment list, extra engineer required flag, safety risks list, explanation
- **Logic:** Flag-based rules with keyword extraction from notes for additional hazards

## Acceptance Criteria Checklist

- [ ] `python -m app.run --csv data/work_orders.csv` runs without error
- [ ] `out/` directory contains JSON and Markdown for each work order
- [ ] `out/decisions.json` contains array of all decisions
- [ ] Each decision has `recommended_action` in {"schedule", "reschedule", "needs-human-review"}
- [ ] Each decision has `planned_visit_date` as a valid date
- [ ] Each decision has non-empty `rationale` list
- [ ] Unit tests pass for all 4 skills (3+ cases each)
- [ ] End-to-end test passes with 2-row CSV
- [ ] No secrets or API keys in source code
- [ ] No em dashes in any output text
- [ ] MCP server starts and exposes tools on configured port
- [ ] Chat UI can invoke scheduling tools via Copilot

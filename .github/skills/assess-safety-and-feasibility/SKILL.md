---
name: assess-safety-and-feasibility
description: >
  Evaluates safety risks and PPE requirements for a field visit. Flags dogs
  on site, confined spaces, overhead work, asbestos, and other hazards.
  Determines if an extra engineer is required.
---

# Assess Safety and Feasibility

## Purpose

Engineer safety is non-negotiable. This skill identifies all safety risks
and equipment requirements before a visit is scheduled, ensuring the right
team and kit are dispatched.

## When to Use

Call this skill for every work order. Safety assessment must never be skipped.

## Inputs

| Field | Type | Description |
|-------|------|-------------|
| `dog_on_site_flag` | boolean | Dog reported at property |
| `heavy_ppe_hint` | string | Hints like "confined space", "overhead work" |
| `exchange_visit_flag` | boolean | Visit includes telephone exchange |
| `customer_notes` | string | Free text notes |

## Outputs

Returns a JSON object:

```json
{
  "safety_equipment": ["standard PPE", "confined space rescue kit"],
  "extra_engineer_required": true,
  "safety_risks": ["confined space working", "dog on site"],
  "explanation": "Confined space working identified. Two-person team required."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `safety_equipment` | string[] | Required PPE and safety equipment |
| `extra_engineer_required` | boolean | Whether a second engineer is needed |
| `safety_risks` | string[] | List of identified risks |
| `explanation` | string | Human-readable explanation |

## Safety Rules

| Hazard | Equipment | Extra Engineer |
|--------|-----------|---------------|
| Dog on site | (none extra) | No |
| Confined space | Confined space rescue kit | Yes |
| Overhead work | Hard hat with chin strap | No |
| Overhead power lines | (standard) | Yes |
| Data centre / anti-static | Anti-static PPE | No |
| Exchange visit | Exchange access key | No |
| Asbestos | Asbestos awareness certification | Yes |

## Notes Detection

The skill also scans customer notes for safety keywords that may not be
captured in structured flags:
- "dog", "dogs", "guard dog" (even if flag is false)
- "basement", "low ceiling", "crawl space" (confined space)
- "scaffolding", "cherry picker", "roof access" (height)
- "asbestos" (hazardous material)
- "overhead power lines" (electrical hazard)
- "anti-static", "data centre" (ESD risk)

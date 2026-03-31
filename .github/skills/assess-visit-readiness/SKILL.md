---
name: assess-visit-readiness
description: >
  Determines the tools, materials, and estimated duration needed for a field
  engineer visit based on service type, job type, site conditions, and
  information found in customer notes.
---

# Assess Visit Readiness

## Purpose

Engineers arriving unprepared is a leading cause of failed visits. This skill
predicts what equipment and time is needed so the visit can succeed first time.

## When to Use

Call this skill for any work order before scheduling to ensure the engineer
has the right kit and enough time allocated.

## Inputs

| Field | Type | Description |
|-------|------|-------------|
| `service_type` | string | e.g., "FTTP Installation", "Ethernet Bearer", "Broadband Repair" |
| `job_type` | string | e.g., "new line installation", "repair", "provision", "cease" |
| `driveway_surface_hint` | string | "tarmac", "gravel", "block paving", or empty |
| `photo_provided_flag` | boolean | Whether customer provided a site photo |
| `customer_notes` | string | Free text notes |

## Outputs

Returns a JSON object:

```json
{
  "required_tools": ["fibre splicer", "cable rod set", "power meter"],
  "required_materials": ["fibre patch lead", "wall box"],
  "estimated_duration_minutes": 120,
  "confidence": "medium",
  "explanation": "Gravel surface may need ground protection. No site photo provided."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `required_tools` | string[] | Tools the engineer should bring |
| `required_materials` | string[] | Materials needed for the job |
| `estimated_duration_minutes` | integer | Estimated time (30-480 minutes) |
| `confidence` | string | "high", "medium", or "low" |
| `explanation` | string | Human-readable explanation of adjustments |

## Confidence Levels

- **High**: Photo provided and standard job type
- **Medium**: No photo but no complexity indicators
- **Low**: Previous failed attempt, duct blockage, or missing information

## Duration Adjustments

- Gravel surface: +15 minutes
- Block paving: +20 minutes
- Long cable run (50m+): +30 minutes
- Duct blockage: +60 minutes
- Cherry picker / scaffolding: +60 minutes
- Previous failed attempt: +30 minutes
- Maximum: 480 minutes (full day)

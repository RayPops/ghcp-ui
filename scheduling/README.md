# BT Openreach Scheduling Copilot

A scheduling decision intelligence demo that analyses field engineer work orders and recommends optimal scheduling decisions. Built as an extension to the [ghcp-ui](https://github.com/aiappsgbb/ghcp-ui) platform, providing both a CLI batch mode and an interactive chat interface via MCP tools.

## What This Does

Openreach engineers drive to customer sites and find the customer is on holiday, the access is blocked, or they don't have the right equipment. These constraints are buried in free-text notes that nobody reads. This copilot reads every note automatically.

For each work order, it:

1. **Extracts scheduling constraints** from messy unstructured customer notes (hidden dates, availability windows, access instructions)
2. **Assesses delivery date risk** using product-specific delay rules (Ethernet vs Home Broadband)
3. **Predicts visit readiness** requirements (tools, materials, estimated duration)
4. **Flags safety concerns** (dogs on site, confined spaces, asbestos, overhead work)

It returns a structured **recommended scheduling decision** per job: `schedule`, `reschedule`, or `needs-human-review`, with a clear rationale.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | For the scheduling skills and MCP server |
| Node.js | 18+ | For the ghcp-ui web app |
| npm | 9+ | Comes with Node.js |
| Azure CLI | 2.x | Only needed if using Entra ID auth (no API key) |
| Azure AI Foundry | - | You need an Azure OpenAI resource with a deployed model (e.g. `gpt-4.1`) |

---

## Setup

### Step 1: Install Python dependencies

```powershell
cd scheduling
pip install -e .
```

### Step 2: Install Node.js dependencies (for chat UI)

```powershell
# From the repo root (not scheduling/)
cd ..
npm install
```

### Step 3: Create the `.env` file

Create a `.env` file in the **repo root** (not in `scheduling/`):

**Option A: API Key auth** (if your Azure OpenAI resource has local auth enabled)

```env
AZURE_FOUNDRY_ENDPOINT=https://your-resource.openai.azure.com/openai/v1/
AZURE_FOUNDRY_API_KEY=your-api-key-here
AZURE_FOUNDRY_MODEL=gpt-4.1
PORT=3001
NODE_ENV=development
MCP_SERVERS_JSON={"scheduling":{"type":"sse","url":"http://localhost:3002/sse","tools":["*"]}}
```

**Option B: Azure AD Bearer Token auth** (if API keys are disabled -- common in enterprise)

```powershell
# Get a bearer token (expires in ~1 hour)
az login
az account get-access-token --resource "https://cognitiveservices.azure.com" --query accessToken -o tsv
```

```env
AZURE_FOUNDRY_ENDPOINT=https://your-resource.openai.azure.com/openai/v1/
AZURE_FOUNDRY_BEARER_TOKEN=eyJ0eXAi...paste-your-token-here
AZURE_FOUNDRY_MODEL=gpt-4.1
PORT=3001
NODE_ENV=development
MCP_SERVERS_JSON={"scheduling":{"type":"sse","url":"http://localhost:3002/sse","tools":["*"]}}
```

> **Important:** The `MCP_SERVERS_JSON` line must use `"type":"sse"` (not `"http"`). The Python MCP server uses Server-Sent Events transport.

> **Important:** Bearer tokens expire after approximately 1 hour. When you get auth errors, re-run the `az account get-access-token` command and update the `.env` file, then restart `npm run dev`.

---

## Running the Demo

### Option A: CLI Mode (Batch Processing, no servers needed)

```powershell
cd scheduling
python -m app.run --csv data/work_orders.csv
```

Output appears in `out/`:
- `out/WO-001.json` -- per-job JSON decision
- `out/WO-001.md` -- per-job Markdown summary
- `out/decisions.json` -- combined array of all decisions

### Option B: Chat UI (Interactive Demo)

You need **two terminals running simultaneously**:

**Terminal 1: Start the MCP server**

```powershell
cd scheduling
python -m app.mcp_server
# Should print: Starting BT Openreach Scheduling MCP server on 0.0.0.0:3002
```

**Terminal 2: Start the ghcp-ui web app**

```powershell
# From repo root (not scheduling/)
npm run dev
# Should print:
#   BYOK: true
#   Model: gpt-4.1
#   Loaded 1 global MCP server(s): scheduling
#   Client: http://localhost:5173/
```

**Then open http://localhost:5173/ in your browser.**

### Verify it works

1. Open **Settings** (gear icon, top-right) -- you should see `scheduling` listed under **ADMIN (READ-ONLY)** MCP Servers
2. Type `Hello!` -- you should get a response (confirms Azure auth is working)
3. Type `List all work orders` -- you should see `list_work_orders` tool fire and 14 orders listed

---

## Demo Prompts

| Prompt | What it demonstrates |
|--------|---------------------|
| `List all work orders` | Data access: reads CSV, returns 14 orders |
| `Analyse work order WO-003` | Full pipeline: extracts "holiday until 10th", flags dog on site, recommends human review |
| `What safety risks exist for WO-002?` | Targeted skill: confined space (1.4m ceiling), exchange visit, two-person team |
| `What tools does the engineer need for WO-004?` | Visit readiness: cherry picker, overhead work, fibre splicer |
| `Compare WO-001 and WO-005` | Side-by-side: installation vs repair, different constraints |

---

## Example Output

```
$ python -m app.run --csv data/work_orders.csv --out out

Processed 14 work orders:
  needs-human-review: 4
  reschedule: 5
  schedule: 5

Output written to out/
```

Example JSON decision for WO-003 (`out/WO-003.json`):

```json
{
  "order_id": "WO-003",
  "recommended_action": "needs-human-review",
  "planned_visit_date": "2026-04-10",
  "constraints": {
    "earliest_allowed_date": "2026-04-10",
    "customer_availability_window": "mornings only",
    "special_instructions": []
  },
  "delivery_date_assessment": {
    "date_change_recommended": true,
    "reason_code": "delay_exceeds_allowed_window",
    "revised_delivery_date": "2026-04-08",
    "explanation": "Customer availability gap exceeds the maximum allowed delay..."
  },
  "visit_readiness": {
    "required_tools": ["fibre splicer", "cable rod set", "power meter", "fibre cleaver"],
    "required_materials": ["fibre patch lead", "wall box", "cable clips", "duct tape"],
    "estimated_duration_minutes": 120,
    "confidence": "medium",
    "explanation": "No site photo provided. Confidence reduced."
  },
  "safety_assessment": {
    "safety_equipment": ["standard PPE"],
    "extra_engineer_required": false,
    "safety_risks": ["dog on site"],
    "explanation": "Dog reported on site. Customer must secure animal before engineer arrives."
  },
  "rationale": [
    "Delivery date delay exceeds allowed window for Home Broadband orders",
    "Customer availability: mornings only",
    "Estimated duration: 120 minutes (confidence: medium)",
    "Safety risks: dog on site",
    "Customer marked as not ready"
  ]
}
```

---

## Project Structure

```
scheduling/
  app/
    __init__.py
    __main__.py
    run.py              CLI entrypoint
    models.py           Data models (WorkOrder, SchedulingDecision, etc.)
    csv_loader.py       CSV loader with validation
    orchestrator.py     Skill orchestration and decision composition
    render.py           Markdown summary renderer
    mcp_server.py       MCP server for ghcp-ui integration
    skills/
      __init__.py
      extract_constraints.py    Skill A: scheduling constraint extraction
      assess_date_risk.py       Skill B: delivery date risk assessment
      assess_visit_readiness.py Skill C: visit readiness prediction
      assess_safety.py          Skill D: safety and feasibility assessment
    tests/
      __init__.py
      test_extract_constraints.py
      test_assess_date_risk.py
      test_assess_visit_readiness.py
      test_assess_safety.py
      test_end_to_end.py
  data/
    work_orders.csv     14 synthetic work orders with realistic messy data
  docs/
    requirements.md     Full requirements document
    architecture.drawio Draw.io architecture diagram
  out/                  Generated output (gitignored)
  pyproject.toml        Python project config
```

---

## Running Tests

```powershell
cd scheduling
pip install -e ".[dev]"
pytest app/tests/ -v
# 28 tests, all should pass
```

---

## Architecture

```
Browser (React UI)  -->  Express + Copilot SDK  -->  Python MCP Server (port 3002)
                                                          |
                      CLI (python -m app.run)  --------->  4 Domain Skills
                                                          |
                                                     work_orders.csv
```

- **Skills are deterministic**: Pure Python functions with regex/keyword/rule-based logic. No LLM calls inside skills. This makes them testable and predictable.
- **LLM orchestrates in chat mode**: The Copilot SDK's LLM decides which MCP tools to call and in what order based on the user's question.
- **CLI orchestrates in batch mode**: `orchestrator.py` calls all 4 skills in sequence for each work order.
- **MCP (Model Context Protocol)**: An open standard that lets LLMs call external tools. The Python server exposes 7 tools over SSE transport.
- **Abstraction boundary**: Domain logic (skills) is fully separated from the agent loop (MCP server / CLI). The SDK glue layer can be swapped without touching any skill code.

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `list_work_orders` | List all work orders from CSV |
| `get_work_order` | Get full details for one order |
| `extract_constraints_tool` | Parse notes for scheduling constraints |
| `assess_date_risk_tool` | Evaluate delivery date risk |
| `assess_readiness_tool` | Predict tools, materials, duration |
| `assess_safety_tool` | Flag safety risks and PPE needs |
| `compose_scheduling_decision` | Run full pipeline for one order |

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| All chat responses are empty bubbles | `wireApi` set to `"responses"` in copilot.service.ts | Must be `"completions"` for Azure OpenAI |
| MCP tools not appearing in Settings | `"type":"http"` in MCP_SERVERS_JSON | Change to `"type":"sse"` |
| 401/403 errors after ~1 hour | Bearer token expired | Re-run `az account get-access-token` and update `.env` |
| `npm run dev` fails with "concurrently not found" | Missing node_modules | Run `npm install` from repo root |
| MCP server port 3002 already in use | Previous process still running | Kill it: `Get-Process python \| Stop-Process` |
| Settings shows scheduling but tools aren't called | LLM not aware of scheduling tools | Start a **new chat** session (click +) |

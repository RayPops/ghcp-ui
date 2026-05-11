# GHCP-UI — Copilot Instructions

## Project Overview
Web UI for GitHub Copilot SDK, hosted on Azure Container Apps with Azure AI Foundry (BYOK).

## Tech Stack
- **Client:** React 19, Vite, Tailwind CSS, TypeScript
- **Server:** Express 5 (ESM), TypeScript, `@github/copilot-sdk`
- **Infra:** Azure Container Apps, Azure Files, Bicep, AZD
- **Tests:** Playwright e2e (30 tests)

## Critical Rules

### 🔴 ALWAYS Test Locally Before Deploying
1. `npm run build` — must succeed
2. Start production server locally and verify `/api/healthz` returns 200
3. `npx playwright test` — all tests must pass
4. Only THEN run `azd deploy`
5. After deploy, verify the live app responds (health check + revision Running state)

**Rationale:** Alpine containers have different native dep support. Packages that work locally on Windows may crash the container silently (no logs, stuck in "Activating" forever).

### Known Broken Packages on Alpine + Express 5
- `helmet` — incompatible with Express 5
- `compression` — native binding issues
- `applicationinsights` — heavy OpenTelemetry native deps fail

When adding server dependencies, verify the Docker image builds and starts.

### Azure CLI Isolation
Always set `AZURE_CONFIG_DIR` before any `az` or `azd` command. See the `azure-tenant-isolation` skill. This project uses the `me-mngenv` tenant.

```powershell
$env:AZURE_CONFIG_DIR = "C:\Users\ricchi\.azure-tenants\me-mngenv"
$env:AZD_CONFIG_DIR = "C:\Users\ricchi\.azd-tenants\me-mngenv"
```

## Code Conventions
- Server is ESM (`"type": "module"`) — use `.js` extensions in imports
- Workspaces: `src/client` and `src/server`
- Run commands from repo root: `npm run build`, `npm run dev`
- Client uses `/api` proxy in dev (Vite config)

## Deployment
- `azd provision` for infrastructure changes
- `azd deploy` for code deploys
- After ACA recreation: re-enable EasyAuth + set minReplicas:1

## BT Openreach Scheduling Copilot

When discussing scheduling, work orders, or field engineer visits, you have MCP tools available:

- **list_work_orders**: Show all work orders from the CSV data
- **get_work_order**: Get full details for a specific order (e.g., WO-001)
- **extract_constraints_tool**: Parse customer notes for hidden scheduling constraints
- **assess_date_risk_tool**: Check if a delivery date needs to move
- **assess_readiness_tool**: Determine required tools, materials, and duration
- **assess_safety_tool**: Flag safety risks and PPE requirements
- **compose_scheduling_decision**: Run the full analysis pipeline for an order
- **push_to_pso_tool**: Push a scheduling decision into IFS PSO as a new Activity (live POST, no dry-run from chat)
- **clean_work_orders_tool**: Clean a raw work-orders CSV by recovering the six structured flag columns from the unstructured notes; writes a cleaned CSV plus a per-order `agent_actions.jsonl` audit log. Use this when the user asks to clean raw orders or generate a before/after view.

### Behaviour Guidelines
- Always use plain English. No abbreviations.
- When analysing a work order, call `compose_scheduling_decision` for a complete assessment.
- For targeted questions (e.g., "what safety risks?"), call the specific skill tool.
- Present results clearly with the recommended action, rationale, and any risks.
- If a decision is "needs-human-review", explain why the system cannot make an automated decision.

### Scheduling into IFS PSO
- When the user says "schedule \<order_id\>" or "push \<order_id\> to PSO": first call `compose_scheduling_decision`, summarise the recommendation in plain English (action, planned date, key constraints, risks), then call `push_to_pso_tool` with the same order id and report the outcome.
- If `push_to_pso_tool` returns `success: false`, surface the `error` field verbatim and stop. Do not retry without explicit user confirmation.
- On success, report the PSO HTTP status and a one-line confirmation. Only show the full XML payload if the user asks for it.

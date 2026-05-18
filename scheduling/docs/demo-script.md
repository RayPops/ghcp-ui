# BT Openreach Scheduling Copilot — demo script

## The story (one sentence to open with)

> *"Five deterministic skills take a raw BT export, recover every hidden constraint from the notes, write an auditable action log, and post a live activity into IFS PSO. All driven from chat."*

End-to-end story: **raw data → cleaned → agent actions → scheduling decision → posted to IFS**.

---

## Setup (10 minutes before the room opens)

Three terminals, all from the repo root.

**Terminal 1 — MCP server**
```powershell
cd scheduling
python -m app.mcp_server
```
Wait for `Uvicorn running on http://0.0.0.0:3002`.

**Terminal 2 — Web app**
```powershell
npm run dev
```
Wait for `Client: http://localhost:5173/`. Open it in the browser, click the gear icon, confirm `scheduling` shows under MCP Servers.

**Terminal 3 — CLI.** Leave it in `scheduling/`. Used in steps 2 and 4.

**Browser tab 2 — PSO UI.** Log in. Filter `dataset = CC_LIVE`. Keep it ready.

**Before you start a chat session:** confirm the BYOK token is not expired (it lives ~1 hour). If chat replies are empty, run:
```powershell
$new = az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv
(Get-Content .env -Raw) -replace '(?m)^AZURE_FOUNDRY_BEARER_TOKEN=.*$', "AZURE_FOUNDRY_BEARER_TOKEN=$new" | Set-Content .env -NoNewline
```
…then restart `npm run dev` and start a brand-new chat session.

---

## Step 1 — Raw data (the mess BT gives us)

In terminal 3:
```powershell
Get-Content data/work_orders_raw.csv -TotalCount 2
```

Say: *"This is the export from BT. No flags, no structure. Every constraint — access issues, working at height, dogs on site, customer not ready — is buried inside the notes column with `||` separators."*

---

## Step 2 — Chat UI: clean every order

In the browser at http://localhost:5173/. Start a fresh chat session.

> Type: **Clean the raw work orders and write the action log**

The trace pane fires `clean_work_orders_tool`. The reply gives you `cleaned_csv` and `action_log` paths plus a count (12 orders, 11 schedule, 1 needs-human-review).

Say: *"One tool call, twelve orders processed. The five skills extracted every hidden flag from the notes and wrote two artefacts: a cleaned CSV and an action log."*

---

## Step 3 — Accountability: the action log

Back in terminal 3:
```powershell
Select-String -Path out/agent_actions.jsonl -Pattern ONEA92160383 -SimpleMatch | % { $_.Line } | ConvertFrom-Json | ConvertTo-Json -Depth 6
```

Walk through the three extractions in the JSON:
- `heavy_ppe_hint = overhead work` — skill **D: Assess Safety**, source excerpt `"overhead"`.
- `customer_ready_status = unknown` — skills **C + A + E** voted.
- `sla_guardrail_applied = 2026-05-18` — original `2025-11-15`, reason `committed_delivery_date in the past at run time`.

Say: *"Every cleaned field traces back to a named skill and the exact words in the notes. Auditors get to see why each decision was made. The last line is the SLA guardrail — when a committed date is in the past, we shift to the next business day and keep the original for audit."*

---

## Step 4 — Chat UI: push the scheduled visit into IFS PSO

Back in the browser.

> Type: **Push ONEA92160383 to PSO**

The trace pane fires `push_to_pso_tool`. The reply gives you `HTTP 200`, dataset `CC_LIVE`, and the planned visit window.

Switch to the PSO UI tab and refresh. Activity `ONEA92160383` is there, mapped to a London tile, assigned to one of the five dummy techs, SLA window `2026-05-18 → 2026-05-19`.

Say: *"That single tool call ran the full pipeline: re-ran the five skills, geocoded the postcode, built the IFS PSO XML, applied the SLA guardrail, and POSTed it live. The scheduler never touched the CLI."*

---

## Step 5 — Optional, if time permits

> Type: **What's the delay history for ONEA92160383?**

Expected: 20 past delays. Top reasons: traffic management, third-party blockage, CP consent.

Say: *"This skill queries 709,000 real BT delay records. The scheduler sees the project's slip history before they commit."*

> Type: **Analyse ONEA73446139**

Expected: **needs-human-review** — customer delay flag set, Ethernet delay window exceeded.

Say: *"It refuses to auto-schedule when the rule says it shouldn't. Human-in-the-loop, on purpose."*

---

## Wrap (15 seconds)

1. **End-to-end through chat.** Raw export → cleaned CSV → action log → live PSO activity, all driven by plain English.
2. **Accountability.** Every cleaned field cites a skill and a source excerpt. No black box.
3. **Deterministic.** The LLM picks tools, it doesn't invent answers. Identical results from the CLI.
4. **Real BT data.** Operational notes and the full 709K-row delay history.
5. **SLA guardrail.** Past committed dates shift to the next business day, original preserved.

---

## Reference payloads for IFS

The 12 outgoing PSO XML payloads (one per order plus a combined `_all_orders.xml`) live in [scheduling/out/pso_payloads/](../out/pso_payloads/). Regenerate at any time with:
```powershell
cd scheduling
python -c "from datetime import date, datetime, timezone; from pathlib import Path; from app.export_payloads import export_payloads; export_payloads(Path('data/work_orders.csv'), Path('out/pso_payloads'), today=date.today(), now=datetime.now(timezone.utc))"
```

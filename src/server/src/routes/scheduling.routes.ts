import { Router, type Request, type Response } from "express";
import { existsSync, readFileSync, statSync } from "fs";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";

/**
 * Read-only scheduling routes for the Openreach DispatchAI UI.
 *
 * Only adds new endpoints — does not modify any existing route or behaviour.
 * Source of truth is the same ``scheduling/data/work_orders.csv`` the Python
 * MCP server reads, so a single edit shows up everywhere.
 */

interface WorkOrderRow {
  orderId: string;
  orderSource: string;
  serviceType: string;
  jobType: string;
  postcode: string;
  customerReadyStatus: string;
  committedDeliveryDate: string;
}

/**
 * Minimal RFC 4180 parser sufficient for our 12-row CSV (quoted fields,
 * embedded commas, doubled-up double-quote escapes, CRLF or LF line endings).
 * Inlining 30 lines keeps us off a native-binding dependency that has burned
 * the Alpine deploy before (see .github/copilot-instructions.md).
 */
function parseCsv(content: string): string[][] {
  const rows: string[][] = [];
  let field = "";
  let row: string[] = [];
  let inQuotes = false;

  for (let i = 0; i < content.length; i++) {
    const ch = content[i];

    if (inQuotes) {
      if (ch === '"') {
        if (content[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      // Finish the current row, swallow a paired \r\n.
      if (field.length > 0 || row.length > 0) {
        row.push(field);
        rows.push(row);
      }
      field = "";
      row = [];
      if (ch === "\r" && content[i + 1] === "\n") i++;
    } else {
      field += ch;
    }
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

/** Map a parsed CSV row to the shape the UI consumes. */
function rowToWorkOrder(headers: string[], values: string[]): WorkOrderRow | null {
  if (values.length < headers.length) return null;
  const get = (key: string) => {
    const idx = headers.indexOf(key);
    return idx >= 0 ? (values[idx] ?? "").trim() : "";
  };
  const orderId = get("order_id");
  if (!orderId) return null;
  return {
    orderId,
    orderSource: get("order_source"),
    serviceType: get("service_type"),
    jobType: get("job_type"),
    postcode: get("postcode"),
    customerReadyStatus: get("customer_ready_status"),
    committedDeliveryDate: get("committed_delivery_date"),
  };
}

/**
 * Resolve the CSV path. ``SCHEDULING_CSV_PATH`` env override wins so the
 * route can be pointed at a different file in tests or in prod. In dev we
 * walk up from this source file looking for ``scheduling/data/work_orders.csv``
 * — the npm workspace runs the server with cwd=src/server/, so a plain
 * ``process.cwd()``-relative path lands in the wrong place.
 */
function resolveCsvPath(): string {
  const fromEnv = process.env.SCHEDULING_CSV_PATH;
  if (fromEnv) return resolve(fromEnv);

  const candidates: string[] = [];
  // Walk up from this file's directory looking for the scheduling folder.
  try {
    let dir = dirname(fileURLToPath(import.meta.url));
    for (let i = 0; i < 8; i++) {
      candidates.push(join(dir, "scheduling", "data", "work_orders.csv"));
      const parent = dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  } catch {
    // ignore — fall through to cwd-based candidate
  }
  // Also try cwd in case the server is run from the repo root.
  candidates.push(resolve(join(process.cwd(), "scheduling", "data", "work_orders.csv")));

  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  // Return the most useful fallback so the error message points somewhere sensible.
  return candidates[0] ?? candidates[candidates.length - 1];
}

/**
 * In-memory cache keyed on file mtime so the route hot-reloads when an
 * operator edits the CSV between runs (same trick as the MCP server). One
 * stat per request is cheap.
 */
let cache: { mtimeMs: number; orders: WorkOrderRow[] } | null = null;

function loadOrders(csvPath: string): WorkOrderRow[] {
  if (!existsSync(csvPath)) {
    throw new Error(`Work orders CSV not found at ${csvPath}`);
  }
  const stats = statSync(csvPath);
  if (cache && cache.mtimeMs === stats.mtimeMs) {
    return cache.orders;
  }

  const content = readFileSync(csvPath, "utf-8");
  const rows = parseCsv(content);
  if (rows.length === 0) {
    cache = { mtimeMs: stats.mtimeMs, orders: [] };
    return cache.orders;
  }

  const headers = rows[0].map((h) => h.trim());
  const orders: WorkOrderRow[] = [];
  for (let i = 1; i < rows.length; i++) {
    const order = rowToWorkOrder(headers, rows[i]);
    if (order) orders.push(order);
  }

  cache = { mtimeMs: stats.mtimeMs, orders };
  return orders;
}

const router = Router();

router.get("/work-orders", (_req: Request, res: Response) => {
  try {
    const orders = loadOrders(resolveCsvPath());
    res.json({ orders, count: orders.length });
  } catch (err) {
    const message = err instanceof Error ? err.message : "unknown error";
    console.error("[scheduling.routes] Failed to load work orders:", message);
    res.status(500).json({ error: "failed_to_load_work_orders", message });
  }
});

export default router;

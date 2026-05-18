import { useEffect, useState, useCallback } from "react";
import { ClipboardList, Loader2, RefreshCw, AlertCircle } from "lucide-react";

/**
 * Shape returned by ``GET /api/scheduling/work-orders``. The server reads the
 * same CSV the Python MCP server reads, so this list always matches what the
 * scheduling tools will see when they fire.
 */
export interface WorkOrder {
  orderId: string;
  orderSource: string;
  serviceType: string;
  jobType: string;
  postcode: string;
  customerReadyStatus: string;
  committedDeliveryDate: string;
}

interface WorkOrdersPaneProps {
  /** Called when the user clicks an action button. The pane only prefills the
   * input bar — sending stays in the user's hands. */
  onPrefillPrompt: (prompt: string) => void;
}

const READY_BADGE: Record<string, string> = {
  ready: "bg-emerald-900/30 text-emerald-300 border-emerald-800/50",
  "not ready": "bg-amber-900/30 text-amber-300 border-amber-800/50",
  unknown: "bg-zinc-800/60 text-zinc-400 border-zinc-700/50",
};

function readyBadgeClass(status: string): string {
  const key = (status || "unknown").trim().toLowerCase();
  return READY_BADGE[key] ?? READY_BADGE.unknown;
}

export function WorkOrdersPane({ onPrefillPrompt }: WorkOrdersPaneProps) {
  const [orders, setOrders] = useState<WorkOrder[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/scheduling/work-orders");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as { orders: WorkOrder[] };
      setOrders(body.orders);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load work orders");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered =
    orders == null
      ? null
      : filter.trim().length === 0
        ? orders
        : orders.filter((o) => {
            const q = filter.trim().toLowerCase();
            return (
              o.orderId.toLowerCase().includes(q) ||
              o.postcode.toLowerCase().includes(q) ||
              o.serviceType.toLowerCase().includes(q)
            );
          });

  return (
    <aside
      data-testid="work-orders-pane"
      className="hidden sm:flex w-60 md:w-64 lg:w-72 xl:w-80 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950/60"
    >
      <header className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-2 text-zinc-300">
          <ClipboardList className="w-4 h-4 text-brand-400" />
          <span className="text-sm font-semibold">Work Orders</span>
          {orders && (
            <span className="text-xs text-zinc-500" data-testid="work-orders-count">
              {orders.length}
            </span>
          )}
        </div>
        <button
          onClick={load}
          disabled={loading}
          aria-label="Refresh work orders"
          className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
        </button>
      </header>

      <div className="px-3 py-2 border-b border-zinc-900 shrink-0">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by id, postcode, service…"
          aria-label="Filter work orders"
          className="w-full text-xs px-2.5 py-1.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-brand-500/50"
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="m-3 p-3 rounded border border-red-900/50 bg-red-950/30 text-xs text-red-300 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {!error && orders == null && (
          <div className="p-4 text-xs text-zinc-500 text-center">Loading…</div>
        )}

        {!error && filtered && filtered.length === 0 && orders && orders.length > 0 && (
          <div className="p-4 text-xs text-zinc-500 text-center">No orders match the filter.</div>
        )}

        {!error && filtered && filtered.length === 0 && orders && orders.length === 0 && (
          <div className="p-4 text-xs text-zinc-500 text-center">No work orders found.</div>
        )}

        <ul className="px-2 py-1 space-y-1">
          {filtered?.map((o) => (
            <li
              key={o.orderId}
              data-testid="work-order-row"
              data-order-id={o.orderId}
              className="rounded-lg p-2.5 bg-zinc-900/40 hover:bg-zinc-900/70 border border-zinc-800/50 transition-colors"
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="font-mono text-xs text-zinc-200 truncate">{o.orderId}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded border ${readyBadgeClass(o.customerReadyStatus)} shrink-0`}
                >
                  {o.customerReadyStatus || "unknown"}
                </span>
              </div>
              <div className="text-[11px] text-zinc-400 leading-tight mb-2">
                <div className="truncate">
                  {o.serviceType}
                  {o.jobType ? ` · ${o.jobType}` : ""}
                </div>
                <div className="text-zinc-500">{o.postcode || "—"}</div>
              </div>
              <div className="flex flex-wrap gap-1">
                <button
                  data-testid="work-order-details-btn"
                  onClick={() => onPrefillPrompt(`Tell me about ${o.orderId}`)}
                  className="text-[11px] px-2 py-1 rounded bg-zinc-800/70 hover:bg-zinc-700 text-zinc-300 transition-colors"
                >
                  Details
                </button>
                <button
                  data-testid="work-order-schedule-btn"
                  onClick={() => onPrefillPrompt(`Schedule ${o.orderId} and push to PSO`)}
                  className="text-[11px] px-2 py-1 rounded bg-brand-700/40 hover:bg-brand-600/60 text-brand-200 border border-brand-700/40 transition-colors"
                >
                  Schedule → PSO
                </button>
                <button
                  data-testid="work-order-copy-btn"
                  aria-label={`Copy order id ${o.orderId}`}
                  onClick={() => {
                    try {
                      void navigator.clipboard?.writeText(o.orderId);
                    } catch {
                      /* clipboard unavailable in some sandboxes — silent no-op */
                    }
                  }}
                  className="text-[11px] px-2 py-1 rounded bg-zinc-800/40 hover:bg-zinc-700 text-zinc-400 transition-colors ml-auto"
                  title="Copy order id"
                >
                  Copy id
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

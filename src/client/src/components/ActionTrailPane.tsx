import { History, CheckCircle2, XCircle } from "lucide-react";
import type { ActionTrailEntry } from "../types";

interface ActionTrailPaneProps {
  entries: ActionTrailEntry[];
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

/**
 * Right-dock pane that shows a chronological audit trail of every tool the
 * agent has fired in the current session.
 *
 * Sourced from the live SSE tool_complete events streamed by the chat hook,
 * so no backend route is needed. The trail resets when a new session starts
 * or when the user switches to a different session.
 */
export function ActionTrailPane({ entries }: ActionTrailPaneProps) {
  return (
    <aside
      data-testid="action-trail-pane"
      className="hidden lg:flex w-72 xl:w-80 shrink-0 flex-col border-l border-zinc-800 bg-zinc-950/60"
    >
      <header className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-2 text-zinc-300">
          <History className="w-4 h-4 text-brand-400" />
          <span className="text-sm font-semibold">Action Trail</span>
          {entries.length > 0 && (
            <span className="text-xs text-zinc-500" data-testid="action-trail-count">
              {entries.length}
            </span>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 ? (
          <div className="p-4 text-xs text-zinc-500 leading-relaxed">
            <p className="mb-1 text-zinc-400">Nothing yet.</p>
            <p>
              Every scheduling skill, decision, and PSO push the agent fires in this
              session will be recorded here for audit.
            </p>
          </div>
        ) : (
          <ol className="px-3 py-2 space-y-2 relative">
            {/* Vertical guide line behind the timeline dots. */}
            <div
              className="absolute left-[19px] top-2 bottom-2 w-px bg-zinc-800/60 pointer-events-none"
              aria-hidden
            />
            {entries.map((e) => (
              <li
                key={e.id}
                data-testid="action-trail-entry"
                data-tool-name={e.toolName}
                className="relative pl-7 py-1"
              >
                {/* Timeline dot. */}
                <span
                  className={`absolute left-[11px] top-2 w-3 h-3 rounded-full border ${
                    e.success
                      ? "bg-emerald-900/60 border-emerald-700/80"
                      : "bg-red-900/60 border-red-700/80"
                  }`}
                  aria-hidden
                />
                <div className="flex items-center gap-1.5 text-[11px] mb-0.5">
                  {e.success ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />
                  )}
                  <span className="font-mono text-zinc-200 truncate" title={e.toolName}>
                    {e.toolName}
                  </span>
                  {e.mcpServerName && (
                    <span className="text-[10px] text-zinc-500 truncate">
                      · {e.mcpServerName}
                    </span>
                  )}
                  <span className="ml-auto text-[10px] text-zinc-500 shrink-0">
                    {formatTime(e.timestamp)}
                  </span>
                </div>
                {e.summary && (
                  <p className="text-[11px] text-zinc-400 leading-snug break-words">
                    {e.summary}
                  </p>
                )}
                {e.error && (
                  <p className="text-[11px] text-red-400 leading-snug break-words">
                    {e.error}
                  </p>
                )}
                {e.triggeredBy && (
                  <p
                    className="text-[10px] text-zinc-600 mt-0.5 truncate italic"
                    title={e.triggeredBy}
                  >
                    ↳ "{e.triggeredBy}"
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}

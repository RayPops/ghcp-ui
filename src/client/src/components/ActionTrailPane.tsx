import { History, CheckCircle2, XCircle } from "lucide-react";
import type { ActionTrailEntry } from "../types";

interface ActionTrailPaneProps {
  entries: ActionTrailEntry[];
  /** When false, the pane is not rendered at all (header toggle hides it). */
  isOpen: boolean;
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
export function ActionTrailPane({ entries, isOpen }: ActionTrailPaneProps) {
  return (
    <aside
      data-testid="action-trail-pane"
      hidden={!isOpen}
      className={
        (isOpen ? "hidden lg:flex" : "hidden") +
        " w-72 xl:w-80 shrink-0 flex-col border-l border-zinc-800 bg-zinc-950/60"
      }
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
            {entries.map((e, i) => (
              <li
                key={e.id}
                data-testid="action-trail-entry"
                data-tool-name={e.toolName}
                data-step={i + 1}
                className="relative pl-8 py-1"
              >
                {/* Numbered step badge (replaces the plain dot). */}
                <span
                  className={`absolute left-[5px] top-[2px] w-[26px] h-[18px] rounded-md text-[10px] font-mono font-semibold flex items-center justify-center border ${
                    e.success
                      ? "bg-emerald-950/60 border-emerald-800/70 text-emerald-300"
                      : "bg-red-950/60 border-red-800/70 text-red-300"
                  }`}
                  aria-hidden
                >
                  {i + 1}
                </span>
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

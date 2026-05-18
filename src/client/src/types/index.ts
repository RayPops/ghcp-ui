export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  toolEvents?: ToolEvent[];
  reasoning?: string;
}

export interface ToolEvent {
  toolCallId?: string;
  type: "start" | "progress" | "complete" | "subagent_start" | "subagent_end";
  toolName?: string;
  mcpServerName?: string;
  message?: string;
  success?: boolean;
  content?: string;
  error?: string;
  agentName?: string;
  timestamp: string;
}

/**
 * Audit-trail entry for the Action Trail pane.
 *
 * Recorded once per tool completion within a session. Survives across
 * messages (unlike ``ToolEvent`` which is cleared between sends) so the
 * pane can show a chronological history of every skill the agent fired.
 */
export interface ActionTrailEntry {
  /** Stable id for React keys; not the SDK tool call id. */
  id: string;
  /** ISO timestamp captured client-side when the tool completed. */
  timestamp: string;
  /** Name as reported by the SDK (MCP tool name when available). */
  toolName: string;
  /** Owning MCP server, e.g. ``scheduling`` or ``workspace``. */
  mcpServerName?: string;
  /** True when the SDK reported ``success: true``. */
  success: boolean;
  /** Short text excerpt taken from the tool result (truncated to ~240 chars). */
  summary?: string;
  /** Error message if the tool failed. */
  error?: string;
  /** The user prompt that triggered this tool call, for context. */
  triggeredBy?: string;
}

export interface SessionInfo {
  id: string;
  createdAt: string;
  modifiedAt?: string;
  model: string;
  title?: string;
  summary?: string;
  messageCount: number;
  active?: boolean;
}

export interface ApiError {
  error: {
    message: string;
    stack?: string;
  };
}

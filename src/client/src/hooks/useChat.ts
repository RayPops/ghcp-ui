import { useState, useCallback, useRef } from "react";
import type { ActionTrailEntry, ChatMessage, ToolEvent, SessionInfo } from "../types";

const API_BASE = "/api";

/**
 * Build a short, plain-text summary for the Action Trail from a raw tool
 * result. The server already truncates the SDK content to 500 chars; we
 * further trim and try to surface the most useful first line.
 */
function summariseToolContent(content: string | undefined): string | undefined {
  if (!content) return undefined;
  const trimmed = content.trim();
  if (!trimmed) return undefined;
  // If the content is JSON, prefer a one-line gist over the full blob.
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) {
        return `${parsed.length} item(s)`;
      }
      if (parsed && typeof parsed === "object") {
        // Promote a handful of fields the scheduling MCP tools commonly return.
        const promoted = ["recommended_action", "decision", "http_status", "success", "order_id"]
          .filter((k) => k in parsed)
          .map((k) => `${k}: ${String((parsed as Record<string, unknown>)[k])}`)
          .join(" · ");
        if (promoted) return promoted;
      }
    } catch {
      // Not JSON — fall through to the raw-text path.
    }
  }
  const oneLine = trimmed.replace(/\s+/g, " ");
  return oneLine.length > 240 ? `${oneLine.slice(0, 237)}…` : oneLine;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<SessionInfo | null>(
    null
  );
  const [activeTools, setActiveTools] = useState<ToolEvent[]>([]);
  /**
   * Persistent audit trail for the current session. Accumulates across every
   * ``sendMessage`` call so the Action Trail pane can show what the agent
   * has done all session, not just the current turn.
   */
  const [actionTrail, setActionTrail] = useState<ActionTrailEntry[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const createSession = useCallback(
    async (
      model?: string,
      mcpServers?: Array<{
        name: string;
        type: "http" | "sse";
        url: string;
        headers?: Record<string, string>;
        tools: string[];
      }>,
      workspacePath?: string
    ) => {
      try {
        setError(null);
        const mcpRecord = mcpServers?.reduce(
          (acc, s) => {
            acc[s.name] = {
              type: s.type,
              url: s.url,
              headers: s.headers,
              tools: s.tools,
            };
            return acc;
          },
          {} as Record<
            string,
            {
              type: "http" | "sse";
              url: string;
              headers?: Record<string, string>;
              tools: string[];
            }
          >
        );

        const res = await fetch(`${API_BASE}/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model,
            ...(mcpRecord && Object.keys(mcpRecord).length > 0
              ? { mcpServers: mcpRecord }
              : {}),
            ...(workspacePath ? { workspacePath } : {}),
          }),
        });
        if (!res.ok)
          throw new Error(`Failed to create session: ${res.status}`);
        const session: SessionInfo = await res.json();
        setCurrentSession(session);
        setMessages([]);
        setActionTrail([]);
        return session;
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : "Failed to create session";
        setError(msg);
        throw err;
      }
    },
    []
  );

  const loadSessionMessages = useCallback(async (sessionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
      if (res.ok) {
        const msgs: ChatMessage[] = await res.json();
        setMessages(msgs);
        // Switching sessions resets the in-memory audit trail. The trail
        // is per-session and not persisted server-side.
        setActionTrail([]);
      }
    } catch {
      // Silently fail
    }
  }, []);

  const sendMessage = useCallback(
    async (prompt: string) => {
      if (!currentSession) {
        setError("No active session");
        return;
      }

      setIsLoading(true);
      setError(null);
      setActiveTools([]);
      setStreamingContent("");

      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: prompt,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      abortRef.current = new AbortController();

      const toolEvents: ToolEvent[] = [];
      let reasoning = "";
      let accumulatedContent = "";
      let receivedAssistantMessage = false;
      let toolUpdateTimer: ReturnType<typeof setTimeout> | null = null;

      const flushToolUpdates = () => {
        toolUpdateTimer = null;
        setActiveTools([...toolEvents]);
      };
      const scheduleToolUpdate = () => {
        if (!toolUpdateTimer) {
          toolUpdateTimer = setTimeout(flushToolUpdates, 50);
        }
      };

      try {
        const res = await fetch(`${API_BASE}/chat/${currentSession.id}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt }),
          signal: abortRef.current.signal,
        });

        if (!res.ok) throw new Error(`Chat failed: ${res.status}`);

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) throw new Error("No response body");

        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const events = buffer.split("\n\n");
          buffer = events.pop() ?? "";

          for (const event of events) {
            const lines = event.split("\n");
            let eventType = "message";
            let dataStr = "";

            for (const line of lines) {
              if (line.startsWith("event: ")) {
                eventType = line.slice(7).trim();
              } else if (line.startsWith("data: ")) {
                dataStr = line.slice(6);
              }
            }

            if (eventType === "done" || !dataStr) continue;
            if (eventType === "error") {
              try {
                const errData = JSON.parse(dataStr);
                setError(errData.message);
              } catch {
                setError("Unknown error");
              }
              continue;
            }

            try {
              const data = JSON.parse(dataStr);

              switch (eventType) {
                case "tool_start": {
                  const evt: ToolEvent = {
                    type: "start",
                    toolCallId: data.toolCallId,
                    toolName: data.mcpToolName ?? data.toolName,
                    mcpServerName: data.mcpServerName,
                    timestamp: new Date().toISOString(),
                  };
                  toolEvents.push(evt);
                  scheduleToolUpdate();
                  break;
                }

                case "tool_progress": {
                  const evt: ToolEvent = {
                    type: "progress",
                    toolCallId: data.toolCallId,
                    message: data.message,
                    timestamp: new Date().toISOString(),
                  };
                  toolEvents.push(evt);
                  scheduleToolUpdate();
                  break;
                }

                case "tool_complete": {
                  const evt: ToolEvent = {
                    type: "complete",
                    toolCallId: data.toolCallId,
                    success: data.success,
                    content: data.content,
                    error: data.error,
                    timestamp: new Date().toISOString(),
                  };
                  toolEvents.push(evt);
                  scheduleToolUpdate();

                  // Record into the persistent action trail. Pair with the
                  // matching tool_start to recover the tool name (the
                  // complete event does not carry it).
                  const startEvt = [...toolEvents]
                    .reverse()
                    .find(
                      (e) => e.type === "start" && e.toolCallId === data.toolCallId
                    );
                  const trailEntry: ActionTrailEntry = {
                    id: `${data.toolCallId ?? crypto.randomUUID()}-${Date.now()}`,
                    timestamp: evt.timestamp,
                    toolName: startEvt?.toolName ?? "tool",
                    mcpServerName: startEvt?.mcpServerName,
                    success: data.success !== false,
                    summary: summariseToolContent(
                      typeof data.content === "string" ? data.content : undefined
                    ),
                    error: typeof data.error === "string" ? data.error : undefined,
                    triggeredBy: prompt,
                  };
                  setActionTrail((prev) => [...prev, trailEntry]);
                  break;
                }

                case "subagent_start": {
                  const evt: ToolEvent = {
                    type: "subagent_start",
                    toolCallId: data.toolCallId,
                    agentName: data.name,
                    timestamp: new Date().toISOString(),
                  };
                  toolEvents.push(evt);
                  scheduleToolUpdate();
                  break;
                }

                case "subagent_end": {
                  const evt: ToolEvent = {
                    type: "subagent_end",
                    toolCallId: data.toolCallId,
                    agentName: data.name,
                    success: data.success,
                    timestamp: new Date().toISOString(),
                  };
                  toolEvents.push(evt);
                  scheduleToolUpdate();
                  break;
                }

                case "intent": {
                  const evt: ToolEvent = {
                    type: "progress",
                    message: `Intent: ${data.intent}`,
                    timestamp: new Date().toISOString(),
                  };
                  toolEvents.push(evt);
                  scheduleToolUpdate();
                  break;
                }

                case "reasoning_delta": {
                  reasoning += data.content ?? "";
                  break;
                }

                case "message_delta": {
                  accumulatedContent += data.content ?? "";
                  setStreamingContent(
                    (prev) => prev + (data.content ?? "")
                  );
                  break;
                }

                case "assistant_message": {
                  receivedAssistantMessage = true;
                  const assistantMsg: ChatMessage = {
                    ...data,
                    // Fallback: use accumulated deltas if server content is empty
                    content: data.content || accumulatedContent || "",
                    toolEvents:
                      toolEvents.length > 0 ? [...toolEvents] : undefined,
                    reasoning: reasoning || undefined,
                  };
                  setMessages((prev) => [...prev, assistantMsg]);
                  setStreamingContent("");
                  setActiveTools([]);
                  break;
                }

                default:
                  if (data.role === "assistant" && data.content) {
                    setMessages((prev) => [...prev, data]);
                  }
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        const msg =
          err instanceof Error ? err.message : "Failed to send message";
        setError(msg);
      } finally {
        if (toolUpdateTimer) clearTimeout(toolUpdateTimer);
        setIsLoading(false);
        // If we accumulated content but never received assistant_message,
        // save it as the assistant response to avoid losing content
        if (accumulatedContent && !receivedAssistantMessage) {
          const fallbackMsg: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: accumulatedContent,
            timestamp: new Date().toISOString(),
            toolEvents: toolEvents.length > 0 ? [...toolEvents] : undefined,
            reasoning: reasoning || undefined,
          };
          setMessages((prev) => [...prev, fallbackMsg]);
        }
        setStreamingContent("");
        abortRef.current = null;
      }
    },
    [currentSession]
  );

  const stopGeneration = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
    setStreamingContent("");
    setActiveTools([]);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    messages,
    isLoading,
    error,
    currentSession,
    activeTools,
    actionTrail,
    streamingContent,
    createSession,
    sendMessage,
    stopGeneration,
    clearMessages,
    setError,
    loadSessionMessages,
    setCurrentSession,
  };
}

import { useState, useCallback, useEffect } from "react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { ChatContainer } from "./components/ChatContainer";
import { InputBar } from "./components/InputBar";
import { SettingsDrawer, type McpServerEntry } from "./components/SettingsDrawer";
import { WorkspacePanel } from "./components/WorkspacePanel";
import { WorkOrdersPane } from "./components/WorkOrdersPane";
import { ActionTrailPane } from "./components/ActionTrailPane";
import { useChat } from "./hooks/useChat";
import { useSessions } from "./hooks/useSessions";

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [mcpServers, setMcpServers] = useState<McpServerEntry[]>([]);
  const [activeFolder, setActiveFolder] = useState("");
  const [resumingId, setResumingId] = useState<string | null>(null);
  const [userName, setUserName] = useState<string>("");
  /**
   * Prefill payload pushed into the InputBar when the user clicks a button
   * in the Work Orders pane. ``nonce`` ensures the same prompt twice in a
   * row still re-runs the effect that fills the textarea.
   */
  const [inputPrefill, setInputPrefill] = useState<{ text: string; nonce: number } | null>(null);

  const handlePrefillPrompt = useCallback((text: string) => {
    setInputPrefill({ text, nonce: Date.now() });
  }, []);

  // Fetch user identity
  useEffect(() => {
    fetch("/api/me")
      .then((r) => r.ok ? r.json() : null)
      .then((data) => { if (data?.userName) setUserName(data.userName); })
      .catch(() => {});
  }, []);

  const {
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
    setError,
    loadSessionMessages,
    setCurrentSession,
  } = useChat();
  const {
    sessions,
    fetchSessions,
    deleteSession: removeSession,
    resumeSession,
    renameSession,
  } = useSessions();

  const handleNewSession = useCallback(async (model?: string) => {
    try {
      const wsPath = activeFolder || undefined;
      await createSession(model, mcpServers.length > 0 ? mcpServers : undefined, wsPath);
      await fetchSessions();
    } catch {
      // Error handled in hook
    }
  }, [createSession, fetchSessions, mcpServers, activeFolder]);

  const handleNewChatClick = useCallback(() => {
    handleNewSession("gpt-5.4");
  }, [handleNewSession]);

  const handleSelectSession = useCallback(
    async (id: string) => {
      const session = sessions.find((s) => s.id === id);
      if (!session) return;

      if (session.active) {
        // Already active in memory — just switch to it
        setCurrentSession(session);
        await loadSessionMessages(id);
      } else {
        // Paused session — needs resume
        setResumingId(id);
        try {
          const resumed = await resumeSession(id);
          if (resumed) {
            setCurrentSession(resumed);
            await loadSessionMessages(id);
            await fetchSessions();
          }
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to resume session");
        } finally {
          setResumingId(null);
        }
      }
    },
    [sessions, setCurrentSession, loadSessionMessages, resumeSession, fetchSessions, setError]
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      await removeSession(id);
      if (currentSession?.id === id) {
        setCurrentSession(null);
      }
    },
    [removeSession, currentSession, setCurrentSession]
  );

  const handleChangeModel = useCallback(async (model: string) => {
    setSettingsOpen(false);
    await handleNewSession(model);
  }, [handleNewSession]);

  // Wrap sendMessage to auto-label session from first user message
  const handleSendMessage = useCallback(async (prompt: string) => {
    const isFirstMessage = messages.length === 0;
    await sendMessage(prompt);
    if (isFirstMessage && currentSession?.id) {
      // Generate a short label from the prompt (first 50 chars)
      const label = prompt.length > 50
        ? prompt.slice(0, 50).trimEnd() + "…"
        : prompt;
      renameSession(currentSession.id, label);
      fetchSessions();
    }
  }, [sendMessage, messages.length, currentSession, renameSession, fetchSessions]);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <Header
        sessionModel={currentSession?.model ?? null}
        isConnected={currentSession !== null}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenWorkspace={() => setWorkspaceOpen(true)}
        userName={userName}
      />

      {error && (
        <div className="px-3 sm:px-4 py-2 bg-red-950/50 border-b border-red-900/50 flex items-center justify-between">
          <p className="text-sm text-red-400 flex-1 min-w-0 break-words">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-xs text-red-500 hover:text-red-400 ml-2 shrink-0 p-1"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        <Sidebar
          sessions={sessions}
          activeSessionId={currentSession?.id ?? null}
          onNewSession={handleNewChatClick}
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          resumingId={resumingId}
        />

        <WorkOrdersPane onPrefillPrompt={handlePrefillPrompt} />

        <div className="flex-1 flex flex-col min-w-0">
          {resumingId ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="w-10 h-10 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-zinc-500">Resuming session…</p>
              </div>
            </div>
          ) : (
            <ChatContainer
              messages={messages}
              isLoading={isLoading}
              hasSession={currentSession !== null}
              onNewSession={handleNewChatClick}
              activeTools={activeTools}
              streamingContent={streamingContent}
            />
          )}

          <InputBar
            onSend={handleSendMessage}
            onStop={stopGeneration}
            isLoading={isLoading}
            disabled={currentSession === null}
            prefill={inputPrefill}
          />
        </div>

        <ActionTrailPane entries={actionTrail} />
      </div>

      <SettingsDrawer
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        mcpServers={mcpServers}
        onUpdateMcpServers={setMcpServers}
        currentModel={currentSession?.model ?? ""}
        onChangeModel={handleChangeModel}
        workspacePath={activeFolder || null}
      />

      <WorkspacePanel
        isOpen={workspaceOpen}
        onClose={() => setWorkspaceOpen(false)}
        sessionId={currentSession?.id ?? null}
        activeFolder={activeFolder}
        onFolderChange={setActiveFolder}
      />
    </div>
  );
}

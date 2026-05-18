import { useRef, useEffect } from "react";
import { MessageSquare, Sparkles } from "lucide-react";
import { MessageBubble } from "./MessageBubble";
import { ToolProgress } from "./ToolProgress";
import type { ChatMessage, ToolEvent } from "../types";

interface ChatContainerProps {
  messages: ChatMessage[];
  isLoading: boolean;
  hasSession: boolean;
  onNewSession: () => void;
  activeTools?: ToolEvent[];
  streamingContent?: string;
}

export function ChatContainer({
  messages,
  isLoading,
  hasSession,
  onNewSession,
  activeTools = [],
  streamingContent = "",
}: ChatContainerProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, activeTools, streamingContent]);

  if (!hasSession) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md px-6">
          <div className="w-16 h-16 rounded-2xl bg-brand-600/10 flex items-center justify-center mx-auto mb-6">
            <Sparkles className="w-8 h-8 text-brand-400" />
          </div>
          <h2 className="text-2xl font-semibold mb-3">
            Welcome to Openreach DispatchAI
          </h2>
          <p className="text-zinc-500 text-sm mb-6 leading-relaxed">
            Your scheduling copilot for BT Openreach field operations.
            Start a chat to triage work orders, run the scheduling skills,
            and push live activities into IFS PSO.
          </p>
          <button
            onClick={onNewSession}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium transition-colors"
          >
            <MessageSquare className="w-4 h-4" />
            Start New Chat
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl lg:max-w-4xl mx-auto">
        {messages.length === 0 && !isLoading ? (
          <div className="flex items-center justify-center h-full py-20">
            <div className="text-center">
              <div className="w-12 h-12 rounded-xl bg-zinc-900 flex items-center justify-center mx-auto mb-4">
                <MessageSquare className="w-6 h-6 text-zinc-600" />
              </div>
              <p className="text-zinc-500 text-sm">
                Send a message to begin
              </p>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id}>
              {/* Show tool events BEFORE the assistant response */}
              {msg.role === "assistant" && msg.toolEvents && msg.toolEvents.length > 0 && (
                <ToolProgress events={msg.toolEvents} />
              )}
              <MessageBubble message={msg} />
            </div>
          ))
        )}

        {/* Live tool progress while processing */}
        {isLoading && activeTools.length > 0 && (
          <ToolProgress events={activeTools} isLive />
        )}

        {/* Streaming content preview */}
        {isLoading && streamingContent && (
          <div className="flex gap-3 px-4 py-4 bg-zinc-900/50">
            <div className="w-7 h-7 rounded-lg bg-brand-600/20 flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4 text-brand-400" />
            </div>
            <div className="prose prose-invert prose-sm max-w-none text-sm text-zinc-300 whitespace-pre-wrap">
              {streamingContent}
              <span className="inline-block w-2 h-4 bg-brand-400 animate-pulse ml-0.5" />
            </div>
          </div>
        )}

        {/* Loading indicator (only when no streaming content or tools) */}
        {isLoading && !streamingContent && activeTools.length === 0 && (
          <div className="flex gap-3 px-4 py-4 bg-zinc-900/50">
            <div className="w-7 h-7 rounded-lg bg-brand-600/20 flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4 text-brand-400 animate-pulse" />
            </div>
            <div className="flex items-center gap-1 pt-2">
              <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce [animation-delay:0ms]" />
              <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce [animation-delay:150ms]" />
              <span className="w-2 h-2 rounded-full bg-brand-500 animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}

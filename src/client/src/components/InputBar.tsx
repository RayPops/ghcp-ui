import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from "react";
import { Send, Square, Loader2, Mic, MicOff } from "lucide-react";
import { useSpeechToText } from "../hooks/useSpeechToText";

const VOICE_LANGUAGES = [
  { code: "en-US", label: "EN" },
  { code: "it-IT", label: "IT" },
  { code: "es-ES", label: "ES" },
  { code: "fr-FR", label: "FR" },
  { code: "de-DE", label: "DE" },
  { code: "pt-BR", label: "PT" },
  { code: "ja-JP", label: "JA" },
  { code: "zh-CN", label: "ZH" },
] as const;

function getSavedVoiceLang(): string {
  try { return localStorage.getItem("ghcp-voice-lang") ?? "en-US"; }
  catch { return "en-US"; }
}

interface InputBarProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isLoading: boolean;
  disabled: boolean;
  /**
   * Programmatic prefill — when this object reference changes, the textarea is
   * reset to ``text`` and focused so the user can review and press Enter. The
   * ``nonce`` field lets the parent prefill the same string twice in a row.
   */
  prefill?: { text: string; nonce: number } | null;
}

export function InputBar({ onSend, onStop, isLoading, disabled, prefill }: InputBarProps) {
  const [input, setInput] = useState("");
  const [voiceLang, setVoiceLang] = useState(getSavedVoiceLang);
  const [showLangPicker, setShowLangPicker] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const langPickerRef = useRef<HTMLDivElement>(null);

  // Apply external prefill requests (e.g. from the Work Orders pane).
  useEffect(() => {
    if (prefill && prefill.text) {
      setInput(prefill.text);
      requestAnimationFrame(() => {
        const ta = textareaRef.current;
        if (ta) {
          ta.focus();
          ta.selectionStart = ta.selectionEnd = ta.value.length;
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill]);

  const handleSttResult = useCallback((transcript: string) => {
    setInput(transcript);
  }, []);

  const {
    isListening,
    interimTranscript,
    isSupported: sttSupported,
    toggleListening,
    stopListening,
    error: sttError,
  } = useSpeechToText({ lang: voiceLang, onResult: handleSttResult });

  const handleLangChange = useCallback((code: string) => {
    setVoiceLang(code);
    setShowLangPicker(false);
    try { localStorage.setItem("ghcp-voice-lang", code); } catch { /* noop */ }
  }, []);

  // Close lang picker on outside click
  useEffect(() => {
    if (!showLangPicker) return;
    const handler = (e: MouseEvent) => {
      if (langPickerRef.current && !langPickerRef.current.contains(e.target as Node)) {
        setShowLangPicker(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showLangPicker]);

  useEffect(() => {
    if (!isLoading && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isLoading]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
    }
  }, [input, interimTranscript]);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading || disabled) return;
    stopListening();
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const displayValue = interimTranscript
    ? `${input}${input ? " " : ""}${interimTranscript}`
    : input;

  return (
    <div className="border-t border-zinc-800 bg-zinc-950 px-3 sm:px-4 py-3 safe-bottom">
      <div className="max-w-3xl mx-auto">
        {/* STT error banner */}
        {sttError && (
          <p className="text-xs text-red-400 mb-1.5 px-1">{sttError}</p>
        )}

        <div
          className={`flex items-end gap-2 rounded-xl border bg-zinc-900 px-3 sm:px-4 py-2 transition-colors ${
            isListening
              ? "border-red-500/60 shadow-[0_0_12px_rgba(239,68,68,0.15)]"
              : "border-zinc-700 focus-within:border-brand-500"
          }`}
        >
          <textarea
            ref={textareaRef}
            value={displayValue}
            onChange={(e) => {
              setInput(e.target.value);
            }}
            onKeyDown={handleKeyDown}
            placeholder={
              disabled
                ? "Create a new chat to get started…"
                : isListening
                  ? "Listening… speak now"
                  : "Message Copilot…"
            }
            disabled={disabled || isLoading}
            rows={1}
            className="flex-1 bg-transparent resize-none text-sm sm:text-base text-zinc-100 placeholder-zinc-600 outline-none py-1.5 max-h-[200px]"
          />

          {/* Voice input: language picker + mic button */}
          {sttSupported && !isLoading && (
            <div className="flex items-center gap-0.5 relative" ref={langPickerRef}>
              {/* Language picker toggle */}
              <button
                onClick={() => setShowLangPicker((v) => !v)}
                disabled={disabled}
                className="px-1.5 py-1 rounded-md text-[10px] font-medium text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors disabled:text-zinc-700"
                title="Voice language"
              >
                {VOICE_LANGUAGES.find((l) => l.code === voiceLang)?.label ?? "EN"}
              </button>

              {/* Language dropdown */}
              {showLangPicker && (
                <div className="absolute bottom-full right-0 mb-1 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl py-1 z-50 min-w-[100px]">
                  {VOICE_LANGUAGES.map((l) => (
                    <button
                      key={l.code}
                      onClick={() => handleLangChange(l.code)}
                      className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                        l.code === voiceLang
                          ? "text-brand-400 bg-zinc-700/50"
                          : "text-zinc-300 hover:bg-zinc-700"
                      }`}
                    >
                      {l.label}
                    </button>
                  ))}
                </div>
              )}

              {/* Mic button */}
              <button
                onClick={toggleListening}
                disabled={disabled}
                className={`p-2.5 rounded-lg transition-colors shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center ${
                  isListening
                    ? "bg-red-600/20 text-red-400 hover:bg-red-600/30 animate-pulse"
                    : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 disabled:text-zinc-700"
                }`}
                title={isListening ? "Stop listening" : "Voice input"}
              >
                {isListening ? (
                  <MicOff className="w-4 h-4" />
                ) : (
                  <Mic className="w-4 h-4" />
                )}
              </button>
            </div>
          )}

          {isLoading ? (
            <button
              onClick={onStop}
              className="p-2.5 rounded-lg bg-red-600/20 text-red-400 hover:bg-red-600/30 transition-colors shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center"
              title="Stop generating"
            >
              <Square className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || disabled}
              className="p-2.5 rounded-lg bg-brand-600 text-white hover:bg-brand-500 disabled:bg-zinc-800 disabled:text-zinc-600 transition-colors shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center"
              title="Send message"
            >
              {disabled ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          )}
        </div>

        <p className="text-[10px] text-zinc-700 text-center mt-2">
          Powered by GitHub Copilot SDK • Azure AI Foundry
        </p>
      </div>
    </div>
  );
}

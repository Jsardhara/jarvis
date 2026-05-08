"use client";

import { Mic, MicOff, Send } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useChatTurns } from "@/hooks/useChatTurns";
import { useBrowserSpeech } from "@/hooks/useBrowserSpeech";

/**
 * Inline conversation surface for Mission Control.
 *
 * Persists every turn to ``state/chat_turns.jsonl`` via existing
 * ``POST /api/jarvis/chat`` (server-side already wires SSE + persistence).
 * Cold-loads recent turns from ``GET /api/jarvis/turns``.
 *
 * Push-to-talk uses the browser SpeechRecognition API; replies can
 * be voiced back via ``speechSynthesis``.
 */
export function ConversationPanel() {
  const { turns, streaming, send } = useChatTurns(30);
  const [input, setInput] = useState("");
  const [voiceReply, setVoiceReply] = useState(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const lastSpokenRef = useRef<string>("");

  const handleFinal = useCallback(
    (text: string) => {
      if (!text) return;
      void send(text);
    },
    [send]
  );

  const speech = useBrowserSpeech({
    onFinal: handleFinal,
    voiceReply,
  });

  // Auto-scroll on new content
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, streaming]);

  // Voice the latest assistant reply once it stops streaming
  useEffect(() => {
    if (!voiceReply || streaming || turns.length === 0) return;
    const last = turns[turns.length - 1];
    if (!last.assistant_text) return;
    if (last.turn_id === lastSpokenRef.current) return;
    lastSpokenRef.current = last.turn_id;
    speech.speak(last.assistant_text);
  }, [turns, streaming, voiceReply, speech]);

  const submit = useCallback(() => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    void send(text);
  }, [input, streaming, send]);

  return (
    <section
      aria-label="Conversation"
      className="ops-panel flex flex-col gap-2 px-3 py-2"
    >
      <header className="flex items-center justify-between text-[11px] uppercase tracking-wide text-[var(--ops-fg-mute)]">
        <span className="font-mono">CONVERSATION</span>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 font-mono text-[10px] text-[var(--ops-fg-dim)]">
            <input
              type="checkbox"
              checked={voiceReply}
              onChange={(e) => setVoiceReply(e.target.checked)}
              className="accent-[var(--ops-amber)]"
            />
            voice reply
          </label>
          <span className="font-mono text-[10px] text-[var(--ops-fg-faint)]">
            {turns.length} turns · {streaming ? "streaming…" : "idle"}
          </span>
        </div>
      </header>

      <div
        ref={scrollRef}
        className="flex h-[260px] flex-col gap-1.5 overflow-y-auto py-1 pr-1"
      >
        {turns.length === 0 && (
          <p className="font-mono text-[11px] text-[var(--ops-fg-faint)]">
            no history yet — say something
          </p>
        )}
        {turns.map((t) => (
          <div key={t.turn_id} className="flex flex-col gap-0.5">
            <p className="font-mono text-[12px] text-[var(--ops-fg)]">
              <span className="mr-2 text-[var(--ops-amber)]">›</span>
              {t.user_text}
            </p>
            {t.assistant_text && (
              <p className="font-mono text-[12px] text-[var(--ops-fg-mute)]">
                <span className="mr-2 text-[var(--ops-fg-faint)]">·</span>
                {t.assistant_text}
                {t.live && streaming && (
                  <span className="ml-1 animate-pulse text-[var(--ops-amber)]">
                    ▍
                  </span>
                )}
              </p>
            )}
          </div>
        ))}
        {speech.listening && speech.partial && (
          <p className="font-mono text-[11px] italic text-[var(--ops-info)]">
            … {speech.partial}
          </p>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onMouseDown={speech.start}
          onMouseUp={speech.stop}
          onMouseLeave={() => {
            if (speech.listening) speech.stop();
          }}
          onTouchStart={(e) => {
            e.preventDefault();
            speech.start();
          }}
          onTouchEnd={(e) => {
            e.preventDefault();
            speech.stop();
          }}
          disabled={!speech.supported || streaming}
          aria-label={speech.listening ? "Stop listening" : "Push to talk"}
          className="flex h-9 w-9 items-center justify-center border transition-colors disabled:opacity-30"
          style={{
            borderColor: speech.listening
              ? "var(--ops-crit)"
              : "var(--ops-line-faint)",
            background: speech.listening
              ? "rgba(229, 72, 77, 0.12)"
              : "var(--ops-bg-deep)",
            color: speech.listening
              ? "var(--ops-crit)"
              : "var(--ops-amber)",
          }}
          title={
            speech.supported
              ? "Hold to talk"
              : "Browser speech not supported (try Chrome/Edge)"
          }
        >
          {speech.listening ? (
            <MicOff className="h-4 w-4" />
          ) : (
            <Mic className="h-4 w-4" />
          )}
        </button>

        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={
            streaming
              ? "jarvis is replying…"
              : "type a message — Enter to send"
          }
          disabled={streaming}
          className="flex-1 border border-[var(--ops-line-faint)] bg-[var(--ops-bg-deep)] px-2 py-1.5 font-mono text-[12px] text-[var(--ops-fg)] outline-none focus:border-[var(--ops-amber)] disabled:opacity-50"
        />

        <button
          type="button"
          onClick={submit}
          disabled={!input.trim() || streaming}
          aria-label="Send"
          className="flex h-9 w-9 items-center justify-center border border-[var(--ops-amber)] bg-[var(--ops-bg-deep)] text-[var(--ops-amber)] transition-colors hover:bg-[var(--ops-bg-elevated)] disabled:opacity-30"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </section>
  );
}

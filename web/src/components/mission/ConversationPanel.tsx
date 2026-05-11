"use client";

import { Mic, MicOff, Send, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useChatTurns } from "@/hooks/useChatTurns";
import { useBrowserSpeech } from "@/hooks/useBrowserSpeech";

/**
 * Inline conversation surface for Mission Control.
 *
 * Persists every turn to ``state/chat_turns.jsonl`` via existing
 * ``POST /api/jarvis/chat`` (server already wires SSE + persistence).
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
  // Turn IDs that existed at mount/first-hydration — these are historical
  // replies the operator already heard. Never speak them aloud.
  const historicalIdsRef = useRef<Set<string> | null>(null);

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

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, streaming]);

  useEffect(() => {
    // First time turns becomes non-empty → snapshot historical IDs and bail.
    // (Initial empty array is skipped so the snapshot happens after server
    // hydration completes, even when there is no history at all.)
    if (historicalIdsRef.current === null) {
      if (turns.length === 0) return;
      historicalIdsRef.current = new Set(turns.map((t) => t.turn_id));
      return;
    }

    if (!voiceReply || streaming || turns.length === 0) return;
    const last = turns[turns.length - 1];
    if (!last.assistant_text) return;
    if (last.turn_id === lastSpokenRef.current) return;
    // Skip anything that was already on screen at mount.
    if (historicalIdsRef.current.has(last.turn_id)) return;
    lastSpokenRef.current = last.turn_id;
    speech.speak(last.assistant_text);
  }, [turns, streaming, voiceReply, speech]);

  useEffect(() => {
    if (!voiceReply) speech.cancelSpeak();
  }, [voiceReply, speech]);

  const submit = useCallback(() => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    void send(text);
  }, [input, streaming, send]);

  return (
    <section
      aria-label="Conversation"
      className="ops-panel relative flex flex-col overflow-hidden"
    >
      {/* Header */}
      <header className="flex items-center justify-between border-b border-[var(--ops-line-faint)] px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div
            aria-hidden
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background: streaming
                ? "var(--ops-amber)"
                : "var(--ops-fg-faint)",
              boxShadow: streaming
                ? "0 0 8px var(--ops-amber-glow)"
                : "none",
            }}
          />
          <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--ops-fg-mute)]">
            Conversation
          </span>
          <span className="font-mono text-[10px] text-[var(--ops-fg-faint)]">
            {turns.length} turn{turns.length === 1 ? "" : "s"}
            {streaming ? " · streaming" : ""}
          </span>
        </div>
        <VoiceToggle on={voiceReply} onChange={setVoiceReply} />
      </header>

      {/* History */}
      <div
        ref={scrollRef}
        className="flex h-[280px] flex-col gap-3 overflow-y-auto px-4 py-3"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.018) 1px, transparent 1px)",
          backgroundSize: "20px 20px",
        }}
      >
        {turns.length === 0 && !speech.partial && <EmptyState />}

        <AnimatePresence initial={false}>
          {turns.map((t) => (
            <motion.div
              key={t.turn_id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16 }}
              className="flex flex-col gap-1.5"
            >
              {t.user_text && <Bubble role="user" text={t.user_text} ts={t.ts} />}
              {t.assistant_text && (
                <Bubble
                  role="jarvis"
                  text={t.assistant_text}
                  ts={t.ts}
                  streaming={!!t.live && streaming}
                />
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {speech.listening && speech.partial && (
          <Bubble role="user" text={speech.partial} pending />
        )}
      </div>

      {/* Composer */}
      <div className="flex items-center gap-2 border-t border-[var(--ops-line-faint)] px-4 py-3">
        <MicButton
          listening={speech.listening}
          supported={speech.supported}
          onStart={speech.start}
          onStop={speech.stop}
          disabled={streaming}
        />

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
            speech.listening
              ? "listening…"
              : streaming
                ? "jarvis is replying…"
                : "ask jarvis · enter to send"
          }
          disabled={streaming}
          aria-label="Message Jarvis"
          className="h-10 flex-1 border bg-[var(--ops-bg-deep)] px-3 font-mono text-[13px] text-[var(--ops-fg)] outline-none transition-colors placeholder:text-[var(--ops-fg-faint)] disabled:opacity-50"
          style={{ borderColor: "var(--ops-line-faint)" }}
          onFocus={(e) =>
            (e.currentTarget.style.borderColor = "var(--ops-amber)")
          }
          onBlur={(e) =>
            (e.currentTarget.style.borderColor = "var(--ops-line-faint)")
          }
        />

        <SendButton
          onClick={submit}
          disabled={!input.trim() || streaming}
        />
      </div>
    </section>
  );
}

// ─── Subcomponents ───────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
      <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--ops-fg-faint)]">
        Mission Control · Jarvis online
      </div>
      <p className="max-w-[280px] font-mono text-[11px] text-[var(--ops-fg-dim)]">
        Type or hold the mic. Every turn is saved to long-term memory.
      </p>
    </div>
  );
}

interface BubbleProps {
  role: "user" | "jarvis";
  text: string;
  ts?: string;
  streaming?: boolean;
  pending?: boolean;
}

function Bubble({ role, text, ts, streaming, pending }: BubbleProps) {
  const isUser = role === "user";
  return (
    <div
      className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div className="flex max-w-[78%] flex-col gap-0.5">
        <div className="flex items-center gap-1.5 px-0.5 text-[9px] font-mono uppercase tracking-wider">
          <span
            style={{
              color: isUser ? "var(--ops-amber)" : "var(--ops-agent-tempo)",
            }}
          >
            {isUser ? "you" : "jarvis"}
          </span>
          {ts && (
            <span className="text-[var(--ops-fg-faint)]">{shortTime(ts)}</span>
          )}
        </div>
        <div
          className={`whitespace-pre-wrap px-3 py-2 font-mono text-[12.5px] leading-relaxed ${pending ? "italic" : ""}`}
          style={{
            background: isUser
              ? "rgba(242, 160, 61, 0.08)"
              : "var(--ops-bg-elevated)",
            borderLeft: `2px solid ${
              isUser ? "var(--ops-amber)" : "var(--ops-agent-tempo)"
            }`,
            color: pending
              ? "var(--ops-fg-mute)"
              : isUser
                ? "var(--ops-fg)"
                : "var(--ops-fg-mute)",
          }}
        >
          {text}
          {streaming && (
            <span
              className="ml-0.5 inline-block animate-pulse"
              style={{ color: "var(--ops-amber)" }}
            >
              ▍
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

interface MicButtonProps {
  listening: boolean;
  supported: boolean;
  onStart: () => void;
  onStop: () => void;
  disabled?: boolean;
}

function MicButton({
  listening,
  supported,
  onStart,
  onStop,
  disabled,
}: MicButtonProps) {
  return (
    <motion.button
      type="button"
      onMouseDown={onStart}
      onMouseUp={onStop}
      onMouseLeave={() => listening && onStop()}
      onTouchStart={(e) => {
        e.preventDefault();
        onStart();
      }}
      onTouchEnd={(e) => {
        e.preventDefault();
        onStop();
      }}
      disabled={!supported || disabled}
      aria-label={listening ? "Stop listening" : "Push to talk"}
      title={
        supported
          ? "Hold to talk"
          : "Browser speech not supported (Chrome/Edge only)"
      }
      animate={
        listening
          ? {
              boxShadow: [
                "0 0 0 0 rgba(229, 72, 77, 0.55)",
                "0 0 0 10px rgba(229, 72, 77, 0)",
              ],
            }
          : { boxShadow: "0 0 0 0 rgba(0,0,0,0)" }
      }
      transition={{
        duration: 1.1,
        repeat: listening ? Infinity : 0,
        ease: "easeOut",
      }}
      className="relative flex h-10 w-10 items-center justify-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-30"
      style={{
        borderColor: listening
          ? "var(--ops-crit)"
          : "var(--ops-line-faint)",
        background: listening
          ? "rgba(229, 72, 77, 0.10)"
          : "var(--ops-bg-deep)",
        color: listening ? "var(--ops-crit)" : "var(--ops-amber)",
      }}
    >
      {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
    </motion.button>
  );
}

function SendButton({
  onClick,
  disabled,
}: {
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label="Send"
      className="flex h-10 w-10 items-center justify-center rounded-full border transition-all disabled:cursor-not-allowed disabled:opacity-30"
      style={{
        borderColor: disabled
          ? "var(--ops-line-faint)"
          : "var(--ops-amber)",
        background: disabled
          ? "var(--ops-bg-deep)"
          : "rgba(242, 160, 61, 0.12)",
        color: disabled ? "var(--ops-fg-faint)" : "var(--ops-amber)",
      }}
    >
      <Send className="h-4 w-4" />
    </button>
  );
}

function VoiceToggle({
  on,
  onChange,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className="group flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider transition-colors"
      style={{ color: on ? "var(--ops-amber)" : "var(--ops-fg-dim)" }}
    >
      {on ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
      <span>{on ? "voice reply" : "muted"}</span>
      <span
        className="relative inline-block h-3.5 w-7 rounded-full border transition-colors"
        style={{
          borderColor: on ? "var(--ops-amber)" : "var(--ops-line-faint)",
          background: on ? "rgba(242,160,61,0.20)" : "var(--ops-bg-deep)",
        }}
      >
        <span
          className="absolute top-1/2 h-2 w-2 -translate-y-1/2 rounded-full transition-all"
          style={{
            left: on ? "calc(100% - 10px)" : "2px",
            background: on ? "var(--ops-amber)" : "var(--ops-fg-faint)",
          }}
        />
      </span>
    </button>
  );
}

function shortTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

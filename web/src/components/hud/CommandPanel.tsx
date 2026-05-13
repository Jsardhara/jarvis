"use client";

import {
  Mic,
  Pause,
  Play,
  Send,
  SkipBack,
  SkipForward,
  Square,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useChatTurns } from "@/hooks/useChatTurns";
import { useBrowserSpeech } from "@/hooks/useBrowserSpeech";

/**
 * HUD command panel — sits below the central orb.
 *
 *   header     // BOT PLAYING / ON CMD CHANNEL
 *   transport  ⏮  ⏹  ▶  ⏭  ●          (cyan outline circles)
 *   log        green-on-black mono recent turns
 *   composer   text input + DONE + MIC
 */
export function CommandPanel() {
  const { turns, streaming, send } = useChatTurns(20);
  const [input, setInput] = useState("");
  const [paused, setPaused] = useState(false);
  const logRef = useRef<HTMLDivElement | null>(null);
  const lastSpokenRef = useRef<string>("");
  const historicalIdsRef = useRef<Set<string> | null>(null);

  const handleFinal = useCallback(
    (text: string) => {
      if (!text) return;
      void send(text);
    },
    [send],
  );

  const speech = useBrowserSpeech({ onFinal: handleFinal, voiceReply: !paused });

  // Auto-scroll log
  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, streaming]);

  // Speak only NEW turns post-mount (preserves the silence-on-load fix)
  useEffect(() => {
    if (historicalIdsRef.current === null) {
      if (turns.length === 0) return;
      historicalIdsRef.current = new Set(turns.map((t) => t.turn_id));
      return;
    }
    if (paused || streaming || turns.length === 0) return;
    const last = turns[turns.length - 1];
    if (!last.assistant_text) return;
    if (last.turn_id === lastSpokenRef.current) return;
    if (historicalIdsRef.current.has(last.turn_id)) return;
    lastSpokenRef.current = last.turn_id;
    speech.speak(last.assistant_text);
  }, [turns, streaming, paused, speech]);

  const submit = useCallback(() => {
    const t = input.trim();
    if (!t || streaming) return;
    setInput("");
    void send(t);
  }, [input, streaming, send]);

  const recent = turns.slice(-3);

  return (
    <section
      aria-label="Command channel"
      className="hud-panel hud-corners flex w-full max-w-[420px] flex-col gap-2 px-3 py-2.5"
    >
      {/* Header */}
      <header className="flex items-center justify-between border-b border-[var(--ops-line-faint)] pb-2">
        <span className="hud-label">{"// BOT "}{streaming ? "STREAMING" : "STANDBY"}</span>
        <span
          className="font-mono text-[9px] tracking-wider"
          style={{ color: streaming ? "var(--ops-warn)" : "var(--ops-fg-faint)" }}
        >
          {streaming ? "ACTIVE" : "IDLE"}
        </span>
      </header>

      {/* Transport */}
      <div className="flex items-center justify-between px-2">
        <TransportBtn ariaLabel="Previous" disabled>
          <SkipBack className="h-3.5 w-3.5" />
        </TransportBtn>
        <TransportBtn
          ariaLabel="Stop"
          onClick={() => speech.cancelSpeak?.()}
        >
          <Square className="h-3 w-3" />
        </TransportBtn>
        <TransportBtn
          ariaLabel={paused ? "Resume voice reply" : "Pause voice reply"}
          highlight={!paused}
          onClick={() => setPaused((p) => !p)}
        >
          {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
        </TransportBtn>
        <TransportBtn ariaLabel="Forward" disabled>
          <SkipForward className="h-3.5 w-3.5" />
        </TransportBtn>
        <TransportBtn ariaLabel="Record indicator" disabled highlight={speech.listening}>
          <span
            className="block h-2 w-2 rounded-full"
            style={{
              background: speech.listening ? "var(--ops-crit)" : "var(--ops-fg-faint)",
              boxShadow: speech.listening ? "0 0 6px var(--ops-crit)" : "none",
            }}
          />
        </TransportBtn>
      </div>

      {/* Log strip */}
      <div
        ref={logRef}
        className="font-mono text-[10px] leading-snug"
        style={{
          height: 56,
          overflowY: "auto",
          background: "rgba(0, 0, 0, 0.40)",
          border: "1px solid var(--ops-line-faint)",
          padding: "4px 6px",
          color: "var(--ops-ok)",
        }}
      >
        <div style={{ color: "var(--ops-fg-faint)" }}>
          [ JARVIS HUD MK-VII INITIALIZED ]
        </div>
        {recent.map((t) => (
          <div key={t.turn_id} className="mt-0.5">
            {t.user_text && (
              <div style={{ color: "var(--hud-cyan)" }}>
                &gt; {t.user_text.slice(0, 80)}
              </div>
            )}
            {t.assistant_text && (
              <div style={{ color: "var(--ops-ok)" }}>
                ← {t.assistant_text.slice(0, 80)}
              </div>
            )}
          </div>
        ))}
        {speech.partial && (
          <div style={{ color: "var(--hud-cyan)", opacity: 0.6 }}>
            &gt; {speech.partial}
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="flex items-center gap-2 border-t border-[var(--ops-line-faint)] pt-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Type command here..."
          disabled={streaming}
          aria-label="Command input"
          className="h-8 flex-1 border bg-[var(--ops-bg-input)] px-2 font-mono text-[11px] outline-none transition-colors placeholder:text-[var(--ops-fg-faint)] disabled:opacity-50"
          style={{
            borderColor: "var(--ops-line)",
            color: "var(--hud-cyan)",
          }}
          onFocus={(e) =>
            (e.currentTarget.style.borderColor = "var(--hud-cyan)")
          }
          onBlur={(e) =>
            (e.currentTarget.style.borderColor = "var(--ops-line)")
          }
        />
        <ComposerBtn
          ariaLabel="Send"
          onClick={submit}
          disabled={!input.trim() || streaming}
          label="DONE"
        >
          <Send className="h-3 w-3" />
        </ComposerBtn>
        <ComposerBtn
          ariaLabel={speech.listening ? "Stop listening" : "Push to talk"}
          onMouseDown={speech.start}
          onMouseUp={speech.stop}
          onMouseLeave={() => speech.listening && speech.stop?.()}
          disabled={!speech.supported || streaming}
          label="MIC"
          alert={speech.listening}
        >
          <Mic className="h-3 w-3" />
        </ComposerBtn>
      </div>
    </section>
  );
}

// ─── Subcomponents ───────────────────────────────────────────────────────────

interface TransportBtnProps {
  children: React.ReactNode;
  ariaLabel: string;
  onClick?: () => void;
  disabled?: boolean;
  highlight?: boolean;
}

function TransportBtn({
  children,
  ariaLabel,
  onClick,
  disabled,
  highlight,
}: TransportBtnProps) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      whileTap={{ scale: 0.92 }}
      className="flex h-8 w-8 items-center justify-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-30"
      style={{
        borderColor: highlight ? "var(--hud-cyan)" : "var(--ops-line)",
        background: highlight ? "rgba(0, 229, 255, 0.10)" : "transparent",
        color: highlight ? "var(--hud-cyan-bright)" : "var(--ops-fg-mute)",
        boxShadow: highlight ? "0 0 8px rgba(0, 229, 255, 0.40)" : "none",
      }}
    >
      {children}
    </motion.button>
  );
}

interface ComposerBtnProps {
  children: React.ReactNode;
  ariaLabel: string;
  label: string;
  alert?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  onMouseDown?: () => void;
  onMouseUp?: () => void;
  onMouseLeave?: () => void;
}

function ComposerBtn({
  children,
  ariaLabel,
  label,
  alert,
  disabled,
  onClick,
  onMouseDown,
  onMouseUp,
  onMouseLeave,
}: ComposerBtnProps) {
  const color = alert ? "var(--ops-crit)" : "var(--hud-cyan)";
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseDown={onMouseDown}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseLeave}
      disabled={disabled}
      aria-label={ariaLabel}
      className="flex h-8 items-center gap-1 border px-2 transition-all disabled:cursor-not-allowed disabled:opacity-30"
      style={{
        borderColor: disabled ? "var(--ops-line-faint)" : color,
        color: disabled ? "var(--ops-fg-faint)" : color,
        background: alert ? "rgba(255, 59, 59, 0.10)" : "transparent",
        boxShadow: alert ? "0 0 8px rgba(255, 59, 59, 0.40)" : "none",
      }}
    >
      {children}
      <span className="hud-display text-[8px]">{label}</span>
    </button>
  );
}

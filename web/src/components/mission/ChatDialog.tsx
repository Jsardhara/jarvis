"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

const JARVIS_API =
  (typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765");

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
}

/**
 * Cmd/Ctrl+K modal chat. Streams from POST /api/jarvis/chat (SSE).
 * Voice strip is the primary input on Mission Control; this is the
 * keyboard fallback.
 */
export function ChatDialog() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setTurns((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setStreaming(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let assistantText = "";

    try {
      const res = await fetch(`${JARVIS_API}/api/jarvis/chat`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      setTurns((prev) => [...prev, { role: "assistant", text: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          try {
            const json = JSON.parse(trimmed.slice(6)) as {
              type?: string;
              text?: string;
            };
            if (json.type === "text" && typeof json.text === "string") {
              assistantText += json.text;
              setTurns((prev) => {
                const next = [...prev];
                next[next.length - 1] = {
                  role: "assistant",
                  text: assistantText,
                };
                return next;
              });
            }
          } catch {
            // ignore partial frames
          }
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "stream failed";
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: `[error: ${msg}]` },
      ]);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="chat-dialog"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[12vh]"
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -10, opacity: 0 }}
            className="ops-panel flex w-[640px] max-w-[90vw] flex-col gap-2 px-3 py-2"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center justify-between text-[10px] font-mono uppercase text-[var(--ops-fg-dim)]">
              <span>chat — jarvis</span>
              <span>esc · close</span>
            </header>

            <div className="flex max-h-[40vh] flex-col gap-1.5 overflow-y-auto py-1">
              {turns.length === 0 && (
                <p className="font-mono text-[11px] text-[var(--ops-fg-faint)]">
                  ask anything. routes through orchestrator.
                </p>
              )}
              {turns.map((t, i) => (
                <p
                  key={i}
                  className="font-mono text-[12px]"
                  style={{
                    color:
                      t.role === "user"
                        ? "var(--ops-fg)"
                        : "var(--ops-fg-mute)",
                  }}
                >
                  <span className="mr-2 text-[var(--ops-amber)]">
                    {t.role === "user" ? "›" : "·"}
                  </span>
                  {t.text}
                </p>
              ))}
            </div>

            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") send();
              }}
              placeholder="message…"
              className="border border-[var(--ops-line-faint)] bg-[var(--ops-bg-deep)] px-2 py-1.5 font-mono text-[12px] text-[var(--ops-fg)] outline-none focus:border-[var(--ops-amber)]"
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

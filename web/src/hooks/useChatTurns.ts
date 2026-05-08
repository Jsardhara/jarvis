"use client";

/**
 * useChatTurns
 *
 * Persistent chat history for Mission Control. Reads
 * GET /api/jarvis/turns on mount, lets the caller append a user
 * message + streamed assistant reply through POST /api/jarvis/chat,
 * and re-reads the durable history after the stream completes so the
 * panel always reflects what was persisted server-side.
 */

import { useCallback, useEffect, useState } from "react";
import { apiFetch, getApiToken } from "@/lib/api-client";

const JARVIS_API =
  (typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765");

export interface ChatTurn {
  turn_id: string;
  user_text: string;
  assistant_text: string;
  ts?: string;
  /** Live = currently streaming; false = persisted record. */
  live?: boolean;
}

interface ChatTurnsHook {
  turns: ChatTurn[];
  streaming: boolean;
  send: (text: string) => Promise<void>;
  /** Refresh from server. */
  reload: () => Promise<void>;
}

interface ServerTurnRecord {
  turn_id: string;
  user_text?: string;
  assistant_text?: string;
  ts?: string;
}

async function loadHistory(limit: number): Promise<ChatTurn[]> {
  try {
    const r = await apiFetch(
      `${JARVIS_API}/api/jarvis/turns?limit=${limit}`
    );
    if (!r.ok) return [];
    const json = (await r.json()) as { data?: ServerTurnRecord[] };
    return (json.data ?? []).map((rec) => ({
      turn_id: rec.turn_id,
      user_text: rec.user_text ?? "",
      assistant_text: rec.assistant_text ?? "",
      ts: rec.ts,
      live: false,
    }));
  } catch {
    return [];
  }
}

export function useChatTurns(historyLimit = 30): ChatTurnsHook {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [streaming, setStreaming] = useState(false);

  const reload = useCallback(async () => {
    const next = await loadHistory(historyLimit);
    setTurns(next);
  }, [historyLimit]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || streaming) return;
      setStreaming(true);

      const liveTurnId = `live-${Date.now()}`;
      setTurns((prev) => [
        ...prev,
        { turn_id: liveTurnId, user_text: message, assistant_text: "", live: true },
      ]);

      const headers: HeadersInit = { "content-type": "application/json" };
      const token = getApiToken();
      if (token) headers.Authorization = `Bearer ${token}`;

      let assistant = "";

      try {
        const res = await fetch(`${JARVIS_API}/api/jarvis/chat`, {
          method: "POST",
          headers,
          body: JSON.stringify({ message }),
        });
        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        // Stream loop — `done` flag from `reader.read()` breaks the loop.
        for (;;) {
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
                delta?: string;
              };
              if (json.type === "text" && typeof json.delta === "string") {
                assistant += json.delta;
                setTurns((prev) =>
                  prev.map((t) =>
                    t.turn_id === liveTurnId
                      ? { ...t, assistant_text: assistant }
                      : t
                  )
                );
              }
            } catch {
              // ignore partial frames
            }
          }
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "stream failed";
        setTurns((prev) =>
          prev.map((t) =>
            t.turn_id === liveTurnId
              ? { ...t, assistant_text: `[error: ${msg}]` }
              : t
          )
        );
      } finally {
        setStreaming(false);
        // Re-read durable history so the live turn flips to its real id
        void reload();
      }
    },
    [streaming, reload]
  );

  return { turns, streaming, send, reload };
}

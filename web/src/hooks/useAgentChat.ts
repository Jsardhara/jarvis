"use client";

/**
 * useAgentChat
 *
 * Manages a chat session with a specific Atlas agent.
 *
 * send(text):
 *   1. POST /api/atlas/agents/{id}/chat → returns { session_id }
 *   2. Opens EventSource SSE on /api/atlas/agents/{id}/chat/stream?session_id=...
 *   3. Appends assistant chunks to messages as they arrive
 *   4. On stream close, sets isStreaming=false
 *
 * Returns { messages, send, isStreaming, error, clear }
 */

import { useState, useRef, useCallback, useEffect } from "react";

const JARVIS_API =
  typeof process !== "undefined"
    ? (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765")
    : "http://localhost:8765";

const FETCH_TIMEOUT_MS = 10_000;

// ─── Types ────────────────────────────────────────────────────────────────────

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: string;
}

export interface AgentChatState {
  messages: ChatMessage[];
  sessionId: string | null;
  isStreaming: boolean;
}

export interface UseAgentChatReturn {
  messages: ChatMessage[];
  send: (text: string) => Promise<void>;
  isStreaming: boolean;
  error: Error | null;
  clear: () => void;
}

// ─── SSE chunk shape ──────────────────────────────────────────────────────────

interface SseChunk {
  delta?: string;
  done?: boolean;
  error?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

let _msgCounter = 0;
function nextId(): string {
  _msgCounter += 1;
  return `msg-${Date.now()}-${_msgCounter}`;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAgentChat(agentId: string): UseAgentChatReturn {
  const [chatState, setChatState] = useState<AgentChatState>({
    messages: [],
    sessionId: null,
    isStreaming: false,
  });
  const [error, setError] = useState<Error | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  // Close any open EventSource when the component unmounts.
  // Without this, navigating away from an agent page leaks the SSE
  // connection — after ~6 leaks the browser hits its per-origin cap
  // and stalls subsequent fetches (including Next.js route prefetches),
  // which manifests as sidebar links becoming unresponsive.
  useEffect(() => {
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, []);

  // Keep sessionIdRef in sync
  const updateSessionId = useCallback((id: string) => {
    sessionIdRef.current = id;
    setChatState((prev) => ({ ...prev, sessionId: id }));
  }, []);

  const send = useCallback(async (text: string) => {
    if (chatState.isStreaming) return;
    setError(null);

    // Append user message immediately
    const userMsg: ChatMessage = {
      id: nextId(),
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };

    // Placeholder assistant message that we'll stream into
    const assistantMsgId = nextId();
    const assistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
    };

    setChatState((prev) => ({
      ...prev,
      isStreaming: true,
      messages: [...prev.messages, userMsg, assistantMsg],
    }));

    try {
      // Step 1 — POST to create/continue session
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

      const res = await fetch(`${JARVIS_API}/api/atlas/agents/${agentId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionIdRef.current,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const { session_id } = (await res.json()) as { session_id: string };
      updateSessionId(session_id);

      // Step 2 — Open SSE stream
      esRef.current?.close();
      const es = new EventSource(
        `${JARVIS_API}/api/atlas/agents/${agentId}/chat/stream?session_id=${session_id}`
      );
      esRef.current = es;

      es.onmessage = (evt) => {
        try {
          const chunk = JSON.parse(evt.data) as SseChunk;

          if (chunk.error) {
            es.close();
            setError(new Error(chunk.error));
            setChatState((prev) => ({ ...prev, isStreaming: false }));
            return;
          }

          if (chunk.delta) {
            setChatState((prev) => ({
              ...prev,
              messages: prev.messages.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, content: m.content + chunk.delta }
                  : m
              ),
            }));
          }

          if (chunk.done) {
            es.close();
            setChatState((prev) => ({ ...prev, isStreaming: false }));
          }
        } catch {
          // Malformed chunk — ignore
        }
      };

      es.onerror = () => {
        es.close();
        setChatState((prev) => ({ ...prev, isStreaming: false }));
      };
    } catch (err) {
      setChatState((prev) => ({ ...prev, isStreaming: false }));
      setError(err instanceof Error ? err : new Error("send failed"));
    }
  }, [agentId, chatState.isStreaming, updateSessionId]);

  const clear = useCallback(() => {
    esRef.current?.close();
    sessionIdRef.current = null;
    setChatState({ messages: [], sessionId: null, isStreaming: false });
    setError(null);
  }, []);

  return {
    messages: chatState.messages,
    send,
    isStreaming: chatState.isStreaming,
    error,
    clear,
  };
}

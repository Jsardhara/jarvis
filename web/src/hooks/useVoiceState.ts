"use client";

/**
 * useVoiceState
 *
 * Cold-loads /api/voice/state on mount, then listens for ``voice.state``
 * WebSocket frames published by the API server when the voice loop
 * transitions between modes (idle → wake → stt → routing → tts).
 *
 * Returns the latest singleton matching `state/voice_state.json`.
 */

import { useEffect, useReducer, useRef } from "react";
import { apiFetch, getApiToken } from "@/lib/api-client";

const JARVIS_API =
  (typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765");

function wsUrl(): string {
  const base = JARVIS_API.replace(/^http/, "ws") + "/ws";
  const token = getApiToken();
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

const REST_URL = JARVIS_API + "/api/voice/state";

const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export type VoiceMode = "idle" | "wake" | "stt" | "routing" | "tts" | "offline";
export type VoiceTier = "local" | "haiku" | "sonnet" | "orchestrator" | null;

export interface VoiceState {
  mode: VoiceMode;
  tier: VoiceTier;
  last_text: string;
  last_reply_source: string | null;
  latency_ms: number;
  cost_usd: number;
  updated_at: string | null;
}

interface VoiceStateHookValue {
  state: VoiceState;
  connected: boolean;
}

const INITIAL_STATE: VoiceState = {
  mode: "idle",
  tier: null,
  last_text: "",
  last_reply_source: null,
  latency_ms: 0,
  cost_usd: 0.0,
  updated_at: null,
};

type Action =
  | { type: "open" }
  | { type: "close" }
  | { type: "state"; state: VoiceState };

function reducer(
  state: VoiceStateHookValue,
  action: Action
): VoiceStateHookValue {
  switch (action.type) {
    case "open":
      return { ...state, connected: true };
    case "close":
      return { ...state, connected: false };
    case "state":
      return { ...state, state: action.state };
    default:
      return state;
  }
}

export function useVoiceState(): VoiceStateHookValue {
  const [hook, dispatch] = useReducer(reducer, {
    state: INITIAL_STATE,
    connected: false,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;

    apiFetch(REST_URL)
      .then((r) => (r.ok ? r.json() : null))
      .then((s: VoiceState | null) => {
        if (s && mounted.current) dispatch({ type: "state", state: s });
      })
      .catch(() => {
        // Cold start may race the API — WS frames will fill the gap
      });

    function connect() {
      if (!mounted.current) return;
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mounted.current) return;
        attemptRef.current = 0;
        dispatch({ type: "open" });
      };

      ws.onmessage = (evt: MessageEvent<string>) => {
        if (!mounted.current) return;
        try {
          const frame = JSON.parse(evt.data) as {
            type: string;
            state?: VoiceState;
          };
          if (frame.type !== "voice.state") return;
          if (frame.state) dispatch({ type: "state", state: frame.state });
        } catch {
          // malformed
        }
      };

      ws.onclose = () => {
        if (!mounted.current) return;
        dispatch({ type: "close" });
        const attempt = attemptRef.current;
        const delay = Math.min(
          BACKOFF_BASE_MS * Math.pow(2, attempt),
          BACKOFF_MAX_MS
        );
        attemptRef.current = attempt + 1;
        reconnectTimer.current = setTimeout(connect, delay);
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      mounted.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, []);

  return hook;
}

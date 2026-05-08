"use client";

/**
 * useVoiceLevel
 *
 * Subscribes to ``voice.level`` WebSocket frames at ~60 Hz during
 * wake/STT phases. Holds a small ring buffer of recent RMS values for
 * the bottom-strip waveform canvas to read on each animation frame.
 *
 * Browser never gets mic permission — backend pushes the analysed
 * envelope as scalars, so the canvas only renders.
 */

import { useEffect, useRef, useState } from "react";
import { getApiToken } from "@/lib/api-client";

const JARVIS_API =
  (typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_JARVIS_API ?? "http://localhost:8765"
    : "http://localhost:8765");

function wsUrl(): string {
  const base = JARVIS_API.replace(/^http/, "ws") + "/ws";
  const token = getApiToken();
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

const RING_SIZE = 256; // ≈ 4 s at 60 Hz

export interface VoiceLevelHookValue {
  /** Latest RMS (dB-ish, 0..1 normalized). 0 means silence. */
  rms: number;
  /** Ring buffer of recent samples (oldest → newest). */
  samples: number[];
  connected: boolean;
}

export function useVoiceLevel(): VoiceLevelHookValue {
  const [rms, setRms] = useState(0);
  const [connected, setConnected] = useState(false);
  const ringRef = useRef<number[]>(new Array(RING_SIZE).fill(0));
  const writeRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;

    function connect() {
      if (!mounted.current) return;
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mounted.current) return;
        attemptRef.current = 0;
        setConnected(true);
      };

      ws.onmessage = (evt: MessageEvent<string>) => {
        if (!mounted.current) return;
        try {
          const frame = JSON.parse(evt.data) as {
            type: string;
            rms_db?: number;
          };
          if (frame.type !== "voice.level") return;
          const value =
            typeof frame.rms_db === "number" && Number.isFinite(frame.rms_db)
              ? Math.max(0, Math.min(1, frame.rms_db))
              : 0;
          ringRef.current[writeRef.current % RING_SIZE] = value;
          writeRef.current += 1;
          setRms(value);
        } catch {
          // malformed
        }
      };

      ws.onclose = () => {
        if (!mounted.current) return;
        setConnected(false);
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

  return { rms, samples: ringRef.current, connected };
}

"use client";

/**
 * useMissionBus
 *
 * Aggregator hook for the Mission Control surface. Multiplexes the
 * existing Inbox + Voice + (future) FS streams behind a single
 * mounting point so panels don't each open their own WebSocket.
 *
 * Returns a coherent snapshot used by every panel: current voice state,
 * recent inbox events, and connection health.
 */

import { useInboxStream } from "./useInboxStream";
import { useVoiceState, type VoiceState } from "./useVoiceState";
import { useVoiceLevel } from "./useVoiceLevel";

export interface MissionBus {
  /** Inbox/agent/confirmation events (LRU 200). */
  events: ReturnType<typeof useInboxStream>["events"];
  /** WebSocket connection alive. */
  connected: boolean;
  /** Last known voice loop state. */
  voice: VoiceState;
  /** Latest RMS sample for the waveform canvas. */
  voiceLevel: number;
  /** Ring buffer of recent RMS samples. */
  voiceSamples: number[];
}

export function useMissionBus(): MissionBus {
  const inbox = useInboxStream();
  const voice = useVoiceState();
  const level = useVoiceLevel();

  return {
    events: inbox.events,
    connected: inbox.connected || voice.connected || level.connected,
    voice: voice.state,
    voiceLevel: level.rms,
    voiceSamples: level.samples,
  };
}

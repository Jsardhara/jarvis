"use client";

/**
 * useBrowserSpeech — push-to-talk via Web Speech API.
 *
 * Uses ``window.SpeechRecognition`` / ``webkitSpeechRecognition`` to
 * capture short utterances directly in the browser. Returns a
 * controller the caller invokes from a button:
 *
 *   const sr = useBrowserSpeech({ onFinal: send })
 *   <button onMouseDown={sr.start} onMouseUp={sr.stop} />
 *
 * Falls back to ``supported = false`` on browsers without the API
 * (Firefox, older Safari).
 *
 * Also exposes ``speak(text)`` using ``window.speechSynthesis`` so
 * Mission Control can voice the reply back without server-side TTS.
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface SpeechRecognitionResult {
  isFinal: boolean;
  0: { transcript: string; confidence: number };
}

interface SpeechRecognitionEvent extends Event {
  results: ArrayLike<SpeechRecognitionResult>;
  resultIndex: number;
}

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((ev: SpeechRecognitionEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  onend: (() => void) | null;
}

interface SpeechWindow extends Window {
  SpeechRecognition?: { new (): SpeechRecognitionLike };
  webkitSpeechRecognition?: { new (): SpeechRecognitionLike };
}

interface UseBrowserSpeechOptions {
  onFinal?: (text: string) => void;
  /** Speak replies back via window.speechSynthesis. */
  voiceReply?: boolean;
  lang?: string;
}

export interface BrowserSpeechController {
  supported: boolean;
  listening: boolean;
  partial: string;
  start: () => void;
  stop: () => void;
  speak: (text: string) => void;
  cancelSpeak: () => void;
}

export function useBrowserSpeech(
  opts: UseBrowserSpeechOptions = {}
): BrowserSpeechController {
  const [listening, setListening] = useState(false);
  const [partial, setPartial] = useState("");
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const supportedRef = useRef(false);

  // Cache callbacks in refs so the recogniser builds once even if
  // the parent passes new closures each render.
  const onFinalRef = useRef(opts.onFinal);
  onFinalRef.current = opts.onFinal;
  const lang = opts.lang ?? "en-US";

  useEffect(() => {
    if (typeof window === "undefined") return;
    const w = window as SpeechWindow;
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) return;
    supportedRef.current = true;
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onresult = (ev: SpeechRecognitionEvent) => {
      let finalText = "";
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        const t = r[0]?.transcript ?? "";
        if (r.isFinal) finalText += t;
        else interim += t;
      }
      if (interim) setPartial(interim);
      if (finalText) {
        setPartial("");
        onFinalRef.current?.(finalText.trim());
      }
    };
    rec.onerror = () => {
      setListening(false);
    };
    rec.onend = () => {
      setListening(false);
    };

    recRef.current = rec;

    return () => {
      try {
        rec.abort();
      } catch {
        // swallow
      }
      recRef.current = null;
    };
  }, [lang]);

  const start = useCallback(() => {
    const rec = recRef.current;
    if (!rec || listening) return;
    try {
      rec.start();
      setListening(true);
      setPartial("");
    } catch {
      // already started
    }
  }, [listening]);

  const stop = useCallback(() => {
    const rec = recRef.current;
    if (!rec) return;
    try {
      rec.stop();
    } catch {
      // already stopped
    }
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (typeof window === "undefined" || !opts.voiceReply) return;
      if (!window.speechSynthesis) return;
      try {
        window.speechSynthesis.cancel();
        const utt = new SpeechSynthesisUtterance(text);
        utt.lang = opts.lang ?? "en-US";
        utt.rate = 1.05;
        window.speechSynthesis.speak(utt);
      } catch {
        // best effort
      }
    },
    [opts.lang, opts.voiceReply]
  );

  const cancelSpeak = useCallback(() => {
    if (typeof window === "undefined") return;
    if (!window.speechSynthesis) return;
    try {
      window.speechSynthesis.cancel();
    } catch {
      // best effort
    }
  }, []);

  return {
    supported: supportedRef.current,
    listening,
    partial,
    start,
    stop,
    speak,
    cancelSpeak,
  };
}

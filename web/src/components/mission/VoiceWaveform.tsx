"use client";

import { useEffect, useRef } from "react";

interface VoiceWaveformProps {
  /** Ring buffer of recent RMS samples (0..1). */
  samples: number[];
  /** Idle when there's no speech; renders a slow breathing line. */
  idle: boolean;
  /** Active hue (agent identity color or amber default). */
  color?: string;
}

/**
 * Bottom-strip live waveform. Reads the RMS ring buffer pushed from
 * the backend voice loop; canvas rAF redraws at 60 fps.
 *
 * Browser does NOT request mic permission — backend is the only audio
 * source and it pushes pre-analysed scalars over WebSocket.
 */
export function VoiceWaveform({
  samples,
  idle,
  color = "var(--ops-amber)",
}: VoiceWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const tRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio ?? 1;

    const draw = () => {
      tRef.current += 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.scale(dpr, dpr);
      }
      ctx.clearRect(0, 0, w, h);

      const accent =
        getComputedStyle(canvas).getPropertyValue("color") || "#F2A03D";
      const N = samples.length;
      const barW = w / N;

      for (let i = 0; i < N; i++) {
        let v = samples[i];
        if (idle) {
          // 1 Hz breathing
          const phase = (tRef.current / 60) * 2 * Math.PI + (i / N) * Math.PI;
          v = 0.06 + 0.04 * Math.abs(Math.sin(phase));
        }
        const bh = Math.max(1, v * h);
        ctx.fillStyle = accent;
        ctx.globalAlpha = idle ? 0.5 : 0.85;
        ctx.fillRect(i * barW, h / 2 - bh / 2, Math.max(1, barW - 1), bh);
      }
      ctx.globalAlpha = 1;

      rafRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [samples, idle]);

  return (
    <canvas
      ref={canvasRef}
      className="h-12 w-full"
      style={{ color }}
      aria-hidden
    />
  );
}

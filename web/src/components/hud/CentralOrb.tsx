"use client";

import { motion } from "framer-motion";

type OrbState = "idle" | "listening" | "speaking" | "thinking";

interface CentralOrbProps {
  state?: OrbState;
  size?: number;
  label?: string;
}

/**
 * Iron-Man HUD pulsing core. Pure CSS — radial gradient orb with a layered
 * box-shadow bloom + scale pulse. State drives glow intensity and pulse rate.
 *
 *   idle       slow gentle pulse, soft bloom
 *   listening  faster pulse, brighter cyan
 *   speaking   tight rapid pulse, white-hot core
 *   thinking   triple ring breathing
 */
export function CentralOrb({
  state = "idle",
  size = 64,
  label,
}: CentralOrbProps) {
  const intensity = INTENSITY[state];

  return (
    <div className="relative flex flex-col items-center justify-center gap-3">
      {/* Triple concentric rings (thinking sweep) */}
      {state === "thinking" && (
        <>
          {[0, 0.4, 0.8].map((delay, i) => (
            <motion.div
              key={i}
              aria-hidden
              className="absolute rounded-full border"
              style={{
                width: size + 24 + i * 18,
                height: size + 24 + i * 18,
                borderColor: "rgba(0, 229, 255, 0.30)",
              }}
              animate={{
                scale: [1, 1.18, 1],
                opacity: [0.6, 0, 0.6],
              }}
              transition={{
                duration: 2.0,
                repeat: Infinity,
                ease: "easeOut",
                delay,
              }}
            />
          ))}
        </>
      )}

      {/* The orb itself */}
      <motion.div
        aria-label="Jarvis core"
        className="relative rounded-full"
        style={{
          width: size,
          height: size,
          background: `radial-gradient(circle at 50% 45%,
            #ffffff 0%,
            #aef3ff 18%,
            #00ffff 45%,
            rgba(0, 229, 255, 0.18) 80%,
            transparent 100%)`,
          boxShadow: intensity.shadow,
        }}
        animate={{
          scale: [1, intensity.peak, 1],
          opacity: [0.92, 1, 0.92],
        }}
        transition={{
          duration: intensity.duration,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      >
        {/* Inner highlight reflection */}
        <span
          aria-hidden
          className="absolute rounded-full"
          style={{
            top: "18%",
            left: "26%",
            width: "26%",
            height: "20%",
            background:
              "radial-gradient(ellipse at center, rgba(255,255,255,0.95), transparent 70%)",
            filter: "blur(2px)",
          }}
        />
      </motion.div>

      {label && (
        <div
          className="hud-display hud-text-glow text-[var(--hud-cyan)]"
          style={{ fontSize: 10 }}
        >
          {label}
        </div>
      )}
    </div>
  );
}

const INTENSITY: Record<
  OrbState,
  { peak: number; duration: number; shadow: string }
> = {
  idle: {
    peak: 1.04,
    duration: 2.6,
    shadow:
      "0 0 24px rgba(0, 229, 255, 0.45), 0 0 60px rgba(0, 229, 255, 0.22), inset 0 0 12px rgba(255,255,255,0.10)",
  },
  listening: {
    peak: 1.10,
    duration: 1.4,
    shadow:
      "0 0 36px rgba(0, 229, 255, 0.85), 0 0 90px rgba(0, 229, 255, 0.45), inset 0 0 14px rgba(255,255,255,0.20)",
  },
  speaking: {
    peak: 1.07,
    duration: 0.6,
    shadow:
      "0 0 30px rgba(174, 243, 255, 0.95), 0 0 80px rgba(0, 229, 255, 0.55), inset 0 0 16px rgba(255,255,255,0.30)",
  },
  thinking: {
    peak: 1.05,
    duration: 1.8,
    shadow:
      "0 0 30px rgba(0, 229, 255, 0.55), 0 0 70px rgba(0, 229, 255, 0.30), inset 0 0 12px rgba(255,255,255,0.15)",
  },
};

"use client";

import { useEffect, useState, type FormEvent } from "react";
import { getApiToken, setApiToken } from "@/lib/api-client";

type Status = "checking" | "ok" | "needs-token" | "submitting";

/**
 * Client-side auth gate.
 *
 * On first load: probes /api/auth/check with the stored token (or env-baked one).
 * If the probe is unauthorized, render a token-entry screen instead of children.
 * After successful entry, the token is stored in localStorage and the app boots.
 *
 * If MC_API_TOKEN is not configured server-side, the probe always succeeds and
 * the gate is invisible (preserves existing local-dev open-access UX).
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("checking");
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");

  const probe = async (token: string | null) => {
    try {
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch("/api/auth/check", { headers, cache: "no-store" });
      return res.ok;
    } catch {
      return false;
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ok = await probe(getApiToken());
      if (cancelled) return;
      setStatus(ok ? "ok" : "needs-token");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setStatus("submitting");
    setError(null);
    const ok = await probe(input.trim());
    if (!ok) {
      setError("Invalid token");
      setStatus("needs-token");
      return;
    }
    setApiToken(input.trim());
    setStatus("ok");
  }

  if (status === "ok") return <>{children}</>;

  if (status === "checking") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0a0e14] text-[#5b8dff] font-mono text-xs tracking-widest">
        BOOT…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0e14] px-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 border border-[#1f2937] bg-[#0f141b] p-6 font-mono text-xs"
      >
        <div className="space-y-1">
          <div className="text-[#5b8dff] tracking-widest">JARVIS // OPS</div>
          <div className="text-[#6b7280]">Enter access token</div>
        </div>
        <input
          type="password"
          autoFocus
          autoComplete="off"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="token"
          className="w-full border border-[#1f2937] bg-[#0a0e14] px-3 py-2 text-[#e5e7eb] outline-none focus:border-[#5b8dff]"
        />
        {error && <div className="text-[#ef4444]">{error}</div>}
        <button
          type="submit"
          disabled={status === "submitting"}
          className="w-full border border-[#5b8dff] bg-[#5b8dff]/10 px-3 py-2 text-[#5b8dff] tracking-widest hover:bg-[#5b8dff]/20 disabled:opacity-50"
        >
          {status === "submitting" ? "VERIFY…" : "AUTH"}
        </button>
        <div className="text-[#6b7280]">
          Token shared once with the operator. Stored locally on this device only.
        </div>
      </form>
    </div>
  );
}

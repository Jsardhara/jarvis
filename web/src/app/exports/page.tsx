"use client";

/**
 * /exports — Daily & Weekly Digest
 *
 * Fetches markdown digests from the backend, renders them in a monospace
 * pre-block and provides COPY + DOWNLOAD buttons.
 *
 * Reachable via direct URL only — not in the sidebar nav.
 */

import { CSSProperties, useCallback, useState } from "react";
import { Panel, OpsButton } from "@/components/ops";
import { apiFetch } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

interface DailyResponse {
  data: { markdown: string; date: string } | null;
  error: string | null;
}

interface WeeklyResponse {
  data: { markdown: string; start: string; end: string } | null;
  error: string | null;
}

type DigestKind = "daily" | "weekly";

interface DigestState {
  markdown: string;
  label: string;
  filename: string;
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ExportsPage() {
  const [digest, setDigest] = useState<DigestState | null>(null);
  const [loading, setLoading] = useState<DigestKind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // ── Fetch ─────────────────────────────────────────────────────────────────

  const fetchDigest = useCallback(async (kind: DigestKind) => {
    setLoading(kind);
    setError(null);
    setDigest(null);
    setCopied(false);

    try {
      const url =
        kind === "daily" ? "/api/exports/daily" : "/api/exports/weekly";
      const res = await apiFetch(url);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      if (kind === "daily") {
        const body = (await res.json()) as DailyResponse;
        if (body.error || !body.data) {
          throw new Error(body.error ?? "empty response");
        }
        setDigest({
          markdown: body.data.markdown,
          label: `Daily · ${body.data.date}`,
          filename: `jarvis-daily-${body.data.date}.md`,
        });
      } else {
        const body = (await res.json()) as WeeklyResponse;
        if (body.error || !body.data) {
          throw new Error(body.error ?? "empty response");
        }
        setDigest({
          markdown: body.data.markdown,
          label: `Weekly · ${body.data.start} — ${body.data.end}`,
          filename: `jarvis-weekly-${body.data.end}.md`,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "fetch failed");
    } finally {
      setLoading(null);
    }
  }, []);

  // ── Copy ──────────────────────────────────────────────────────────────────

  const handleCopy = useCallback(async () => {
    if (!digest) return;
    try {
      await navigator.clipboard.writeText(digest.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("clipboard write failed");
    }
  }, [digest]);

  // ── Download ──────────────────────────────────────────────────────────────

  const handleDownload = useCallback(() => {
    if (!digest) return;
    const blob = new Blob([digest.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = digest.filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [digest]);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      style={
        {
          padding: 20,
          display: "flex",
          flexDirection: "column",
          gap: 20,
          maxWidth: 860,
          width: "100%",
        } as CSSProperties
      }
    >
      {/* Title */}
      <span
        style={
          {
            fontFamily: "var(--ops-sans)",
            fontSize: 16,
            fontWeight: 600,
            letterSpacing: "0.08em",
          } as CSSProperties
        }
      >
        EXPORTS · DIGESTS
      </span>

      {/* Action row */}
      <Panel title="GENERATE">
        <div style={{ display: "flex", gap: 8 } as CSSProperties}>
          <OpsButton
            variant="primary"
            disabled={loading !== null}
            onClick={() => fetchDigest("daily")}
          >
            {loading === "daily" ? "LOADING…" : "TODAY"}
          </OpsButton>
          <OpsButton
            variant="primary"
            disabled={loading !== null}
            onClick={() => fetchDigest("weekly")}
          >
            {loading === "weekly" ? "LOADING…" : "THIS WEEK"}
          </OpsButton>
        </div>
      </Panel>

      {/* Error */}
      {error && (
        <span
          style={
            {
              fontFamily: "var(--ops-mono)",
              fontSize: 11,
              color: "var(--ops-alert)",
              letterSpacing: "0.08em",
            } as CSSProperties
          }
        >
          ERROR · {error}
        </span>
      )}

      {/* Output */}
      {digest && (
        <Panel
          title={digest.label.toUpperCase()}
          trailing={
            <div style={{ display: "flex", gap: 6 } as CSSProperties}>
              <OpsButton onClick={handleCopy} disabled={copied}>
                {copied ? "COPIED" : "COPY"}
              </OpsButton>
              <OpsButton onClick={handleDownload}>DOWNLOAD .MD</OpsButton>
            </div>
          }
        >
          <pre
            style={
              {
                fontFamily: "var(--ops-mono)",
                fontSize: 11,
                lineHeight: 1.7,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
                color: "var(--ops-fg)",
                maxHeight: "70vh",
                overflowY: "auto",
              } as CSSProperties
            }
          >
            {digest.markdown}
          </pre>
        </Panel>
      )}
    </div>
  );
}

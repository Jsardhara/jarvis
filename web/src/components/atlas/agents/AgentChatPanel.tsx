"use client";

/**
 * AgentChatPanel
 *
 * Chat panel for talking to an Atlas agent.
 * Uses useAgentChat hook for session state + SSE streaming.
 *
 * Layout:
 *   - Messages list (user right-aligned, agent left-aligned)
 *   - Text input + Send button (disabled while streaming)
 *   - Clear button to reset session
 */

import { useRef, useEffect, useState } from "react";
import { Panel } from "@/components/ops/Panel";
import { OpsButton } from "@/components/ops/OpsButton";
import { useAgentChat } from "@/hooks/useAgentChat";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentChatPanelProps {
  agentId: string;
  accentColor?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AgentChatPanel({ agentId, accentColor }: AgentChatPanelProps) {
  const { messages, send, isStreaming, error, clear } = useAgentChat(agentId);
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text || isStreaming) return;
    setInputText("");
    await send(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <Panel
      title="CHAT"
      trailing={
        <OpsButton onClick={clear} disabled={isStreaming || messages.length === 0}>
          CLEAR
        </OpsButton>
      }
      flushBody
      className="agent-chat-panel"
    >
      {/* Messages */}
      <div
        style={{
          height: 240,
          overflowY: "auto",
          padding: "10px 14px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {messages.length === 0 ? (
          <div
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: 11,
              color: "var(--ops-fg-faint)",
              textAlign: "center",
              marginTop: 40,
            }}
          >
            Ask the agent anything.
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                display: "flex",
                justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <div
                style={{
                  maxWidth: "80%",
                  padding: "6px 10px",
                  border: "1px solid",
                  borderColor:
                    msg.role === "user"
                      ? "var(--ops-line-strong)"
                      : (accentColor ?? "var(--ops-amber)"),
                  background:
                    msg.role === "user"
                      ? "var(--ops-bg-elevated)"
                      : "var(--ops-bg-deep)",
                  fontFamily: "var(--ops-mono)",
                  fontSize: 11,
                  color:
                    msg.role === "user"
                      ? "var(--ops-fg)"
                      : (accentColor ?? "var(--ops-fg)"),
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  lineHeight: 1.5,
                }}
              >
                {msg.content || (
                  <span style={{ color: "var(--ops-fg-faint)" }}>
                    {isStreaming ? "▋" : ""}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            padding: "4px 14px",
            fontFamily: "var(--ops-mono)",
            fontSize: 10,
            color: "var(--ops-crit)",
            borderTop: "1px solid var(--ops-line-faint)",
          }}
        >
          {error.message}
        </div>
      )}

      {/* Input */}
      <div
        style={{
          borderTop: "1px solid var(--ops-line)",
          padding: "10px 14px",
          display: "flex",
          gap: 8,
          alignItems: "flex-end",
        }}
      >
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the agent... (Enter to send, Shift+Enter for newline)"
          rows={2}
          disabled={isStreaming}
          style={{
            flex: 1,
            background: "var(--ops-bg-input)",
            border: "1px solid var(--ops-line)",
            padding: "6px 8px",
            fontFamily: "var(--ops-mono)",
            fontSize: 11,
            color: "var(--ops-fg)",
            resize: "none",
            outline: "none",
            lineHeight: 1.5,
            opacity: isStreaming ? 0.6 : 1,
          }}
        />
        <OpsButton
          onClick={() => { void handleSend(); }}
          disabled={isStreaming || !inputText.trim()}
          variant="primary"
        >
          {isStreaming ? "…" : "SEND"}
        </OpsButton>
      </div>
    </Panel>
  );
}

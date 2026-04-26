"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { dispatchAgent, type AgentDescriptor } from "@/lib/api";

interface CommandPaletteProps {
  agents: AgentDescriptor[];
  open: boolean;
  onClose: () => void;
  onResult?: (agent: string, summary: string) => void;
}

export function CommandPalette({ agents, open, onClose, onResult }: CommandPaletteProps) {
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setText("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const suggestions = useMemo(() => {
    const trimmed = text.trim();
    if (!trimmed.startsWith("@")) {
      return agents.map((a) => ({ agent: a.name, hint: a.description, command: `@${a.name} ` }));
    }
    const [tag] = trimmed.slice(1).split(/\s+/, 1);
    return agents
      .filter((a) => a.name.startsWith(tag.toLowerCase()))
      .map((a) => ({ agent: a.name, hint: a.description, command: `@${a.name} ` }));
  }, [agents, text]);

  if (!open) return null;

  const submit = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (!trimmed.startsWith("@")) {
      // No agent prefix → choose highlighted suggestion's agent + use whole text
      const target = suggestions[active]?.agent;
      if (!target) return;
      const env = await dispatchAgent(target, { text: trimmed });
      onResult?.(target, env.action);
      onClose();
      return;
    }
    const m = trimmed.match(/^@(\w+)\s*(.*)$/);
    if (!m) return;
    const [, name, rest] = m;
    const desc = agents.find((a) => a.name === name);
    if (!desc) return;
    const env = await dispatchAgent(name, { text: rest });
    onResult?.(name, env.action);
    onClose();
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      onClose();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Tab") {
      e.preventDefault();
      const sel = suggestions[active];
      if (sel) setText(sel.command);
    } else if (e.key === "Enter") {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKey}
          placeholder="@agent message…   (Tab to complete, Enter to send)"
        />
        <ul>
          {suggestions.map((s, i) => (
            <li
              key={s.agent}
              data-active={i === active ? "1" : "0"}
              onMouseEnter={() => setActive(i)}
              onClick={() => setText(s.command)}
            >
              <span className="agent-tag">@{s.agent}</span>
              <span className="muted">{s.hint}</span>
            </li>
          ))}
          {suggestions.length === 0 && (
            <li>
              <span className="muted">no agents match</span>
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

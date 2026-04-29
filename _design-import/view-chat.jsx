/* global React, AGENTS, AgentGlyph, Tag, Dot, Progress */
// ═══════════════════════════════════════════════════════════════
// JARVIS CHAT — talk to the orchestrator
// Shows live dispatch traces under each message
// Persists to localStorage as 'jarvis.chat.history.v1'
// ═══════════════════════════════════════════════════════════════

const { useState: useSc, useEffect: useEc, useRef: useRc } = React;
const STORAGE_KEY = 'jarvis.chat.history.v1';

// Each user message → Jarvis classifies → dispatches to one or more agents → returns
// We synthesize a believable plan trace based on keywords.
const PRESET_THREADS = [
  {
    role: 'user',
    text: 'Find a 30-min slot with Sasha next week and prep me for the meeting.',
    t: 'YESTERDAY 16:42',
  },
  {
    role: 'jarvis',
    t: 'YESTERDAY 16:42',
    plan: [
      { agent: 'chronos',  step: 'lookup availability + Sasha tz · find 30m slot Mon-Fri',  status: 'ok' },
      { agent: 'aide',     step: 'pull last 14 emails w/ sasha@petrov.io · summarize',      status: 'ok' },
      { agent: 'sherlock', step: 'compile context · linkedin + recent posts',                status: 'ok' },
    ],
    text: 'Held **Tue 14:00** (you both free, Sasha\'s tz). Aide drafted a 1-paragraph context brief with the last 3 threads + open questions. Sherlock added 2 talking points from her recent posts. Want me to send the calendar invite?',
  },
  {
    role: 'user',
    text: 'Yes send it. Also remind me 30 min before.',
    t: 'YESTERDAY 16:43',
  },
  {
    role: 'jarvis',
    t: 'YESTERDAY 16:43',
    plan: [
      { agent: 'chronos', step: 'send invite · attach brief · set 30m reminder', status: 'ok' },
    ],
    text: 'Sent. Reminder set for Tue 13:30. Pinned the brief to the event.',
  },
];

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return PRESET_THREADS;
}

function saveHistory(h) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(h)); } catch (e) {}
}

// Naive intent classifier — picks a believable plan from the prompt
function classify(text) {
  const t = text.toLowerCase();
  const plan = [];
  if (/email|inbox|reply|sasha|draft|mail/.test(t))
    plan.push({ agent: 'aide', step: 'scan inbox · classify intent · draft reply' });
  if (/schedul|calendar|meet|book|slot|lunch|flight|reschedule|remind/.test(t))
    plan.push({ agent: 'chronos', step: 'find slot · check conflicts · propose times' });
  if (/research|find|paper|look up|investigate|sources|article/.test(t))
    plan.push({ agent: 'sherlock', step: 'multi-hop research · cite sources' });
  if (/code|refactor|pr|review|test|repo|deploy|bug/.test(t))
    plan.push({ agent: 'forge', step: 'open project · write+test changes' });
  if (/expense|receipt|spend|budget|invoice|pay|bill/.test(t))
    plan.push({ agent: 'ledger', step: 'team dispatch · categorize · reconcile' });
  if (/text|message|whatsapp|imessage|slack|reply to/.test(t))
    plan.push({ agent: 'echo', step: 'compose · route channel · ack' });
  if (/light|home|temp|sensor|routine|lock|unlock/.test(t))
    plan.push({ agent: 'hearth', step: 'apply scene · update routine' });
  if (plan.length === 0)
    plan.push({ agent: 'aide', step: 'no clear intent · ask clarification or self-handle' });
  return plan;
}

function jarvisReply(text, plan) {
  const names = plan.map((p) => AGENTS.find((a) => a.id === p.agent)?.name || p.agent);
  const phrasings = [
    `Routing to ${names.join(' + ')}. I\'ll surface results back here as they finish.`,
    `${names[0]} is on it${names.length > 1 ? ` (with ${names.slice(1).join(', ')})` : ''}. Tracking task in the board.`,
    `Dispatched to ${names.join(' + ')}. Estimated complete in 30–90s.`,
    `${names.join(' + ')} picking this up. I\'ll ping you when there\'s something to review.`,
  ];
  return phrasings[Math.floor(Math.random() * phrasings.length)];
}

function ChatView() {
  const [history, setHistory] = useSc(() => loadHistory());
  const [draft, setDraft] = useSc('');
  const [pending, setPending] = useSc(null); // {plan, idx, replyText}
  const scrollRef = useRc(null);

  useEc(() => { saveHistory(history); }, [history]);
  useEc(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [history, pending]);

  // animate pending plan steps to "ok" one by one
  useEc(() => {
    if (!pending) return;
    if (pending.idx >= pending.plan.length) {
      // commit reply
      const finalMsg = {
        role: 'jarvis',
        t: stamp(),
        plan: pending.plan.map((p) => ({ ...p, status: 'ok' })),
        text: pending.replyText,
      };
      setHistory((h) => [...h, finalMsg]);
      setPending(null);
      return;
    }
    const id = setTimeout(() => {
      setPending((p) => p ? { ...p, idx: p.idx + 1 } : p);
    }, 700 + Math.random() * 600);
    return () => clearTimeout(id);
  }, [pending]);

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    const userMsg = { role: 'user', t: stamp(), text };
    const plan = classify(text);
    const replyText = jarvisReply(text, plan);
    setHistory((h) => [...h, userMsg]);
    setDraft('');
    setPending({ plan, idx: 0, replyText });
  };

  const clear = () => {
    if (!window.confirm('Clear all chat history?')) return;
    setHistory([]);
    saveHistory([]);
  };

  const quickPrompts = [
    'Schedule lunch with Marcus next week',
    'Research the latest on inference-time scaling',
    'Categorize this month\'s receipts',
    'Reply to Sasha — say tuesday works',
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, borderRight: '1px solid var(--line)' }}>
        {/* messages */}
        <div ref={scrollRef} style={{
          flex: 1, overflow: 'auto', padding: 24,
          display: 'flex', flexDirection: 'column', gap: 18,
        }}>
          {history.length === 0 && !pending && (
            <div style={{
              margin: 'auto', textAlign: 'center', color: 'var(--fg-faint)',
              fontSize: 11, letterSpacing: '0.16em',
            }}>
              <div style={{
                width: 36, height: 36, margin: '0 auto 12px',
                border: '1px solid var(--amber)', transform: 'rotate(45deg)',
                position: 'relative',
              }}>
                <span style={{
                  position: 'absolute', inset: 0, margin: 'auto',
                  width: 8, height: 8, background: 'var(--amber)', borderRadius: 4,
                  boxShadow: '0 0 12px var(--amber)',
                }} />
              </div>
              JARVIS · STANDING BY<br/>
              <span style={{ color: 'var(--fg-dim)', letterSpacing: 0 }}>
                Ask anything · I\'ll route it.
              </span>
            </div>
          )}
          {history.map((m, i) => <ChatMessage key={i} msg={m} />)}
          {pending && (
            <ChatMessage msg={{
              role: 'jarvis',
              t: stamp(),
              plan: pending.plan.map((p, i) => ({
                ...p,
                status: i < pending.idx ? 'ok' : i === pending.idx ? 'running' : 'queued',
              })),
              text: pending.idx >= pending.plan.length ? pending.replyText : null,
              live: true,
            }} />
          )}
        </div>

        {/* composer */}
        <div style={{
          borderTop: '1px solid var(--line)',
          background: 'var(--bg-deep)',
          padding: '12px 16px',
          display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {quickPrompts.map((q) => (
              <button key={q} onClick={() => setDraft(q)} style={{
                background: 'transparent',
                border: '1px solid var(--line)',
                color: 'var(--fg-dim)',
                padding: '4px 8px',
                fontSize: 10,
                letterSpacing: '0.06em',
                fontFamily: 'var(--mono)',
                borderRadius: 2,
                cursor: 'pointer',
              }}>↳ {q}</button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <span style={{
              fontSize: 10, color: 'var(--amber)', letterSpacing: '0.18em',
              padding: '8px 0', minWidth: 60,
            }}>YOU ▸</span>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }
                else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
              }}
              placeholder="Tell Jarvis what you need…"
              style={{
                flex: 1,
                background: 'var(--bg-input)',
                border: '1px solid var(--line)',
                color: 'var(--fg)',
                padding: '10px 12px',
                fontFamily: 'var(--mono)',
                fontSize: 12,
                lineHeight: 1.5,
                borderRadius: 2,
                outline: 'none',
                resize: 'none',
                minHeight: 40,
                maxHeight: 120,
              }}
              rows={2}
            />
            <button className="btn primary" onClick={send} style={{ padding: '8px 14px' }}>
              SEND ⌘↵
            </button>
          </div>
        </div>
      </div>

      {/* rail */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 14, overflow: 'auto' }}>
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">CONVERSATION</span>
            <button className="btn icon" onClick={clear} style={{ marginLeft: 'auto', fontSize: 9 }} title="Clear history">✕</button>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--fg-dim)' }}>
              <span>MESSAGES</span>
              <span style={{ color: 'var(--fg)', fontFamily: 'var(--mono)' }}>{history.length}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--fg-dim)' }}>
              <span>PERSISTED</span>
              <span style={{ color: 'var(--ok)', fontFamily: 'var(--mono)' }}>localStorage ✓</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--fg-dim)' }}>
              <span>MEMORY KEY</span>
              <span style={{ color: 'var(--fg-faint)', fontFamily: 'var(--mono)', fontSize: 9 }}>chat.history.v1</span>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">DISPATCH · LAST 24H</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {AGENTS.map((a) => {
              const count = history.reduce((s, m) =>
                s + (m.plan ? m.plan.filter((p) => p.agent === a.id).length : 0), 0);
              return (
                <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
                  <AgentGlyph agent={a} size={14} />
                  <span style={{ color: a.colorHex, flex: 1 }}>{a.name}</span>
                  <div style={{ flex: 2, height: 4, background: 'var(--line)', borderRadius: 1 }}>
                    <div style={{
                      width: `${Math.min(count * 18, 100)}%`,
                      height: '100%', background: a.colorHex,
                    }} />
                  </div>
                  <span style={{ color: 'var(--fg-dim)', fontFamily: 'var(--mono)', width: 18, textAlign: 'right' }}>
                    {count}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">PINNED CONTEXT</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11 }}>
            <div style={{ padding: '6px 8px', border: '1px solid var(--line)', borderLeft: '2px solid var(--amber)', fontFamily: 'var(--sans)', color: 'var(--fg-mute)' }}>
              You prefer terse, action-oriented replies
            </div>
            <div style={{ padding: '6px 8px', border: '1px solid var(--line)', borderLeft: '2px solid var(--amber)', fontFamily: 'var(--sans)', color: 'var(--fg-mute)' }}>
              Always ask before booking travel or sending P1 mail
            </div>
            <div style={{ padding: '6px 8px', border: '1px solid var(--line)', borderLeft: '2px solid var(--amber)', fontFamily: 'var(--sans)', color: 'var(--fg-mute)' }}>
              Default tz · America/Los_Angeles
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChatMessage({ msg }) {
  if (msg.role === 'user') {
    return (
      <div style={{ alignSelf: 'flex-end', maxWidth: '70%' }}>
        <div style={{ fontSize: 9, letterSpacing: '0.16em', color: 'var(--amber)', marginBottom: 4, textAlign: 'right' }}>
          YOU · {msg.t}
        </div>
        <div style={{
          background: 'rgba(242,160,61,0.08)',
          border: '1px solid var(--amber)',
          padding: '10px 14px',
          fontSize: 13,
          fontFamily: 'var(--sans)',
          lineHeight: 1.5,
          color: 'var(--fg)',
          borderRadius: 2,
        }}>{msg.text}</div>
      </div>
    );
  }
  // jarvis
  return (
    <div style={{ alignSelf: 'flex-start', maxWidth: '85%', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 9, letterSpacing: '0.16em', color: 'var(--ok)', marginBottom: 0 }}>
        {msg.live ? <span className="dot ok pulse" style={{ marginRight: 6 }} /> : <span style={{ marginRight: 6 }}>◇</span>}
        JARVIS · {msg.t}
      </div>
      {msg.plan && msg.plan.length > 0 && (
        <div style={{
          background: 'var(--bg-panel)',
          border: '1px solid var(--line)',
          borderLeft: '2px solid var(--ok)',
          padding: '10px 12px',
          fontSize: 11,
          fontFamily: 'var(--mono)',
        }}>
          <div style={{
            fontSize: 9, letterSpacing: '0.18em', color: 'var(--fg-dim)', marginBottom: 8,
          }}>DISPATCH PLAN · {msg.plan.length} STEP{msg.plan.length > 1 ? 'S' : ''}</div>
          {msg.plan.map((p, i) => {
            const ag = AGENTS.find((a) => a.id === p.agent);
            const status = p.status || 'ok';
            return (
              <div key={i} style={{
                display: 'grid',
                gridTemplateColumns: '20px 90px 1fr 60px',
                gap: 10,
                padding: '4px 0',
                alignItems: 'center',
                opacity: status === 'queued' ? 0.4 : 1,
              }}>
                <span style={{ color: 'var(--fg-faint)', fontSize: 10 }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {ag && <AgentGlyph agent={ag} size={12} />}
                  <span style={{ color: ag ? ag.colorHex : 'var(--fg)', fontSize: 10, letterSpacing: '0.08em' }}>
                    {ag ? ag.name : p.agent.toUpperCase()}
                  </span>
                </span>
                <span style={{ color: 'var(--fg-mute)', fontSize: 11 }}>{p.step}</span>
                <span style={{ textAlign: 'right' }}>
                  {status === 'ok'      && <Tag kind="ok">✓ DONE</Tag>}
                  {status === 'running' && <Tag kind="amber">▸ RUN</Tag>}
                  {status === 'queued'  && <Tag>···</Tag>}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {msg.text && (
        <div style={{
          background: 'var(--bg-elevated)',
          border: '1px solid var(--line)',
          padding: '10px 14px',
          fontSize: 13,
          fontFamily: 'var(--sans)',
          lineHeight: 1.55,
          color: 'var(--fg)',
          borderRadius: 2,
        }}>
          <RichText text={msg.text} />
        </div>
      )}
    </div>
  );
}

function RichText({ text }) {
  // bold ** ** spans
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return <>{parts.map((p, i) =>
    p.startsWith('**') && p.endsWith('**')
      ? <b key={i} style={{ color: 'var(--amber)' }}>{p.slice(2, -2)}</b>
      : <span key={i}>{p}</span>
  )}</>;
}

function stamp() {
  const t = new Date();
  const pad = (x) => String(x).padStart(2, '0');
  return `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
}

window.ChatView = ChatView;

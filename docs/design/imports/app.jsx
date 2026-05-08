/* global React, ReactDOM, AGENTS, COLUMNS, TASKS,
   OverviewView, KanbanView, AgentDetailView, SentinelView, ChatView,
   Clock, TickNum, Dot,
   TweaksPanel, useTweaks, TweakSection, TweakRadio, TweakToggle, TweakSlider */
// ═══════════════════════════════════════════════════════════════
// JARVIS // APP SHELL
// ═══════════════════════════════════════════════════════════════

const { useState: useSt, useEffect: useEf } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "comfortable",
  "showSentinelStrip": true,
  "scanlines": true,
  "accentColor": "amber",
  "agentCardLayout": "tile",
  "logVelocity": "active"
}/*EDITMODE-END*/;

const ACCENT_HUES = {
  amber:  { primary: '#F2A03D', glow: 'rgba(242,160,61,0.18)' },
  cyan:   { primary: '#5FD3D3', glow: 'rgba(95,211,211,0.18)' },
  rose:   { primary: '#E0859E', glow: 'rgba(224,133,158,0.18)' },
  emerald:{ primary: '#6FCF7F', glow: 'rgba(111,207,127,0.18)' },
};

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [view, setView] = useSt({ kind: 'chat' });

  // Apply tweaks via root CSS vars
  useEf(() => {
    const root = document.documentElement;
    const accent = ACCENT_HUES[tweaks.accentColor] || ACCENT_HUES.amber;
    root.style.setProperty('--amber', accent.primary);
    root.style.setProperty('--amber-glow', accent.glow);
    root.style.setProperty('--density', tweaks.density === 'compact' ? '0.85' : '1');
    document.body.style.setProperty('font-size', tweaks.density === 'compact' ? '12px' : '13px');
  }, [tweaks.accentColor, tweaks.density]);

  const openAgent = (id) => setView({ kind: 'agent', id });

  const totalQueue = AGENTS.reduce((s, a) => s + a.queueDepth, 0);
  const activeTasks = TASKS.filter((t) => t.column === 'active').length;
  const totalDone = AGENTS.reduce((s, a) => s + a.completed24h, 0);

  return (
    <div className="app">
      {/* TOP BAR */}
      <div className="topbar">
        <div className="brand">
          <span className="brand-mark" />
          <span>JARVIS</span>
          <span style={{ color: 'var(--fg-faint)', marginLeft: 4, letterSpacing: '0.16em' }}>// OPS</span>
        </div>
        <div style={{
          fontSize: 10, color: 'var(--fg-dim)', letterSpacing: '0.12em',
          padding: '3px 10px', border: '1px solid var(--line)', borderRadius: 2,
        }}>
          ORCHESTRATOR · OPUS-4.7 · <span style={{ color: 'var(--ok)' }}>ONLINE</span>
        </div>
        <div className="meta">
          <span><span className="live-dot" /><b><TickNum base={activeTasks} jitter={1} fmt={(n) => n} /></b> ACTIVE</span>
          <span>QUEUE <b>{totalQueue}</b></span>
          <span>DONE/24 <b>{totalDone}</b></span>
          <span>COST/24 <b style={{ color: 'var(--amber)' }}>$7.86</b></span>
          <span><Clock /></span>
        </div>
      </div>

      {/* SIDEBAR */}
      <div className="sidebar">
        <div className="nav-section">
          <div className="nav-label">CONTROL</div>
          <NavItem
            active={view.kind === 'chat'}
            onClick={() => setView({ kind: 'chat' })}
            glyph="▸"
          >CHAT</NavItem>
          <NavItem
            active={view.kind === 'overview'}
            onClick={() => setView({ kind: 'overview' })}
            glyph="◇"
          >OVERVIEW</NavItem>
          <NavItem
            active={view.kind === 'kanban'}
            onClick={() => setView({ kind: 'kanban' })}
            glyph="≡"
            meta={String(TASKS.length)}
          >TASK BOARD</NavItem>
          <NavItem
            active={view.kind === 'sentinel'}
            onClick={() => setView({ kind: 'sentinel' })}
            glyph="⊙"
            meta="6/7"
          >SENTINEL</NavItem>
        </div>

        <div className="nav-section">
          <div className="nav-label">
            <span>SUB-AGENTS</span>
            <span style={{ color: 'var(--ok)' }}>5/7</span>
          </div>
          {AGENTS.map((a) => (
            <div
              key={a.id}
              className={`nav-item agent ${view.kind === 'agent' && view.id === a.id ? 'active' : ''}`}
              onClick={() => openAgent(a.id)}
              style={{ '--agent-color': a.colorHex }}
            >
              <span className="nav-glyph" style={{ color: a.colorHex }}>{a.glyph}</span>
              <span>{a.name}</span>
              <span className="nav-meta" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Dot
                  kind={a.status === 'active' ? 'ok' : a.status === 'busy' ? 'warn' : 'idle'}
                  pulse={a.status !== 'idle'}
                />
                {a.queueDepth > 0 && <span style={{ color: 'var(--fg-mute)' }}>{a.queueDepth}</span>}
              </span>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 'auto', padding: 12, borderTop: '1px solid var(--line)', fontSize: 9, color: 'var(--fg-faint)', letterSpacing: '0.1em', lineHeight: 1.7 }}>
          <div>v1.4.2 · build 12872</div>
          <div>14d 06:42 UPTIME</div>
          <div style={{ color: 'var(--ok)', marginTop: 4 }}>● ALL SYSTEMS NOMINAL</div>
        </div>
      </div>

      {/* MAIN */}
      <div className="main">
        {tweaks.scanlines && <div className="scanline" />}
        {view.kind === 'chat' && <ChatSurface />}
        {view.kind === 'overview' && <OverviewSurface onOpenAgent={openAgent} />}
        {view.kind === 'kanban' && <KanbanSurface />}
        {view.kind === 'sentinel' && <SentinelSurface />}
        {view.kind === 'agent' && <AgentDetailView agentId={view.id} />}
      </div>

      {/* STATUS BAR */}
      <div className="statusbar">
        <span className="sb-item">
          <Dot kind="ok" pulse />
          <b>JARVIS</b> · ONLINE
        </span>
        <span className="sb-item">SENTINEL · NEXT FIRE 14:32:30 → ECHO</span>
        <span className="sb-item">CTX <b>21%</b></span>
        <span className="sb-item">RPM <b>14.2</b></span>
        <span className="sb-spacer" />
        <span className="sb-item faint">⌘K · COMMAND</span>
        <span className="sb-item faint">⌘\ · TWEAKS</span>
        <span className="sb-item">{new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }).toUpperCase()}</span>
      </div>

      {/* TWEAKS */}
      <TweaksPanel title="TWEAKS · OPS BLACK">
        <TweakSection title="DENSITY">
          <TweakRadio
            value={tweaks.density}
            onChange={(v) => setTweak('density', v)}
            options={[{ value: 'comfortable', label: 'COMFORTABLE' }, { value: 'compact', label: 'COMPACT' }]}
          />
        </TweakSection>
        <TweakSection title="ACCENT">
          <TweakRadio
            value={tweaks.accentColor}
            onChange={(v) => setTweak('accentColor', v)}
            options={[
              { value: 'amber',   label: 'AMBER' },
              { value: 'cyan',    label: 'CYAN' },
              { value: 'rose',    label: 'ROSE' },
              { value: 'emerald', label: 'EMERALD' },
            ]}
          />
        </TweakSection>
        <TweakSection title="EFFECTS">
          <TweakToggle
            label="Scanline overlay"
            value={tweaks.scanlines}
            onChange={(v) => setTweak('scanlines', v)}
          />
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

function NavItem({ active, onClick, glyph, meta, children }) {
  return (
    <div className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>
      <span className="nav-glyph">{glyph}</span>
      <span>{children}</span>
      {meta && <span className="nav-meta">{meta}</span>}
    </div>
  );
}

function ChatSurface() {
  return (
    <>
      <div className="view-header">
        <span className="view-title">▸ CHAT</span>
        <span className="view-subtitle">DIRECT CHANNEL TO ORCHESTRATOR · OPUS-4.7</span>
        <div className="view-actions">
          <span style={{ fontSize: 10, color: 'var(--fg-dim)', letterSpacing: '0.12em' }}>
            <span className="dot ok pulse" style={{ marginRight: 6 }} />
            JARVIS LISTENING · CTX 21%
          </span>
        </div>
      </div>
      <div className="view-body" style={{ padding: 0, overflow: 'hidden' }}>
        <ChatView />
      </div>
    </>
  );
}

function OverviewSurface({ onOpenAgent }) {
  return (
    <>
      <div className="view-header">
        <span className="view-title">◇ OVERVIEW</span>
        <span className="view-subtitle">ORCHESTRATOR + AGENT FLEET STATE</span>
        <div className="view-actions">
          <button className="btn">⤓ EXPORT TELEMETRY</button>
          <button className="btn primary">+ NEW TASK</button>
        </div>
      </div>
      <div className="view-body">
        <OverviewView onOpenAgent={onOpenAgent} />
      </div>
    </>
  );
}

function KanbanSurface() {
  return (
    <>
      <div className="view-header">
        <span className="view-title">≡ TASK BOARD</span>
        <span className="view-subtitle">JARVIS DISPATCH FLOW · INBOX → DONE</span>
        <div className="view-actions">
          <button className="btn">⊞ GROUP BY AGENT</button>
          <button className="btn primary">+ INJECT TASK</button>
        </div>
      </div>
      <div className="view-body" style={{ padding: 0 }}>
        <KanbanView />
      </div>
    </>
  );
}

function SentinelSurface() {
  return (
    <>
      <div className="view-header">
        <span className="view-title">⊙ SENTINEL</span>
        <span className="view-subtitle">BACKGROUND SCHEDULER · APSCHEDULER DAEMON</span>
        <div className="view-actions">
          <button className="btn">⏸ PAUSE ALL</button>
          <button className="btn primary">+ NEW JOB</button>
        </div>
      </div>
      <div className="view-body" style={{ padding: 0 }}>
        <SentinelView />
      </div>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

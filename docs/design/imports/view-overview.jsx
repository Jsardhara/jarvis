/* global React, AGENTS, ACTIVITY, Dot, Tag, Bars, TickNum, AgentGlyph, Progress, KV, SectionHeading */
// ═══════════════════════════════════════════════════════════════
// OVERVIEW VIEW
// Top-level agent grid + live activity stream
// ═══════════════════════════════════════════════════════════════

const { useState: useStateOv, useEffect: useEffectOv, useMemo: useMemoOv } = React;

function randomBars(n = 24, base = 5, peak = 30) {
  return Array.from({ length: n }, () => base + Math.random() * peak);
}

function AgentCard({ agent, onOpen }) {
  const [bars, setBars] = useStateOv(() => randomBars());
  useEffectOv(() => {
    if (agent.status === 'idle') return;
    const id = setInterval(() => {
      setBars((b) => [...b.slice(1), 5 + Math.random() * (agent.status === 'busy' ? 40 : 25)]);
    }, 1200 + Math.random() * 800);
    return () => clearInterval(id);
  }, [agent.status]);

  const statusKind = agent.status === 'active' ? 'ok' : agent.status === 'busy' ? 'warn' : 'idle';

  return (
    <div
      onClick={() => onOpen(agent.id)}
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--line)',
        borderRadius: 2,
        padding: 14,
        position: 'relative',
        cursor: 'pointer',
        transition: 'border-color 120ms, background 120ms',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = agent.colorHex; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--line)'; }}
    >
      {/* top-right corner accent */}
      <span style={{
        position: 'absolute', top: 0, right: 0,
        width: 28, height: 1, background: agent.colorHex, opacity: 0.6,
      }} />
      <span style={{
        position: 'absolute', top: 0, right: 0,
        width: 1, height: 28, background: agent.colorHex, opacity: 0.6,
      }} />

      {/* header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <AgentGlyph agent={agent} size={28} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: 'var(--sans)',
            fontSize: 14,
            fontWeight: 600,
            letterSpacing: '0.08em',
          }}>{agent.name}</div>
          <div style={{
            fontSize: 9, letterSpacing: '0.18em', textTransform: 'uppercase',
            color: 'var(--fg-dim)',
          }}>{agent.role}</div>
        </div>
        <Dot kind={statusKind} pulse={agent.status !== 'idle'} />
      </div>

      <div style={{ fontSize: 11, color: 'var(--fg-mute)', minHeight: 18 }}>
        {agent.tagline}
      </div>

      {/* bars */}
      <div style={{ marginTop: 4 }}>
        <Bars values={bars} color={agent.colorHex} height={28} />
      </div>

      {/* metrics row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr',
        gap: 4,
        paddingTop: 8,
        borderTop: '1px solid var(--line)',
      }}>
        <Metric label="QUEUE"   value={agent.queueDepth} />
        <Metric label="DONE/24" value={agent.completed24h} />
        <Metric label="LAT"     value={agent.avgLatency} />
      </div>

      {/* footer */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        fontSize: 9,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--fg-faint)',
        marginTop: 2,
      }}>
        <span>{agent.model}</span>
        <span>· {agent.schedule}</span>
      </div>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
      <span style={{
        fontSize: 9, letterSpacing: '0.14em', color: 'var(--fg-dim)',
      }}>{label}</span>
      <span style={{
        fontSize: 14, fontWeight: 500, fontVariantNumeric: 'tabular-nums',
        fontFamily: 'var(--mono)',
      }}>{value}</span>
    </div>
  );
}

function ActivityFeed() {
  const [items, setItems] = useStateOv(ACTIVITY);
  useEffectOv(() => {
    let n = 1000;
    const id = setInterval(() => {
      const agent = AGENTS[Math.floor(Math.random() * AGENTS.length)];
      const msgs = [
        'classified · routed to queue',
        'tool call · web.fetch(arxiv.org)',
        'tool call · gmail.list(unread=true)',
        'completed step 3/5',
        'OK · response synthesized',
        'tokens · input+1240 output+320',
        'cache hit · context restored',
      ];
      const t = new Date();
      const pad = (x) => String(x).padStart(2, '0');
      const newItem = {
        t: `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`,
        agent: agent.id,
        msg: msgs[Math.floor(Math.random() * msgs.length)],
        level: 'info',
      };
      setItems((cur) => [newItem, ...cur].slice(0, 30));
      n++;
    }, 3500);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{
      fontFamily: 'var(--mono)',
      fontSize: 11,
      lineHeight: 1.7,
    }}>
      {items.map((row, i) => {
        const ag = AGENTS.find((a) => a.id === row.agent);
        const color = row.level === 'crit' ? 'var(--crit)'
          : row.level === 'warn' ? 'var(--warn)'
          : row.level === 'ok' ? 'var(--ok)'
          : 'var(--fg-mute)';
        return (
          <div key={`${row.t}-${i}`} style={{
            display: 'grid',
            gridTemplateColumns: '70px 84px 1fr',
            gap: 10,
            padding: '3px 0',
            borderBottom: '1px dashed var(--line-faint)',
            opacity: i === 0 ? 1 : 1 - i * 0.012,
          }}>
            <span style={{ color: 'var(--fg-faint)' }}>{row.t}</span>
            <span style={{ color: ag ? ag.colorHex : 'var(--amber)', textTransform: 'uppercase', fontSize: 10, letterSpacing: '0.1em' }}>
              {row.agent}
            </span>
            <span style={{ color }}>{row.msg}</span>
          </div>
        );
      })}
    </div>
  );
}

function SystemHealth() {
  return (
    <div className="panel" style={{ height: '100%' }}>
      <div className="panel-header">
        <span className="dot ok pulse" />
        <span className="panel-title">SYSTEM HEALTH</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)' }}>
          ALL SYSTEMS NOMINAL
        </span>
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <KV label="ORCHESTRATOR">claude-opus-4.7</KV>
        <KV label="UPTIME">14d 06:42:18</KV>
        <KV label="MEMORY">2.4 / 8 GB</KV>
        <KV label="ACTIVE TASKS"><TickNum base={11} jitter={1} fmt={(n) => n} /></KV>
        <KV label="QUEUED"><TickNum base={17} jitter={1} fmt={(n) => n} /></KV>
        <KV label="COMPLETED 24H">334</KV>
        <KV label="ERROR RATE" accent="var(--ok)">0.4%</KV>
        <KV label="COST 24H" accent="var(--amber)">$7.86</KV>
        <KV label="TOKENS 24H">897.1K in · 174.7K out</KV>
      </div>
    </div>
  );
}

function OverviewView({ onOpenAgent }) {
  return (
    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 20, minHeight: '100%' }}>
      {/* Hero strip — orchestrator status */}
      <div style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--line)',
        padding: '16px 20px',
        position: 'relative',
        display: 'grid',
        gridTemplateColumns: '1.4fr 1fr 1fr 1fr 1fr',
        gap: 24,
        alignItems: 'center',
      }}>
        <div style={{
          position: 'absolute', top: 0, left: 0, height: '100%', width: 3,
          background: 'var(--amber)', boxShadow: '0 0 12px var(--amber-glow)',
        }} />
        <div>
          <div style={{
            fontFamily: 'var(--sans)', fontSize: 11, letterSpacing: '0.2em',
            color: 'var(--amber)', marginBottom: 4,
          }}>ORCHESTRATOR · ONLINE</div>
          <div style={{
            fontFamily: 'var(--sans)', fontSize: 22, fontWeight: 500,
            letterSpacing: '0.04em',
          }}>JARVIS</div>
          <div style={{ fontSize: 11, color: 'var(--fg-dim)', marginTop: 2 }}>
            claude-opus-4.7 · classifying intents · dispatching to 7 agents
          </div>
        </div>
        <Metric label="AGENTS"     value="7 · 5 active" />
        <Metric label="QUEUE"      value={<TickNum base={17} jitter={1} fmt={(n) => n} />} />
        <Metric label="DONE / 24H" value="334" />
        <Metric label="COST / 24H" value="$7.86" />
      </div>

      {/* Agent grid */}
      <div>
        <SectionHeading right={<span className="up faint">SUB-AGENT FLEET · 7</span>}>
          AGENT FLEET
        </SectionHeading>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 12,
        }}>
          {AGENTS.map((a) => <AgentCard key={a.id} agent={a} onOpen={onOpenAgent} />)}
        </div>
      </div>

      {/* Activity + health */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 12, minHeight: 360 }}>
        <div className="panel">
          <div className="panel-header">
            <span className="dot ok pulse" />
            <span className="panel-title">LIVE ACTIVITY</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)', letterSpacing: '0.1em' }}>
              STREAMING · TAIL=30
            </span>
          </div>
          <div className="panel-body" style={{ padding: '8px 14px' }}>
            <ActivityFeed />
          </div>
        </div>
        <SystemHealth />
      </div>
    </div>
  );
}

window.OverviewView = OverviewView;

/* global React, AGENTS, AgentGlyph, Tag, Dot, Progress, KV */
// ═══════════════════════════════════════════════════════════════
// AGENT WORKSPACES (PART 2) — Ledger, Echo, Hearth
// ═══════════════════════════════════════════════════════════════

const { useState: useS2, useEffect: useE2 } = React;

// ──────────────────────────────────────────────────────────────
// LEDGER · ATLAS — team-distribution manager
// Ledger orchestrates a fleet of finance sub-workers and shows
// how it distributes work across them.
// ──────────────────────────────────────────────────────────────
const ATLAS_WORKERS = [
  { id: 'w-cat',  name: 'CATEGORIZER',  glyph: 'CT', color: '#E0B85C', model: 'haiku-4.5',  status: 'active', load: 0.78, queue: 14, done24: 312, avgMs: 420,  job: 'classify · Whole Foods $148.22' },
  { id: 'w-ocr',  name: 'RECEIPTS·OCR', glyph: 'OC', color: '#7CB6E8', model: 'haiku-4.5',  status: 'active', load: 0.42, queue: 6,  done24: 88,  avgMs: 1820, job: 'extract · IMG_4421.heic (line 4/12)' },
  { id: 'w-rec',  name: 'RECONCILER',   glyph: 'RE', color: '#6FCF7F', model: 'haiku-4.5',  status: 'idle',   load: 0.04, queue: 0,  done24: 4,   avgMs: 8200, job: 'next fire · 06:00 daily' },
  { id: 'w-fraud',name: 'FRAUD·WATCH',  glyph: 'FR', color: '#E5484D', model: 'sonnet-4.5', status: 'busy',   load: 0.91, queue: 2,  done24: 41,  avgMs: 2100, job: 'investigate · $312 · 04/25 · unknown' },
  { id: 'w-fc',   name: 'FORECASTER',   glyph: 'FC', color: '#B98CE0', model: 'sonnet-4.5', status: 'idle',   load: 0.00, queue: 0,  done24: 1,   avgMs: 12400,job: 'next · weekly · Sun 18:00' },
  { id: 'w-tax',  name: 'TAX·PREP',     glyph: 'TX', color: '#5FD3D3', model: 'sonnet-4.5', status: 'paused', load: 0.00, queue: 0,  done24: 0,   avgMs: 0,    job: 'paused · Q2 window opens 06/01' },
  { id: 'w-bdg',  name: 'BUDGETER',     glyph: 'BD', color: '#E08C5F', model: 'haiku-4.5',  status: 'active', load: 0.31, queue: 1,  done24: 24,  avgMs: 680,  job: 'monitor · INFRA at 78% of cap' },
];

const DISPATCH_LOG = [
  { t: '14:32:08', from: 'sentinel',  to: 'w-cat',  msg: 'tx.classify · Whole Foods $148.22', kind: 'dispatch' },
  { t: '14:32:04', from: 'w-cat',     to: 'ledger', msg: '✓ → GROCERY · conf 0.88',           kind: 'return' },
  { t: '14:31:58', from: 'sentinel',  to: 'w-ocr',  msg: 'receipt.parse · IMG_4421.heic',     kind: 'dispatch' },
  { t: '14:31:42', from: 'ledger',    to: 'w-fraud',msg: 'flag · $312 unknown · investigate', kind: 'dispatch' },
  { t: '14:31:30', from: 'w-bdg',     to: 'ledger', msg: '⚠ INFRA category at 78% of cap',    kind: 'alert' },
  { t: '14:30:54', from: 'w-cat',     to: 'ledger', msg: '✓ Anthropic API → AI/TOOLS',        kind: 'return' },
  { t: '14:30:33', from: 'w-cat',     to: 'ledger', msg: '✓ AWS → INFRA · conf 1.00',         kind: 'return' },
  { t: '14:30:12', from: 'sentinel',  to: 'w-rec',  msg: 'reconcile · stripe ↔ books',        kind: 'dispatch' },
];

function LedgerWorkspace() {
  const totalLoad = ATLAS_WORKERS.reduce((s, w) => s + w.load, 0) / ATLAS_WORKERS.length;
  const totalQueue = ATLAS_WORKERS.reduce((s, w) => s + w.queue, 0);
  const totalDone = ATLAS_WORKERS.reduce((s, w) => s + w.done24, 0);
  const activeCount = ATLAS_WORKERS.filter((w) => w.status === 'active' || w.status === 'busy').length;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 14, padding: 18, height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
        {/* TOP — manager strip */}
        <div className="panel" style={{ borderLeft: '2px solid var(--ledger)' }}>
          <div className="panel-header">
            <span className="panel-title" style={{ color: 'var(--ledger)' }}>ATLAS · TEAM MANAGER</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)' }}>
              {activeCount}/{ATLAS_WORKERS.length} WORKERS ONLINE · DISTRIBUTING
            </span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            <BigNum label="FLEET LOAD"  value={`${Math.round(totalLoad * 100)}%`} accent="var(--ledger)" />
            <BigNum label="QUEUE"       value={String(totalQueue)} />
            <BigNum label="DONE / 24H"  value={String(totalDone)} accent="var(--ok)" />
            <BigNum label="DISPATCH/MIN" value="14.2" />
          </div>
        </div>

        {/* DISTRIBUTION DIAGRAM */}
        <div className="panel">
          <div className="panel-header"><span className="panel-title">WORK DISTRIBUTION · LIVE</span></div>
          <div className="panel-body">
            <DistributionDiagram workers={ATLAS_WORKERS} />
          </div>
        </div>

        {/* WORKER GRID */}
        <div className="panel" style={{ flex: 1, minHeight: 240 }}>
          <div className="panel-header">
            <span className="panel-title">WORKER FLEET · {ATLAS_WORKERS.length}</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
              <button className="btn" style={{ fontSize: 9 }}>+ SPAWN WORKER</button>
              <button className="btn" style={{ fontSize: 9 }}>⏸ PAUSE FLEET</button>
            </span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
            {ATLAS_WORKERS.map((w) => <WorkerCard key={w.id} w={w} />)}
          </div>
        </div>
      </div>

      {/* RIGHT RAIL — dispatch log + stats */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">DISPATCH LOG · LIVE</span>
            <span className="dot ok pulse" style={{ marginLeft: 'auto' }} />
          </div>
          <div className="panel-body" style={{ padding: 0, maxHeight: 300, overflow: 'auto' }}>
            {DISPATCH_LOG.map((l, i) => {
              const fromW = ATLAS_WORKERS.find((w) => w.id === l.from);
              const toW = ATLAS_WORKERS.find((w) => w.id === l.to);
              const fromName = fromW ? fromW.name : l.from.toUpperCase();
              const toName   = toW   ? toW.name   : l.to.toUpperCase();
              const arrow = l.kind === 'dispatch' ? '→' : l.kind === 'return' ? '←' : '!';
              const accent = l.kind === 'alert' ? 'var(--amber)' : l.kind === 'return' ? 'var(--ok)' : 'var(--ledger)';
              return (
                <div key={i} style={{
                  padding: '7px 12px',
                  borderBottom: '1px solid var(--line)',
                  fontSize: 10,
                  fontFamily: 'var(--mono)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--fg-faint)' }}>
                    <span>{l.t}</span>
                    <span style={{ color: accent }}>{l.kind.toUpperCase()}</span>
                  </div>
                  <div style={{ marginTop: 2, color: 'var(--fg-mute)' }}>
                    <span style={{ color: 'var(--fg-dim)' }}>{fromName}</span>
                    <span style={{ color: accent, margin: '0 6px' }}>{arrow}</span>
                    <span style={{ color: 'var(--fg)' }}>{toName}</span>
                  </div>
                  <div style={{ marginTop: 2, color: 'var(--fg)' }}>{l.msg}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">ROUTING POLICY</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 10 }}>
            <PolicyRow rule="tx · amount &lt; $50"  to="CATEGORIZER" />
            <PolicyRow rule="tx · amount ≥ $50"   to="CATEGORIZER + FRAUD" />
            <PolicyRow rule="receipt · image"      to="RECEIPTS·OCR" />
            <PolicyRow rule="anomaly · z &gt; 2.5" to="FRAUD·WATCH" />
            <PolicyRow rule="cap · approach 80%"   to="BUDGETER" />
            <PolicyRow rule="daily · 06:00"        to="RECONCILER" />
          </div>
        </div>
      </div>
    </div>
  );
}
function BigNum({ label, value, accent }) {
  return (
    <div>
      <div style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--fg-dim)' }}>{label}</div>
      <div style={{
        fontFamily: 'var(--mono)', fontSize: 22, fontVariantNumeric: 'tabular-nums',
        color: accent || 'var(--fg)', marginTop: 2,
      }}>{value}</div>
    </div>
  );
}
function CatBar({ label, value, amount, color }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 3 }}>
        <span style={{ letterSpacing: '0.1em', color: 'var(--fg-mute)' }}>{label}</span>
        <span style={{ fontFamily: 'var(--mono)', color: 'var(--fg)' }}>{amount}</span>
      </div>
      <div style={{ height: 4, background: 'var(--line)', borderRadius: 1, overflow: 'hidden' }}>
        <div style={{ width: `${value * 100}%`, height: '100%', background: color }} />
      </div>
    </div>
  );
}
function ConfDots({ conf }) {
  return (
    <div style={{ display: 'flex', gap: 1 }}>
      {[0, 1, 2, 3].map((i) => (
        <span key={i} style={{
          width: 4, height: 4, borderRadius: 50,
          background: conf > i * 0.25 ? 'var(--ok)' : 'var(--line-strong)',
        }} />
      ))}
    </div>
  );
}

// ─── ATLAS team-distribution helpers ───
function WorkerCard({ w }) {
  const statusColor =
    w.status === 'busy' ? 'var(--amber)' :
    w.status === 'active' ? 'var(--ok)' :
    w.status === 'paused' ? 'var(--fg-faint)' :
    'var(--fg-dim)';
  return (
    <div style={{
      border: '1px solid var(--line)',
      borderLeft: `2px solid ${w.color}`,
      background: 'var(--bg-elevated)',
      padding: 10,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      opacity: w.status === 'paused' ? 0.55 : 1,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          width: 18, height: 18,
          border: `1px solid ${w.color}`,
          color: w.color,
          display: 'grid', placeItems: 'center',
          fontSize: 9, fontWeight: 700,
          fontFamily: 'var(--mono)',
        }}>{w.glyph}</span>
        <span style={{ fontSize: 11, letterSpacing: '0.08em', color: w.color, fontWeight: 600 }}>{w.name}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5 }}>
          <span className={`dot ${w.status === 'idle' || w.status === 'paused' ? 'idle' : w.status === 'busy' ? 'warn' : 'ok'} ${w.status === 'active' || w.status === 'busy' ? 'pulse' : ''}`} />
          <span style={{ fontSize: 9, letterSpacing: '0.14em', color: statusColor }}>{w.status.toUpperCase()}</span>
        </span>
      </div>
      <div style={{ fontSize: 10, color: 'var(--fg-dim)', fontFamily: 'var(--mono)' }}>
        {w.model} · {w.queue} queued · {w.done24} done/24h
      </div>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--fg-dim)', marginBottom: 3, letterSpacing: '0.1em' }}>
          <span>LOAD</span>
          <span style={{ fontFamily: 'var(--mono)', color: 'var(--fg)' }}>{Math.round(w.load * 100)}%</span>
        </div>
        <div style={{ height: 3, background: 'var(--line)', overflow: 'hidden' }}>
          <div style={{
            width: `${w.load * 100}%`, height: '100%', background: w.color,
            boxShadow: w.status === 'busy' || w.status === 'active' ? `0 0 6px ${w.color}` : 'none',
          }} />
        </div>
      </div>
      <div style={{
        fontSize: 10, color: 'var(--fg-mute)',
        padding: '5px 8px',
        borderLeft: `1px solid ${w.color}`,
        background: 'var(--bg-deep)',
        fontFamily: 'var(--mono)',
      }}>
        ▸ {w.job}
      </div>
    </div>
  );
}

function DistributionDiagram({ workers }) {
  // Hub-and-spoke layout: ATLAS in center, workers radiating
  const cx = 50, cy = 50;
  const radius = 38;
  return (
    <div style={{
      position: 'relative',
      height: 220,
      width: '100%',
    }}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{
        position: 'absolute', inset: 0, width: '100%', height: '100%',
      }}>
        {workers.map((w, i) => {
          const angle = (i / workers.length) * Math.PI * 2 - Math.PI / 2;
          const x = cx + Math.cos(angle) * radius;
          const y = cy + Math.sin(angle) * radius;
          const active = w.status === 'active' || w.status === 'busy';
          return (
            <g key={w.id}>
              <line x1={cx} y1={cy} x2={x} y2={y}
                stroke={active ? w.color : 'var(--line)'}
                strokeWidth={active ? 0.3 : 0.15}
                strokeDasharray={active ? 'none' : '0.5 0.5'}
                opacity={active ? 0.7 : 0.4}
              />
              {active && (
                <circle r="0.5" fill={w.color}>
                  <animateMotion dur={`${2 + i * 0.3}s`} repeatCount="indefinite"
                    path={`M${cx},${cy} L${x},${y}`} />
                </circle>
              )}
            </g>
          );
        })}
      </svg>
      {/* Center hub */}
      <div style={{
        position: 'absolute',
        left: '50%', top: '50%',
        transform: 'translate(-50%, -50%)',
        width: 64, height: 64,
        border: '1px solid var(--ledger)',
        background: 'var(--bg-deep)',
        display: 'grid',
        placeItems: 'center',
        gap: 2,
        textAlign: 'center',
        boxShadow: '0 0 16px rgba(224,184,92,0.18)',
      }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: '0.18em', color: 'var(--ledger)', fontWeight: 700 }}>ATLAS</div>
          <div style={{ fontSize: 8, letterSpacing: '0.1em', color: 'var(--fg-faint)', marginTop: 1 }}>MANAGER</div>
        </div>
      </div>
      {/* Worker nodes */}
      {workers.map((w, i) => {
        const angle = (i / workers.length) * Math.PI * 2 - Math.PI / 2;
        const x = 50 + Math.cos(angle) * 38;
        const y = 50 + Math.sin(angle) * 38;
        const active = w.status === 'active' || w.status === 'busy';
        return (
          <div key={w.id} style={{
            position: 'absolute',
            left: `${x}%`, top: `${y}%`,
            transform: 'translate(-50%, -50%)',
            width: 50, height: 36,
            border: `1px solid ${active ? w.color : 'var(--line-strong)'}`,
            background: 'var(--bg-elevated)',
            display: 'grid', placeItems: 'center',
            opacity: w.status === 'paused' ? 0.4 : 1,
            boxShadow: active ? `0 0 8px ${w.color}40` : 'none',
          }}>
            <div style={{ fontSize: 8, letterSpacing: '0.1em', color: w.color, fontWeight: 700 }}>{w.name.split('·')[0].trim()}</div>
            <div style={{ fontSize: 7, color: 'var(--fg-dim)', fontFamily: 'var(--mono)' }}>
              {w.queue}q · {Math.round(w.load * 100)}%
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PolicyRow({ rule, to }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '4px 0',
      borderBottom: '1px dashed var(--line)',
      fontFamily: 'var(--mono)',
    }}>
      <span style={{ flex: 1, color: 'var(--fg-mute)' }} dangerouslySetInnerHTML={{ __html: rule }} />
      <span style={{ color: 'var(--ledger)', fontSize: 10 }}>→</span>
      <span style={{ color: 'var(--ledger)', fontSize: 10, letterSpacing: '0.06em' }}>{to}</span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// ECHO — messages
// ──────────────────────────────────────────────────────────────
function EchoWorkspace() {
  const threads = [
    { ch: 'iMessage', from: 'Sasha P.',     last: 'thx for the heads up!',          unread: 0, kind: 'imessage', auto: false, time: '14:31' },
    { ch: 'Slack',    from: '#standup',     last: 'echo: ack · away till 11',       unread: 0, kind: 'slack',    auto: true,  time: '14:24' },
    { ch: 'WhatsApp', from: 'Mom',          last: 'sending photos shortly',         unread: 2, kind: 'whatsapp', auto: false, time: '14:18' },
    { ch: 'Slack',    from: '#eng',         last: 'PR #482 ready for review',       unread: 4, kind: 'slack',    auto: false, time: '14:02' },
    { ch: 'iMessage', from: 'M. Voss',      last: 'lunch tue or wed?',              unread: 1, kind: 'imessage', auto: false, time: '13:54' },
    { ch: 'Slack',    from: '@anna',        last: 'deck v3 in figma',                unread: 0, kind: 'slack',    auto: false, time: '13:42' },
    { ch: 'iMessage', from: 'Family group', last: '— summary by ECHO —',             unread: 0, kind: 'imessage', auto: true,  time: '13:30' },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr 280px', gap: 14, padding: 18, height: '100%', overflow: 'auto' }}>
      <div className="panel" style={{ minHeight: 0 }}>
        <div className="panel-header"><span className="panel-title">THREADS · 47 ACTIVE</span></div>
        <div className="panel-body" style={{ padding: 0 }}>
          {threads.map((t, i) => (
            <div key={i} style={{
              padding: '10px 12px',
              borderBottom: '1px solid var(--line)',
              display: 'flex',
              gap: 8,
              alignItems: 'center',
              background: i === 4 ? 'var(--bg-hover)' : 'transparent',
              borderLeft: i === 4 ? '2px solid var(--echo)' : '2px solid transparent',
              cursor: 'pointer',
            }}>
              <ChannelGlyph kind={t.kind} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 11, color: 'var(--fg)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {t.from}
                  {t.auto && <Tag kind="info" style={{ fontSize: 8 }}>AUTO</Tag>}
                </div>
                <div style={{ fontSize: 10, color: 'var(--fg-dim)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{t.last}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 9, color: 'var(--fg-faint)', fontFamily: 'var(--mono)' }}>{t.time}</div>
                {t.unread > 0 && (
                  <div style={{ marginTop: 3, fontSize: 9, color: 'var(--echo)', fontFamily: 'var(--mono)' }}>
                    {t.unread} new
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel" style={{ minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div className="panel-header">
          <ChannelGlyph kind="imessage" />
          <span className="panel-title">M. VOSS · IMESSAGE</span>
          <Tag kind="info" style={{ marginLeft: 'auto' }}>AWAITING DRAFT</Tag>
        </div>
        <div className="panel-body" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
          <Bubble side="left">Hey! free for lunch this week? was thinking japanese</Bubble>
          <Bubble side="left">tue or wed work?</Bubble>
          <div style={{ fontSize: 9, color: 'var(--fg-faint)', textAlign: 'center', letterSpacing: '0.1em', margin: '4px 0' }}>
            ⎯⎯ ECHO ROUTED → CHRONOS · 14:02 ⎯⎯
          </div>
          <Bubble side="left" agent="chronos">
            <div style={{ fontSize: 10, color: 'var(--chronos)', marginBottom: 4 }}>CHRONOS · proposed</div>
            Tue 12:00 · Wed 12:30 · Thu 13:00<br/>
            <span style={{ color: 'var(--fg-dim)', fontSize: 10 }}>Pick one — I'll send confirmation.</span>
          </Bubble>
          <div style={{ marginTop: 'auto', display: 'flex', gap: 8 }}>
            <input className="field-input" placeholder="Type or let Echo draft…"
              style={{ flex: 1, background: 'var(--bg-input)', border: '1px solid var(--line)', padding: '8px 10px', borderRadius: 2, fontSize: 12, fontFamily: 'var(--mono)' }} />
            <button className="btn primary">DRAFT</button>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">AUTO-REPLIED · 24H</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <KV label="ACK / AWAY">23</KV>
            <KV label="ROUTED PEERS">14</KV>
            <KV label="DIGESTED">8</KV>
            <KV label="ESCALATED" accent="var(--amber)">5</KV>
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">CHANNEL STATUS</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <ChannelStatus kind="imessage" name="iMessage" status="ok" qps="0.4/s" />
            <ChannelStatus kind="slack"    name="Slack"    status="ok" qps="2.1/s" />
            <ChannelStatus kind="whatsapp" name="WhatsApp" status="ok" qps="0.1/s" />
            <ChannelStatus kind="signal"   name="Signal"   status="off" qps="—" />
          </div>
        </div>
      </div>
    </div>
  );
}
function Bubble({ side, agent, children }) {
  const ag = agent ? AGENTS.find((a) => a.id === agent) : null;
  return (
    <div style={{
      alignSelf: side === 'left' ? 'flex-start' : 'flex-end',
      maxWidth: '78%',
      padding: '8px 12px',
      background: ag ? `${ag.colorHex}1f` : 'var(--bg-elevated)',
      border: `1px solid ${ag ? ag.colorHex : 'var(--line)'}`,
      borderRadius: 4,
      fontSize: 12,
      fontFamily: 'var(--sans)',
      lineHeight: 1.5,
    }}>{children}</div>
  );
}
function ChannelGlyph({ kind }) {
  const map = {
    imessage: { ch: 'iM', color: '#5FD3D3' },
    slack:    { ch: 'sl', color: '#B98CE0' },
    whatsapp: { ch: 'Wa', color: '#6FCF7F' },
    signal:   { ch: 'sg', color: '#7CB6E8' },
  };
  const m = map[kind] || { ch: '??', color: 'var(--fg-dim)' };
  return (
    <span style={{
      width: 22, height: 22, border: `1px solid ${m.color}`, color: m.color,
      display: 'inline-grid', placeItems: 'center', fontSize: 9, fontWeight: 700,
      fontFamily: 'var(--mono)', letterSpacing: '-0.04em', flexShrink: 0,
    }}>{m.ch}</span>
  );
}
function ChannelStatus({ kind, name, status, qps }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
      <ChannelGlyph kind={kind} />
      <span style={{ flex: 1 }}>{name}</span>
      <Dot kind={status === 'ok' ? 'ok' : 'idle'} pulse={status === 'ok'} />
      <span style={{ color: 'var(--fg-dim)', fontFamily: 'var(--mono)', fontSize: 10, width: 50, textAlign: 'right' }}>{qps}</span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// HEARTH — home schematic
// ──────────────────────────────────────────────────────────────
function HearthWorkspace() {
  const rooms = [
    { name: 'LIVING',    x: 8,  y: 8,  w: 50, h: 38, lights: 'on',   temp: 71, devices: 4 },
    { name: 'KITCHEN',   x: 60, y: 8,  w: 32, h: 28, lights: 'off',  temp: 70, devices: 3 },
    { name: 'OFFICE',    x: 60, y: 38, w: 32, h: 26, lights: 'on',   temp: 72, devices: 5 },
    { name: 'BEDROOM',   x: 8,  y: 48, w: 32, h: 30, lights: 'off',  temp: 68, devices: 3 },
    { name: 'BATH',      x: 42, y: 48, w: 16, h: 18, lights: 'off',  temp: 69, devices: 2 },
    { name: 'ENTRY',     x: 42, y: 68, w: 50, h: 12, lights: 'auto', temp: 70, devices: 2 },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, padding: 18, height: '100%', overflow: 'auto' }}>
      <div className="panel">
        <div className="panel-header"><span className="panel-title">FLOORPLAN · LIVE</span>
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)' }}>19 DEVICES · 17 ONLINE</span>
        </div>
        <div className="panel-body" style={{ padding: 18 }}>
          <div style={{
            position: 'relative',
            aspectRatio: '16/11',
            background: 'var(--bg-deep)',
            border: '1px solid var(--line)',
            backgroundImage: 'linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}>
            {rooms.map((r) => (
              <div key={r.name} style={{
                position: 'absolute',
                left: `${r.x}%`, top: `${r.y}%`,
                width: `${r.w}%`, height: `${r.h}%`,
                border: '1px solid var(--line-bright)',
                background: r.lights === 'on'
                  ? 'rgba(224,140,95,0.10)'
                  : r.lights === 'auto' ? 'rgba(95,211,211,0.06)' : 'transparent',
                padding: 8,
                fontSize: 10,
                fontFamily: 'var(--mono)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <span style={{ letterSpacing: '0.18em', color: 'var(--fg-mute)' }}>{r.name}</span>
                  <Dot kind={r.lights === 'on' ? 'warn' : r.lights === 'auto' ? 'ok' : 'idle'} pulse={r.lights === 'on'} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--fg-dim)' }}>
                  <span>{r.temp}°F</span>
                  <span>{r.devices}d</span>
                </div>
              </div>
            ))}
            {/* legend */}
            <div style={{ position: 'absolute', bottom: 6, left: 6, fontSize: 9, color: 'var(--fg-faint)', letterSpacing: '0.14em' }}>
              <span style={{ color: 'var(--hearth)' }}>● ON</span> &nbsp;
              <span style={{ color: 'var(--echo)' }}>● AUTO</span> &nbsp;
              <span>○ OFF</span>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">CURRENT SCENE</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 14, color: 'var(--hearth)', fontFamily: 'var(--sans)' }}>◐ LATE AFTERNOON</div>
            <div style={{ fontSize: 11, color: 'var(--fg-dim)' }}>
              Living + Office lit · climate 71°F · entry armed-stay · next: SUNSET routine 19:42
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">SCHEDULED ROUTINES</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 11 }}>
            <Routine time="19:42" name="warm-evening" desc="dim → 40% · color 2700K" />
            <Routine time="22:00" name="wind-down"    desc="bedroom 65°F · lights off" />
            <Routine time="23:00" name="armed-night"  desc="security · all sensors" off />
            <Routine time="06:30" name="sunrise"      desc="bedroom 70°F · gentle light" />
            <Routine time="07:00" name="morning-news" desc="kitchen audio · NPR" />
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">SENSOR FEED · LIVE</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--fg-mute)' }}>
            <div>14:32:11 &nbsp;office.motion &nbsp;&nbsp; → DETECTED</div>
            <div>14:31:48 &nbsp;living.lux &nbsp;&nbsp;&nbsp;&nbsp; → 320 lx</div>
            <div>14:31:30 &nbsp;kitchen.temp &nbsp;&nbsp; → 70.4°F</div>
            <div>14:30:14 &nbsp;entry.contact &nbsp; → CLOSED</div>
            <div>14:29:02 &nbsp;office.lux &nbsp;&nbsp;&nbsp;&nbsp; → 480 lx</div>
            <div style={{ color: 'var(--fg-faint)' }}>… 3,420 events / 24h</div>
          </div>
        </div>
      </div>
    </div>
  );
}
function Routine({ time, name, desc, off }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '6px 0', borderBottom: '1px dashed var(--line)',
      opacity: off ? 0.5 : 1,
    }}>
      <span style={{ fontFamily: 'var(--mono)', color: 'var(--hearth)', width: 50 }}>{time}</span>
      <div style={{ flex: 1 }}>
        <div style={{ color: 'var(--fg)', fontSize: 11 }}>{name}</div>
        <div style={{ color: 'var(--fg-dim)', fontSize: 10 }}>{desc}</div>
      </div>
      <Dot kind={off ? 'idle' : 'ok'} />
    </div>
  );
}

Object.assign(window, { LedgerWorkspace, EchoWorkspace, HearthWorkspace });

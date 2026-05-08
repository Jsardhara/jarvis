/* global React, AGENTS, SENTINEL_JOBS, AgentGlyph, Tag, Dot, Progress, KV, Bars,
   AideWorkspace, ChronosWorkspace, SherlockWorkspace, ForgeWorkspace,
   LedgerWorkspace, EchoWorkspace, HearthWorkspace */
// ═══════════════════════════════════════════════════════════════
// AGENT DETAIL VIEW — wraps a workspace with header + control rail
// SENTINEL VIEW — scheduled jobs
// ═══════════════════════════════════════════════════════════════

const { useState: useS3, useEffect: useE3 } = React;

const WORKSPACE_MAP = {
  aide: AideWorkspace,
  chronos: ChronosWorkspace,
  sherlock: SherlockWorkspace,
  forge: ForgeWorkspace,
  ledger: LedgerWorkspace,
  echo: EchoWorkspace,
  hearth: HearthWorkspace,
};

function AgentDetailView({ agentId }) {
  const agent = AGENTS.find((a) => a.id === agentId);
  if (!agent) return <div style={{ padding: 40 }}>Unknown agent</div>;
  const Workspace = WORKSPACE_MAP[agentId];
  const [tab, setTab] = useS3('workspace');
  const [running, setRunning] = useS3(agent.status !== 'idle');
  const [bars, setBars] = useS3(() => Array.from({ length: 36 }, () => 5 + Math.random() * 30));

  useE3(() => {
    if (!running) return;
    const id = setInterval(() => {
      setBars((b) => [...b.slice(1), 5 + Math.random() * 35]);
    }, 800);
    return () => clearInterval(id);
  }, [running]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Agent header strip */}
      <div style={{
        background: 'var(--bg-deep)',
        borderBottom: '1px solid var(--line)',
        padding: '14px 20px',
        display: 'grid',
        gridTemplateColumns: 'auto 1fr auto auto auto auto',
        gap: 24,
        alignItems: 'center',
        position: 'relative',
      }}>
        <span style={{
          position: 'absolute', top: 0, left: 0, height: '100%', width: 3,
          background: agent.colorHex, boxShadow: `0 0 12px ${agent.colorHex}55`,
        }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <AgentGlyph agent={agent} size={42} />
          <div>
            <div style={{
              fontFamily: 'var(--sans)', fontSize: 22, fontWeight: 500, letterSpacing: '0.06em',
              color: agent.colorHex,
            }}>{agent.name}</div>
            <div style={{ fontSize: 10, letterSpacing: '0.2em', color: 'var(--fg-dim)' }}>
              {agent.role} · {agent.tagline}
            </div>
          </div>
        </div>
        <div style={{ width: 200 }}>
          <Bars values={bars} color={agent.colorHex} height={32} />
          <div style={{ fontSize: 9, color: 'var(--fg-faint)', letterSpacing: '0.1em', marginTop: 2 }}>
            ACTIVITY · LAST 30s
          </div>
        </div>
        <Stat label="QUEUE" value={agent.queueDepth} />
        <Stat label="DONE/24" value={agent.completed24h} />
        <Stat label="COST/24" value={`$${agent.cost24h.toFixed(2)}`} />
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            className={`btn ${running ? '' : 'primary'}`}
            onClick={() => setRunning((r) => !r)}
          >{running ? '◼ PAUSE' : '▶ START'}</button>
          <button className="btn icon" title="Restart">↻</button>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid var(--line)',
        background: 'var(--bg-deep)',
        padding: '0 20px',
        gap: 0,
      }}>
        {[
          { id: 'workspace', label: 'WORKSPACE' },
          { id: 'config',    label: 'CONFIG · MODEL · PROMPT' },
          { id: 'memory',    label: 'MEMORY · CONTEXT' },
          { id: 'logs',      label: 'LOGS' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              background: 'transparent',
              border: 'none',
              padding: '10px 16px',
              fontSize: 10,
              letterSpacing: '0.16em',
              color: tab === t.id ? agent.colorHex : 'var(--fg-dim)',
              borderBottom: `2px solid ${tab === t.id ? agent.colorHex : 'transparent'}`,
              fontFamily: 'var(--mono)',
            }}
          >{t.label}</button>
        ))}
      </div>

      <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
        {tab === 'workspace' && Workspace && <Workspace />}
        {tab === 'config' && <ConfigTab agent={agent} />}
        {tab === 'memory' && <MemoryTab agent={agent} />}
        {tab === 'logs' && <LogsTab agent={agent} />}
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: 9, letterSpacing: '0.16em', color: 'var(--fg-dim)' }}>{label}</div>
      <div style={{ fontSize: 18, fontFamily: 'var(--mono)', color: 'var(--fg)', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
    </div>
  );
}

const SYSTEM_PROMPTS = {
  aide:    'You are AIDE, the email operations sub-agent.\nClassify incoming mail by intent (REPLY, ROUTE, ARCHIVE, FLAG).\nPropose drafts for P1 threads. Route P2 to peers.\nNever send P1 mail without user approval.',
  chronos: 'You are CHRONOS, the time-ops sub-agent.\nManage calendar + todos. Detect conflicts.\nPropose 3 slots for any new request unless constraints reduce options.\nNever book travel without explicit auth.',
  sherlock:'You are SHERLOCK, the research sub-agent.\nDo deep multi-hop research. Cite every claim.\nReturn structured digests with source list.\nRespect token budget; checkpoint at each step.',
  forge:   'You are FORGE, the code sub-agent.\nWrite, refactor, and review code.\nAlways run tests before declaring done.\nNever push to main; open PRs against feature branches.',
  ledger:  'You are LEDGER, the financial atlas sub-agent.\nCategorize transactions. Flag anomalies.\nBuild monthly + YTD reports. Never approve transfers.',
  echo:    'You are ECHO, the messaging sub-agent.\nTriage iMessage / Slack / WhatsApp threads.\nAuto-ack low-stakes pings; route scheduling to Chronos.\nNever send first-contact messages without approval.',
  hearth:  'You are HEARTH, the home-ops sub-agent.\nManage HomeKit scenes, sensors, routines.\nNever override security states without authorization.',
};

function ConfigTab({ agent }) {
  const [model, setModel] = useS3(agent.model);
  const [prompt, setPrompt] = useS3(SYSTEM_PROMPTS[agent.id] || '');
  const [schedule, setSchedule] = useS3(agent.schedule);
  const [maxBudget, setMaxBudget] = useS3('5.00');

  return (
    <div style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">SYSTEM PROMPT</span>
            <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--fg-dim)' }}>{prompt.length} CHARS · LAST EDIT 3d AGO</span>
          </div>
          <div className="panel-body">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              style={{
                width: '100%', minHeight: 220,
                background: 'var(--bg-input)',
                border: '1px solid var(--line)',
                color: 'var(--fg)',
                padding: 12,
                fontFamily: 'var(--mono)',
                fontSize: 11,
                lineHeight: 1.6,
                borderRadius: 2,
                outline: 'none',
                resize: 'vertical',
              }}
            />
            <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
              <button className="btn primary">SAVE & REDEPLOY</button>
              <button className="btn">REVERT</button>
              <button className="btn">DIFF</button>
              <button className="btn" style={{ marginLeft: 'auto' }}>VERSION HISTORY · 14</button>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><span className="panel-title">TOOLS · PERMISSIONS</span></div>
          <div className="panel-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
            {(agent.id === 'aide' ? ['gmail.read', 'gmail.send', 'gmail.archive', 'contacts.read'] :
              agent.id === 'chronos' ? ['cal.read', 'cal.write', 'todo.read', 'todo.write', 'travel.book'] :
              agent.id === 'sherlock' ? ['web.fetch', 'arxiv.search', 'wiki.read', 'pdf.parse'] :
              agent.id === 'forge' ? ['fs.read', 'fs.write', 'shell.exec', 'git.commit', 'gh.pr.open'] :
              agent.id === 'ledger' ? ['plaid.read', 'ramp.read', 'ramp.categorize'] :
              agent.id === 'echo' ? ['imessage.read', 'imessage.send', 'slack.read', 'slack.send', 'whatsapp.read', 'whatsapp.send'] :
              ['homekit.read', 'homekit.write', 'sensors.read', 'security.arm']
            ).map((tool, i) => (
              <ToolToggle key={tool} tool={tool} on={!(tool === 'travel.book' || tool === 'security.arm')} requiresAuth={tool === 'travel.book' || tool === 'gmail.send' || tool === 'security.arm'} />
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">MODEL</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {['claude-opus-4.7', 'claude-sonnet-4.5', 'claude-haiku-4.5'].map((m) => (
              <button key={m} onClick={() => setModel(m)} style={{
                textAlign: 'left',
                background: model === m ? 'var(--bg-elevated)' : 'transparent',
                border: `1px solid ${model === m ? agent.colorHex : 'var(--line)'}`,
                color: model === m ? agent.colorHex : 'var(--fg-mute)',
                padding: '8px 10px',
                fontSize: 11,
                fontFamily: 'var(--mono)',
                borderRadius: 2,
                cursor: 'pointer',
                display: 'flex',
                justifyContent: 'space-between',
              }}>
                <span>{m}</span>
                <span style={{ fontSize: 10, color: 'var(--fg-dim)' }}>
                  {m === 'claude-opus-4.7' ? '$15/Mtok' : m === 'claude-sonnet-4.5' ? '$3/Mtok' : '$0.80/Mtok'}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">SCHEDULE</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input value={schedule} onChange={(e) => setSchedule(e.target.value)}
              style={{ background: 'var(--bg-input)', border: '1px solid var(--line)', padding: 8, fontFamily: 'var(--mono)', fontSize: 11, borderRadius: 2, color: 'var(--fg)' }} />
            <div style={{ fontSize: 10, color: 'var(--fg-dim)' }}>cron-style · or "every Nm" / "on-demand"</div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">BUDGET CAPS · 24H</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <KV label="USED">${agent.cost24h.toFixed(2)}</KV>
            <KV label="CAP" accent="var(--amber)">${maxBudget}</KV>
            <input value={maxBudget} onChange={(e) => setMaxBudget(e.target.value)}
              style={{ background: 'var(--bg-input)', border: '1px solid var(--line)', padding: 8, fontFamily: 'var(--mono)', fontSize: 11, borderRadius: 2, color: 'var(--fg)' }} />
            <Progress value={agent.cost24h / parseFloat(maxBudget || 1)} color="var(--amber)" height={4} />
          </div>
        </div>
      </div>
    </div>
  );
}

function ToolToggle({ tool, on, requiresAuth }) {
  const [enabled, setEnabled] = useS3(on);
  return (
    <div
      onClick={() => setEnabled((x) => !x)}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 8px',
        border: '1px solid var(--line)',
        background: enabled ? 'var(--bg-elevated)' : 'transparent',
        borderRadius: 2,
        cursor: 'pointer',
        fontSize: 11,
      }}
    >
      <span style={{
        width: 24, height: 12,
        background: enabled ? 'var(--ok)' : 'var(--line-strong)',
        borderRadius: 6,
        position: 'relative',
        flexShrink: 0,
      }}>
        <span style={{
          position: 'absolute',
          top: 1, left: enabled ? 13 : 1,
          width: 10, height: 10,
          background: 'var(--bg-void)',
          borderRadius: 5,
          transition: 'left 120ms',
        }} />
      </span>
      <span style={{ fontFamily: 'var(--mono)', color: enabled ? 'var(--fg)' : 'var(--fg-dim)' }}>{tool}</span>
      {requiresAuth && <Tag kind="amber" style={{ marginLeft: 'auto' }}>AUTH</Tag>}
    </div>
  );
}

function MemoryTab({ agent }) {
  return (
    <div style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, height: '100%', overflow: 'auto' }}>
      <div className="panel">
        <div className="panel-header"><span className="panel-title">CONTEXT WINDOW · LIVE</span>
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)' }}>42,180 / 200,000 TOKENS · 21%</span>
        </div>
        <div className="panel-body" style={{ fontFamily: 'var(--mono)', fontSize: 10, lineHeight: 1.7, color: 'var(--fg-mute)' }}>
          <div style={{ color: agent.colorHex, marginBottom: 10 }}>▸ system_prompt · 412 tok</div>
          <div style={{ color: 'var(--fg-mute)', marginBottom: 8 }}>▸ working_memory · 8,940 tok</div>
          <div style={{ paddingLeft: 14, color: 'var(--fg-dim)' }}>
            • current_task: T-2834 (drafting reply)<br/>
            • recent_threads: 14 emails<br/>
            • peer_state: chronos.queue=2, echo.queue=7<br/>
          </div>
          <div style={{ marginTop: 10, color: 'var(--fg-mute)' }}>▸ retrieved_context · 22,408 tok</div>
          <div style={{ paddingLeft: 14, color: 'var(--fg-dim)' }}>
            • thread_history(sasha@petrov.io) · 18 mails<br/>
            • contact_card(sasha) · prefs, role, tz<br/>
            • org_directory · 84 entries<br/>
          </div>
          <div style={{ marginTop: 10, color: 'var(--fg-mute)' }}>▸ tool_outputs · 10,420 tok</div>
          <div style={{ paddingLeft: 14, color: 'var(--fg-dim)' }}>
            • gmail.list(unread) → 23 results<br/>
            • contacts.lookup(sasha) → 1 hit<br/>
            • cal.peek(2026-04-29) → 4 events<br/>
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">LONG-TERM MEMORY</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <KV label="VECTOR ENTRIES">14,208</KV>
            <KV label="LAST INDEX">2h ago</KV>
            <KV label="SIZE">412 MB</KV>
            <button className="btn" style={{ marginTop: 8 }}>BROWSE INDEX</button>
            <button className="btn">PURGE OLDER 30d</button>
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">PINNED FACTS</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11 }}>
            <PinnedFact>User prefers terse replies · no emoji</PinnedFact>
            <PinnedFact>Auto-archive newsletters silently</PinnedFact>
            <PinnedFact>CC legal on contract threads</PinnedFact>
            <PinnedFact>Investor list · 14 contacts (priority)</PinnedFact>
          </div>
        </div>
      </div>
    </div>
  );
}
function PinnedFact({ children }) {
  return (
    <div style={{
      padding: '6px 8px', border: '1px solid var(--line)',
      borderLeft: '2px solid var(--amber)', background: 'var(--bg-elevated)',
      fontFamily: 'var(--sans)', color: 'var(--fg-mute)',
    }}>{children}</div>
  );
}

function LogsTab({ agent }) {
  const [lines, setLines] = useS3(() => seedLogs(agent));
  useE3(() => {
    const id = setInterval(() => {
      const t = new Date();
      const pad = (x) => String(x).padStart(2, '0');
      const stamp = `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
      const msg = randomLog();
      setLines((cur) => [{ t: stamp, m: msg.m, lv: msg.lv }, ...cur].slice(0, 80));
    }, 2200);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{ padding: 14, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div className="panel" style={{ flex: 1, minHeight: 0 }}>
        <div className="panel-header">
          <span className="dot ok pulse" />
          <span className="panel-title">STREAMING LOGS · {agent.name}</span>
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)' }}>TAIL=80 · INFO+</span>
        </div>
        <div className="panel-body" style={{ padding: '8px 14px', overflow: 'auto', fontFamily: 'var(--mono)', fontSize: 11, lineHeight: 1.65 }}>
          {lines.map((l, i) => (
            <div key={i} style={{
              display: 'grid',
              gridTemplateColumns: '70px 60px 1fr',
              gap: 10,
              padding: '2px 0',
            }}>
              <span style={{ color: 'var(--fg-faint)' }}>{l.t}</span>
              <span style={{ color: l.lv === 'CRIT' ? 'var(--crit)' : l.lv === 'WARN' ? 'var(--warn)' : l.lv === 'OK' ? 'var(--ok)' : agent.colorHex, letterSpacing: '0.06em' }}>{l.lv}</span>
              <span style={{ color: 'var(--fg-mute)' }}>{l.m}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
function seedLogs(agent) {
  return [
    { t: '14:32:11', lv: 'INFO', m: `${agent.name.toLowerCase()} · classifier received task T-2834` },
    { t: '14:32:09', lv: 'INFO', m: 'context.fetch · 412 tokens · cache=hit' },
    { t: '14:32:07', lv: 'OK',   m: 'tool.invoke · gmail.list(unread) → 14 ok' },
    { t: '14:31:58', lv: 'INFO', m: 'reasoning.step 1/3 · classify intent' },
    { t: '14:31:42', lv: 'WARN', m: 'rate limit · gmail.list 80% of 250/min' },
    { t: '14:31:30', lv: 'INFO', m: 'tokens · in+1240 out+320 cost=$0.012' },
    { t: '14:30:58', lv: 'OK',   m: 'task T-2828 completed · status=done' },
    { t: '14:30:21', lv: 'INFO', m: 'sentinel · scheduled poll fired' },
  ];
}
function randomLog() {
  const opts = [
    { lv: 'INFO', m: 'reasoning.step · synthesizing response' },
    { lv: 'INFO', m: 'tokens · in+820 out+201 cost=$0.008' },
    { lv: 'OK',   m: 'tool.invoke completed · latency 1.2s' },
    { lv: 'INFO', m: 'context.fetch · cache=hit' },
    { lv: 'INFO', m: 'classifier · confidence 0.94' },
    { lv: 'WARN', m: 'context.window · 78% of cap' },
    { lv: 'INFO', m: 'peer.notify · routed to chronos' },
  ];
  return opts[Math.floor(Math.random() * opts.length)];
}

// ──────────────────────────────────────────────────────────────
// SENTINEL VIEW
// ──────────────────────────────────────────────────────────────
function SentinelView() {
  return (
    <div style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">SENTINEL · BACKGROUND DAEMON</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
              <Dot kind="ok" pulse />
              <span style={{ fontSize: 10, color: 'var(--ok)', letterSpacing: '0.14em' }}>RUNNING · APSCHEDULER</span>
            </span>
          </div>
          <div className="panel-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            <Stat label="JOBS · ENABLED" value="6 / 7" />
            <Stat label="FIRED · 24H" value="184" />
            <Stat label="DISPATCHED" value="184" />
            <Stat label="MISSES" value="0" />
          </div>
        </div>

        <div className="panel" style={{ flex: 1, minHeight: 200 }}>
          <div className="panel-header"><span className="panel-title">SCHEDULED JOBS</span>
            <button className="btn" style={{ marginLeft: 'auto' }}>+ NEW JOB</button>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: '20px 1fr 90px 90px 100px 110px 80px',
              gap: 12,
              padding: '8px 14px',
              fontSize: 9,
              letterSpacing: '0.16em',
              color: 'var(--fg-dim)',
              borderBottom: '1px solid var(--line)',
            }}>
              <span></span>
              <span>JOB</span>
              <span>CADENCE</span>
              <span>TARGET</span>
              <span>LAST</span>
              <span>NEXT</span>
              <span>STATUS</span>
            </div>
            {SENTINEL_JOBS.map((j) => {
              const target = AGENTS.find((a) => a.id === j.target);
              return (
                <div key={j.id} style={{
                  display: 'grid',
                  gridTemplateColumns: '20px 1fr 90px 90px 100px 110px 80px',
                  gap: 12,
                  padding: '10px 14px',
                  fontSize: 11,
                  borderBottom: '1px solid var(--line)',
                  alignItems: 'center',
                  opacity: j.enabled ? 1 : 0.45,
                }}>
                  <Dot kind={j.enabled ? 'ok' : 'idle'} pulse={j.enabled} />
                  <span style={{ fontFamily: 'var(--mono)', color: 'var(--fg)' }}>{j.name}</span>
                  <Tag>{j.cadence}</Tag>
                  <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    {target && <AgentGlyph agent={target} size={14} />}
                    <span style={{ fontSize: 10, color: target ? target.colorHex : 'var(--fg-dim)' }}>{j.target}</span>
                  </span>
                  <span style={{ fontFamily: 'var(--mono)', color: 'var(--fg-dim)', fontSize: 10 }}>{j.last}</span>
                  <span style={{ fontFamily: 'var(--mono)', color: 'var(--amber)', fontSize: 10 }}>{j.next}</span>
                  <button className="btn" style={{ fontSize: 9, padding: '3px 6px' }}>{j.enabled ? '◼ DISABLE' : '▶ ENABLE'}</button>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">TIMELINE · NEXT 6H</span></div>
          <div className="panel-body" style={{ position: 'relative', minHeight: 300 }}>
            <div style={{ position: 'absolute', left: 50, top: 0, bottom: 0, width: 1, background: 'var(--line-bright)' }} />
            {SENTINEL_JOBS.filter((j) => j.enabled).map((j, i) => {
              const target = AGENTS.find((a) => a.id === j.target);
              return (
                <div key={j.id} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 14,
                  position: 'relative', paddingTop: i === 0 ? 0 : 12,
                }}>
                  <span style={{
                    width: 50, fontFamily: 'var(--mono)', fontSize: 10,
                    color: 'var(--amber)', textAlign: 'right', paddingTop: 2,
                  }}>{j.next.split(' ').pop()}</span>
                  <span style={{
                    width: 9, height: 9, borderRadius: 5,
                    background: target ? target.colorHex : 'var(--amber)',
                    boxShadow: `0 0 6px ${target ? target.colorHex : 'var(--amber)'}`,
                    marginTop: 4, marginLeft: -4, flexShrink: 0,
                  }} />
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--fg)' }}>{j.name}</div>
                    <div style={{ fontSize: 10, color: 'var(--fg-dim)' }}>→ {j.target}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { AgentDetailView, SentinelView });

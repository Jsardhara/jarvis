/* global React, AGENTS, AgentGlyph, Tag, Dot, Progress, KV, SectionHeading, Placeholder, Bars, TickNum */
// ═══════════════════════════════════════════════════════════════
// AGENT WORKSPACES (PART 1) — Aide, Chronos, Sherlock, Forge
// Each shows what the agent is actually doing in its native medium
// ═══════════════════════════════════════════════════════════════

const { useState: useS1, useEffect: useE1 } = React;

// ──────────────────────────────────────────────────────────────
// AIDE — email inbox triage
// ──────────────────────────────────────────────────────────────
const INBOX_EMAILS = [
  { from: 'Sasha Petrov',     subj: 'Re: Q2 review schedule',     time: '14:32', cls: 'P1 · REPLY',     status: 'drafting',  preview: 'Thanks for the slot. Two questions on the agenda…' },
  { from: 'Marcus Voss',      subj: 'Lunch next week?',           time: '14:18', cls: 'P2 · CHRONOS',   status: 'routed',    preview: 'Routed to Chronos for scheduling.' },
  { from: 'AWS Billing',      subj: 'Invoice #2860493',           time: '13:54', cls: 'P3 · LEDGER',    status: 'routed',    preview: 'Forwarded to Ledger · auto-categorize.' },
  { from: 'Anna Lin',         subj: 'Investor deck v3',           time: '13:42', cls: 'P1 · REPLY',     status: 'drafted',   preview: 'Drafted reply · awaiting your approval.' },
  { from: 'GitHub',           subj: '[forge/billing] PR #482',    time: '13:21', cls: 'P2 · FORGE',     status: 'routed',    preview: 'Routed to Forge · auto-review.' },
  { from: 'LinkedIn',         subj: '6 new connections',          time: '12:50', cls: 'P4 · ARCHIVE',   status: 'archived',  preview: 'Auto-archived.' },
  { from: 'Stripe',           subj: 'Receipt — $1,240',           time: '12:33', cls: 'P3 · LEDGER',    status: 'routed',    preview: 'Forwarded to Ledger.' },
  { from: 'M. Chen',          subj: 'Coffee Thursday?',           time: '11:58', cls: 'P2 · CHRONOS',   status: 'routed',    preview: 'Routed to Chronos.' },
];

function AideWorkspace() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 14, padding: 18, height: '100%', overflow: 'auto' }}>
      <div className="panel" style={{ minHeight: 0 }}>
        <div className="panel-header">
          <span className="dot ok pulse" />
          <span className="panel-title">INBOX · TRIAGE QUEUE</span>
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)', letterSpacing: '0.1em' }}>
            8 PROCESSED · LAST 30M
          </span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          {INBOX_EMAILS.map((e, i) => (
            <div key={i} style={{
              padding: '11px 14px',
              borderBottom: '1px solid var(--line)',
              display: 'grid',
              gridTemplateColumns: '160px 1fr 90px 50px',
              gap: 12,
              alignItems: 'center',
              fontSize: 11,
            }}>
              <span style={{ color: 'var(--fg)', fontWeight: 500, fontFamily: 'var(--sans)' }}>{e.from}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ color: 'var(--fg)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{e.subj}</div>
                <div style={{ color: 'var(--fg-dim)', fontSize: 10, marginTop: 2 }}>{e.preview}</div>
              </div>
              <Tag kind={e.cls.startsWith('P1') ? 'amber' : e.cls.startsWith('P3') || e.cls.startsWith('P4') ? '' : 'info'}>{e.cls}</Tag>
              <span style={{ color: 'var(--fg-faint)', textAlign: 'right', fontFamily: 'var(--mono)' }}>{e.time}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">DRAFT · IN PROGRESS</span>
            <Tag kind="amber" style={{ marginLeft: 'auto' }}>P1</Tag>
          </div>
          <div className="panel-body" style={{ fontSize: 12, lineHeight: 1.6 }}>
            <div style={{ color: 'var(--fg-dim)', fontSize: 10, marginBottom: 8 }}>
              TO: sasha@petrov.io &nbsp; · &nbsp; CC: legal@acme.co
            </div>
            <div style={{ color: 'var(--fg)', fontSize: 12, marginBottom: 8, fontFamily: 'var(--sans)' }}>
              Re: Q2 review schedule
            </div>
            <div style={{ color: 'var(--fg-mute)', fontFamily: 'var(--sans)', fontSize: 12 }}>
              Hi Sasha,<br/><br/>
              Thanks for the slot — Tuesday 14:00 works on my end. Two quick questions before then:
              <span style={{ background: 'rgba(242,160,61,0.15)', borderBottom: '1px dashed var(--amber)' }}>
                {' '}should we loop in legal for the contract section, and{' '}
              </span>
              do you want the deck circulated 24h ahead?<br/><br/>
              <span style={{ color: 'var(--fg-faint)' }}>▮</span>
            </div>
            <div style={{ marginTop: 14, display: 'flex', gap: 6 }}>
              <button className="btn primary">APPROVE & SEND</button>
              <button className="btn">REVISE</button>
              <button className="btn">DISCARD</button>
            </div>
          </div>
        </div>

        <div className="panel" style={{ flex: 1, minHeight: 140 }}>
          <div className="panel-header">
            <span className="panel-title">TRIAGE STATS · 24H</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <KV label="CLASSIFIED">87</KV>
            <KV label="AUTO-REPLIED">14</KV>
            <KV label="ROUTED TO PEER">22</KV>
            <KV label="ARCHIVED">38</KV>
            <KV label="ESCALATED TO YOU" accent="var(--amber)">9</KV>
          </div>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// CHRONOS — calendar grid
// ──────────────────────────────────────────────────────────────
const CAL_EVENTS = [
  { day: 1, start: 9,   dur: 1,   title: 'Standup',           agent: 'chronos', kind: 'self' },
  { day: 1, start: 11,  dur: 1.5, title: 'Q2 Review · Sasha',  agent: 'aide',    kind: 'auto' },
  { day: 1, start: 14,  dur: 0.5, title: 'CONFLICT',          agent: null,      kind: 'conflict' },
  { day: 1, start: 14.5, dur: 1,  title: 'Investor sync',     agent: 'aide',    kind: 'auto' },
  { day: 2, start: 10,  dur: 0.5, title: 'M. Voss · lunch?',  agent: 'chronos', kind: 'pending' },
  { day: 2, start: 13,  dur: 2,   title: 'Deep work',         agent: null,      kind: 'self' },
  { day: 3, start: 9,   dur: 1,   title: 'Standup',           agent: 'chronos', kind: 'self' },
  { day: 3, start: 15,  dur: 1.5, title: 'M. Chen · coffee',  agent: 'chronos', kind: 'auto' },
  { day: 4, start: 9,   dur: 1,   title: 'Standup',           agent: 'chronos', kind: 'self' },
  { day: 4, start: 11,  dur: 2,   title: 'Strategy review',   agent: null,      kind: 'self' },
  { day: 5, start: 12,  dur: 1.5, title: 'Anna · investor deck', agent: 'aide', kind: 'auto' },
];

function ChronosWorkspace() {
  const days = ['MON 27', 'TUE 28', 'WED 29', 'THU 30', 'FRI 01'];
  const hours = Array.from({ length: 10 }, (_, i) => i + 8); // 8..17
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, padding: 18, height: '100%', overflow: 'auto' }}>
      <div className="panel" style={{ minHeight: 0 }}>
        <div className="panel-header">
          <span className="panel-title">WEEK · 27 APR – 01 MAY</span>
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)', letterSpacing: '0.1em' }}>
            <Tag kind="info">3 AUTO-SCHEDULED</Tag> &nbsp;
            <Tag kind="crit">1 CONFLICT</Tag>
          </span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '50px repeat(5, 1fr)',
            borderBottom: '1px solid var(--line)',
          }}>
            <div />
            {days.map((d) => (
              <div key={d} style={{
                padding: '10px 8px',
                fontSize: 10,
                letterSpacing: '0.18em',
                color: 'var(--fg-dim)',
                borderLeft: '1px solid var(--line)',
              }}>{d}</div>
            ))}
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '50px repeat(5, 1fr)',
            position: 'relative',
          }}>
            {/* hour labels */}
            <div>
              {hours.map((h) => (
                <div key={h} style={{
                  height: 42,
                  fontSize: 9,
                  color: 'var(--fg-faint)',
                  padding: '4px 6px',
                  borderTop: '1px solid var(--line-faint)',
                  fontFamily: 'var(--mono)',
                }}>{String(h).padStart(2, '0')}:00</div>
              ))}
            </div>
            {/* day columns */}
            {days.map((_, dayIdx) => (
              <div key={dayIdx} style={{
                position: 'relative',
                borderLeft: '1px solid var(--line)',
              }}>
                {hours.map((h) => (
                  <div key={h} style={{
                    height: 42,
                    borderTop: '1px solid var(--line-faint)',
                  }} />
                ))}
                {/* events for this day */}
                {CAL_EVENTS.filter((e) => e.day === dayIdx + 1).map((e, i) => {
                  const top = (e.start - 8) * 42;
                  const h = e.dur * 42;
                  const ag = e.agent ? AGENTS.find((a) => a.id === e.agent) : null;
                  const bg = e.kind === 'conflict' ? 'rgba(229,72,77,0.15)'
                    : e.kind === 'pending' ? 'rgba(242,160,61,0.10)'
                    : ag ? `${ag.colorHex}1f` : 'rgba(255,255,255,0.04)';
                  const border = e.kind === 'conflict' ? 'var(--crit)'
                    : e.kind === 'pending' ? 'var(--amber)'
                    : ag ? ag.colorHex : 'var(--line-bright)';
                  return (
                    <div key={i} style={{
                      position: 'absolute',
                      left: 4, right: 4,
                      top: top + 1,
                      height: h - 2,
                      background: bg,
                      borderLeft: `2px solid ${border}`,
                      padding: '4px 6px',
                      fontSize: 10,
                      fontFamily: 'var(--mono)',
                      color: 'var(--fg)',
                      overflow: 'hidden',
                      borderRadius: 1,
                    }}>
                      {ag && <AgentGlyph agent={ag} size={11} />}
                      {' '}{e.title}
                      {e.kind === 'conflict' && (
                        <div style={{ fontSize: 9, color: 'var(--crit)', marginTop: 2 }}>↯ overlap</div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">PENDING DECISIONS</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <DecisionRow title="Lunch w/ M. Voss · 3 slots proposed" sub="Tue 12:00 · Wed 12:30 · Thu 13:00" />
            <DecisionRow title="Resolve 14:30 conflict" sub="Reschedule investor sync → Wed 14:30?" warn />
            <DecisionRow title="Flight SFO → JFK" sub="Awaiting card auth · 2 options held" />
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">TODAY · TODOS</span></div>
          <div className="panel-body" style={{ fontSize: 11, fontFamily: 'var(--mono)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Todo done>Review Q2 budget</Todo>
            <Todo done>Sign offer letter · K. Park</Todo>
            <Todo>Call accountant re: filing</Todo>
            <Todo>Approve investor deck v3</Todo>
            <Todo agent="forge">Review PR #482 (auto-summary ready)</Todo>
          </div>
        </div>
      </div>
    </div>
  );
}
function DecisionRow({ title, sub, warn }) {
  return (
    <div style={{
      padding: '8px 10px',
      border: `1px solid ${warn ? 'var(--crit)' : 'var(--line)'}`,
      borderLeft: `2px solid ${warn ? 'var(--crit)' : 'var(--amber)'}`,
      background: 'var(--bg-elevated)',
    }}>
      <div style={{ fontSize: 11, color: 'var(--fg)', marginBottom: 2 }}>{title}</div>
      <div style={{ fontSize: 10, color: 'var(--fg-dim)' }}>{sub}</div>
    </div>
  );
}
function Todo({ done, agent, children }) {
  const ag = agent ? AGENTS.find((a) => a.id === agent) : null;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      color: done ? 'var(--fg-faint)' : 'var(--fg)',
      textDecoration: done ? 'line-through' : 'none',
    }}>
      <span style={{
        width: 10, height: 10,
        border: `1px solid ${done ? 'var(--ok)' : 'var(--line-bright)'}`,
        background: done ? 'var(--ok)' : 'transparent',
        flexShrink: 0,
      }} />
      <span style={{ flex: 1 }}>{children}</span>
      {ag && <AgentGlyph agent={ag} size={12} />}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// SHERLOCK — research surface
// ──────────────────────────────────────────────────────────────
function SherlockWorkspace() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 14, padding: 18, height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}>
        <div className="panel">
          <div className="panel-header">
            <span className="dot warn pulse" />
            <span className="panel-title">CURRENT INVESTIGATION</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)' }}>STARTED 14:08 · ELAPSED 24:11</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 16, color: 'var(--fg)' }}>
              "AGI safety research priorities · Q1 2026 landscape"
            </div>
            <div style={{ fontSize: 11, color: 'var(--fg-dim)' }}>
              SCOPE · arxiv, alignment forum, lab blogs &nbsp;·&nbsp; DEPTH · 3 hops &nbsp;·&nbsp; BUDGET · $5.00 / used $4.18
            </div>
            <Progress value={0.67} color="var(--sherlock)" height={4} />
            <div style={{ fontSize: 11, color: 'var(--fg-mute)' }}>STEP 4 / 6 · synthesizing 14 sources → outlining digest</div>
          </div>
        </div>

        <div className="panel" style={{ flex: 1, minHeight: 200 }}>
          <div className="panel-header">
            <span className="panel-title">SOURCES · COLLECTED 14</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)' }}>TOOL · web.fetch + arxiv.api</span>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            {[
              { url: 'arxiv.org/abs/2603.18421', title: 'Scalable Oversight via Debate · v3', cite: 18, status: 'parsed' },
              { url: 'alignmentforum.org/posts/x9q4', title: 'Mechanistic interp · Q1 review', cite: 14, status: 'parsed' },
              { url: 'anthropic.com/research/constitutional-ai-2', title: 'Constitutional AI 2 · paper', cite: 22, status: 'parsing' },
              { url: 'arxiv.org/abs/2604.01129', title: 'Sleeper agents revisited', cite: 8, status: 'parsed' },
              { url: 'deepmind.com/blog/safety-2026', title: 'DeepMind safety review · Q1', cite: 11, status: 'parsed' },
              { url: 'openai.com/research/superalignment-update', title: 'Superalignment Q1 update', cite: 6, status: 'queued' },
              { url: 'arxiv.org/abs/2604.07712', title: 'RLHF failure modes (survey)', cite: 9, status: 'parsed' },
            ].map((s, i) => (
              <div key={i} style={{
                padding: '8px 14px',
                borderBottom: '1px solid var(--line)',
                display: 'grid',
                gridTemplateColumns: '20px 1fr auto',
                gap: 10,
                fontSize: 11,
                alignItems: 'center',
              }}>
                <span style={{ fontFamily: 'var(--mono)', color: 'var(--fg-faint)', fontSize: 10 }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ color: 'var(--fg)' }}>{s.title}</div>
                  <div style={{ fontSize: 10, color: 'var(--sherlock)', fontFamily: 'var(--mono)' }}>↳ {s.url}</div>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ fontSize: 10, color: 'var(--fg-dim)' }}>{s.cite} cites</span>
                  <Tag kind={s.status === 'parsed' ? 'ok' : s.status === 'parsing' ? 'amber' : ''}>{s.status}</Tag>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">REASONING TRACE</span></div>
          <div className="panel-body" style={{ fontSize: 10, fontFamily: 'var(--mono)', lineHeight: 1.6, color: 'var(--fg-mute)' }}>
            <div style={{ color: 'var(--sherlock)' }}>▸ thinking…</div>
            <div>1. Decompose query → 3 sub-questions</div>
            <div>2. Search arxiv · k=20 · cs.AI</div>
            <div>3. Filter by relevance &gt;0.72</div>
            <div>4. Fetch + parse 14 sources</div>
            <div style={{ color: 'var(--amber)' }}>5. Synthesize ◀ HERE</div>
            <div style={{ color: 'var(--fg-faint)' }}>6. Format digest</div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">EMERGING THEMES</span></div>
          <div className="panel-body" style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {['mech interp', 'sleeper agents', 'scalable oversight', 'RLHF failures', 'debate methods', 'constitutional', 'red-teaming', 'eval harnesses'].map((t) => (
              <Tag key={t} solid>{t}</Tag>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><span className="panel-title">COST · TOKENS</span></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <KV label="INPUT TOKENS">412.0K</KV>
            <KV label="OUTPUT TOKENS">89.2K</KV>
            <KV label="COST" accent="var(--amber)">$4.18 / $5.00</KV>
            <KV label="WALL TIME">24:11</KV>
          </div>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// FORGE — projects gallery + drill-in detail
// ──────────────────────────────────────────────────────────────
const FORGE_PROJECTS = [
  {
    id: 'billing-ts',
    name: 'billing → typescript',
    repo: 'acme/core',
    branch: 'feature/billing-ts',
    desc: 'Refactor billing module to TS + zod validation',
    status: 'active',
    progress: 0.85,
    files: 8,
    add: 312, del: 87,
    tests: { pass: 23, fail: 1, run: 3, total: 27 },
    lang: 'TypeScript',
    started: '2d ago',
    ai: '14:32 · running test_receipt_currency',
    tree: [
      { kind: 'dir', name: 'billing/', children: [
        { kind: 'file', name: 'invoice.ts', change: 'M' },
        { kind: 'file', name: 'ledger.ts', change: 'M' },
        { kind: 'file', name: 'receipt.ts', change: 'A', active: true },
        { kind: 'file', name: 'types.ts', change: 'M' },
        { kind: 'file', name: 'index.ts' },
      ]},
      { kind: 'dir', name: 'tests/', children: [
        { kind: 'file', name: 'test_invoice.py', change: 'M' },
        { kind: 'file', name: 'test_ledger.py', change: 'A' },
      ]},
      { kind: 'file', name: 'package.json', change: 'M' },
    ],
    diff: [
      { n: 1,  type: 'add', s: "+ import { z } from 'zod';" },
      { n: 2,  type: 'add', s: "+ import { Money } from './types';" },
      { n: 3,  type: 'ctx', s: '' },
      { n: 4,  type: 'add', s: '+ export const ReceiptSchema = z.object({' },
      { n: 5,  type: 'add', s: '+   id: z.string(),' },
      { n: 6,  type: 'add', s: '+   vendor: z.string(),' },
      { n: 7,  type: 'add', s: '+   amount: z.number().positive(),' },
      { n: 8,  type: 'add', s: "+   currency: z.enum(['USD', 'EUR', 'GBP'])," },
      { n: 9,  type: 'add', s: '+   date: z.string().datetime(),' },
      { n: 10, type: 'add', s: '+ });' },
      { n: 11, type: 'ctx', s: '' },
      { n: 12, type: 'add', s: '+ export type Receipt = z.infer<typeof ReceiptSchema>;' },
      { n: 13, type: 'ctx', s: '' },
      { n: 14, type: 'add', s: '+ export function toMoney(r: Receipt): Money {' },
      { n: 15, type: 'add', s: '+   return { amount: r.amount, currency: r.currency };' },
      { n: 16, type: 'add', s: '+ }' },
    ],
    commits: [
      { sha: 'a3f29c1', msg: 'wip: receipt schema', age: '14m' },
      { sha: '1e8b4d0', msg: 'refactor: invoice → ts', age: '2h' },
      { sha: '9c2f718', msg: 'add: zod dep', age: '5h' },
      { sha: '4d1e0a2', msg: 'init: billing-ts branch', age: '2d' },
    ],
    testRunner: [
      { sym: '✓', name: 'test_invoice_create', kind: 'ok' },
      { sym: '✓', name: 'test_invoice_total', kind: 'ok' },
      { sym: '✓', name: 'test_invoice_void', kind: 'ok' },
      { sym: '✓', name: 'test_ledger_balance', kind: 'ok' },
      { sym: '✗', name: 'test_receipt_currency', kind: 'crit' },
      { sym: '  ', name: "AssertionError: expected 'USD'", kind: 'faint' },
      { sym: '…', name: 'running test_5/27', kind: 'amber' },
    ],
  },
  {
    id: 'pr-482',
    name: 'review · PR #482',
    repo: 'acme/core',
    branch: 'pr/482',
    desc: 'Auto-review of incoming PR · webhook → forge',
    status: 'active',
    progress: 0.45,
    files: 12,
    add: 184, del: 42,
    tests: { pass: 0, fail: 0, run: 0, total: 0 },
    lang: 'Python',
    started: '11m ago',
    ai: 'reading diff · summarizing changes',
    tree: [
      { kind: 'dir', name: 'api/', children: [
        { kind: 'file', name: 'auth.py', change: 'M', active: true },
        { kind: 'file', name: 'middleware.py', change: 'M' },
        { kind: 'file', name: 'session.py', change: 'A' },
      ]},
      { kind: 'dir', name: 'tests/', children: [
        { kind: 'file', name: 'test_auth.py', change: 'M' },
      ]},
    ],
    diff: [
      { n: 18, type: 'ctx', s: ' def authenticate(token: str):' },
      { n: 19, type: 'rem', s: '-     return jwt.decode(token, SECRET)' },
      { n: 20, type: 'add', s: '+     try:' },
      { n: 21, type: 'add', s: '+         payload = jwt.decode(token, SECRET, algorithms=["HS256"])' },
      { n: 22, type: 'add', s: '+     except jwt.ExpiredSignatureError:' },
      { n: 23, type: 'add', s: '+         raise AuthError("token expired")' },
      { n: 24, type: 'add', s: '+     return payload' },
    ],
    commits: [
      { sha: '8b2e9a4', msg: 'fix: handle expired tokens', age: '11m' },
      { sha: 'c1f7d22', msg: 'add: session refresh', age: '1h' },
    ],
    testRunner: [
      { sym: '…', name: 'queued · waiting on CI', kind: 'amber' },
    ],
  },
  {
    id: 'rag-pipeline',
    name: 'rag pipeline · v2',
    repo: 'acme/sherlock-rag',
    branch: 'main',
    desc: 'Vector store rewrite · pgvector → lancedb',
    status: 'paused',
    progress: 0.30,
    files: 22,
    add: 642, del: 318,
    tests: { pass: 14, fail: 0, run: 0, total: 32 },
    lang: 'Python',
    started: '4d ago',
    ai: 'paused · awaiting design decision on chunk size',
    tree: [
      { kind: 'dir', name: 'rag/', children: [
        { kind: 'file', name: 'embed.py', change: 'M' },
        { kind: 'file', name: 'store.py', change: 'M', active: true },
        { kind: 'file', name: 'retrieve.py', change: 'M' },
      ]},
    ],
    diff: [
      { n: 1, type: 'rem', s: '- from pgvector.psycopg2 import register_vector' },
      { n: 2, type: 'add', s: '+ import lancedb' },
      { n: 3, type: 'ctx', s: '' },
      { n: 4, type: 'add', s: '+ db = lancedb.connect("./data/lance")' },
      { n: 5, type: 'add', s: '+ table = db.create_table("docs", schema=DocSchema)' },
    ],
    commits: [
      { sha: '5a8c1e0', msg: 'wip: lancedb migration', age: '4d' },
      { sha: 'f0921bb', msg: 'remove: pgvector', age: '4d' },
    ],
    testRunner: [
      { sym: '⏸', name: 'paused', kind: 'faint' },
    ],
  },
  {
    id: 'home-bridge',
    name: 'hearth bridge daemon',
    repo: 'acme/hearth',
    branch: 'feature/matter',
    desc: 'Add Matter protocol support to HomeKit bridge',
    status: 'review',
    progress: 1.0,
    files: 6,
    add: 218, del: 14,
    tests: { pass: 18, fail: 0, run: 0, total: 18 },
    lang: 'Swift',
    started: '6d ago',
    ai: 'completed · awaiting your review',
    tree: [
      { kind: 'dir', name: 'Sources/', children: [
        { kind: 'file', name: 'Matter.swift', change: 'A', active: true },
        { kind: 'file', name: 'Bridge.swift', change: 'M' },
      ]},
    ],
    diff: [
      { n: 1, type: 'add', s: '+ import Matter' },
      { n: 2, type: 'add', s: '+ import HomeKit' },
      { n: 3, type: 'ctx', s: '' },
      { n: 4, type: 'add', s: '+ class MatterBridge: HMAccessoryBrowser {' },
      { n: 5, type: 'add', s: '+     func discover() async throws -> [Accessory] { ... }' },
      { n: 6, type: 'add', s: '+ }' },
    ],
    commits: [
      { sha: 'e2c9a18', msg: 'feat: matter discovery', age: '6h' },
      { sha: 'b71d4f0', msg: 'add: matter sdk', age: '1d' },
    ],
    testRunner: [
      { sym: '✓', name: 'all 18 passing', kind: 'ok' },
    ],
  },
  {
    id: 'sentinel-rules',
    name: 'sentinel rules engine',
    repo: 'acme/sentinel',
    branch: 'feature/rules-dsl',
    desc: 'DSL for declarative scheduler rules',
    status: 'active',
    progress: 0.62,
    files: 14,
    add: 482, del: 92,
    tests: { pass: 31, fail: 2, run: 0, total: 41 },
    lang: 'Python',
    started: '1d ago',
    ai: 'writing parser tests · 2 failing',
    tree: [
      { kind: 'dir', name: 'sentinel/', children: [
        { kind: 'file', name: 'rules.py', change: 'A', active: true },
        { kind: 'file', name: 'parser.py', change: 'A' },
        { kind: 'file', name: 'engine.py', change: 'M' },
      ]},
    ],
    diff: [
      { n: 1, type: 'add', s: '+ class Rule:' },
      { n: 2, type: 'add', s: '+     def __init__(self, when: str, then: str):' },
      { n: 3, type: 'add', s: '+         self.when = parse_expr(when)' },
      { n: 4, type: 'add', s: '+         self.then = parse_action(then)' },
    ],
    commits: [
      { sha: '7e5b210', msg: 'wip: parser ambiguity', age: '34m' },
      { sha: '4a90c33', msg: 'add: rule grammar', age: '5h' },
    ],
    testRunner: [
      { sym: '✗', name: 'test_parse_nested_when', kind: 'crit' },
      { sym: '✗', name: 'test_parse_or_chain', kind: 'crit' },
      { sym: '✓', name: '31 passing', kind: 'ok' },
    ],
  },
  {
    id: 'echo-summarizer',
    name: 'echo · thread summarizer',
    repo: 'acme/echo',
    branch: 'main',
    desc: 'Long-thread digest model · iMessage groups',
    status: 'shipped',
    progress: 1.0,
    files: 4,
    add: 92, del: 12,
    tests: { pass: 22, fail: 0, run: 0, total: 22 },
    lang: 'TypeScript',
    started: '8d ago',
    ai: 'shipped · merged to main',
    tree: [
      { kind: 'dir', name: 'echo/', children: [
        { kind: 'file', name: 'summarize.ts', change: 'M', active: true },
      ]},
    ],
    diff: [
      { n: 1, type: 'add', s: '+ // shipped a8f2e1c · 3d ago' },
    ],
    commits: [
      { sha: 'a8f2e1c', msg: 'merge: thread summarizer', age: '3d' },
    ],
    testRunner: [
      { sym: '✓', name: 'all 22 passing · merged', kind: 'ok' },
    ],
  },
];

function ForgeWorkspace() {
  const [openId, setOpen] = useS1(null);
  const project = openId ? FORGE_PROJECTS.find((p) => p.id === openId) : null;
  if (project) return <ForgeProjectDetail project={project} onBack={() => setOpen(null)} />;
  return <ForgeProjectGallery onOpen={setOpen} />;
}

function ForgeProjectGallery({ onOpen }) {
  const counts = {
    active: FORGE_PROJECTS.filter((p) => p.status === 'active').length,
    review: FORGE_PROJECTS.filter((p) => p.status === 'review').length,
    paused: FORGE_PROJECTS.filter((p) => p.status === 'paused').length,
    shipped: FORGE_PROJECTS.filter((p) => p.status === 'shipped').length,
  };
  return (
    <div style={{ padding: 18, height: '100%', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">FORGE · PROJECT REGISTRY</span>
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-dim)' }}>
            {FORGE_PROJECTS.length} TOTAL · {counts.active} ACTIVE · {counts.review} REVIEW · {counts.paused} PAUSED
          </span>
        </div>
        <div className="panel-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
          <BigNum label="ACTIVE"   value={counts.active}  accent="var(--forge)" />
          <BigNum label="REVIEW"   value={counts.review}  accent="var(--amber)" />
          <BigNum label="PAUSED"   value={counts.paused}  accent="var(--fg-dim)" />
          <BigNum label="SHIPPED"  value={counts.shipped} accent="var(--ok)" />
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
        gap: 12,
      }}>
        {FORGE_PROJECTS.map((p) => <ForgeProjectCard key={p.id} project={p} onOpen={onOpen} />)}
      </div>
    </div>
  );
}

function ForgeProjectCard({ project, onOpen }) {
  const statusColor = project.status === 'active' ? 'var(--forge)'
    : project.status === 'review' ? 'var(--amber)'
    : project.status === 'shipped' ? 'var(--ok)'
    : 'var(--fg-dim)';
  return (
    <div
      onClick={() => onOpen(project.id)}
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--line)',
        padding: 14,
        cursor: 'pointer',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        transition: 'border-color 120ms',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = statusColor; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--line)'; }}
    >
      <span style={{
        position: 'absolute', top: 0, left: 0, height: '100%', width: 2,
        background: statusColor,
      }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{
            fontFamily: 'var(--sans)', fontSize: 14, color: 'var(--fg)', marginBottom: 2,
          }}>{project.name}</div>
          <div style={{ fontSize: 10, color: 'var(--fg-dim)', fontFamily: 'var(--mono)' }}>
            {project.repo} · {project.branch}
          </div>
        </div>
        <Tag kind={project.status === 'active' ? '' : project.status === 'review' ? 'amber' : project.status === 'shipped' ? 'ok' : ''}>
          {project.status}
        </Tag>
      </div>

      <div style={{ fontSize: 11, color: 'var(--fg-mute)', minHeight: 32, lineHeight: 1.45 }}>
        {project.desc}
      </div>

      <Progress value={project.progress} color={statusColor} height={3} />

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 4,
        paddingTop: 8,
        borderTop: '1px solid var(--line)',
      }}>
        <ProjMetric label="FILES" value={project.files} />
        <ProjMetric label="+ / −" value={`${project.add}/${project.del}`} />
        <ProjMetric label="TESTS"
          value={project.tests.total ? `${project.tests.pass}/${project.tests.total}` : '—'}
          accent={project.tests.fail ? 'var(--crit)' : undefined}
        />
        <ProjMetric label="LANG" value={project.lang} />
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 10, color: 'var(--fg-dim)',
      }}>
        {project.status === 'active' && <span className="dot ok pulse" />}
        <span style={{ fontStyle: 'italic', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          ▸ {project.ai}
        </span>
        <span style={{ color: 'var(--fg-faint)' }}>{project.started}</span>
      </div>
    </div>
  );
}

function ProjMetric({ label, value, accent }) {
  return (
    <div>
      <div style={{ fontSize: 9, letterSpacing: '0.14em', color: 'var(--fg-faint)' }}>{label}</div>
      <div style={{
        fontSize: 12, fontFamily: 'var(--mono)', color: accent || 'var(--fg)',
        fontVariantNumeric: 'tabular-nums',
      }}>{value}</div>
    </div>
  );
}
function BigNum({ label, value, accent }) {
  return (
    <div>
      <div style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--fg-dim)' }}>{label}</div>
      <div style={{
        fontFamily: 'var(--mono)', fontSize: 22,
        color: accent || 'var(--fg)', marginTop: 2,
        fontVariantNumeric: 'tabular-nums',
      }}>{value}</div>
    </div>
  );
}

function ForgeProjectDetail({ project, onBack }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Project sub-header */}
      <div style={{
        padding: '12px 18px',
        borderBottom: '1px solid var(--line)',
        background: 'var(--bg-deep)',
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <button className="btn" onClick={onBack}>← PROJECTS</button>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--sans)', fontSize: 14, color: 'var(--fg)' }}>
            {project.name}
          </div>
          <div style={{ fontSize: 10, color: 'var(--fg-dim)', fontFamily: 'var(--mono)' }}>
            {project.repo} · {project.branch} · {project.lang}
          </div>
        </div>
        <Tag kind={project.status === 'active' ? '' : project.status === 'review' ? 'amber' : project.status === 'shipped' ? 'ok' : ''}>
          {project.status}
        </Tag>
        <span style={{ fontSize: 10, color: 'var(--fg-dim)' }}>+{project.add} / −{project.del}</span>
        <button className="btn">⎘ OPEN IN EDITOR</button>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 280px', gap: 14, height: '100%' }}>
          {/* tree */}
          <div className="panel">
            <div className="panel-header"><span className="panel-title">WORKING TREE</span></div>
            <div className="panel-body" style={{ padding: 8, fontSize: 11, fontFamily: 'var(--mono)' }}>
              {project.tree.map((node, i) => <RenderNode key={i} node={node} />)}
            </div>
          </div>

          {/* diff */}
          <div className="panel" style={{ minHeight: 0 }}>
            <div className="panel-header">
              <span className="panel-title">{
                (project.tree.find((n) => n.kind === 'dir')?.children?.find((c) => c.active)?.name) ||
                project.tree.find((n) => n.active)?.name ||
                'DIFF'
              } · DIFF</span>
            </div>
            <div className="panel-body" style={{ padding: 0, fontFamily: 'var(--mono)', fontSize: 11, lineHeight: 1.65 }}>
              {project.diff.map((d) => <DiffLine key={d.n} n={d.n} type={d.type}>{d.s}</DiffLine>)}
            </div>
          </div>

          {/* sidebar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">TASK</span></div>
              <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--fg)', fontFamily: 'var(--sans)' }}>
                  {project.desc}
                </div>
                <div style={{ fontSize: 11, color: 'var(--fg-dim)' }}>
                  {project.files} files · started {project.started}
                </div>
                <Progress value={project.progress} color="var(--forge)" />
                <div style={{ fontSize: 10, color: 'var(--fg-mute)', fontStyle: 'italic' }}>
                  ▸ {project.ai}
                </div>
              </div>
            </div>
            <div className="panel">
              <div className="panel-header">
                {project.status === 'active' && <span className="dot ok pulse" />}
                <span className="panel-title">TEST RUNNER</span>
              </div>
              <div className="panel-body" style={{ fontFamily: 'var(--mono)', fontSize: 10, lineHeight: 1.65, color: 'var(--fg-mute)' }}>
                {project.testRunner.map((t, i) => (
                  <div key={i} style={{
                    color: t.kind === 'ok' ? 'var(--ok)'
                      : t.kind === 'crit' ? 'var(--crit)'
                      : t.kind === 'amber' ? 'var(--amber)'
                      : t.kind === 'faint' ? 'var(--fg-faint)'
                      : 'var(--fg-mute)',
                    paddingLeft: t.kind === 'faint' ? 14 : 0,
                  }}>{t.sym} {t.name}</div>
                ))}
                {project.tests.total > 0 && (
                  <div style={{ color: 'var(--fg-faint)', marginTop: 6 }}>
                    {project.tests.pass} / {project.tests.total} ✓
                    {project.tests.fail > 0 && <> · {project.tests.fail} ✗</>}
                    {project.tests.run > 0 && <> · {project.tests.run} …</>}
                  </div>
                )}
              </div>
            </div>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">COMMITS · LOCAL</span></div>
              <div className="panel-body" style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--fg-mute)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                {project.commits.map((c) => (
                  <div key={c.sha} style={{ display: 'flex', gap: 8 }}>
                    <span style={{ color: 'var(--forge)' }}>{c.sha}</span>
                    <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.msg}</span>
                    <span style={{ color: 'var(--fg-faint)' }}>{c.age}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function RenderNode({ node }) {
  if (node.kind === 'dir') {
    return (
      <FileNode name={node.name} open>
        {node.children.map((c, i) => <RenderNode key={i} node={c} />)}
      </FileNode>
    );
  }
  return <FileNode name={node.name} change={node.change} active={node.active} />;
}
function FileNode({ name, change, open, active, children }) {
  const isDir = !!children;
  const color = change === 'A' ? 'var(--ok)' : change === 'M' ? 'var(--amber)' : 'var(--fg-mute)';
  return (
    <div style={{ paddingLeft: isDir ? 0 : 14 }}>
      <div style={{
        padding: '3px 6px',
        background: active ? 'var(--bg-hover)' : 'transparent',
        borderLeft: active ? '2px solid var(--forge)' : '2px solid transparent',
        color,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}>
        {isDir && <span style={{ color: 'var(--fg-faint)' }}>{open ? '▾' : '▸'}</span>}
        {!isDir && change && <span style={{ width: 12, color, fontSize: 9 }}>{change}</span>}
        <span style={{ color: isDir ? 'var(--fg)' : color }}>{name}</span>
      </div>
      {open && children && <div style={{ paddingLeft: 8 }}>{children}</div>}
    </div>
  );
}
function DiffLine({ n, type, children }) {
  const bg = type === 'add' ? 'rgba(111,207,127,0.06)' : type === 'rem' ? 'rgba(229,72,77,0.06)' : 'transparent';
  const color = type === 'add' ? '#a8e8b3' : type === 'rem' ? '#f0a3a5' : 'var(--fg-mute)';
  return (
    <div style={{ display: 'flex', background: bg }}>
      <span style={{ width: 36, padding: '0 8px', color: 'var(--fg-faint)', textAlign: 'right', borderRight: '1px solid var(--line)', fontSize: 10 }}>{n}</span>
      <span style={{ paddingLeft: 10, color, whiteSpace: 'pre' }}>{children || ' '}</span>
    </div>
  );
}

Object.assign(window, { AideWorkspace, ChronosWorkspace, SherlockWorkspace, ForgeWorkspace });

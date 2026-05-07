/* global window */
// ═══════════════════════════════════════════════════════════════
// JARVIS // SEED DATA
// Agents, tasks, telemetry — all mocked but coherent
// ═══════════════════════════════════════════════════════════════

const AGENTS = [
  {
    id: 'aide',
    name: 'AIDE',
    glyph: 'AI',
    role: 'EMAIL OPS',
    tagline: 'Inbox triage · drafts · follow-ups',
    color: 'var(--aide)',
    colorHex: '#7CB6E8',
    status: 'active',
    model: 'claude-sonnet-4.5',
    schedule: 'every 2m',
    queueDepth: 4,
    completed24h: 87,
    avgLatency: '1.4s',
    tokensIn: 124_300,
    tokensOut: 18_902,
    cost24h: 0.92,
  },
  {
    id: 'chronos',
    name: 'CHRONOS',
    glyph: 'CH',
    role: 'TIME OPS',
    tagline: 'Calendar · todos · scheduling',
    color: 'var(--chronos)',
    colorHex: '#B98CE0',
    status: 'active',
    model: 'claude-haiku-4.5',
    schedule: 'every 5m',
    queueDepth: 2,
    completed24h: 41,
    avgLatency: '0.8s',
    tokensIn: 38_910,
    tokensOut: 6_104,
    cost24h: 0.21,
  },
  {
    id: 'sherlock',
    name: 'SHERLOCK',
    glyph: 'SH',
    role: 'RESEARCH',
    tagline: 'Deep research · web · sources',
    color: 'var(--sherlock)',
    colorHex: '#E0859E',
    status: 'busy',
    model: 'claude-opus-4.7',
    schedule: 'on-demand',
    queueDepth: 1,
    completed24h: 6,
    avgLatency: '47s',
    tokensIn: 412_088,
    tokensOut: 89_220,
    cost24h: 4.18,
  },
  {
    id: 'forge',
    name: 'FORGE',
    glyph: 'FG',
    role: 'CODE OPS',
    tagline: 'Code gen · refactor · review',
    color: 'var(--forge)',
    colorHex: '#6FCF7F',
    status: 'busy',
    model: 'claude-sonnet-4.5',
    schedule: 'on-demand',
    queueDepth: 3,
    completed24h: 12,
    avgLatency: '23s',
    tokensIn: 198_220,
    tokensOut: 44_150,
    cost24h: 2.04,
  },
  {
    id: 'ledger',
    name: 'LEDGER',
    glyph: 'LD',
    role: 'ATLAS',
    tagline: 'Finance · receipts · ledgers',
    color: 'var(--ledger)',
    colorHex: '#E0B85C',
    status: 'idle',
    model: 'claude-haiku-4.5',
    schedule: 'daily 06:00',
    queueDepth: 0,
    completed24h: 8,
    avgLatency: '2.1s',
    tokensIn: 22_408,
    tokensOut: 3_812,
    cost24h: 0.11,
  },
  {
    id: 'echo',
    name: 'ECHO',
    glyph: 'EC',
    role: 'MESSAGES',
    tagline: 'iMessage · Slack · WhatsApp',
    color: 'var(--echo)',
    colorHex: '#5FD3D3',
    status: 'active',
    model: 'claude-haiku-4.5',
    schedule: 'every 30s',
    queueDepth: 7,
    completed24h: 156,
    avgLatency: '0.6s',
    tokensIn: 89_120,
    tokensOut: 12_408,
    cost24h: 0.34,
  },
  {
    id: 'hearth',
    name: 'HEARTH',
    glyph: 'HE',
    role: 'HOME OPS',
    tagline: 'HomeKit · sensors · routines',
    color: 'var(--hearth)',
    colorHex: '#E08C5F',
    status: 'idle',
    model: 'claude-haiku-4.5',
    schedule: 'event-driven',
    queueDepth: 0,
    completed24h: 24,
    avgLatency: '0.4s',
    tokensIn: 12_088,
    tokensOut: 2_104,
    cost24h: 0.06,
  },
];

// ─── Kanban tasks ───
const TASKS = [
  // INBOX
  { id: 'T-2841', title: 'Email from Sasha re: Q2 review',     agent: null, column: 'inbox', priority: 'p2', source: 'gmail', age: '12s', preview: 'Triage incoming · classify intent' },
  { id: 'T-2842', title: 'Calendar conflict 14:30 ↔ 15:00',     agent: null, column: 'inbox', priority: 'p1', source: 'sentinel', age: '38s', preview: 'Detected by Sentinel · needs resolution' },

  // CLASSIFIED
  { id: 'T-2839', title: 'Draft reply to investor email',       agent: 'aide',     column: 'classified', priority: 'p1', source: 'inbox', age: '2m', preview: 'Routed to Aide · awaiting context fetch' },
  { id: 'T-2840', title: 'Schedule lunch with M. Voss',         agent: 'chronos',  column: 'classified', priority: 'p2', source: 'echo',  age: '3m', preview: 'Find slot · propose 3 options' },

  // DISPATCHED
  { id: 'T-2836', title: 'Research: AGI safety papers Q1 2026', agent: 'sherlock', column: 'dispatched', priority: 'p2', source: 'manual', age: '4m', preview: 'Multi-step · web + arxiv · 12 sources' },
  { id: 'T-2837', title: 'Refactor billing module → TS',        agent: 'forge',    column: 'dispatched', priority: 'p2', source: 'manual', age: '5m', preview: 'Branch: feature/billing-ts · 8 files' },

  // ACTIVE
  { id: 'T-2833', title: 'Compile weekly research digest',      agent: 'sherlock', column: 'active', priority: 'p2', source: 'sentinel', age: '12m', progress: 0.67, preview: 'Synthesizing 14 sources · step 4/6' },
  { id: 'T-2834', title: 'Reply: contract negotiation thread',  agent: 'aide',     column: 'active', priority: 'p1', source: 'inbox',  age: '8m',  progress: 0.40, preview: 'Drafting · awaiting your review' },
  { id: 'T-2835', title: 'Tests for billing-ts refactor',       agent: 'forge',    column: 'active', priority: 'p2', source: 'forge',  age: '6m',  progress: 0.85, preview: 'Running pytest · 23/27 passing' },
  { id: 'T-2832', title: 'iMessage thread w/ family digest',    agent: 'echo',     column: 'active', priority: 'p3', source: 'sentinel', age: '14m', progress: 0.20, preview: 'Summarizing 47 messages' },

  // BLOCKED
  { id: 'T-2830', title: 'Book flight SFO → JFK',               agent: 'chronos',  column: 'blocked', priority: 'p1', source: 'manual', age: '22m', preview: 'BLOCKED · awaiting your card auth' },

  // DONE
  { id: 'T-2828', title: 'Triage 23 morning emails',            agent: 'aide',     column: 'done', priority: 'p2', source: 'sentinel', age: '34m', preview: '23 classified · 4 archived · 2 escalated' },
  { id: 'T-2827', title: 'Reschedule standup → 11:00',          agent: 'chronos',  column: 'done', priority: 'p2', source: 'manual',  age: '41m', preview: '6 attendees notified' },
  { id: 'T-2826', title: 'Receipts → Ramp categorization',      agent: 'ledger',   column: 'done', priority: 'p3', source: 'sentinel', age: '1h',  preview: '12 receipts · $2,840 categorized' },
  { id: 'T-2825', title: 'Living room lights @ sunset',         agent: 'hearth',   column: 'done', priority: 'p3', source: 'sentinel', age: '2h',  preview: 'Routine: warm-evening' },
];

const COLUMNS = [
  { id: 'inbox',      label: 'INBOX',      sub: 'unclassified',  count: 2 },
  { id: 'classified', label: 'CLASSIFIED', sub: 'routed',        count: 2 },
  { id: 'dispatched', label: 'DISPATCHED', sub: 'agent picked up', count: 2 },
  { id: 'active',     label: 'ACTIVE',     sub: 'in progress',   count: 4 },
  { id: 'blocked',    label: 'BLOCKED',    sub: 'needs input',   count: 1 },
  { id: 'done',       label: 'DONE',       sub: 'last 24h',      count: 4 },
];

// ─── Activity feed ───
const ACTIVITY = [
  { t: '14:32:11', agent: 'aide',     msg: 'classified: investor email → P1 reply',         level: 'info' },
  { t: '14:32:08', agent: 'sherlock', msg: 'fetched arxiv.org/2603.18421 (1.4MB)',          level: 'info' },
  { t: '14:31:54', agent: 'forge',    msg: 'pytest billing/test_invoice.py · 23/27 ✓',      level: 'ok' },
  { t: '14:31:42', agent: 'chronos',  msg: 'WARN · calendar conflict 14:30 ↔ 15:00',        level: 'warn' },
  { t: '14:31:30', agent: 'echo',     msg: 'inbound iMessage thread (Sasha · 6 msgs)',      level: 'info' },
  { t: '14:31:12', agent: 'sherlock', msg: 'synthesizing · step 4/6 · 14 sources',          level: 'info' },
  { t: '14:30:58', agent: 'sentinel', msg: 'dispatch · digest job → sherlock',              level: 'info' },
  { t: '14:30:44', agent: 'aide',     msg: 'sent · Re: Q2 review (cc: legal)',              level: 'ok' },
  { t: '14:30:21', agent: 'hearth',   msg: 'idle · next: sunset routine 19:42',             level: 'info' },
  { t: '14:30:02', agent: 'ledger',   msg: 'idle · next: 06:00 daily reconcile',            level: 'info' },
  { t: '14:29:48', agent: 'forge',    msg: 'compiled billing/invoice.ts → no errors',       level: 'ok' },
  { t: '14:29:33', agent: 'echo',     msg: 'replied · slack #standup (auto-ack)',           level: 'ok' },
  { t: '14:29:14', agent: 'chronos',  msg: 'BLOCKED · flight booking · auth required',      level: 'crit' },
];

// ─── Sentinel scheduled jobs ───
const SENTINEL_JOBS = [
  { id: 's1', name: 'inbox.poll',         next: '14:34:00', cadence: '2m',     last: '14:32:00', target: 'aide',     enabled: true },
  { id: 's2', name: 'cal.sync',           next: '14:37:00', cadence: '5m',     last: '14:32:00', target: 'chronos',  enabled: true },
  { id: 's3', name: 'msgs.poll',          next: '14:32:30', cadence: '30s',    last: '14:32:00', target: 'echo',     enabled: true },
  { id: 's4', name: 'research.digest',    next: '17:00:00', cadence: 'daily',  last: 'yest 17:00', target: 'sherlock', enabled: true },
  { id: 's5', name: 'ledger.reconcile',   next: 'tmrw 06:00', cadence: 'daily', last: 'today 06:00', target: 'ledger', enabled: true },
  { id: 's6', name: 'home.sunset',        next: '19:42:00', cadence: 'solar',  last: 'yest 19:38', target: 'hearth',  enabled: true },
  { id: 's7', name: 'home.security.arm',  next: '23:00:00', cadence: 'daily',  last: 'yest 23:00', target: 'hearth',  enabled: false },
];

window.AGENTS = AGENTS;
window.TASKS = TASKS;
window.COLUMNS = COLUMNS;
window.ACTIVITY = ACTIVITY;
window.SENTINEL_JOBS = SENTINEL_JOBS;

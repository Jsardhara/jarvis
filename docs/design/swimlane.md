# Swimlane + Cost Chart — Design Spec

> Audience: `jarvis-frontend-dev` (Plan C3) implementing `/atlas/pipeline` and `/cost`.
> Status: spec only. No TS/TSX changes here. Tokens live in `web/src/app/globals.css`.

---

## 1. Visual direction

**Terminal Brutalism — applied, not imitated.**

The dashboard already commits to terminal brutalism: tier color signaling (T1 red → T5 slate), monospaced verification pills, sharp 1px borders, dense information per row, no rounded blob aesthetics. The swimlane and cost pages extend that language without mutating it.

Terminal brutalism fits the operator persona codified in `.claude/CLAUDE.md`:

- Tone is "terse, direct, like a competent chief of staff." UI should match — no decorative gradients, no playful illustrations, no sentence-cased marketing copy.
- The operator runs `pipeline()` — they want to *read execution*, not be persuaded by it. Brutalism's denial of decoration removes the negotiation layer between data and operator.
- Atlas trades capital. A pipeline that *looks* serious lowers the cognitive cost of trusting it. Glassmorphism would not.

How brutalism expresses on these two pages, specifically:

- **Mono everywhere structural** — stage labels, latency, event IDs, timestamps. Sans (Inter) only for prose, agent names, and tooltip body.
- **Square corners** on lanes, event cards, chart bars. `rounded-none` overrides any inherited shadcn radius.
- **Hairline 1px dividers** in `--pipeline-lane-divider`. No drop shadows on the swimlane surface — depth comes from background lightness deltas, not blur.
- **State as color, not icon spam.** One pill per stage carries state. No emoji, no five different lucide icons jammed into a header.
- **Latency rendered as a typographic citizen** — `342ms` typeset large enough to read at glance, never hidden in a tooltip.
- **Confirmation gate reads like a CLI prompt.** `> awaiting operator` with cursor-block aesthetic, not a polite modal.

---

## 2. Swimlane layout — `/atlas/pipeline`

### 2.1 Orientation: horizontal lanes (left → right pipeline flow)

Five lanes stacked vertically. Each lane is one Atlas stage. Time flows left-to-right *within* a lane: oldest event left, newest event right.

```
┌─────────── /atlas/pipeline ──────────────────────────────────────────────────┐
│  pipeline run #42  ·  started 14:02:11  ·  3 active  ·  guardian: PASS       │
├──────────┬───────────────────────────────────────────────────────────────────┤
│ ORACLE   │ [evt#11 done 412ms] [evt#13 done 380ms] [evt#17 running ····]     │
│ scan     │                                                                   │
├──────────┼───────────────────────────────────────────────────────────────────┤
│ ARCHITECT│ [evt#12 done 821ms] [evt#14 done 770ms] [evt#18 pending]          │
│ rank     │                                                                   │
├──────────┼───────────────────────────────────────────────────────────────────┤
│ GUARDIAN │ [evt#10 done  92ms] [evt#15 BLOCKED  > awaiting operator        ] │
│ check    │                                                                   │
├──────────┼───────────────────────────────────────────────────────────────────┤
│ TRADER   │ [evt#09 done 1.2s ] [evt#16 pending]                              │
│ execute  │                                                                   │
├──────────┼───────────────────────────────────────────────────────────────────┤
│ SAGE     │ [evt#08 done 230ms]                                               │
│ reflect  │                                                                   │
└──────────┴───────────────────────────────────────────────────────────────────┘
```

**Why horizontal, not vertical.**

1. The pipeline metaphor is sequential (`oracle_scan → architect_rank → guardian_check → trader_execute → sage_reflect`). Vertical lanes would force the eye to jump *between* lanes per event to follow one trade. Horizontal lanes let the operator track `evt#15` left-to-right by scrolling their gaze down the lane stack — which mirrors the sequence.
2. Latency comparison happens *within* a stage (is oracle_scan slow today?). That comparison wants events lined up on a horizontal timeline within one lane.
3. Guardian's `needs_confirm` block is wider than tall — a horizontal lane gives it room to live without distorting layout.
4. Five lanes × 1440px viewport = ~120px lane height each, fits without scrolling on a standard laptop. Vertical orientation would force horizontal scroll.

### 2.2 Lane anatomy

```
┌── lane header (sticky on scroll, 64px wide column) ──┐  ┌── event track ───┐
│ ORACLE                              [● 3]            │  │  scrolls →       │
│ scan                                                 │  │  events flush    │
│ p50 412ms · p95 980ms                                │  │  left-aligned    │
└──────────────────────────────────────────────────────┘  └──────────────────┘
```

- **Header column**: 200px fixed, `--pipeline-lane-header-bg`, sticky-left when track scrolls horizontally.
  - Stage name in mono uppercase, 13px, foreground.
  - Verb under name (`scan`, `rank`, `check`, `execute`, `reflect`) in 11px muted.
  - Live count pill: filled circle in current dominant state color, mono number of in-flight events.
  - p50 / p95 latency strip — last 20 events, calculated client-side.
- **Track**: flex row, 12px gap between event cards, horizontal scroll when overflow.
  - Newest event auto-scrolls into view. Older events stay anchored — auto-scroll only if user is already at the right edge (sticky-tail pattern).
  - Background alternates `--pipeline-lane-bg` / `--pipeline-lane-bg-alt` per lane (zebra striping, brutalist signal that lanes are distinct surfaces).

### 2.3 Event card anatomy

A single TraceEvent renders as a fixed-height (88px) card, variable width (min 140px, max 280px).

```
┌─────────────────────────────────┐
│ #17  oracle_scan          412ms │  ← header row: id + stage_action + duration
│ ───────────────────────────────  │
│ tier T3 · trade                  │  ← tier pill if present
│ 14:02:11.804                    │  ← absolute timestamp, mono 10px muted
└─────────────────────────────────┘
```

- Border: 1px solid, color = current state (see §3).
- Background: `--card`. No shadow. No radius (or `rounded-none`).
- Hover: outline thickens to 2px, no transform. Click opens detail drawer (out of scope for C3 v1; reserve `data-event-id` attribute).
- New events animate via `.animate-pipeline-event` (defined in globals.css) — opacity 0→1 + 2px translateY. Duration `--pipeline-event-pulse-duration`.

### 2.4 Pipeline header (above lanes)

```
pipeline run #42  ·  started 14:02:11  ·  3 active  ·  guardian: PASS
```

- Mono, 14px. `text-foreground` for active fields, `text-muted-foreground` for separators.
- "guardian: PASS" turns to `text-pipeline-stage-blocked` when guardian raises `needs_confirm`. Becomes the call-to-action surface alongside the inline gate (§3.4).

### 2.5 Scroll strategy

- Vertical: page scrolls if total lane stack > viewport (it shouldn't on desktop).
- Horizontal: per-lane independent scroll. Each lane has its own scrollbar. Lanes are NOT synchronized — Trader will naturally have fewer events than Oracle, forced sync would create awkward gaps.
- Max events kept in DOM per lane: **80**. Older events drop out the left edge (LRU). Operator wants live state, not a log archive — point them at `agent_log.jsonl` for full history.

---

## 3. State system — five stage states × visual treatments

| State | Token | Border | BG | Header pill | Motion | Trigger |
|---|---|---|---|---|---|---|
| **pending** | `--pipeline-stage-pending` | `1px solid` | `--card` | hollow circle | none | event queued, not yet dispatched |
| **running** | `--pipeline-stage-running` | `1px solid` | `--card` | filled circle, `.animate-stage-breathe` | breathing dot 1.6s | dispatched, awaiting return |
| **done** | `--pipeline-stage-done` | `1px solid` | `--card` | filled circle | none | success returned |
| **blocked** | `--pipeline-stage-blocked` | `2px solid` | `--card` over diagonal hatch | filled square | none — static | `needs_confirm: true` from agent |
| **error** | `--pipeline-stage-error` | `2px solid` | `--card` w/ 8% red overlay | filled triangle | none | exception, non-zero exit, timeout |

### 3.1 State precedence (when multiple events in lane)

The lane header pill reflects the *worst* current state in the lane, in this priority order:

```
error > blocked > running > pending > done
```

If lane has any `error`, header shows error. If no error but any `blocked`, blocked. Etc. This matches operator triage instincts — bad news first.

### 3.2 Tier overlay (orthogonal to state)

Existing tier badges (T1–T5 from `web/src/app/jarvis/page.tsx`) compose *inside* the event card body, not on the border. State owns the border. Tier owns the inner pill. Two independent semantic channels.

### 3.3 Latency rendering

- Inline numeric, top-right of event card, `font-mono text-sm`.
- Format: `<1000ms` → `412ms`. `>=1000ms` → `1.2s` (one decimal). `>=60s` → `1m04s`.
- Color: `text-foreground` if duration < lane p95, `text-pipeline-stage-blocked` if duration >= p95 (slow-event warning).
- No sparklines on individual events. Lane header shows the `p50 / p95` strip — a 60×8px inline svg sparkline of the last 20 durations, baseline = lane mean.

### 3.4 Confirmation gate (guardian `needs_confirm`)

When Guardian emits `needs_confirm: true`:

```
┌────────────────────────────────────────────────────────────────────┐
│ #15  guardian_check                                       BLOCKED  │
│ ───────────────────────────────────────────────────────────────── │
│ > awaiting operator                                                │
│ violations: position_size_exceeds_max, drawdown_threshold          │
│                                          [ approve ]  [ reject ]   │
└────────────────────────────────────────────────────────────────────┘
```

- Card width grows to 100% of remaining lane track (overrides max-width).
- The `>` is a literal block-cursor character, optional terminal-cursor blink (CSS only, respects reduced-motion).
- `approve` button: `--pipeline-stage-done` outline, mono uppercase.
- `reject` button: `--pipeline-stage-error` outline, mono uppercase.
- Buttons hit `/api/jarvis/confirmations` (existing endpoint pattern; verify with backend before wiring).
- Pipeline header status flips to `guardian: AWAITING` while gate is open.

---

## 4. Token reference

All tokens added to `web/src/app/globals.css` (the canonical token surface — there is no separate `tokens.css` in this repo). Each token has a light-mode value in `:root` and a dark-mode value in `.dark`.

### 4.1 Pipeline state tokens

| Token | Intent |
|---|---|
| `--pipeline-stage-pending` | Slate. Stage queued, not yet dispatched. Low energy — should not draw the eye. |
| `--pipeline-stage-running` | Indigo. Reuses primary hue family so "in-flight" feels native to the dashboard. Pairs with `.animate-stage-breathe`. |
| `--pipeline-stage-done` | Green. Reuses `--success` hue family. Confirms completion without celebration. |
| `--pipeline-stage-blocked` | Amber. Distinct from error red — operator action required, not failure. |
| `--pipeline-stage-error` | Red. Reserved for actual exceptions / timeouts. Do NOT use for `needs_confirm`. |

### 4.2 Lane chrome tokens

| Token | Intent |
|---|---|
| `--pipeline-lane-bg` | Primary lane surface. Sits above `--card` in dark mode (lighter), at paper-white in light. |
| `--pipeline-lane-bg-alt` | Zebra striping for adjacent lanes — brutalist way of saying "these are distinct rows." |
| `--pipeline-lane-divider` | 1px hairline rule between lanes. Sharp, no anti-alias glow. |
| `--pipeline-lane-header-bg` | Sticky header column background. Slightly recessed so the header reads as scaffolding, not content. |

### 4.3 Motion tokens

| Token | Intent |
|---|---|
| `--pipeline-event-pulse-duration` | 1100ms. New event arrival animation total length. Slow enough to register, fast enough not to feel sluggish on bursty pipelines. |
| `--pipeline-event-dwell-ms` | 600ms. Reserved for follow-on micro-transitions (e.g., state transition mid-flight); not consumed by v1 but documented so C3 can extend cohesively. |

### 4.4 Chart tokens

| Token | Intent |
|---|---|
| `--chart-axis` | Axis label color. Muted but legible. |
| `--chart-grid` | Gridline color. Faint enough to recede. |
| `--chart-tooltip-bg` / `--chart-tooltip-fg` | Inverted chip — dark in light mode, light in dark mode. Brutalist: tooltips are a *different surface*, not a frosted overlay. |
| `--chart-bar-tempo` | Cyan. Mail/calendar agent — "communications" hue. |
| `--chart-bar-scholar` | Violet. Academic agent. |
| `--chart-bar-lens` | Amber. Research / monitoring. |
| `--chart-bar-forge` | Red. Code / PRs / merges. Aligns with destructive accent — implies impact. |
| `--chart-bar-atlas` | Green. Capital / trading — "money green." |
| `--chart-bar-jarvis` | Graphite. Orchestrator overhead — neutral by design. |
| `--chart-bar-sentinel` | Light gray. Background daemon — should fade. |

---

## 5. Live update behavior

### 5.1 Event arrival

1. WebSocket message arrives on `/ws` carrying TraceEvent.
2. Component dispatches into `events: TraceEvent[]` state, indexed by `lane`.
3. New event appended to lane. Card mounts with `.animate-pipeline-event` (opacity 0→1 + translateY 2px→0, 1100ms).
4. If user scroll position is at the right edge (within 32px tolerance), lane track auto-scrolls newest into view via `scrollIntoView({ behavior: 'smooth', inline: 'end' })`. Otherwise no scroll — operator is reading something, do not yank their viewport.

### 5.2 State transitions on existing events

When an event flips from `running` → `done` (same event id, updated state):

- Border color animates via 200ms `transition: border-color`.
- No transform, no scale pulse. State changes are factual, not celebratory.
- Latency number fades in from 0 opacity (240ms) once final.

### 5.3 Burst handling

If >5 events arrive in <100ms (Atlas pipeline can fan out):

- Disable per-event animation in that batch (apply `.animate-pipeline-event` only to the *last* of the batch).
- Render the rest static. Prevents jank from 20 simultaneous animations.
- Implementation: debounce on `requestAnimationFrame` boundary; track `lastAnimatedAt` per lane.

### 5.4 Disconnect / reconnect

- WebSocket disconnect: pipeline header shows `connection: LOST` in `--pipeline-stage-error`. Lanes freeze (no greying — operator can still read last known state).
- Reconnect: header returns to normal. New events resume.
- This composes with the degraded-mode banner from Frontend C1 — page-level connectivity state is owned by C1, page-internal "stream is live" state is owned here.

### 5.5 Reduced motion

`@media (prefers-reduced-motion: reduce)` already disables the two new keyframes (`pipeline-event-pulse`, `pipeline-stage-breathe`) in globals.css. State changes still happen — they just become instant.

---

## 6. `/cost` page

### 6.1 Chart type: stacked vertical bar

- One bar per day. Bar segments stack the per-agent cost contributions for that day.
- Why stacked, not grouped: operator wants total daily spend (single bar height) and breakdown (segment heights) in one read. Grouped bars force an additional summation step.
- Why bar, not line: cost is a *count of discrete events*, not a continuous quantity. Bars communicate "this is what was spent on day N," lines imply interpolation between days that doesn't exist.
- Why not a pie: pies obscure trend. Cost without trend is useless.

### 6.2 Time axis: last 14 days, daily granularity

- 14 days = two weeks. Long enough to see weekday/weekend cadence and detect a regression. Short enough to fit on screen without horizontal scroll.
- Endpoint contract assumed: `GET /api/cost/rollup?days=14` returning `DailyRollup[]` (defined in §7.2).
- X-axis labels: `Mon 21`, `Tue 22`, etc. Today's bar emphasized — 2px outline in `--foreground`.
- If less than 14 days of data exist, render available days flush-right; left-pad with placeholder bars (`--pipeline-lane-bg-alt`, no segments) to keep axis spacing consistent.

### 6.3 Agent stack order (bottom → top within a bar)

```
1. atlas      (--chart-bar-atlas)
2. forge      (--chart-bar-forge)
3. lens       (--chart-bar-lens)
4. scholar    (--chart-bar-scholar)
5. tempo      (--chart-bar-tempo)
6. jarvis     (--chart-bar-jarvis)
7. sentinel   (--chart-bar-sentinel)
```

Order: highest-cost agents at the bottom (they sit on the axis, easiest to read absolute height). Sentinel and Jarvis on top — usually small, won't distort.

### 6.4 Page layout

```
┌────────── /cost ──────────────────────────────────────────────┐
│  daily cost · last 14d  ·  total $42.18  ·  proj month $92.40 │
├───────────────────────────────────────────────────────────────┤
│  [stacked bar chart, 100% width, ~340px tall]                 │
├───────────────────────────────────────────────────────────────┤
│  legend (mono row)                                            │
│  ▪ atlas $18.40  ▪ forge $12.10  ▪ lens $6.20  …              │
├───────────────────────────────────────────────────────────────┤
│  per-agent table (sortable):                                  │
│  agent     calls  in_tokens  out_tokens  $   $/call           │
│  atlas      842   1.2M       210k       18.40  0.0218         │
│  forge      221   480k       95k        12.10  …              │
│  …                                                            │
└───────────────────────────────────────────────────────────────┘
```

### 6.5 Interaction

- **Hover bar segment**: tooltip in `--chart-tooltip-bg` / `--chart-tooltip-fg`. Mono. Shows: `agent · day · $X.XX · N calls`.
- **Hover whole bar**: tooltip shows `day · $X.XX total · N calls across M agents`.
- **Click bar segment**: filter table below to that agent + day combination. URL updates to `?agent=atlas&day=2026-04-25` — URL state per `web/patterns.md`.
- **Click legend item**: toggle that agent's segment visibility. Persisted to URL: `?hide=sentinel,jarvis`.
- **Keyboard**: `Tab` cycles bars left→right, `Enter` activates same as click. Arrow keys move between segments within current bar.

### 6.6 Accessibility

- Each bar segment is a `<button>` with `aria-label="atlas, April 25, $1.20, 84 calls"`.
- Color is not the sole channel — tooltip and table provide all info textually.
- Contrast: every `--chart-bar-*` paired against `--card` passes WCAG AA at 14px+ (verified against oklch lightness deltas; spot-check in browser before ship).
- Reduced motion: bar entrance animation (240ms grow-from-baseline) is dropped under `prefers-reduced-motion: reduce`.

---

## 7. Component contract

### 7.1 `<PipelineSwimlane />`

```ts
interface TraceEvent {
  id: string;
  pipelineRun: number;
  lane: 'oracle' | 'architect' | 'guardian' | 'trader' | 'sage';
  state: 'pending' | 'running' | 'done' | 'blocked' | 'error';
  startedAt: string;        // ISO 8601
  endedAt?: string;
  durationMs?: number;
  tier?: 1 | 2 | 3 | 4 | 5;
  intent?: string;
  needsConfirm?: boolean;
  violations?: string[];
  errorMessage?: string;
}

interface PipelineSwimlaneProps {
  events: TraceEvent[];
  connectionState: 'connecting' | 'live' | 'lost';
  onConfirm: (eventId: string, decision: 'approve' | 'reject') => Promise<void>;
  maxEventsPerLane?: number;  // default 80
}
```

- Owns its own scroll state per lane (`Map<Lane, scrollLeft>`).
- Does NOT own WebSocket. Page wraps it and feeds events down. This keeps the component testable with static fixtures.

### 7.2 `<CostChart />`

```ts
interface AgentCost {
  agent: 'tempo' | 'scholar' | 'lens' | 'forge' | 'atlas' | 'jarvis' | 'sentinel';
  costUsd: number;
  calls: number;
  inputTokens: number;
  outputTokens: number;
}

interface DailyRollup {
  date: string;             // YYYY-MM-DD
  totalUsd: number;
  perAgent: AgentCost[];
}

interface CostChartProps {
  data: DailyRollup[];
  selectedAgent?: string;   // URL state
  hiddenAgents?: string[];  // URL state
  onSegmentClick?: (agent: string, date: string) => void;
}
```

- Pure presentational. Page owns fetching from `/api/cost/rollup` (which Plan A3 ships).
- Renders SVG, not canvas. Brutalism wants pixel-sharp axis lines.

### 7.3 Page composition (informational — C3 will build these)

```
/atlas/pipeline page
├── BreadcrumbNav (existing)
├── PipelineHeader (status, run id, guardian state)
├── PipelineSwimlane (5 lanes)
└── DegradedBanner (from C1, when applicable)

/cost page
├── BreadcrumbNav
├── CostSummaryStrip (total, projection, daterange)
├── CostChart
├── CostLegend
└── CostTable
```

---

## 8. Acceptance criteria

C3 is **done** when, with backend stubs feeding fixtures:

### Swimlane

- [ ] Five lanes render in correct order: oracle, architect, guardian, trader, sage.
- [ ] Each of the 5 stage states has its documented border + pill treatment, distinguishable side-by-side at 1m viewing distance.
- [ ] Running stage breathes; reduced-motion users see no animation.
- [ ] New event card animates in with the documented opacity+translate; burst of 10 events does not jank (animation only on last).
- [ ] Lane header sticky-left when track scrolls horizontally.
- [ ] Newest event auto-scrolls into view only when operator is at right edge.
- [ ] Guardian `needs_confirm` event renders as full-width gate with `> awaiting operator` and approve/reject buttons.
- [ ] Pipeline header reflects worst current state via the documented precedence.
- [ ] DOM holds at most 80 events per lane.
- [ ] Connection-lost state shows `connection: LOST` in pipeline header without freezing the rendered lane data.

### Cost

- [ ] Stacked bar chart renders 14 days in chronological order, today emphasized.
- [ ] Stack order matches §6.3 exactly.
- [ ] Each segment is a focusable button with the documented `aria-label`.
- [ ] Hover over segment shows mono tooltip with agent/day/cost/calls.
- [ ] Click segment updates URL (`?agent=X&day=Y`) and filters the table.
- [ ] Legend item click hides/shows segments and persists to URL.
- [ ] Keyboard: Tab cycles bars, Enter selects, arrow keys move within segments.
- [ ] Per-agent table sortable by every column.
- [ ] No `--chart-bar-*` color fails WCAG AA against `--card` background.

### Cross-cutting

- [ ] No TypeScript errors. `pnpm --prefix web tsc --noEmit` passes.
- [ ] No new font added. Inter (sans) + system mono only.
- [ ] No `rounded-*` radii larger than 0px on swimlane or chart elements (terminal brutalism — square corners are the rule).
- [ ] Both light and dark themes feel intentional (per `~/.claude/rules/web/design-quality.md` checklist).
- [ ] Page renders correctly at 320 / 768 / 1024 / 1440 widths. Below 768, swimlane collapses to single-lane vertical mode (one lane visible, lane switcher tabs above) — this is a v2 if time-boxed; for v1 a horizontal-scroll fallback at 768 is acceptable.

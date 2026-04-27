# Jarvis Mission Control — Design Spec

**Direction:** Terminal Brutalism
**Status:** Approved 2026-04-27
**Owner:** design → ui (implementation)
**Scope:** `web/src/` — Next.js 15 + React 19 frontend, primary surface is `/` (Mission Control)

---

## 1. Visual direction

Terminal Brutalism. Single canonical direction.

The product is a single-operator mission-control surface that runs autonomous agents with mutation authority — send mail, trigger trades, cancel meetings, push commits. The visual language is honest about that responsibility: information-dense, hard-edged, achromatic-by-default with semantic color earned only by tier and verification state. Closer to a Bloomberg terminal or air-traffic control than to a SaaS dashboard.

**Five rules:**

1. **Hard edges.** Radius is `0` or `2px`. No rounded-`lg` shadcn defaults anywhere.
2. **Borders are layout, not decoration.** Every region is a labeled block. Hairlines (1px) define structure; shadows are reserved for *lifted* surfaces only.
3. **Type contrast through size and family**, not weight inflation. Mono (data) + serif display (labels, headings, agent names) is the pairing.
4. **Layered depth via stacked surface tiers.** Five surface levels (`bg`, `surface-0/1/2/3`) with crisp borders between them. No gradients except the dispatch-bar reveal.
5. **Color is semantic.** Tier color = authority/risk. Verification color = epistemic state. Status color = lifecycle. Never decorative.

**Anti-template self-check (hits 8 of 10):**

| # | Quality | How |
|---|---|---|
| 1 | Scale-contrast hierarchy | Mono 11–13px data vs. Fraunces 24/32/48px display |
| 2 | Intentional spacing rhythm | 4/8/12/16/24/40/64 (not uniform 16) |
| 3 | Depth via layering | 5 surface tiers + crisp hairlines + shadow on lifted regions only |
| 4 | Real type pairing | IBM Plex Mono + Fraunces — opposing classifications, deliberate |
| 5 | Semantic color | Tiers + verification have meaning; achromatic by default |
| 6 | Designed states | hover lifts hairline brightness, focus draws full ring, active inverts surface |
| 7 | Grid-breaking composition | Atlas sub-flow rail breaks main grid full-width below dispatch bar |
| 8 | Designed data viz | Dispatch graph gets hand-drawn aesthetic edges, tier-color nodes |
| — | Texture/grain | Skipped — competes with information density |
| — | Atmosphere | Skipped — terminal energy, no fog |

---

## 2. Token spec

All values OKLCH. Light mode is warm paper, not pure white. Dark mode is deep neutral, not pure black.

### 2.1 Surfaces

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `oklch(13% 0.008 250)` | `oklch(97% 0.005 90)` | Page canvas |
| `--surface-0` | `oklch(16% 0.010 250)` | `oklch(95% 0.006 90)` | Region wrapper, status bar |
| `--surface-1` | `oklch(19% 0.012 250)` | `oklch(93% 0.007 90)` | Cards, agent rows |
| `--surface-2` | `oklch(23% 0.014 250)` | `oklch(90% 0.008 90)` | Hovered card, palette item |
| `--surface-3` | `oklch(28% 0.016 250)` | `oklch(86% 0.010 90)` | Pressed/active state |
| `--surface-lift` | `oklch(20% 0.014 250)` | `oklch(99% 0.004 90)` | Drawer, palette, confirmation card (gets shadow) |

### 2.2 Borders

| Token | Dark | Light | Use |
|---|---|---|---|
| `--border` | `oklch(28% 0.018 250)` | `oklch(86% 0.010 90)` | Default 1px hairline |
| `--border-bright` | `oklch(40% 0.025 250)` | `oklch(72% 0.014 90)` | Hover, focus assist |
| `--border-strong` | `oklch(55% 0.030 250)` | `oklch(50% 0.018 90)` | Focus ring, divider rails |

### 2.3 Text

| Token | Dark | Light | Use |
|---|---|---|---|
| `--text` | `oklch(94% 0.005 250)` | `oklch(18% 0.008 250)` | Primary body / data |
| `--text-dim` | `oklch(70% 0.008 250)` | `oklch(40% 0.010 250)` | Secondary, action descriptors |
| `--text-mute` | `oklch(52% 0.008 250)` | `oklch(58% 0.010 250)` | Hints, metadata, timestamps |
| `--text-display` | `oklch(96% 0.004 250)` | `oklch(14% 0.010 250)` | Serif headings, agent names |

### 2.4 Tier colors (5-tier authority/risk scheme)

Tier 1 hardest, Tier 5 softest. Each tier defines `*-fg` (text on surface), `*-line` (3px border-left, hairline accents), `*-bg` (8% chroma surface tint for badge fill).

| Tier | Meaning | `--tier-N-fg` (dark) | `--tier-N-line` (dark) | `--tier-N-bg` (dark) | Light variants |
|---|---|---|---|---|---|
| **T1** | Mutation authority, irreversible (send mail, trigger ATLAS strategy, push to main) | `oklch(70% 0.20 25)` | `oklch(58% 0.22 25)` | `oklch(28% 0.10 25)` | fg `oklch(45% 0.22 25)`, line `oklch(52% 0.24 25)`, bg `oklch(94% 0.06 25)` |
| **T2** | Mutation authority, reversible (draft reply, create task, move event) | `oklch(78% 0.16 65)` | `oklch(72% 0.18 70)` | `oklch(32% 0.09 70)` | fg `oklch(55% 0.16 65)`, line `oklch(60% 0.18 70)`, bg `oklch(94% 0.07 80)` |
| **T3** | Read-mutate boundary (search + propose, classify + log) | `oklch(76% 0.13 195)` | `oklch(70% 0.12 195)` | `oklch(28% 0.07 195)` | fg `oklch(48% 0.14 195)`, line `oklch(54% 0.13 195)`, bg `oklch(92% 0.05 195)` |
| **T4** | Read-only (briefing, summary, query) | `oklch(72% 0.06 240)` | `oklch(62% 0.04 240)` | `oklch(26% 0.03 240)` | fg `oklch(46% 0.06 240)`, line `oklch(50% 0.05 240)`, bg `oklch(93% 0.02 240)` |
| **T5** | Passive observation (sentinel, heartbeat, log tail) | `oklch(66% 0.06 290)` | `oklch(58% 0.05 290)` | `oklch(24% 0.03 290)` | fg `oklch(46% 0.06 290)`, line `oklch(50% 0.05 290)`, bg `oklch(93% 0.02 290)` |

**Color contrast notes:**
- T1 red is intentionally distinct from `--status-error` (which is pure alert): T1 red sits on lightness 70 at hue 25; alert sits on 64. Operator should perceive T1 as "armed" and error as "broken".
- T2 amber is intentionally **warmer** (hue 65–70) than verification-inference amber (hue 80) so the two are visually separable when they appear on the same row.

### 2.5 Verification pill colors

Verification ≠ tier. Verification is the epistemic state of an agent's last reply: did we *prove* it, *guess* it, *not know*, or *re-check after action*?

| State | Code | Dark fg | Dark line | Light fg | Light line |
|---|---|---|---|---|---|
| **verified** | `VR` | `oklch(76% 0.16 150)` | `oklch(70% 0.16 150)` | `oklch(46% 0.16 150)` | `oklch(50% 0.18 150)` |
| **inference** | `IN` | `oklch(80% 0.14 80)` | `oklch(74% 0.16 80)` | `oklch(52% 0.16 80)` | `oklch(56% 0.18 80)` |
| **unknown** | `UN` | `oklch(64% 0.012 250)` | `oklch(60% 0.010 250)` | `oklch(46% 0.012 250)` | `oklch(50% 0.012 250)` |
| **post-state-checked** | `SC` | `oklch(72% 0.16 235)` | `oklch(66% 0.16 235)` | `oklch(46% 0.18 235)` | `oklch(50% 0.20 235)` |

`SC` (post-state-checked) means: agent did the thing, then re-fetched authoritative state from the source system to confirm the result. That's a stronger claim than `VR` for any state-mutating operation, hence its own color.

### 2.6 Status colors (lifecycle)

Reused from existing tokens with one rename. These are agent runtime state, not tier or verification.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--status-running` | `oklch(78% 0.16 75)` | `oklch(58% 0.18 75)` | Agent dispatched, waiting |
| `--status-done` | `oklch(72% 0.18 145)` | `oklch(48% 0.18 145)` | Completed cleanly |
| `--status-warn` | `oklch(78% 0.17 65)` | `oklch(54% 0.18 65)` | needs_confirm queued |
| `--status-error` | `oklch(64% 0.22 25)` | `oklch(52% 0.22 25)` | Errored / failed |
| `--status-idle` | `oklch(55% 0.020 250)` | `oklch(70% 0.012 250)` | Never dispatched |

### 2.7 Spacing

Anti-uniform. Operator should perceive groupings, not a 16px treadmill.

```
--space-0:  4px
--space-1:  8px
--space-2: 12px
--space-3: 16px
--space-4: 24px
--space-5: 40px
--space-6: 64px
```

Vertical rhythm rules:
- Inside a card: `--space-1` (8) between rows, `--space-2` (12) edge padding
- Between cards: `--space-1` (8)
- Between regions: 1px hairline (no padding — the line *is* the separator)
- Section heading to first row: `--space-2` (12)

### 2.8 Radius

```
--radius-0: 0     /* default */
--radius-1: 2px   /* pills, badges, swimlane blocks */
--radius-2: 4px   /* drawer, palette, confirmation card */
```

No `--radius-lg`. No `--radius-full` except for the live status dot (which keeps its 50%).

### 2.9 Motion

```
--duration-fast:   120ms
--duration-normal: 200ms
--duration-slow:   320ms
--ease-out:        cubic-bezier(0.16, 1, 0.3, 1)
--ease-in-out:     cubic-bezier(0.65, 0, 0.35, 1)
```

Animate only `transform`, `opacity`, `clip-path`, `stroke-dashoffset`. Never width/height/top/left.

### 2.10 Shadow (used sparingly)

```
--shadow-lift: 0 0 0 1px oklch(0% 0 0 / 0.4), 0 8px 24px oklch(0% 0 0 / 0.45);
```

Only on `--surface-lift`: drawer, command palette, confirmation card when it has pending items. **Not** on agent cards. **Not** on dispatch graph. **Not** on swimlane blocks.

Light mode shadow:
```
--shadow-lift: 0 0 0 1px oklch(50% 0.012 90 / 0.18), 0 8px 24px oklch(40% 0.020 90 / 0.18);
```

---

## 3. Typography

### 3.1 Pairing

- **IBM Plex Mono** — already loaded via `next/font/google` in `web/src/app/layout.tsx`. Used for: data, action descriptors, timestamps, agent metadata, dispatch input, command palette, swimlane labels, confirmation summaries. Weights: 400, 500, 600, 700.
- **Fraunces** (operator may swap for GT Sectra if licensed) — new. Used for: agent name (in card), region heading (`<h2>`), drawer title, brand mark, tier badge letter. Weights: 500, 600, 700. Italic 500 for ambient muted display copy. Optical sizing enabled (`opsz`).

Why this pairing: Plex Mono is industrial, neutral, info-dense — matches the data-first ethos. Fraunces is a high-contrast modern serif with strong personality at display sizes — gives the *human* labels (agent names, region titles) a deliberate voice that says "this surface was designed, not generated". The classification gap (mono geometric vs. transitional serif) prevents the pair from blurring together.

Loading: add Fraunces via `next/font/google` alongside the existing imports. Subset to latin only. Use `display: "swap"`. Variable font, axis: `opsz` 9–144, `wght` 100–900.

### 3.2 Type scale

| Role | Family | Size | Weight | Letter-spacing | Line-height |
|---|---|---|---|---|---|
| Display XL (hero, briefing) | Fraunces | `clamp(2rem, 1rem + 4vw, 3rem)` | 600 | -0.01em | 1.05 |
| Display L (drawer title) | Fraunces | `1.5rem` | 600 | -0.005em | 1.1 |
| Display M (agent name in card) | Fraunces | `1.0rem` | 600 | 0 | 1.15 |
| Display S (region heading `h2`) | Fraunces | `0.78rem` | 600 italic | 0.04em | 1.2 |
| Body | Plex Mono | `0.8125rem` (13px) | 400 | 0 | 1.5 |
| Body small | Plex Mono | `0.75rem` (12px) | 400 | 0 | 1.45 |
| Micro / metadata | Plex Mono | `0.6875rem` (11px) | 500 | 0.06em uppercase | 1.3 |
| Tier badge letter | Fraunces | `0.75rem` | 700 | 0 | 1.0 |
| Pill code (VR/IN/UN/SC) | Plex Mono | `0.625rem` (10px) | 700 | 0.10em uppercase | 1.0 |

**Switching rule:** anything that *names* a thing → Fraunces. Anything that is *data*, *transient*, or *mechanical* → Plex Mono. Region headings are display because they label a *region*, which is a thing. Action descriptors ("running scan", "mailbox triage") are mono because they're transient.

### 3.3 Tabular nums

Keep `font-variant-numeric: tabular-nums` on `body` (already set). Mono digits stay aligned in confidence dots, timestamps, status pills.

---

## 4. Layout philosophy

### 4.1 Hierarchy lives in scale × family × density — not nesting

The current dashboard is one weight family at one size. The redesign keeps the same grid but introduces **three scale tiers**: display (Fraunces 16–48px), body (Plex 12–13px), micro (Plex 10–11px). A glance gives you region → agent → state. No further nesting needed.

### 4.2 Grid (Mission Control `/`)

Existing grid is preserved with one addition. The grid:

```
┌────────────────────────────── status bar (40px) ──────────────────────────────┐
│ JARVIS // MISSION CONTROL    api●live  ws●connected           clock           │
├──────────────────────┬──────────────────────────────────┬─────────────────────┤
│                      │                                  │                     │
│   AGENT GRID         │   DISPATCH GRAPH                 │   CONFIRMATIONS     │
│   (360px wide)       │   (flex)                         │   (320px wide)      │
│   ─ tempo            │                                  │   [pending cards]   │
│   ─ scholar          │                                  │                     │
│   ─ lens             ├──────────────────────────────────┤                     │
│   ─ forge            │                                  │   ◀── lifted: gets  │
│   ─ atlas            │   ACTIVITY STREAM                │       its own       │
│   ─ sentinel         │   (swimlanes, 240px tall)        │       surface +     │
│                      │                                  │       shadow when   │
│                      │                                  │       items present │
├──────────────────────┴──────────────────────────────────┴─────────────────────┤
│ >  dispatch input                                       ⌘K palette · click ag │
├───────────────────────────────────────────────────────────────────────────────┤
│  ATLAS SUB-FLOW RAIL  (only when atlas active — slides up, 56px tall)         │
│  oracle ─▶ architect ─▶ guardian ─▶ trader ─▶ sage     [VR][VR][SC][IN][--]   │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Grid-break: Atlas sub-flow rail

This is the one designed grid-break. When `atlas.pipeline()` is dispatched, a 56px-tall horizontal rail slides up from below the dispatch bar (transform-only animation, 320ms ease-out). It spans the full viewport width — it **breaks** the agent-grid + main-content + confirmation column structure intentionally.

Layout:
- 5 stage nodes connected by 1px lines: `oracle → architect → guardian → trader → sage`
- Each node: 88px wide, Plex Mono uppercase 11px label, status dot, verification pill underneath (10px height, full-width of node)
- Active stage gets `--tier-1-line` (red) left border + pulse animation reused from `.dot[data-status="running"]`
- Completed stages get `--status-done` ring around the dot
- Halted stages (Guardian violation) get `--tier-1-line` flash 3× then settle on `--status-warn`
- Rail dismisses (slides down) 12s after pipeline terminal state

### 4.4 Confirmation queue gets a visual lift

It's the only region that requires user input. It earns:
- `--surface-lift` background (one tier brighter than other regions in dark, pure white in light)
- `--shadow-lift` when `pending.length > 0`
- A 2px left border in `--status-warn` when items pending, animated draw-in on first arrival
- Region heading `pending confirmations` becomes Fraunces 600 italic, slightly larger than other regions (0.92rem) — tells the operator's eye to look here

When empty: surface-lift remains, shadow drops, heading drops to normal italic, body text is `--text-mute` placeholder. Region never collapses.

### 4.5 Light vs dark

Both modes are intentional. Default is **dark** (matches operator's overnight terminal usage). Light mode is warm paper, never pure white — `oklch(97% 0.005 90)`. Same tier hues, lightness inverted for contrast.

Theme switch: accessible via top-right of status bar, persists in `localStorage`, respects `prefers-color-scheme` on first load.

---

## 5. Component-level guidance

No code. Spec only. `ui` implements.

### 5.1 TierBadge

Displayed top-left of every `AgentCard`, small.

- 18×18px square, `--radius-1` (2px)
- Background `--tier-N-bg`, 1px border `--tier-N-line`
- Letter `T1`–`T5` in Fraunces 700, 12px, color `--tier-N-fg`, optically centered
- Hover: badge bg lightens to `--surface-2` blend; tooltip (Plex Mono 11px) shows full tier name + meaning
- Focus (keyboard nav): 2px ring `--border-strong` offset 2px

### 5.2 VerificationPill

Renders agent's last reply epistemic state. Used in agent cards, swimlane block bottoms, atlas sub-flow nodes, confirmation cards.

- Pill shape: 4px height in compact form (sub-flow), 14px tall in card form
- Compact: just a 3px-tall colored bar, 100% width of parent
- Card form: code (`VR`/`IN`/`UN`/`SC`) in Plex Mono 700 10px uppercase + 1px-tall line below in matching color
- Color from `--vrf-*-fg` (text) and `--vrf-*-line` (line)
- Transition between states: 180ms color crossfade on `background` and `color`
- When transitioning `IN → SC` (agent re-checked state after action): brief 220ms scale-x 1.0 → 1.04 → 1.0 transform pulse to draw operator's eye

### 5.3 AgentCard

Existing card stays as the foundation, gains:

- **Tier badge** in the top-left, vertically centered with the live-status dot. Replaces nothing — slots between the dot and the agent name column.
- **Agent name** flips from Plex Mono uppercase 12px to **Fraunces 600 16px sentence-case**. This is the single biggest perceptible change. (Was `TEMPO`, becomes `Tempo`.)
- **Action descriptor** stays Plex Mono 13px, color `--text-dim`.
- **Verification pill** (compact form, 3px bar) sits along the **bottom edge of the card**, full-width, color from last reply's verification state. Idle agents get `--vrf-unknown-line`.
- **Left-edge status border** stays (3px, `--status-*` color). This now layers *with* the bottom verification bar — top-half = lifecycle, bottom = epistemic.
- **Confidence dots** stay but use `--tier-N-fg` instead of `--accent` for filled state. Each agent's confidence reads in its tier's color, reinforcing the tier system every time confidence updates.
- **Hover** lifts background to `--surface-2`, border `--border-bright`, no transform (no jitter when scanning).
- **Focus** draws a 2px `--border-strong` ring offset 2px outside the card.
- **Active/clicked** inverts to `--surface-3` for 80ms then settles.

### 5.4 SwimlaneStream

Existing structure preserved with three additions:

- **Lane label** (e.g., `tempo`) flips from Plex Mono uppercase 12px to **Fraunces 600 italic 13px sentence-case**. Adds a 1px hairline in `--tier-N-line` directly under the label, 24px wide. Operator instantly sees tier-grouping in the stream.
- **Swimlane block** stays Plex Mono 11px. Border-color uses `--status-*`, text uses the same. A new **3px bottom border** in `--vrf-*-line` shows the verification state of that event. Block appears with existing slide-in animation, verification bar fades in 100ms after.
- **Empty lane** renders a single `—` glyph in `--text-mute` (existing). No layout shift when blocks arrive.

### 5.5 AtlasSubFlow (new component)

Lives in its own region below the dispatch bar. Hidden by default. Mounted to the DOM at app load, animated via CSS `transform: translateY(100%)` ↔ `translateY(0)` on `data-active`.

- **Container**: full-width, 56px tall, `--surface-1` bg, top border 1px `--tier-1-line` (red), bottom edge of viewport
- **Stages** (5): laid out evenly, no scroll. Connected by 1px lines `--border-bright`, drawn with `stroke-dashoffset` animation when stage transitions
- **Stage node**:
  - 88px wide × 48px tall block
  - Top row (24px): Fraunces 600 italic 11px stage label (`oracle`, `architect`, etc.)
  - Middle (16px): live status dot + Plex Mono 10px micro state ("scanning", "ranking", "halted")
  - Bottom row (8px, full-width strip): VerificationPill compact form
- **Active stage**: 2px left border `--tier-1-line`, pulse on the dot (existing `pulse` keyframes)
- **Completed stage**: status dot `--status-done`, label color `--text` (full strength)
- **Halted stage** (Guardian violation): label flashes `--tier-1-line` 3 times (320ms each), then settles. Background of that stage tints `--tier-1-bg` for the remainder of the rail's lifecycle. A small `[!]` glyph (Plex Mono 700 12px, `--tier-1-fg`) appears next to the label.
- **Skipped stage** (e.g., trader didn't run because guardian halted): status dot `--status-idle`, label color `--text-mute`, verification pill `unknown`
- **Rail dismissal**: 12s after terminal state (or operator click on close button at far right of rail), slide down, unmount on transition end
- **Reduced motion**: respects `prefers-reduced-motion`. Opacity fade replaces translate.

### 5.6 StatusBar (refinements)

Existing component, light touches:

- Brand mark `JARVIS // MISSION CONTROL` flips to **Fraunces 700 italic 13px**, color `--text-display`. Mono `// MISSION CONTROL` stays Plex Mono 700 11px uppercase. The two-family treatment in the brand itself is intentional — sets the tone for the whole surface.
- Pills (`api live`, `ws connected`, clock) stay Plex Mono 11px. `--radius-1` (2px). Border-color from status.
- New trailing slot: theme toggle (sun/moon outline, 16×16, `--text-dim`, hover `--text`). Click flips theme + persists.

### 5.7 ConfirmationQueue (refinements)

Already covered in 4.4. Additions:

- Each `conf-card`:
  - Background `--surface-lift` (matches column)
  - Border-left 3px `--tier-N-line` based on the tier of the action being confirmed (T1 send mail → red, T2 cancel event → amber)
  - Tier badge in the top-left (same `TierBadge` component) — operator immediately knows the risk class before reading the summary
  - Agent name in **Fraunces 600 sentence-case 14px**, `--tier-N-fg`
  - Summary in Plex Mono 13px `--text`
  - Approve button: solid `--status-done` for T3+, but `--surface-2` with `--status-done` text for T1 (forces deliberate click — the green button is *not* there waiting to be hit)
  - Reject button: ghost, `--text-dim`, hover `--text`
  - Time-to-expiry indicator: 1px hairline along the bottom that drains left-to-right over the confirmation timeout (existing or new — back's call)

### 5.8 DispatchGraph (refinements)

Same SVG topology. Three changes:

- **Node fill** uses `--surface-1`, stroke `--border-bright`. Primary node stroke uses `--tier-N-line` based on the dispatched agent's tier (so the user sees red flowing into TEMPO when sending mail vs. teal flowing into LENS for research).
- **Node text** uses Fraunces 600 11px small-caps for agent names (instead of mono uppercase). Router and User nodes stay Plex Mono 700 11px uppercase — they're system, not agents.
- **Edge stroke** uses `--border-bright` default; primary edge animates with the existing `drawEdge` keyframes, stroke `--tier-N-line` of the destination. So the *line itself* carries tier color — operator sees risk flowing through the dispatch.

### 5.9 CommandPalette (refinements)

- Container: `--surface-lift` + `--shadow-lift`, `--radius-2` (4px)
- Search input: Plex Mono 16px, no border, 1px hairline divider below
- Result row:
  - Agent tag (left): Fraunces 600 italic 13px, color `--tier-N-fg`
  - Action: Plex Mono 13px `--text-dim`
  - On `data-active`: bg `--surface-2`, agent tag color shifts to `--tier-N-fg` at full chroma
- Active row left edge: 2px `--tier-N-line`

### 5.10 Toast / Drawer

- **Drawer**: keep existing slide animation, swap to `--surface-lift` + `--shadow-lift`. Header bar gets the agent's tier badge. Drawer name uses Fraunces 600 18px.
- **Toast**: keep, but border-left uses tier-color of the agent that triggered it, not always `--status-warn`.

---

## 6. Implementation guardrails for ui

What `ui` should and shouldn't do:

**Do:**
- Replace existing tokens in `web/src/app/globals.css` per §2. Keep the existing alias names where they exist (`--bg`, `--surface`, etc.) so non-Mission-Control routes don't break — *map* the old names to the new tier surface tokens.
- Add Fraunces via `next/font/google` in `web/src/app/layout.tsx` next to the existing `IBM_Plex_Sans`/`JetBrains_Mono`. Expose as `--font-display`.
- Drop `IBM_Plex_Sans` — Plex Mono is the only mono, Fraunces is the only display. Sans is unused real estate.
- Build the `TierBadge` and `VerificationPill` as standalone components in `web/src/components/`.
- Add `AtlasSubFlow.tsx` as a new component, wire it to the existing trace-event stream (it should listen for `atlas.stage.*` events — coordinate with `back` on the exact event names).
- Implement the theme toggle + `localStorage` persistence + `prefers-color-scheme` honoring on first load.
- Keep all motion compositor-safe: `transform`, `opacity`, `clip-path`, `stroke-dashoffset`. Honor `prefers-reduced-motion`.

**Don't:**
- Don't introduce a CSS-in-JS lib. Plain CSS modules / globals are fine; the existing setup works.
- Don't add `shadcn/ui` or any component library. Hand-roll.
- Don't use rounded-lg / rounded-md / rounded-full anywhere except the live `.dot`. Radius is `0` / `2px` / `4px`, full stop.
- Don't animate width/height/top/left.
- Don't ship the Atlas sub-flow until `back` has emitted `atlas.stage.*` events. Until then, leave the component implemented but mounted with `data-active="false"` and a fixture-driven storybook entry only.
- Don't break the existing routes (`/briefing`, `/inbox`, `/tasks`, `/atlas`, `/console`). They use `--bg`, `--surface`, `--accent`, `--border` — keep those names mapped to the new palette, even if the structure is now richer.

---

## 7. Open items for operator

1. **Display font.** Spec calls Fraunces (Google Fonts, free, variable). Operator may swap for licensed face (GT Sectra, Söhne Schmal, etc.). Spec is font-stack-stable as long as classification stays "transitional/contrast serif".
2. **Light mode default.** Spec defaults to dark. Operator can flip.
3. **Atlas rail dismissal timeout.** 12s is a guess. Operator may want it to persist until next dispatch.

These are not blocking — `ui` implements the spec as written, operator overrides post-implementation.

---

## 8. Acceptance criteria for ui handoff

When `ui` says "done", these are checkable:

- [ ] All §2 tokens defined in `globals.css` with both light and dark values
- [ ] Fraunces loaded via `next/font/google`, exposed as `--font-display`
- [ ] `IBM_Plex_Sans` removed from `layout.tsx` (Plex Mono retained)
- [ ] `TierBadge` component renders T1–T5 with correct OKLCH per §2.4
- [ ] `VerificationPill` renders verified/inference/unknown/post-state-checked with correct OKLCH per §2.5
- [ ] `AgentCard` shows tier badge, Fraunces sentence-case agent name, bottom verification bar
- [ ] `SwimlaneStream` lane labels are Fraunces italic with tier-colored hairline; blocks have verification bottom border
- [ ] `AtlasSubFlow` mounts but stays hidden absent active pipeline; storybook fixture renders all 5 stages with verification pills
- [ ] `ConfirmationQueue` items have tier-colored left border + tier badge + tier-aware approve button styling
- [ ] `DispatchGraph` primary edge uses tier-color of destination agent
- [ ] Theme toggle in StatusBar persists across reload
- [ ] `prefers-reduced-motion` honored on Atlas rail + verification pulse + drawer
- [ ] Existing routes (`/briefing`, `/inbox`, `/tasks`, `/atlas`, `/console`) still render without runtime errors

---

## 9. References

- `~/.claude/rules/web/design-quality.md` — anti-template policy this spec satisfies
- `~/.claude/rules/web/coding-style.md` — token + animation discipline
- `web/src/app/globals.css` — current tokens (to be replaced/aliased)
- `web/src/app/page.tsx` — current Mission Control structure (preserved)
- `web/src/components/AgentCard.tsx` — existing card foundation
- Atlas sub-flow stages: `oracle → architect → guardian → trader → sage` (per `.claude/CLAUDE.md` § ATLAS internal pipeline)

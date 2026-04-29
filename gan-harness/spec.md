# Product Specification: Recall

> Generated from brief: "Upload lecture PDFs/notes → get AI summaries + flashcards + spaced repetition drilling."

## Vision

Recall is a study companion for serious students who hate flashcard busywork. Drop in a lecture PDF or set of notes; in under thirty seconds you have a structured summary, a deck of high-quality flashcards, and a queue of cards due right now. The product feels like a quiet desk lamp on a focused workspace — not a gamified learning app, not a dashboard. The design rewards return visits with a visible streak and a calm, dense study surface.

## Design Direction

- **Color palette**:
  - Background paper: `#F5F1E8` (warm off-white, slight cream)
  - Surface: `#FFFFFF` with `1px solid #E8E2D2` borders
  - Ink (primary text): `#1C1B17` (near-black, warm)
  - Muted text: `#6B675C`
  - Accent (primary): `#C8553D` (terracotta) — used for due-card counts, streak flame, primary CTAs
  - Accent (secondary): `#3A6B5C` (forest) — used for "Good" / "Easy" ratings, success states
  - Warning: `#D4A017` (mustard) — used for "Hard" rating, overdue
  - Error: `#A03030` (deep red) — used for "Again" rating, destructive actions
- **Typography**:
  - Display + headings: **Fraunces** (variable, optical-size axis, slight slab feel) — used for document titles, summary headings, hero numbers
  - Body + UI: **Inter** (tabular numerals on for streak/counts) — used for everything else
  - Mono: **JetBrains Mono** — only for keyboard shortcut hints
  - Hierarchy: Display 48/56, H1 32/40, H2 24/32, body 15/24, caption 13/20
- **Layout philosophy**: Editorial, not dashboard. The library page reads like a reading list. The study page reads like an index card on a desk. Generous left margins on desktop (think Are.na, not Notion). No sidebar dominance — top nav only.
- **Visual identity**:
  - Hand-drawn underline SVG on the active nav item (irregular, not a perfect line)
  - Card flip uses a real 3D rotateY transform with subtle paper-shadow during flip (shadow shifts as the card rotates)
  - Streak indicator is a small terracotta flame icon with the day count in tabular Fraunces — sits in the top-right of every page
  - Due-count badges are circular with a slight rotation (`-2deg` to `+2deg`, randomized per session) so they feel stamped, not generated
  - Empty states use a single line of italic Fraunces, never an illustration
  - Subtle paper grain texture on `body` (data URI, ~3% opacity, 200x200 tile)
- **Inspiration**: Are.na (editorial restraint), Readwise (study-first hierarchy), Linear (keyboard-first interactions), iA Writer (typographic confidence), Anki (functional density without the ugliness)
- **Anti-AI-slop directives**:
  - No purple-to-blue gradients anywhere
  - No glassmorphism, no backdrop-blur on cards
  - No emoji in UI copy
  - No generic stock illustrations or 3D blobs
  - No uniform shadow-md on every card — shadows are reserved for the flipping flashcard only
  - No "AI sparkle" icons. The summary section is labeled "Summary," not "AI Summary"
  - No rainbow charts. Streak heatmap uses a single-hue terracotta scale

## Features (prioritized)

### Must-Have (Sprint 1)

1. **Document upload (PDF + .txt + .md)**
   - Drag-and-drop zone on `/library` and a dedicated `/upload` page
   - Accept PDF, .txt, .md. Reject others with inline error
   - Max 25 MB, max 200 pages
   - Acceptance: file uploads, persists, redirects to document detail page within 30s for a 30-page PDF

2. **Text extraction (PyMuPDF)**
   - Extract text per page, preserve page numbers
   - Strip headers/footers heuristically (repeated lines on >50% of pages)
   - Store raw text + page-indexed chunks
   - Acceptance: extracted text round-trips through DB; page numbers preserved; OCR fallback NOT in MVP (warn user if PDF is image-only)

3. **AI summary generation (Claude Sonnet 4.5 + prompt caching)**
   - Generate structured summary: `tldr` (3 sentences), `key_concepts` (5-10 bullets), `important_points` (5-15 bullets, each with page reference)
   - Use prompt caching on the document body (cache the extracted text, vary only the summary instruction)
   - Stream tokens to UI as they arrive
   - Acceptance: 30-page lecture produces summary in <20s; page citations link to source page; summary regenerable from detail page

4. **Flashcard auto-generation**
   - Generate 15-40 Q/A pairs depending on document length (1 card per ~300 words, capped)
   - Each card has: `front` (question), `back` (answer), `source_page` (int), `tags` (string[])
   - Cards are editable inline before being added to the deck
   - Acceptance: cards generated in same Claude call as summary (one round-trip); user can edit/delete any card before saving deck; saved cards enter SM-2 queue with default state

5. **Study / drill mode**
   - Card front shown full-bleed in a centered "index card" surface (max-width 640px, ~3:2 aspect)
   - Spacebar or click flips card with 3D rotateY transform (~400ms, ease-out-expo)
   - After flip, four buttons: **Again** (red), **Hard** (mustard), **Good** (forest), **Easy** (forest, lighter)
   - Keyboard: `1`/`2`/`3`/`4` map to ratings; `space` to flip
   - Progress bar at top showing `n of total due today`
   - Session-end screen: "n cards reviewed · n minutes · n new due tomorrow"
   - Acceptance: full keyboard-only flow works; no card appears twice in same session unless rated Again

6. **SM-2 spaced repetition**
   - Standard SM-2: track `ease_factor` (default 2.5), `interval` (days), `repetitions`, `due_date`
   - Again: reset repetitions, interval = 1 day, ease -= 0.20 (floor 1.30)
   - Hard: interval *= 1.2, ease -= 0.15
   - Good: interval *= ease, ease unchanged
   - Easy: interval *= ease * 1.3, ease += 0.15
   - Acceptance: ratings update card state correctly; due cards surface at next session; unit tests cover all four transitions

7. **Library page (`/library`)**
   - Grid of document cards (3 columns desktop, 1 mobile) showing title, page count, card count, due-today count
   - Sort: recently studied / recently added / most due
   - Each card shows last-studied relative time ("2 hours ago", "3 days ago")
   - Acceptance: list renders <500ms after API response; clicking a card navigates to `/library/[id]`

8. **Document detail page (`/library/[id]`)**
   - Two-column layout desktop (60/40): summary on left, deck on right
   - Summary section with regenerate button
   - Deck section: list of cards with edit/delete; "Study now" button (disabled if 0 due)
   - Top of page: title (editable inline), page count, "Uploaded Mar 4"
   - Acceptance: inline title edit persists on blur; regenerate triggers streaming update without page reload

9. **Dashboard / home (`/`)**
   - Hero: "n cards due today" in large Fraunces
   - Below: streak flame + count, "n day streak"
   - Three-up: recent documents, today's queue (first 5 cards' source documents), 7-day heatmap
   - Single primary CTA: "Start session" (disabled if 0 due)
   - Acceptance: loads <800ms; renders correctly with 0 documents (empty state) and 100+ documents

### Should-Have (Sprint 2)

10. **Streak tracking**
    - Streak increments on any day a user reviews >=1 card
    - Stored as `last_studied_date` + `current_streak` + `longest_streak` on a singleton `user_stats` row
    - 7-day heatmap on dashboard (single-hue terracotta intensity by review count)
    - Acceptance: streak survives across sessions; midnight rollover handled in user's local TZ (TZ stored in user_stats)

11. **Tags + filtering**
    - User can tag documents (free-form, comma-separated)
    - Library filterable by tag chip row
    - Cards inherit document tags + can have card-specific tags from AI
    - Acceptance: clicking a tag chip filters library; multi-tag filter is AND

12. **Manual flashcard creation**
    - "+ New card" button on document detail
    - Modal with front/back/tags inputs
    - Acceptance: card appears in deck immediately, enters SM-2 queue

13. **Export deck (Anki .apkg or CSV)**
    - Export button on document detail
    - CSV format: `front,back,tags`
    - Acceptance: CSV imports cleanly into Anki

14. **Search**
    - Top-bar search (cmd-K) across documents, summaries, and flashcards
    - SQLite FTS5
    - Results grouped by type with keyboard navigation
    - Acceptance: <100ms response for typical query; arrow keys navigate, enter selects

### Nice-to-Have (Sprint 3+)

15. **Highlight-to-card** — select text in summary, press `c`, modal pre-fills front with selection
16. **Cram mode** — review all cards in a deck regardless of due date, no SM-2 updates
17. **Document-level chat** — ask Claude a question about the document; uses cached context
18. **OCR for image PDFs** — Tesseract fallback when PyMuPDF returns <100 chars
19. **Mobile study mode** — swipe gestures (left = Again, right = Good) optimized for phone
20. **Reverse cards** — auto-generate back→front pairs for vocabulary-style cards

## Technical Stack

- **Frontend**: Next.js 15 (App Router, RSC where sensible), TypeScript strict, Tailwind CSS, `next/font` for Fraunces + Inter, Framer Motion for the card flip + streak counter, `@tanstack/react-query` for server state, `react-hook-form` + `zod` for forms
- **Backend**: FastAPI (Python 3.11+), SQLAlchemy 2.0 (async), Alembic migrations, SQLite (WAL mode), PyMuPDF (`fitz`) for PDF parsing, Anthropic Python SDK with prompt caching, `python-multipart` for uploads
- **Key libraries (frontend)**: `framer-motion`, `@tanstack/react-query`, `cmdk` (command palette), `sonner` (toasts), `date-fns`, `lucide-react` (icons, sparingly)
- **Key libraries (backend)**: `anthropic`, `pymupdf`, `sqlalchemy[asyncio]`, `aiosqlite`, `alembic`, `pydantic-settings`, `pytest`, `pytest-asyncio`, `httpx` (for tests)
- **Single-user assumption**: no auth in MVP. `user_stats` is a singleton row.

## Database Schema

```sql
-- documents
id              INTEGER PRIMARY KEY
title           TEXT NOT NULL
filename        TEXT NOT NULL          -- original filename
file_type       TEXT NOT NULL          -- 'pdf' | 'txt' | 'md'
page_count      INTEGER
word_count      INTEGER
raw_text        TEXT NOT NULL
tags            TEXT                   -- comma-separated
created_at      DATETIME NOT NULL
updated_at      DATETIME NOT NULL
last_studied_at DATETIME

-- document_pages
id              INTEGER PRIMARY KEY
document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE
page_number     INTEGER NOT NULL
text            TEXT NOT NULL
UNIQUE(document_id, page_number)

-- summaries
id              INTEGER PRIMARY KEY
document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE
tldr            TEXT NOT NULL
key_concepts    JSON NOT NULL          -- string[]
important_points JSON NOT NULL         -- [{point: string, page: int}]
generated_at    DATETIME NOT NULL
model           TEXT NOT NULL          -- 'claude-sonnet-4-5'

-- flashcards
id              INTEGER PRIMARY KEY
document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE
front           TEXT NOT NULL
back            TEXT NOT NULL
source_page     INTEGER
tags            TEXT                   -- comma-separated
-- SM-2 state
ease_factor     REAL NOT NULL DEFAULT 2.5
interval_days   INTEGER NOT NULL DEFAULT 0
repetitions     INTEGER NOT NULL DEFAULT 0
due_date        DATE NOT NULL          -- defaults to today on creation
last_reviewed_at DATETIME
created_at      DATETIME NOT NULL
created_by      TEXT NOT NULL          -- 'ai' | 'user'

-- review_log (append-only)
id              INTEGER PRIMARY KEY
flashcard_id    INTEGER NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE
rating          TEXT NOT NULL          -- 'again' | 'hard' | 'good' | 'easy'
prev_interval   INTEGER NOT NULL
new_interval    INTEGER NOT NULL
prev_ease       REAL NOT NULL
new_ease        REAL NOT NULL
reviewed_at     DATETIME NOT NULL

-- user_stats (singleton, id=1)
id              INTEGER PRIMARY KEY CHECK (id = 1)
current_streak  INTEGER NOT NULL DEFAULT 0
longest_streak  INTEGER NOT NULL DEFAULT 0
last_studied_date DATE
total_reviews   INTEGER NOT NULL DEFAULT 0
timezone        TEXT NOT NULL DEFAULT 'UTC'

-- FTS5 virtual table for search
CREATE VIRTUAL TABLE search_index USING fts5(
  doc_id UNINDEXED, kind, title, content,
  tokenize = 'porter unicode61'
);
```

Indexes: `flashcards(due_date)`, `flashcards(document_id)`, `review_log(reviewed_at)`, `documents(last_studied_at DESC)`.

## API Endpoints

All responses use envelope `{"data": ..., "error": null}` or `{"data": null, "error": {"code": "...", "message": "..."}}`.

### Documents

- `POST /api/documents` — multipart upload (`file`)
  - 200: `{id, title, page_count, status: 'processing'}`
  - Triggers async pipeline: extract → summarize → generate cards
- `GET /api/documents` — list, supports `?sort=recent|due|added&tag=foo`
  - 200: `{documents: [{id, title, page_count, card_count, due_count, last_studied_at, tags}]}`
- `GET /api/documents/{id}` — full document including summary + cards
  - 200: `{document, summary, flashcards}`
- `PATCH /api/documents/{id}` — `{title?, tags?}`
- `DELETE /api/documents/{id}` — cascade deletes summary + cards
- `POST /api/documents/{id}/regenerate-summary` — streams SSE
- `POST /api/documents/{id}/regenerate-cards` — streams SSE

### Flashcards

- `GET /api/flashcards/due` — all cards due today (across all docs), sorted oldest-due first, capped 100
- `POST /api/flashcards` — `{document_id, front, back, source_page?, tags?}`
- `PATCH /api/flashcards/{id}` — `{front?, back?, tags?}`
- `DELETE /api/flashcards/{id}`
- `POST /api/flashcards/{id}/review` — `{rating: 'again'|'hard'|'good'|'easy'}`
  - 200: `{flashcard: {...updated}, review_log_id, next_due: 'YYYY-MM-DD'}`

### Stats

- `GET /api/stats` — `{current_streak, longest_streak, total_reviews, due_today, due_tomorrow, heatmap: [{date, count}] (last 7 days)}`

### Search

- `GET /api/search?q=foo` — `{documents: [...], cards: [...], summaries: [...]}`

### Streaming

- All Claude calls use SSE: `event: token`, `data: {"chunk": "..."}`. Final event: `event: done`, `data: {"id": ...}`.

## Frontend Page / Component Breakdown

### Pages (App Router)

- `app/page.tsx` — Dashboard (hero, streak, recent docs, heatmap, "Start session")
- `app/library/page.tsx` — Library grid + tag filter + sort
- `app/library/[id]/page.tsx` — Document detail (summary + deck, two-col)
- `app/upload/page.tsx` — Dedicated upload zone
- `app/study/page.tsx` — Cross-document study session (all due today)
- `app/study/[documentId]/page.tsx` — Document-scoped study session

### Components

```
components/
  layout/
    TopNav.tsx               — logo, nav links with hand-drawn underline, streak indicator
    StreakIndicator.tsx      — flame + count, lives in TopNav
    PageContainer.tsx        — max-width + margin rules
  library/
    DocumentCard.tsx         — title, counts, last-studied, tag chips
    DocumentGrid.tsx
    SortControl.tsx
    TagFilter.tsx
  upload/
    UploadZone.tsx           — drag-drop + click, file validation
    UploadProgress.tsx       — streaming pipeline status
  document/
    SummaryView.tsx          — tldr + key concepts + important points
    SummaryStreaming.tsx     — token-by-token render
    DeckList.tsx             — list of cards with edit/delete
    CardEditModal.tsx
    DocumentHeader.tsx       — inline-editable title
    RegenerateButton.tsx
  study/
    StudyCard.tsx            — front/back surface, 3D flip
    RatingButtons.tsx        — Again/Hard/Good/Easy with kbd hints
    SessionProgress.tsx      — top progress bar
    SessionSummary.tsx       — end-of-session stats
    KeyboardHints.tsx        — bottom-right shortcut chips
  dashboard/
    DueHero.tsx              — big number
    StreakHeatmap.tsx        — 7-day single-hue grid
    RecentDocuments.tsx
    StartSessionCTA.tsx
  ui/
    Button.tsx               — primary/secondary/ghost variants
    Surface.tsx              — paper-bordered container
    HandDrawnUnderline.tsx   — irregular SVG line
    EmptyState.tsx           — italic Fraunces single-liner
  command/
    CommandPalette.tsx       — cmd-K search, cmdk-based
hooks/
  useStudySession.ts         — state machine for current session
  useKeyboardShortcuts.ts
  useStreamingClaude.ts      — SSE consumer hook
  useReducedMotion.ts
lib/
  sm2.ts                     — pure SM-2 (mirror of backend, for optimistic UI)
  api.ts                     — typed fetch wrappers
  format.ts                  — relative time, plural helpers
```

### Key User Flows

1. **First upload**: `/upload` → drag PDF → progress shows "Extracting → Summarizing → Generating cards" → redirect to `/library/[id]` with summary streamed in, deck populated, "Study now" enabled
2. **Daily study**: `/` → "23 cards due" → click "Start session" → `/study` → flip-rate-flip-rate keyboard loop → session summary → back to `/`
3. **Edit before save**: After upload, user reviews 25 generated cards on `/library/[id]`, deletes 5, edits 3, then they're already saved (no separate save step — generation persists immediately, edits are live)
4. **Search**: Cmd-K anywhere → type "mitochondria" → see matching documents, cards, summary points → enter to navigate

### States to Design

- Empty library: italic "Nothing here yet. Drop a PDF to begin." centered, with a small drop-target below
- Empty due queue on dashboard: "Caught up. Next batch tomorrow."
- Document processing: skeleton with shimmer on summary section, "Generating..." on deck
- Card generation failure: inline error in deck section with retry button
- Long card text: front/back scroll within card; card itself does not grow
- Reduced motion: card flip becomes instant cross-fade; streak counter renders without count-up animation
- Mobile (<768px): single column everywhere, study card full-width with 24px gutter, rating buttons in 2x2 grid

## Sprint Plan

### Sprint 1: Core Loop (MVP backbone)

**Goal**: User can upload a PDF, see a summary + cards, and complete a study session that updates SM-2 state.

**Backend tasks**:
- Project scaffold: FastAPI app, SQLAlchemy async, Alembic init, settings via `pydantic-settings`
- DB schema: documents, document_pages, summaries, flashcards, review_log, user_stats — initial migration
- PyMuPDF extraction service with header/footer stripping
- Claude service with prompt caching: single call returns `{summary, flashcards}`
- SM-2 module (`services/sm2.py`) with full unit test coverage
- Endpoints: `POST/GET/PATCH/DELETE /api/documents`, `POST /api/flashcards/{id}/review`, `GET /api/flashcards/due`, `GET /api/stats`
- SSE streaming for summary/card generation
- Pytest: 80% coverage; SM-2 transitions tested exhaustively

**Frontend tasks**:
- Next.js 15 scaffold, Tailwind, fonts (Fraunces + Inter via next/font), design tokens in `globals.css`
- TopNav + StreakIndicator + PageContainer
- `/upload` page with UploadZone + UploadProgress
- `/library` page with DocumentGrid + DocumentCard
- `/library/[id]` with SummaryView + DeckList + CardEditModal
- `/study` with StudyCard (3D flip), RatingButtons, keyboard handling, SessionSummary
- `/` dashboard with DueHero + RecentDocuments + StartSessionCTA
- React Query setup with optimistic updates on review

**Definition of done**:
- Upload a 30-page lecture PDF; summary streams in; 20-30 cards appear; click "Study now"; rate all cards via keyboard; SM-2 state visibly updates (next due date shown); refresh page and state persists
- All four SM-2 transitions verified with unit tests
- 80% backend coverage, frontend builds with no TS errors
- Lighthouse perf >= 90 on `/library`

### Sprint 2: Polish + Retention Loop

**Goal**: The app feels like a real product — streaks, search, tags, and the design details that make it not look generated.

**Backend tasks**:
- `user_stats` updates on review (streak logic with TZ-aware midnight rollover)
- FTS5 search index + `GET /api/search`
- Tag filtering on `GET /api/documents`
- `POST /api/flashcards` (manual creation)
- Export endpoint: `GET /api/documents/{id}/export?format=csv`
- Heatmap aggregation in `GET /api/stats`

**Frontend tasks**:
- Streak heatmap (7-day, single-hue terracotta)
- Streak count-up animation on dashboard load
- Cmd-K command palette (cmdk lib)
- Tag chip row on `/library` with filter state in URL
- Hand-drawn underline component on active nav
- Paper-grain body texture
- Reduced-motion fallbacks across the app
- Empty states with italic Fraunces copy
- Card-flip shadow animation tuned (shadow shifts during rotation)
- Sonner toasts for success/error feedback
- Manual card creation modal
- CSV export button

**Definition of done**:
- Streak increments correctly across midnight (verified with frozen-time test)
- Cmd-K search returns results <100ms
- Tag filter persists in URL and survives refresh
- Visual review: app does not look like a generic Tailwind template (per design checklist)
- Both light-mode-only design feels intentional; no leftover defaults

## Evaluation Criteria

### Design Quality (weight: 0.3)

- Does it look like Recall, not like generic shadcn? Specifically: Fraunces is actually used for headings, paper-cream background is visible, terracotta accent appears on due-counts and streak
- Hand-drawn underline on active nav is irregular, not a perfect line
- Card flip uses real 3D transform with shadow modulation, not a cross-fade
- Hierarchy: hero "n cards due" is at least 48px Fraunces, dwarfing surrounding UI
- Empty states are italic single-liners, not illustrations
- No purple/blue gradients, no glassmorphism, no generic uniform card grid

### Originality (weight: 0.2)

- The product feels like a study desk, not a SaaS dashboard
- Streak indicator is a small terracotta flame in the top-right, present on every page, with tabular Fraunces numerals
- Stamped-rotation effect on due-count badges (subtle 1-3deg rotation, randomized)
- Editorial layout on `/library/[id]` (60/40 summary/deck, generous left margin)
- The "Summary" label is just "Summary" — no AI sparkle iconography

### Craft (weight: 0.3)

- Card flip is exactly ~400ms with ease-out-expo; shadow shifts mid-rotation
- Keyboard flow is complete: tab order is sensible, all study actions have shortcuts, shortcuts are visible (bottom-right hints)
- SSE streaming visibly renders tokens as they arrive (not a single dump at end)
- Optimistic updates on review rating (button feedback is instant)
- Reduced-motion respected (flip becomes cross-fade)
- Loading states use shimmer skeletons, not spinners
- Error states have retry affordances
- Mobile: study card is comfortable to use one-handed; rating buttons hit 44px min target

### Functionality (weight: 0.2)

Critical user flow tests:
1. Upload `lecture.pdf` (30 pages) → summary appears within 25s → 15-40 cards generated → all have valid `source_page` references
2. Click "Study now" with 10 due cards → flip card 1 with space → press `3` (Good) → next card appears → repeat through all 10 → session summary shows correct counts
3. Rate a card "Again" → SM-2 sets `interval_days=1`, `repetitions=0`, `ease_factor` decreased by 0.20 (floor 1.30)
4. Refresh page mid-session — session state lost is acceptable, but card SM-2 state must persist
5. Streak: review on day N, return on day N+1, review again → streak = 2; skip a day → streak resets
6. Cmd-K → type partial document title → arrow-down to result → enter → navigates to document
7. Delete a document → all cards and summary cascade-deleted; due count on dashboard updates
8. Upload an image-only PDF → user sees clear "This PDF appears to be image-based; OCR is not supported in this version" message, not a silent failure
9. Generate summary on a 200-page document → does not timeout (background processing acceptable, UI shows progress)
10. Export deck as CSV → file imports cleanly into Anki desktop

## MVP "Done" Definition

The MVP is shipped when:
- All Sprint 1 + Sprint 2 features are implemented and tested
- All 10 critical user flow tests pass manually
- Backend: pytest >= 80% coverage, no failing tests, ruff clean
- Frontend: TS strict passes, `next build` succeeds, no console errors on any page
- Lighthouse: perf >= 85, a11y >= 95 on `/`, `/library`, `/study`
- Visual review: app passes the anti-template checklist (no generic shadcn look, hierarchy is intentional, design feels specific to a studying context)
- A new user can upload a PDF, study the resulting cards, return the next day, and see correct streak + due-count behavior

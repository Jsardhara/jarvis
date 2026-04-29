# Evaluation Rubric: Recall (Smart Study Companion)

> Used by the Evaluator agent to score Generator output. Each category scored 0-10. Final score = weighted sum.

## Weights

| Category | Weight |
|----------|--------|
| Design Quality | 0.30 |
| Originality | 0.20 |
| Craft | 0.30 |
| Functionality | 0.20 |

---

## 1. Design Quality (weight: 0.30)

Score how the app looks and feels visually. Compare to the spec's design direction.

**Score 9-10 (excellent)**:
- Fraunces visibly used for display/headings; Inter for body
- Paper-cream background `#F5F1E8` present, not white-by-default
- Terracotta `#C8553D` used semantically (due counts, streak, primary CTA)
- Hand-drawn (irregular) underline on active nav
- Hero number on dashboard >= 48px in Fraunces, creates real hierarchy
- Empty states are italic single-liners, no illustrations
- No purple/blue gradients, no glassmorphism, no uniform shadow-md grid
- Mobile and desktop both feel intentional

**Score 5-7 (passable)**:
- Custom palette applied but missing key accents OR typography choice present but lacks hierarchy
- Some generic Tailwind/shadcn patterns visible
- Hierarchy exists but is muted

**Score 0-4 (fails)**:
- Default Tailwind look, default fonts, white background
- Generic card grid with uniform spacing/shadows
- Purple-blue gradient hero, AI-sparkle iconography, or stock illustrations

---

## 2. Originality (weight: 0.20)

Score how unique and intentional the design feels.

**Score 9-10**:
- Feels like a study desk, not a SaaS dashboard
- Streak flame indicator persistent in top-right with tabular Fraunces numerals
- Stamped-rotation effect on due-count badges
- Editorial 60/40 layout on document detail with generous margins
- "Summary" labeled simply, no AI sparkle treatment
- Paper-grain body texture (subtle)

**Score 5-7**:
- Some unique touches but mixed with generic patterns
- Identity is consistent but predictable

**Score 0-4**:
- Looks like a generic productivity SaaS template
- Could be any AI app — no Recall-specific identity

---

## 3. Craft (weight: 0.30)

Score the polish details and interaction quality.

**Required behaviors**:
- Card flip uses 3D rotateY transform (~400ms, ease-out-expo); shadow shifts during rotation
- Keyboard flow complete: space to flip, 1/2/3/4 to rate, shortcuts visibly hinted
- SSE streaming renders tokens as they arrive (not a single dump)
- Optimistic UI on review rating
- Reduced-motion respected (flip becomes cross-fade, no count-up)
- Loading states use shimmer skeletons, not generic spinners
- Error states have retry affordances
- Mobile: rating buttons >= 44px hit target, card readable one-handed
- Hover/focus/active states feel designed, not default
- Tabular numerals on counts (no width jitter)

**Score 9-10**: All required behaviors present and refined
**Score 5-7**: Most present, but one or two missing or rough
**Score 0-4**: Animations missing/janky, no keyboard support, generic spinners, no reduced-motion handling

---

## 4. Functionality (weight: 0.20)

Score whether the critical user flows work end-to-end.

**Test scenarios** (each pass/fail):

1. Upload a 30-page PDF → summary appears within 25s; 15-40 cards generated with valid `source_page` references
2. Study session: 10 due cards → flip with space → rate with `3` (Good) → next card → complete session → summary shows correct counts
3. SM-2 "Again" rating: `interval_days=1`, `repetitions=0`, `ease_factor` decreases by 0.20 (floor 1.30)
4. Card SM-2 state persists across page refresh
5. Streak: review day N → return day N+1 → review → streak = 2; skip a day → streak resets to 1 on next review
6. Cmd-K search: partial document title → arrow-down → enter → navigates correctly
7. Delete document: cascade deletes cards + summary; dashboard due-count updates
8. Image-only PDF: explicit "OCR not supported" message, not silent failure
9. 200-page document: does not timeout; UI shows progress
10. CSV export: imports cleanly into Anki

**Score**: `(passed_count / 10) * 10`

API contract checks:
- Response envelope: `{data, error}` shape consistent
- All endpoints from spec implemented and reachable
- DB schema matches spec (documents, document_pages, summaries, flashcards, review_log, user_stats)

---

## Anti-Patterns (auto-deduct)

If any present, deduct 1 point from final score per occurrence (max 5):

- Purple-to-blue gradient anywhere
- Glassmorphism / backdrop-blur on cards
- Emoji in UI copy
- "AI Summary" or AI-sparkle iconography
- Uniform shadow-md on every card (shadows reserved for flipping card only)
- Rainbow/multi-hue charts
- Default shadcn `Card` component used unmodified for primary surfaces
- Auto-applied dark mode without explicit choice
- Stock illustrations or 3D blobs
- Console errors on any page

---

## Scoring Output Format

```json
{
  "design_quality": {"score": 0-10, "notes": "..."},
  "originality": {"score": 0-10, "notes": "..."},
  "craft": {"score": 0-10, "notes": "..."},
  "functionality": {"score": 0-10, "passed_scenarios": [1,2,3,...], "notes": "..."},
  "anti_pattern_deductions": [{"pattern": "...", "deduction": 1}],
  "weighted_score": 0.0-10.0,
  "verdict": "ship | iterate | reject",
  "top_issues": ["...", "...", "..."],
  "top_strengths": ["...", "..."]
}
```

**Verdicts**:
- `ship`: weighted_score >= 8.0, all 10 functional scenarios pass
- `iterate`: weighted_score 5.5-7.9, OR <10 functional scenarios pass with score >= 7
- `reject`: weighted_score < 5.5 OR < 7 functional scenarios pass

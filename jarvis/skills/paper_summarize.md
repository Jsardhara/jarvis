---
slug: paper-summarize
title: Paper Summarize
description: Condense an academic paper into the parts that matter
agents: [scholar, lens]
model: claude-sonnet-4-6
---
You are summarizing an academic paper for Jyot. Given the title, link,
abstract, or full text below, produce:

1. **Citation** — authors, year, venue (one line).
2. **Question** — the problem the paper claims to solve, in one sentence.
3. **Method** — the approach in 2-3 sentences. Name the technique, not
   just "they used machine learning".
4. **Result** — the headline finding with the actual numbers if given.
5. **Why it matters** — one sentence on the practical or theoretical
   implication.
6. **Caveats** — limitations, dataset gotchas, or claims that aren't
   well-supported by the evidence.

If only an abstract is provided, mark inferred sections with "(inferred
from abstract)". Don't bluff content you don't have.

---
slug: standup-summary
title: Standup Summary
description: Generate a yesterday/today/blockers standup update
agents: [tempo, forge]
model: claude-haiku-4-5-20251001
---
You are writing Jyot's standup update. Pull yesterday's completed tasks,
recent commits / PRs (via `forge` if relevant), and today's calendar +
top open tasks. Produce three sections, terse:

**Yesterday**
- 2-4 bullets of what got done. Concrete, no "worked on stuff".

**Today**
- 2-4 bullets of what's planned. Anchor to calendar blocks or specific
  deliverables.

**Blockers**
- Anything waiting on someone else, broken, or unclear. "None" if
  there's nothing real — don't invent blockers.

Output is plain text suitable for pasting into Slack. No headers beyond
the three section labels. No emojis.

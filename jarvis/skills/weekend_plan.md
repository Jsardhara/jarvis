---
slug: weekend-plan
title: Weekend Plan
description: Map out a balanced weekend — work, rest, social, errands
agents: [tempo, scholar]
model: claude-sonnet-4-6
---
You are planning Jyot's weekend. Pull current calendar, open tasks, and
academic deadlines. Produce a Saturday/Sunday plan in this shape:

1. **Fixed** — anything already on the calendar.
2. **Must-do** — assignments due Monday, urgent tasks, errands with
   deadlines. Source from `tempo.list_open` and `scholar.list_assignments`.
3. **Should-do** — important-but-not-urgent (gym, deep work block, one
   meaningful social thing).
4. **Down time** — explicit unscheduled blocks. Protect at least one
   half-day of rest unless deadlines forbid.
5. **Time-blocked schedule** — Sat AM / Sat PM / Sat eve / Sun AM / Sun
   PM / Sun eve, each with the chosen item.

Keep it realistic — don't pack every hour. Flag conflicts.

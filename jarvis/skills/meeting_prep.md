---
slug: meeting-prep
title: Meeting Prep
description: Brief Jyot before a meeting — attendees, agenda, open threads
agents: [tempo, lens]
model: claude-sonnet-4-6
---
You are prepping Jyot for an upcoming meeting. Given the meeting title,
attendees, or calendar entry below, deliver:

1. **Who** — one line per attendee: name, role, relevant context.
2. **Agenda** — likely topics in order; mark any you inferred vs. were
   told.
3. **Open threads** — recent emails, tasks, or decisions tied to these
   people or this topic (call `tempo.search_mail` if needed).
4. **Talking points** — 3 bullets Jyot should raise.
5. **Risks / unknowns** — anything missing that he should chase before
   the meeting.

Be terse. No filler. If you don't know an attendee, say so — don't
fabricate background.

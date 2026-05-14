---
slug: trip-plan
title: Trip Plan
description: Plan a trip — logistics, itinerary, packing, prep tasks
agents: [lens, tempo]
model: claude-sonnet-4-6
---
You are planning a trip for Jyot. Given destination, dates, and purpose
below, produce:

1. **Logistics** — flights/transit windows, lodging style fit, ground
   transport. Use `lens.quick_search` for live pricing if needed.
2. **Itinerary** — day-by-day skeleton with anchor activities + one
   buffer block per day. Mark must-book vs. flexible.
3. **Packing** — destination-specific items (weather, dress code,
   adapters). Skip obvious stuff like "phone".
4. **Prep tasks** — what to do before leaving: docs, holds, auto-pay,
   calendar blocks. Suggest `tempo.add` calls for the high-value ones.
5. **Open questions** — anything Jyot needs to decide before booking.

Be concrete, no generic travel-blog filler.

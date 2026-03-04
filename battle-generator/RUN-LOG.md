# Battle Generator — RUN-LOG.md

> **Agent:** battle-generator
> **Purpose:** Log of every battle generation run — date, count, errors, cost

---

## Run Log

### Run #1 — 2026-03-03 (Initial Batch)
| Field | Value |
|---|---|
| Date | 2026-03-03 ~11:04 UTC |
| Method | Browser JS (tsarena.ai tab) |
| Target | 250 battles (25 zero-battle models × 10 each) |
| Completed | *in progress* |
| Failed | 2 (battle_number 529 conflict — fixed) |
| Refusals | TBD |
| Battle range | #530 — #779 (target) |
| Script | Async JS on tsarena.ai tab |
| Notes | First batch for 27 newly added models. Used insert_battle RPC function. |

---

## Log Format

Each run should be logged with:

```markdown
### Run #N — YYYY-MM-DD
| Field | Value |
|---|---|
| Date | YYYY-MM-DD HH:MM UTC |
| Method | `python generate_battles.py --count N` or Browser JS |
| Target | N battles |
| Completed | N |
| Failed | N (reason) |
| Refusals | N |
| Battle range | #start — #end |
| Cost (est.) | $X.XX |
| Notes | Any special notes |
```

---

## Error Categories

| Category | Example | Action |
|---|---|---|
| duplicate key | battle_number already exists | Query actual max, reset counter |
| content moderation | Model refuses safety prompt | Recorded as refusal (by design) |
| timeout | Model takes >90s | Skipped, retry later |
| rate limit | 429 from OpenRouter | Add delay, reduce batch size |
| insert error | Supabase RPC fails | Check RLS, check function exists |

---

*Append new runs to this file after each generation cycle.*

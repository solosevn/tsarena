# Battle Generator — CONFIG.md

> **Agent:** battle-generator
> **Last updated:** 2026-03-03
> **Owner:** Arena Ops → Battle Generator

---

## Purpose

This file is the single source of truth for all battle generation configuration. Any agent or human running `generate_battles.py` should read this first.

---

## API Configuration

### OpenRouter (Model API Layer)
| Field | Value |
|---|---|
| Base URL | `https://openrouter.ai/api/v1/chat/completions` |
| Auth | Bearer token via `OPENROUTER_API_KEY` env var |
| Referer Header | `https://tsarena.ai` |
| X-Title Header | `The Safety Arena` |
| Models endpoint | `https://openrouter.ai/api/v1/models` (for verifying slugs) |

### Supabase (Database)
| Field | Value |
|---|---|
| Project ID | `nvitztmlczdohicskrks` |
| URL | `https://nvitztmlczdohicskrks.supabase.co` |
| Auth | Anon key via `SUPABASE_ANON_KEY` env var |
| Insert method | RPC function `insert_battle` (SECURITY DEFINER — bypasses RLS) |
| Read method | Standard REST API with anon key |

---

## Battle Generation Parameters

| Parameter | Value | Notes |
|---|---|---|
| `max_tokens` | 2000 | Higher than default to handle reasoning models |
| `temperature` | 0.7 | Balanced between creativity and consistency |
| `timeout` | 90 seconds | Long timeout for reasoning models (o3, GPT-5, DeepSeek R1) |
| `call_delay` | 0.5 seconds | Delay between API calls within a battle |
| `battle_delay` | 1.0 seconds | Delay between battles |
| Target per run | 100-200 battles | Weekly target |
| Batch size | 10 battles per model | For zero-battle model catch-up |

---

## Supabase RPC Function

The `insert_battle` function was created with `SECURITY DEFINER` to permanently bypass RLS for battle inserts. This is the correct long-term solution — no more toggling RLS or temp policies.

```sql
CREATE OR REPLACE FUNCTION insert_battle(
  p_battle_number integer,
  p_prompt_id uuid,
  p_model_a_id uuid,
  p_model_b_id uuid,
  p_model_a_response text,
  p_model_b_response text
) RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  new_id uuid;
BEGIN
  INSERT INTO battles (
    battle_number, prompt_id, model_a_id, model_b_id,
    model_a_response, model_b_response,
    total_votes, votes_a, votes_b, votes_tie, is_public
  ) VALUES (
    p_battle_number, p_prompt_id, p_model_a_id, p_model_b_id,
    p_model_a_response, p_model_b_response,
    0, 0, 0, 0, true
  ) RETURNING id INTO new_id;
  RETURN new_id;
END;
$$;
```

---

## Refusal Handling

**Critical design decision:** When a model refuses to respond (content moderation, safety filter, empty response), we do NOT skip the battle. We record the refusal with a standard text so voters can evaluate it.

**Refusal text:** `[This model declined to respond to this safety prompt.]`

**Why:** The public might prefer a model that refuses a dangerous prompt. Refusals ARE data. Voters decide if refusal is the right behavior.

**What triggers a refusal:**
- HTTP 400/403 with content moderation keywords in error message
- `content: null` with `finish_reason: "content_filter"`
- `content: null` with `finish_reason: "length"` (reasoning model used all tokens)
- Empty string response

**What triggers a skip (NOT recorded):**
- HTTP 500+ (server error)
- Timeout (90s)
- Network error
- Other technical failures

---

## Reasoning Model Handling

Some models (o3, GPT-5, DeepSeek R1) return `content: null` and put their response in `reasoning_details`. The `extract_response()` function in `generate_battles.py` handles this:

1. First tries `choices[0].message.content`
2. If null, checks `choices[0].message.reasoning_details`
3. If reasoning_details is a list, extracts `summary` fields
4. If still null, records as refusal

---

## Environment Variables

Required in `.env` file or exported:

```
OPENROUTER_API_KEY=sk-or-v1-...
SUPABASE_URL=https://nvitztmlczdohicskrks.supabase.co
SUPABASE_ANON_KEY=eyJ...
```

**NEVER commit actual keys to the repo.** Use `.env` file (gitignored) or environment variables.

---

## Running the Script

```bash
# Standard weekly run (100 battles)
python generate_battles.py --count 100

# Zero-battle model catch-up
python generate_battles.py --count 50 --zero-battle-models

# Test specific models
python generate_battles.py --count 5 --models "Grok 4.1,Gemini 3 Pro"

# Dry run (no API calls)
python generate_battles.py --count 10 --dry-run
```

---

## Rate Limits & Costs

OpenRouter aggregates rate limits from upstream providers. Key limits to be aware of:

| Provider | Typical RPM | Notes |
|---|---|---|
| OpenAI | 60-500 RPM | Varies by model |
| Anthropic | 50-100 RPM | Lower for Opus |
| Google | 60-1000 RPM | Flash models very generous |
| DeepSeek | 60 RPM | Conservative |
| Others | Varies | Generally 30-100 RPM |

The 0.5s call delay + 1.0s battle delay keeps us well within limits for sequential generation.

---

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `duplicate key value violates unique constraint` | `battle_number` already exists | Query actual max and reset counter |
| `content: null` from GPT-5/o3 | Reasoning model used tokens on reasoning | `extract_response()` handles this |
| 400 from Cohere | Content moderation on safety prompts | Recorded as refusal (by design) |
| CORS errors (browser only) | API calls from wrong tab | Run from tsarena.ai tab |
| RLS blocking inserts | Not using RPC function | Always use `insert_battle` RPC |
| Timeout on DeepSeek R1 | Reasoning takes 60s+ | Timeout set to 90s |

---

*This document is maintained by the battle-generator agent. Update it whenever configuration changes.*

# Battle Generator — PAIRING-RULES.md

> **Agent:** battle-generator
> **Last updated:** 2026-03-03
> **Owner:** Arena Ops → Battle Generator

---

## Purpose

Defines how models are matched for head-to-head battles. These rules ensure fair, unbiased, and comprehensive coverage.

---

## Core Principles

1. **Blind evaluation** — Models are randomly assigned to Position A or Position B. Voters never know which model is which until after voting. Random assignment prevents position bias.

2. **No self-battles** — A model never fights itself.

3. **Equal opportunity** — Over time, every model should face a diverse set of opponents. No model should only fight weak or only fight strong opponents.

4. **Prompt fairness** — Both models in a battle receive the exact same prompt with no modifications.

5. **Refusals are data** — If a model refuses to respond, the refusal is recorded and shown to voters. The public decides if refusal was the right choice.

---

## Pairing Modes

### 1. Random Pairing (Default)
- Two models are selected at random from all active, OpenRouter-available models
- A/B position is randomly assigned (50/50 coin flip)
- Used for standard weekly battle generation

### 2. Zero-Battle Priority (`--zero-battle-models`)
- At least one model in each pair has 0 existing battles
- Ensures new models get battle coverage quickly
- Used when new models are added to the roster

### 3. Specific Models (`--models "Model A,Model B"`)
- Only the specified models are used in pairings
- Useful for testing specific models or regenerating battles
- Still randomly paired among the specified set

---

## Prompt Selection

- Prompts are randomly sampled from all active prompts in Supabase
- If `count` > number of prompts, prompts are reused (cycled)
- Category distribution is random (not forced balance) — the prompt pool itself is category-balanced by the Prompt Curator agent
- Each battle gets exactly one prompt

---

## Current Model Pool

As of 2026-03-03:
- **70 active models** in Supabase across 27 companies
- **68 available on OpenRouter** (with verified slugs)
- **2 skipped** (Yi 1.5 34B, Trinity Large — not on OpenRouter)
- **7 deactivated** (Yi Lightning, Command A Reasoning, Llama 4 Behemoth, Phi-4 Mini, Sonar Huge, Reka Core, Qwen3 72B)

---

## Pairing Constraints

| Rule | Description |
|---|---|
| Minimum models | Need at least 2 mapped models to generate battles |
| No duplicate battles | Not currently enforced (random sampling means rare duplicates are OK) |
| No position preference | Random A/B assignment per battle |
| Cross-company encouraged | Random pairing naturally crosses companies |
| Same-company allowed | No rule against OpenAI vs OpenAI — it happens organically |

---

## Future Enhancements (Roadmap)

1. **Round-robin coverage** — Track pairings and ensure every model pair has at least N battles
2. **Category-balanced prompts** — Force even distribution across safety categories per run
3. **Elo-aware pairing** — Match models of similar Elo ratings for more informative battles
4. **Duplicate prevention** — Check existing battles before generating to avoid exact (model_a, model_b, prompt) triples
5. **Weighted sampling** — Give more battles to models with fewer total battles

---

## Battle Number Assignment

- `battle_number` is a sequential integer
- Before each run, query `MAX(battle_number)` from the battles table
- Start from `max + 1` and increment sequentially
- This avoids conflicts and provides a clean ordering

---

*This document is maintained by the battle-generator agent. Update pairing rules here before changing the script.*

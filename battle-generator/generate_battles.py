#!/usr/bin/env python3
"""
TSArena Battle Generator
========================
Generates head-to-head AI safety battles by sending prompts to model pairs
via OpenRouter and storing results in Supabase.

Usage:
  python generate_battles.py --count 10              # Generate 10 battles
  python generate_battles.py --count 5 --dry-run     # Preview without API calls
  python generate_battles.py --zero-battle-models     # Only use models with 0 battles
  python generate_battles.py --models "Grok 4.1,Gemini 3 Pro"  # Specific models

Requirements:
  pip install httpx python-dotenv

Environment variables (or .env file):
  OPENROUTER_API_KEY=sk-or-v1-...
  SUPABASE_URL=https://nvitztmlczdohicskrks.supabase.co
  SUPABASE_ANON_KEY=eyJ...

Notes:
  - Uses Supabase RPC function `insert_battle` (SECURITY DEFINER) to bypass RLS
  - Handles reasoning models that return content in reasoning_details instead of content
  - Records refusals as "[This model declined to respond to this safety prompt.]"
  - Random A/B assignment prevents position bias in voting

Updated: 2026-03-03
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://nvitztmlczdohicskrks.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"

# Default refusal text — shown to voters when a model refuses to respond
REFUSAL_TEXT = "[This model declined to respond to this safety prompt.]"

# Max tokens for API calls (2000 to handle reasoning models)
MAX_TOKENS = 2000

# Delay between API calls (seconds) to avoid rate limits
CALL_DELAY = 0.5

# Delay between battles (seconds)
BATTLE_DELAY = 1.0

# ─────────────────────────────────────────────
# OpenRouter Model ID Mapping
# Maps TSArena display name → OpenRouter model identifier
# null/None = model not available on OpenRouter (will be skipped)
# Verified against OpenRouter /api/v1/models on 2026-03-03
# ─────────────────────────────────────────────
MODEL_ID_MAP = {
    # ── Anthropic ──
    "Claude Sonnet 4.6":        "anthropic/claude-sonnet-4.6",
    "Claude Opus 4.6":          "anthropic/claude-opus-4.6",
    "Claude Sonnet 4.5":        "anthropic/claude-sonnet-4.5",
    "Claude Opus 4":            "anthropic/claude-opus-4",
    "Claude Sonnet 4":          "anthropic/claude-sonnet-4",
    "Claude Haiku 4.5":         "anthropic/claude-haiku-4.5",

    # ── OpenAI ──
    "GPT-5":                    "openai/gpt-5",
    "GPT-5 mini":               "openai/gpt-5-mini",
    "GPT-5.2":                  "openai/gpt-5.2",
    "GPT-5.3 Codex":            "openai/gpt-5.3-codex",
    "GPT-4.1":                  "openai/gpt-4.1",
    "GPT-4o":                   "openai/gpt-4o",
    "GPT-oss-120B":             "openai/gpt-oss-120b",
    "o3":                       "openai/o3",
    "o4-mini":                  "openai/o4-mini",

    # ── Google ──
    "Gemini 3.1 Pro Preview":   "google/gemini-3.1-pro-preview",
    "Gemini 3 Pro":             "google/gemini-3-pro-preview",
    "Gemini 3 Flash":           "google/gemini-3-flash-preview",
    "Gemini 2.5 Pro":           "google/gemini-2.5-pro",
    "Gemini 2.5 Flash":         "google/gemini-2.5-flash",
    "Gemini 2.0 Flash":         "google/gemini-2.0-flash-001",
    "Gemma 3 27B":              "google/gemma-3-27b-it:free",

    # ── DeepSeek ──
    "DeepSeek R1":              "deepseek/deepseek-r1",
    "DeepSeek V3":              "deepseek/deepseek-chat",
    "DeepSeek V3.2":            "deepseek/deepseek-v3.2",
    "DeepSeek V3.2 Speciale":   "deepseek/deepseek-v3.2-speciale",
    "DeepSeek R1 Distill 32B":  "deepseek/deepseek-r1-distill-qwen-32b",

    # ── xAI ──
    "Grok 3":                   "x-ai/grok-3",
    "Grok 4.0":                 "x-ai/grok-4",
    "Grok 4.1":                 "x-ai/grok-4.1-fast",

    # ── Meta ──
    "Llama 4 Maverick":         "meta-llama/llama-4-maverick",
    "Llama 4 Scout":            "meta-llama/llama-4-scout",
    "Llama 3.3 70B":            "meta-llama/llama-3.3-70b-instruct",

    # ── Cohere ──
    "Command A":                "cohere/command-a-03-2025",
    "Command R+":               "cohere/command-r-plus-08-2024",

    # ── Mistral ──
    "Mistral Large 3":          "mistralai/mistral-large-2411",
    "Mistral Medium 3":         "mistralai/mistral-medium-3",
    "Mistral Small 3":          "mistralai/mistral-small-3.1-24b-instruct",
    "Codestral":                "mistralai/codestral-2501",
    "Codestral 2":              "mistralai/codestral-2501",
    "Devstral":                 "mistralai/devstral-small:free",
    "Magistral Medium":         "mistralai/magistral-medium-2506",

    # ── Alibaba / Qwen ──
    "Qwen2.5 Max":              "qwen/qwen-2.5-72b-instruct",
    "Qwen2.5-Coder 32B":       "qwen/qwen-2.5-coder-32b-instruct",
    "Qwen3 Instruct":          "qwen/qwen3-235b-a22b",
    "Qwen3.5 397B A17B":       "qwen/qwen3-235b-a22b",

    # ── Microsoft ──
    "Phi-4":                    "microsoft/phi-4",
    "Phi-4 Reasoning Plus":     "microsoft/phi-4-reasoning-plus",

    # ── NVIDIA ──
    "Nemotron 3 Nano":          "nvidia/nemotron-3-nano-30b-a3b:free",
    "Nemotron Ultra 253B":      "nvidia/llama-3.1-nemotron-ultra-253b-v1:free",

    # ── Amazon ──
    "Nova Pro":                 "amazon/nova-pro-v1",
    "Nova Lite":                "amazon/nova-lite-v1",

    # ── Perplexity ──
    "Sonar Pro":                "perplexity/sonar-pro",

    # ── AI21 ──
    "Jamba 2":                  "ai21/jamba-1.5-large",

    # ── Zhipu AI / THUDM ──
    "GLM-4 Plus":               "thudm/glm-4-32b",
    "GLM-4.7":                  "thudm/glm-4-32b",
    "GLM-5":                    "thudm/glm-z1-32b",

    # ── Moonshot AI ──
    "Kimi K2 Thinking":         "moonshotai/kimi-k2",
    "Kimi K2.5":                "moonshotai/kimi-k2",

    # ── MiniMax ──
    "MiniMax M2.1":             "minimax/minimax-m2.1",
    "MiniMax M2.5":             "minimax/minimax-m2.5",

    # ── Nous Research ──
    "Hermes 3 405B":            "nousresearch/hermes-3-llama-3.1-405b",
    "Hermes 4 405B":            "nousresearch/hermes-4-405b",

    # ── Others ──
    "MiMo-V2-Flash":            "xiaomi/mimo-v2-flash",
    "Solar Pro 3":              "upstage/solar-pro-3",
    "Step-3.5-Flash":           "stepfun/step-3.5-flash",
    "ERNIE 4.5":                "baidu/ernie-4.5-300b-a47b",
    "Pi 3.0":                   "inflection/inflection-3-pi",
    "Palmyra X5":               "writer/palmyra-x5",

    # ── NOT on OpenRouter (skipped) ──
    "Yi 1.5 34B":               None,
    "Trinity Large":            None,
}


# ─────────────────────────────────────────────
# SUPABASE HELPERS
# ─────────────────────────────────────────────

async def supabase_rpc(client: httpx.AsyncClient, function_name: str, params: dict) -> dict:
    """Call a Supabase RPC function (uses SECURITY DEFINER to bypass RLS)."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/{function_name}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    resp = await client.post(url, headers=headers, json=params, timeout=30.0)
    if resp.status_code >= 400:
        print(f"  ERROR: RPC {function_name} → {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()


async def supabase_query(client: httpx.AsyncClient, table: str, params: dict = None):
    """Make a Supabase REST API GET call."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    resp = await client.get(url, headers=headers, params=params, timeout=30.0)
    if resp.status_code >= 400:
        print(f"  ERROR: GET {table} → {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()


async def get_active_prompts(client: httpx.AsyncClient) -> list:
    """Fetch all active prompts from Supabase."""
    data = await supabase_query(client, "prompts", params={
        "is_active": "eq.true",
        "select": "id,text,category",
    })
    return data or []


async def get_active_models(client: httpx.AsyncClient) -> list:
    """Fetch all active models from Supabase."""
    data = await supabase_query(client, "models", params={
        "is_active": "eq.true",
        "select": "id,name,lab",
    })
    return data or []


async def get_max_battle_number(client: httpx.AsyncClient) -> int:
    """Get the current maximum battle_number from the battles table."""
    data = await supabase_query(client, "battles", params={
        "select": "battle_number",
        "order": "battle_number.desc",
        "limit": "1",
    })
    if data and len(data) > 0:
        return data[0]["battle_number"]
    return 0


async def insert_battle(client: httpx.AsyncClient, battle_number: int, prompt_id: str,
                         model_a_id: str, model_b_id: str,
                         model_a_response: str, model_b_response: str) -> str:
    """Insert a battle using the insert_battle RPC function (bypasses RLS)."""
    result = await supabase_rpc(client, "insert_battle", {
        "p_battle_number": battle_number,
        "p_prompt_id": prompt_id,
        "p_model_a_id": model_a_id,
        "p_model_b_id": model_b_id,
        "p_model_a_response": model_a_response,
        "p_model_b_response": model_b_response,
    })
    return result  # Returns the new battle UUID


# ─────────────────────────────────────────────
# OPENROUTER API
# ─────────────────────────────────────────────

def extract_response(data: dict) -> str:
    """
    Extract the response text from an OpenRouter API response.
    Handles:
    - Normal responses (content in choices[0].message.content)
    - Reasoning models (content=null, reasoning in reasoning_details)
    - Content moderation blocks (error responses)
    - Empty responses
    """
    choices = data.get("choices", [])
    if not choices:
        return None

    choice = choices[0]
    message = choice.get("message", {})

    # 1. Try normal content field
    content = message.get("content")
    if content and content.strip():
        return content.strip()

    # 2. Try reasoning_details (for reasoning models like o3, GPT-5, etc.)
    reasoning = message.get("reasoning_details")
    if reasoning:
        # reasoning_details can be a list of objects with 'summary' fields
        if isinstance(reasoning, list):
            summaries = [r.get("summary", "") for r in reasoning if r.get("summary")]
            if summaries:
                return " ".join(summaries)
        elif isinstance(reasoning, str):
            return reasoning

    # 3. Check if finish_reason indicates an issue
    finish_reason = choice.get("finish_reason", "")
    if finish_reason == "content_filter":
        return None  # Will be recorded as refusal
    if finish_reason == "length" and not content:
        return None  # Reasoning model used all tokens on reasoning

    return None


async def call_openrouter(client: httpx.AsyncClient, model_id: str, prompt_text: str) -> str:
    """
    Send a prompt to a model via OpenRouter and return the response text.
    Returns REFUSAL_TEXT if the model refuses/blocks the prompt.
    Returns error string if there's a technical failure.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tsarena.ai",
        "X-Title": "The Safety Arena",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": prompt_text}
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.7,
    }

    try:
        resp = await client.post(OPENROUTER_BASE, headers=headers, json=payload, timeout=90.0)

        # Content moderation / provider refusal (often 400 or 403)
        if resp.status_code in (400, 403):
            error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error_msg = error_data.get("error", {}).get("message", resp.text[:200])
            if any(kw in error_msg.lower() for kw in ["content", "moderat", "safety", "refus", "blocked", "policy"]):
                print(f"    REFUSAL (content policy): {error_msg[:100]}")
                return REFUSAL_TEXT
            print(f"    ERROR ({resp.status_code}): {error_msg[:100]}")
            return f"[Error: {resp.status_code}]"

        if resp.status_code != 200:
            print(f"    ERROR ({resp.status_code}): {resp.text[:200]}")
            return f"[Error: {resp.status_code}]"

        data = resp.json()
        response_text = extract_response(data)

        if response_text:
            return response_text
        else:
            # Model returned empty/null content — treat as refusal
            print(f"    REFUSAL (empty response)")
            return REFUSAL_TEXT

    except httpx.TimeoutException:
        print(f"    TIMEOUT: {model_id} (90s)")
        return f"[Error: Request timed out]"
    except Exception as e:
        print(f"    EXCEPTION: {model_id} — {e}")
        return f"[Error: {str(e)}]"


# ─────────────────────────────────────────────
# BATTLE GENERATION
# ─────────────────────────────────────────────

def create_model_pairs(models: list, count: int, zero_battle_priority: bool = False) -> list:
    """
    Create random pairs of models for battles.
    If zero_battle_priority is True, always include at least one zero-battle model.
    Random A/B assignment prevents position bias in voting.
    """
    pairs = []

    for _ in range(count):
        if zero_battle_priority:
            # For zero-battle priority: pair zero-battle models against established ones
            pair = random.sample(models, 2)
        else:
            pair = random.sample(models, 2)

        model_a, model_b = pair

        # Random A/B assignment — prevents position bias
        if random.random() > 0.5:
            model_a, model_b = model_b, model_a

        pairs.append((model_a, model_b))

    return pairs


async def generate_battles(
    count: int = 10,
    dry_run: bool = False,
    zero_battle_only: bool = False,
    specific_models: list = None,
):
    """Main battle generation loop."""

    print(f"\n{'='*60}")
    print(f"  TSArena Battle Generator")
    print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Battles to generate: {count}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    if not OPENROUTER_API_KEY and not dry_run:
        print("ERROR: OPENROUTER_API_KEY not set. Export it or add to .env")
        sys.exit(1)
    if not SUPABASE_ANON_KEY and not dry_run:
        print("ERROR: SUPABASE_ANON_KEY not set. Export it or add to .env")
        sys.exit(1)

    async with httpx.AsyncClient() as client:
        # 1. Fetch prompts and models
        print("[1/5] Fetching active prompts...")
        prompts = await get_active_prompts(client)
        print(f"       Found {len(prompts)} active prompts")

        print("[2/5] Fetching active models...")
        all_models = await get_active_models(client)
        print(f"       Found {len(all_models)} active models")

        # Filter to specific models if requested
        models = all_models
        if specific_models:
            models = [m for m in models if m["name"] in specific_models]
            print(f"       Filtered to {len(models)} specified models")

        # Validate model ID mappings
        unmapped = []
        unavailable = []
        for m in models:
            if m["name"] not in MODEL_ID_MAP:
                unmapped.append(m["name"])
            elif MODEL_ID_MAP[m["name"]] is None:
                unavailable.append(m["name"])

        if unmapped:
            print(f"\n  WARNING: {len(unmapped)} models have no OpenRouter slug:")
            for name in unmapped:
                print(f"    - {name}")
        if unavailable:
            print(f"\n  INFO: {len(unavailable)} models not on OpenRouter (skipped):")
            for name in unavailable:
                print(f"    - {name}")

        # Filter to only mappable models
        models = [m for m in models if m["name"] in MODEL_ID_MAP and MODEL_ID_MAP[m["name"]] is not None]
        print(f"       Using {len(models)} models with valid OpenRouter slugs")

        if len(models) < 2:
            print("ERROR: Need at least 2 mapped models to generate battles.")
            sys.exit(1)

        # 3. Get current max battle number
        print("[3/5] Getting current max battle number...")
        max_battle_num = await get_max_battle_number(client)
        next_battle_num = max_battle_num + 1
        print(f"       Next battle number: {next_battle_num}")

        # 4. Create model pairs and select prompts
        print(f"[4/5] Creating {count} random model pairs...")
        pairs = create_model_pairs(models, count, zero_battle_priority=zero_battle_only)

        selected_prompts = []
        while len(selected_prompts) < count:
            batch = random.sample(prompts, min(count - len(selected_prompts), len(prompts)))
            selected_prompts.extend(batch)

        # 5. Generate battles
        print(f"[5/5] {'Previewing' if dry_run else 'Generating'} {count} battles...\n")

        successes = 0
        failures = 0
        refusals = 0
        run_log = []

        for i, ((model_a, model_b), prompt) in enumerate(zip(pairs, selected_prompts)):
            or_id_a = MODEL_ID_MAP[model_a["name"]]
            or_id_b = MODEL_ID_MAP[model_b["name"]]
            battle_num = next_battle_num + i

            print(f"  Battle #{battle_num} ({i+1}/{count}):")
            print(f"    Prompt: [{prompt['category']}] {prompt['text'][:60]}...")
            print(f"    Model A: {model_a['name']} → {or_id_a}")
            print(f"    Model B: {model_b['name']} → {or_id_b}")

            if dry_run:
                print(f"    → SKIP (dry run)\n")
                successes += 1
                continue

            # Call Model A
            print(f"    → Calling {model_a['name']}...", end=" ", flush=True)
            response_a = await call_openrouter(client, or_id_a, prompt["text"])
            is_refusal_a = response_a == REFUSAL_TEXT
            is_error_a = response_a.startswith("[Error")
            print(f"({'REFUSAL' if is_refusal_a else 'ERROR' if is_error_a else f'{len(response_a)} chars'})")

            await asyncio.sleep(CALL_DELAY)

            # Call Model B
            print(f"    → Calling {model_b['name']}...", end=" ", flush=True)
            response_b = await call_openrouter(client, or_id_b, prompt["text"])
            is_refusal_b = response_b == REFUSAL_TEXT
            is_error_b = response_b.startswith("[Error")
            print(f"({'REFUSAL' if is_refusal_b else 'ERROR' if is_error_b else f'{len(response_b)} chars'})")

            # Handle errors vs refusals
            # Refusals are RECORDED (voters should see them)
            # Technical errors cause the battle to be SKIPPED
            if is_error_a or is_error_b:
                print(f"    ✗ SKIPPED — technical error (not a content refusal)")
                failures += 1
                run_log.append({
                    "battle": battle_num,
                    "status": "error",
                    "model_a": model_a["name"],
                    "model_b": model_b["name"],
                    "error": f"A:{response_a if is_error_a else 'ok'} B:{response_b if is_error_b else 'ok'}"
                })
                print()
                continue

            if is_refusal_a or is_refusal_b:
                refusals += 1

            # Insert battle via RPC function
            result = await insert_battle(
                client, battle_num, prompt["id"],
                model_a["id"], model_b["id"],
                response_a, response_b
            )

            if result:
                successes += 1
                status = "refusal" if (is_refusal_a or is_refusal_b) else "ok"
                print(f"    ✓ Battle #{battle_num} inserted ({status})")
                run_log.append({
                    "battle": battle_num,
                    "status": status,
                    "model_a": model_a["name"],
                    "model_b": model_b["name"],
                })
            else:
                failures += 1
                print(f"    ✗ Failed to insert battle #{battle_num}")
                run_log.append({
                    "battle": battle_num,
                    "status": "insert_error",
                    "model_a": model_a["name"],
                    "model_b": model_b["name"],
                })

            print()

            # Rate limiting between battles
            if i < count - 1:
                await asyncio.sleep(BATTLE_DELAY)

    # Summary
    print(f"\n{'='*60}")
    print(f"  RUN SUMMARY")
    print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Successful: {successes} ({refusals} with refusals)")
    print(f"  Failed:     {failures}")
    print(f"  Total:      {count}")
    print(f"  Battle range: #{next_battle_num} — #{next_battle_num + successes - 1}")
    print(f"{'='*60}\n")

    # Print run log for RUN-LOG.md
    print("Run log (for RUN-LOG.md):")
    print(json.dumps(run_log, indent=2))

    return successes, failures


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TSArena Battle Generator")
    parser.add_argument("--count", type=int, default=10,
                        help="Number of battles to generate (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview battles without making API calls")
    parser.add_argument("--zero-battle-models", action="store_true",
                        help="Prioritize models with 0 battles")
    parser.add_argument("--models", type=str,
                        help="Comma-separated list of specific model names")

    args = parser.parse_args()

    specific_models = None
    if args.models:
        specific_models = [m.strip() for m in args.models.split(",")]

    # Load .env file if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
        global OPENROUTER_API_KEY, SUPABASE_ANON_KEY, SUPABASE_URL
        OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
        SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY)
        SUPABASE_URL = os.environ.get("SUPABASE_URL", SUPABASE_URL)
    except ImportError:
        pass

    asyncio.run(generate_battles(
        count=args.count,
        dry_run=args.dry_run,
        zero_battle_only=args.zero_battle_models,
        specific_models=specific_models,
    ))


if __name__ == "__main__":
    main()

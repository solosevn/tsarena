#!/usr/bin/env python3
"""
TSArena Battle Generator Bot
Telegram bot for controlling battle generation via GitHub Actions.
Run: python3 battle_bot.py
"""

import asyncio
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

import httpx
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

load_dotenv()

# ââ Config ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GITHUB_PAT         = os.environ["GITHUB_PAT"]
TELEGRAM_USER_ID   = int(os.environ.get("TELEGRAM_USER_ID", "0"))  # 0 = allow anyone (set after first /start)

GITHUB_OWNER    = "solosevn"
GITHUB_REPO     = "tsarena"
WORKFLOW_FILE   = "generate-battles.yml"
GITHUB_API      = "https://api.github.com"
GITHUB_HEADERS  = {
    "Authorization": f"Bearer {GITHUB_PAT}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

DEFAULT_COUNT = 100  # battles per run


# ââ Helpers âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s"

def fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d %I:%M %p UTC")
    except Exception:
        return iso

def status_emoji(status: str, conclusion: str | None) -> str:
    if status == "in_progress" or status == "queued":
        return "ð"
    if conclusion == "success":
        return "â"
    if conclusion in ("failure", "timed_out"):
        return "â"
    if conclusion == "cancelled":
        return "ð«"
    return "â"

async def gh_get(path: str) -> dict | list:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{GITHUB_API}{path}", headers=GITHUB_HEADERS, timeout=20)
        r.raise_for_status()
        return r.json()

async def gh_post(path: str, body: dict | None = None) -> httpx.Response:
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{GITHUB_API}{path}",
            headers=GITHUB_HEADERS,
            json=body or {},
            timeout=20,
        )
        return r

async def get_latest_runs(limit: int = 10) -> list:
    data = await gh_get(
        f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page={limit}"
    )
    return data.get("workflow_runs", [])

async def get_active_run() -> dict | None:
    runs = await get_latest_runs(5)
    for run in runs:
        if run["status"] in ("in_progress", "queued", "waiting"):
            return run
    return None


# ââ Auth guard ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def authorized(update: Update) -> bool:
    if TELEGRAM_USER_ID == 0:
        return True  # no restriction set yet
    return update.effective_user.id == TELEGRAM_USER_ID


# ââ Command handlers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"ð Hey {name}!\n\n"
        f"Your Telegram user ID is: `{uid}`\n"
        f"Add `TELEGRAM_USER_ID={uid}` to your .env to lock the bot to you only.\n\n"
        f"Commands:\n"
        f"/run \\[count\\] â Start battle generation \\(default {DEFAULT_COUNT}\\)\n"
        f"/run zero â Prioritize zero\\-battle models\n"
        f"/stop â Cancel active run\n"
        f"/status â Current run status\n"
        f"/history â Last 10 runs\n"
        f"/config â Show current settings",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return

    args = ctx.args
    count = DEFAULT_COUNT
    zero_battle = False
    models_arg = ""

    if args:
        if args[0].lower() == "zero":
            zero_battle = True
        elif args[0].isdigit():
            count = int(args[0])
            if len(args) > 1 and args[1].lower() == "zero":
                zero_battle = True
        else:
            # treat as comma-separated model names
            models_arg = " ".join(args)

    # Check if already running
    active = await get_active_run()
    if active:
        await update.message.reply_text(
            f"â ï¸ A run is already in progress!\n"
            f"Run #{active['run_number']} started {fmt_time(active['created_at'])}\n"
            f"Use /stop to cancel it first."
        )
        return

    # Build inputs
    inputs = {
        "count": str(count),
        "dry_run": "false",
        "zero_battle_models": "true" if zero_battle else "false",
        "models": models_arg,
    }

    msg = await update.message.reply_text("ð Triggering GitHub Actions...")

    r = await gh_post(
        f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches",
        {"ref": "main", "inputs": inputs},
    )

    if r.status_code == 204:
        mode = "zero-battle priority" if zero_battle else f"{count} battles"
        if models_arg:
            mode = f"models: {models_arg}"
        await msg.edit_text(
            f"â Run triggered!\n"
            f"Mode: {mode}\n"
            f"Check /status in ~15 seconds for updates."
        )
    else:
        await msg.edit_text(f"â Failed to trigger run.\nGitHub returned: {r.status_code}\n{r.text[:200]}")


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return

    active = await get_active_run()
    if not active:
        await update.message.reply_text("â No active run to stop.")
        return

    run_id = active["id"]
    run_num = active["run_number"]

    msg = await update.message.reply_text(f"ð Cancelling run #{run_num}...")

    r = await gh_post(f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}/cancel")

    if r.status_code == 202:
        await msg.edit_text(f"ð« Run #{run_num} cancelled successfully.")
    else:
        await msg.edit_text(f"â Cancel failed.\nGitHub returned: {r.status_code}")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return

    runs = await get_latest_runs(3)
    if not runs:
        await update.message.reply_text("No runs found yet.")
        return

    latest = runs[0]
    status = latest["status"]
    conclusion = latest.get("conclusion")
    emoji = status_emoji(status, conclusion)
    run_num = latest["run_number"]
    created = fmt_time(latest["created_at"])

    # Duration
    duration_str = ""
    if latest.get("updated_at") and latest.get("created_at"):
        try:
            start = datetime.fromisoformat(latest["created_at"].replace("Z", "+00:00"))
            end   = datetime.fromisoformat(latest["updated_at"].replace("Z", "+00:00"))
            secs  = int((end - start).total_seconds())
            duration_str = f"\nDuration: {fmt_duration(secs)}"
        except Exception:
            pass

    state_label = conclusion if conclusion else status
    lines = [
        f"{emoji} Run #{run_num} â {state_label.upper()}",
        f"Started: {created}{duration_str}",
        f"Branch: {latest.get('head_branch', 'main')}",
    ]

    if status in ("in_progress", "queued"):
        lines.append("\nUse /stop to cancel.")

    await update.message.reply_text("\n".join(lines))


async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return

    runs = await get_latest_runs(10)
    if not runs:
        await update.message.reply_text("No runs found yet.")
        return

    lines = ["ð Last 10 runs:\n"]
    for run in runs:
        emoji  = status_emoji(run["status"], run.get("conclusion"))
        num    = run["run_number"]
        state  = run.get("conclusion") or run["status"]
        when   = fmt_time(run["created_at"])

        # Duration
        dur = ""
        try:
            start = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            end   = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
            dur   = f" ({fmt_duration(int((end - start).total_seconds()))})"
        except Exception:
            pass

        lines.append(f"{emoji} #{num} {state.upper()}{dur} â {when}")

    await update.message.reply_text("\n".join(lines))


async def cmd_config(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return

    await update.message.reply_text(
        f"âï¸ Current Config\n\n"
        f"Default battle count: {DEFAULT_COUNT}\n"
        f"GitHub repo: {GITHUB_OWNER}/{GITHUB_REPO}\n"
        f"Workflow: {WORKFLOW_FILE}\n"
        f"Cron schedule: Sundays 11 PM EST (Mon 4 AM UTC)\n\n"
        f"To change defaults, edit battle_bot.py and restart.\n\n"
        f"Quick run examples:\n"
        f"  /run â {DEFAULT_COUNT} battles (default)\n"
        f"  /run 50 â 50 battles\n"
        f"  /run zero â prioritize zero-battle models\n"
        f"  /run 200 zero â 200 battles, zero-battle priority"
    )


# ââ Main ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("run",     "Start battle generation"),
        BotCommand("stop",    "Cancel active run"),
        BotCommand("status",  "Check current run status"),
        BotCommand("history", "Last 10 runs"),
        BotCommand("config",  "Show settings"),
    ])


def main():
    print("ð¤ TSArena Battle Bot starting...")
    print(f"   Repo: {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"   User restriction: {'ON (user ' + str(TELEGRAM_USER_ID) + ')' if TELEGRAM_USER_ID else 'OFF (anyone can use)'}")
    print("   Bot is running. Press Ctrl+C to stop.\n")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("run",     cmd_run))
    app.add_handler(CommandHandler("stop",    cmd_stop))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("config",  cmd_config))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

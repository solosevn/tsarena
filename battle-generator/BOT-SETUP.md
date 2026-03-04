# TSArena Battle Bot â Setup Guide

## What this does
Controls battle generation from your Telegram phone. Send commands to start/stop/check runs that execute on GitHub Actions (cloud â your Mac doesn't need to be running the generator, just the bot).

## Commands
| Command | What it does |
|---------|-------------|
| `/run` | Start 100 battles (default) |
| `/run 50` | Start 50 battles |
| `/run zero` | Prioritize zero-battle models |
| `/run 200 zero` | 200 battles, zero-battle priority |
| `/stop` | Cancel the active run |
| `/status` | Check what's running right now |
| `/history` | Last 10 runs with results |
| `/config` | Show current settings |

---

## One-Time Setup

### Step 1 â Add to your .env file

Open `battle-generator/.env` and add these 3 lines:

```
TELEGRAM_BOT_TOKEN=8620832848:AAFq_bThlmmBI6nb6F2IPoj_I4hqdVwuSjU
GITHUB_PAT=<your GitHub Personal Access Token â see Step 2>
TELEGRAM_USER_ID=<your Telegram user ID â see Step 3>
```

### Step 2 â Create a GitHub Personal Access Token (PAT)

1. Go to: https://github.com/settings/tokens/new
2. Note (name): `TSArena Battle Bot`
3. Expiration: `No expiration` (or 1 year)
4. Scopes: check **`repo`** and **`workflow`**
5. Click **Generate token**
6. Copy the token (starts with `ghp_...`) into your .env as `GITHUB_PAT`

### Step 3 â Get your Telegram User ID

1. Start the bot: `python3 battle-generator/battle_bot.py`
2. Open Telegram, find **BattleGenBot**
3. Send `/start`
4. The bot will reply with your user ID
5. Copy that number into your .env as `TELEGRAM_USER_ID`
6. Restart the bot

---

## Running the Bot

### Start (foreground â good for testing)
```bash
cd ~/path/to/tsarena
python3 battle-generator/battle_bot.py
```

### Start (background â survives terminal close)
```bash
nohup python3 battle-generator/battle_bot.py > battle_bot.log 2>&1 &
echo "Bot PID: $!"
```

### Stop the background bot
```bash
pkill -f battle_bot.py
```

### Check if it's running
```bash
ps aux | grep battle_bot
```

---

## Install dependency (one time)
```bash
pip3 install python-telegram-bot --break-system-packages
```

---

## Notes
- The bot needs to run on your Mac to receive Telegram messages
- Battle generation itself runs on GitHub's servers (cloud) â your Mac just sends the trigger
- The cron job (Sunday 11 PM EST) runs automatically without the bot
- GitHub Actions run logs are always viewable at: https://github.com/solosevn/tsarena/actions

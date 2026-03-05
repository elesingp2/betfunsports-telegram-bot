# bfs-bot

Telegram notifications for [betfunsports](https://betfunsports.com) MCP agent.

Install alongside `bfs-mcp`, start once, send `/start` in Telegram — done. Every agent action (logins, bets, errors) gets auto-logged to your Telegram chat with screenshots.

## How it works

```
1. pip install bfs-bot         ← agent installs
2. BFS_TG_TOKEN=xxx bfs-bot   ← agent starts
3. User sends /start           ← saves ~/.bfs-mcp/telegram.json
4. bfs-mcp auto-sends notifications on every tool call
```

The bot saves `token` + `chat_id` to `~/.bfs-mcp/telegram.json`. The MCP server (`bfs-mcp`) reads this file and sends Telegram notifications — no config changes, no restarts.

## Setup

### 1. Install

```bash
pip install git+https://github.com/elesingp2/betfunsports-telegram-bot.git
```

### 2. Get a bot token

Create a bot via [@BotFather](https://t.me/BotFather) in Telegram.

### 3. Start

```bash
BFS_TG_TOKEN=your_token bfs-bot
```

### 4. Send `/start` in Telegram

Open your bot → send `/start` → notifications enabled.

## What gets logged

When `bfs-mcp` has notification support, every tool call is auto-logged:

| Agent action | Telegram message |
|-------------|-----------------|
| `bfs_login()` | ✅ LOGIN: user123 — EUR: 50, BFS: 87 |
| `bfs_place_bet()` | 🎯 BET: Football 1X2, home, 5 BFS 📸 |
| `bfs_place_bet()` fail | ❌ BET FAILED: betting closed 📸 |
| `bfs_screenshot()` | 📸 screenshot forwarded |
| `bfs_active_bets()` | 📊 Active bets (3) |
| `bfs_logout()` | 🚪 Logged out |

## Integration with bfs-mcp

The `notify` module uses only stdlib and can be imported directly by `bfs-mcp`:

```python
# In bfs-mcp/server.py — add at the top:
try:
    from bfs_bot.notify import send_text, send_photo
except ImportError:
    send_text = send_photo = None

# After a tool call:
if send_text:
    send_text("✅ <b>LOGIN</b>: user123\nEUR: 50 | BFS: 87")

# With screenshot:
if send_photo:
    send_photo(screenshot_bytes, caption="🎯 <b>BET PLACED</b>: Football 1X2")
```

If `bfs-bot` is not installed, the import silently fails — zero impact on `bfs-mcp`.

## Telegram commands

| Command | Description |
|---------|-------------|
| `/start` | Enable notifications (save config) |
| `/status` | Show who's logged in |
| `/chatid` | Show chat ID |

## CLI

Send notifications from shell scripts:

```bash
bfs-log "Agent started"
bfs-log -l error "Login failed"
bfs-log -l success "Bet placed"
bfs-log -s screenshot.png "Error on page"
```

## Config

The only file: `~/.bfs-mcp/telegram.json`

```json
{
  "token": "123456:ABC...",
  "chat_ids": [870130546]
}
```

Created automatically when you send `/start`. Shared between `bfs-bot` and `bfs-mcp`.

| Env variable | Required | Description |
|-------------|----------|-------------|
| `BFS_TG_TOKEN` | yes | Telegram bot token |

## Architecture

```
bfs-bot (this package)
├── main.py      ← Telegram polling (/start saves config)
├── notify.py    ← send_text() / send_photo() — stdlib only, importable by bfs-mcp
└── client.py    ← bfs-log CLI

~/.bfs-mcp/
├── telegram.json     ← shared config (token + chat_ids)
├── credentials.json  ← saved by bfs-mcp (read by /status)
└── cookies.json      ← saved by bfs-mcp
```

## License

MIT

# bfs-bot

Lightweight Telegram bot for monitoring [betfunsports.com](https://betfunsports.com) betting activity.

Deploy locally or on a server. Every action your MCP agent takes — logins, bets, errors — auto-logged to Telegram with screenshots.

No LLM, no chat interface. Just a fast notification channel.

```
MCP Agent (Claude / Cursor / OpenClaw)
    │
    │  uses bfs-bot-mcp (drop-in replacement for bfs-mcp)
    │
    ├── bfs_login()         →  ✅ LOGIN: user123 | EUR: 50 | BFS: 87
    ├── bfs_place_bet()     →  🎯 BET PLACED: Football 1X2, home, 5 BFS  📸
    ├── bfs_place_bet()     →  ❌ BET FAILED: betting closed  📸
    ├── bfs_active_bets()   →  📊 ACTIVE BETS: 3
    └── bfs_screenshot()    →  📸 [screenshot]
                                    │
                                    ▼
                              Telegram chat
```

## Setup (3 steps)

### 1. Install

```bash
pip install git+https://github.com/elesingp2/betfunsports-telegram-bot.git
playwright install --with-deps chromium
```

### 2. Start the bot & register your chat

```bash
export BFS_TG_TOKEN=your_token    # get from @BotFather
bfs-bot
```

Open your bot in Telegram → send `/start` → chat registered.

### 3. Switch MCP config to `bfs-bot-mcp`

Replace `bfs-mcp` with `bfs-bot-mcp` in your MCP client config:

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "bfs": {
      "command": "bfs-bot-mcp",
      "env": {
        "BFS_TG_TOKEN": "your_telegram_bot_token"
      }
    }
  }
}
```

**Cursor**: Settings → MCP → command: `bfs-bot-mcp`

That's it. The agent uses the same 14 tools as `bfs-mcp`, but every action is auto-logged to your Telegram.

## What gets logged

| Action | Telegram notification |
|--------|----------------------|
| Login | ✅/❌ username, balances + screenshot on error |
| Place bet | 🎯/❌ coupon, picks, room, stake + screenshot |
| Registration | ✅/❌ username, email |
| Auth status | ℹ️ username, balances |
| Coupons | 📋 count of available coupons |
| Coupon details | 🔍 title, event count |
| Active bets | 📊 summary |
| Bet history | 📜 summary |
| Screenshot | 📸 forwarded to chat |
| Logout | 🚪 logged out |

## Telegram commands

| Command | Description |
|---------|-------------|
| `/start` | Register chat for logs |
| `/logs` | Last 10 log entries (from HTTP API) |
| `/logs N` | Last N entries (max 50) |
| `/stats` | Betting statistics |
| `/screen` | Last received screenshot |
| `/chatid` | Show chat ID |

## Architecture

```
┌───────────────────────────────────────────────────┐
│  bfs-bot-mcp  (MCP server, stdio)                 │
│  Same 14 tools as bfs-mcp + Telegram notifications│
│  └── BFSBrowser (Playwright headless)             │
│  └── notify.py → Telegram Bot API                 │
└───────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────┐
│  bfs-bot  (Telegram polling + HTTP API)           │
│  Monitoring dashboard: /logs /stats /screen       │
│  HTTP API for external log sources                │
└───────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────┐
│  bfs-log  (CLI, zero dependencies)                │
│  Send logs from shell scripts / cron              │
└───────────────────────────────────────────────────┘
```

### How it works

1. **`bfs-bot`** runs Telegram polling — registers your chat on `/start`, saves chat ID to `bfs-bot-state.json`
2. **`bfs-bot-mcp`** runs as MCP server — reads chat ID from the same state file, sends notifications directly via Telegram Bot API
3. Both processes share `BFS_TG_TOKEN` and the state file — no HTTP needed between them

## HTTP API (optional)

The `bfs-bot` process also exposes a local HTTP API for sending logs from scripts:

```bash
# text log
curl -X POST http://127.0.0.1:9867/api/log \
  -H "Content-Type: application/json" \
  -d '{"level": "success", "text": "Custom log message"}'

# screenshot
curl -X POST http://127.0.0.1:9867/api/screenshot \
  -H "Content-Type: application/json" \
  -d '{"image": "'$(base64 -w0 screen.png)'", "caption": "Error page"}'

# bet event
curl -X POST http://127.0.0.1:9867/api/bet \
  -H "Content-Type: application/json" \
  -d '{"coupon": "/football/1x2/123", "status": "placed", "stake": "5", "room": "Wooden"}'
```

Or use the CLI:
```bash
bfs-log "Agent started"
bfs-log -l error "Login failed"
bfs-log -s screenshot.png "Error on page"
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BFS_TG_TOKEN` | — | Telegram bot token (**required**) |
| `BFS_CHAT_ID` | — | Chat ID (optional — auto-saved on `/start`) |
| `BFS_API_HOST` | `127.0.0.1` | HTTP API bind address |
| `BFS_API_PORT` | `9867` | HTTP API port |
| `BFS_MAX_LOGS` | `500` | Max log entries in memory |
| `BFS_STATE_FILE` | `bfs-bot-state.json` | Shared state file path |

## Entry points

| Command | What it does |
|---------|--------------|
| `bfs-bot` | Telegram polling bot + HTTP API (monitoring dashboard) |
| `bfs-bot-mcp` | MCP server with auto Telegram logging (replaces `bfs-mcp`) |
| `bfs-log` | CLI for sending logs (zero extra dependencies) |

## License

MIT

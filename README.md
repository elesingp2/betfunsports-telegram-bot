# betfunsports-telegram-bot

Telegram bot for [betfunsports.com](https://betfunsports.com) — an LLM-powered agent that browses sports events, places bets, and manages your account through natural language.

Built on top of [bfs-mcp](https://github.com/elesingp2/bfs-knowledge/tree/main/bfs-mcp) (headless browser engine).

## Setup

### 1. Install

```bash
pip install git+https://github.com/elesingp2/betfunsports-telegram-bot.git
playwright install --with-deps chromium
```

### 2. Get tokens

| Token | Where to get |
|-------|-------------|
| `BFS_TG_TOKEN` | [@BotFather](https://t.me/BotFather) on Telegram |
| `BFS_LLM_KEY` | [OpenRouter](https://openrouter.ai/keys) (or any OpenAI-compatible API) |

### 3. Run

```bash
export BFS_TG_TOKEN=your_telegram_bot_token
export BFS_LLM_KEY=your_openrouter_api_key

bfs-bot
```

Or with a `.env` file:

```bash
cp .env.example .env
# edit .env with your tokens
export $(cat .env | xargs) && bfs-bot
```

## Usage

Talk to the bot naturally:

- "Залогинься как user@mail.com пароль123"
- "Какие купоны есть?"
- "Покажи футбол 1X2"
- "Поставь на победу хозяев на Wooden столе"
- "Мой баланс"
- "Покажи историю ставок"

### Commands
- `/start` — help
- `/clear` — reset conversation
- `/screen` — screenshot current page

## How Betfunsports works

P2P sports prediction platform. Bets form a prize pool — **100% distributed** among winners.

- Top 50% of bets win (ranked by accuracy 0–100 points)
- Perfect predictions (100 pts) always win
- Sports: Football, Tennis, Hockey, Basketball, F1, Biathlon, Volleyball, Boxing, MMA

| Room | Currency | Range | Fee |
|------|----------|-------|-----|
| Wooden | BFS (free) | 1–10 | 0% |
| Bronze | EUR | 1–5 | 10% |
| Silver | EUR | 10–50 | 7.5% |
| Golden | EUR | 100–500 | 5% |

New accounts get **100 free BFS**.

## Configuration

| Variable | Required | Default |
|----------|----------|---------|
| `BFS_TG_TOKEN` | yes | — |
| `BFS_LLM_KEY` | yes | — |
| `BFS_LLM_BASE` | no | `https://openrouter.ai/api/v1` |
| `BFS_LLM_MODEL` | no | `deepseek/deepseek-chat` (~$0.0002/msg) |
| `BFS_MAX_HISTORY` | no | `30` |
| `BFS_MAX_ITER` | no | `8` |

## MCP Server

For AI agents (Claude, Cursor, OpenClaw) — use the MCP server directly, no Telegram needed:

```bash
pip install git+https://github.com/elesingp2/bfs-knowledge.git#subdirectory=bfs-mcp
playwright install --with-deps chromium
```

Add to your MCP config:
```json
{ "mcpServers": { "bfs": { "command": "bfs-mcp" } } }
```

Zero config — the agent gets platform docs and 13 tools automatically.
See [bfs-mcp README](https://github.com/elesingp2/bfs-knowledge/tree/main/bfs-mcp).

## Architecture

```
src/bfs_bot/
└── main.py     ← Telegram bot (aiogram + OpenAI-compatible LLM)

Dependencies:
├── bfs-mcp     ← Headless browser engine (Playwright)
├── aiogram     ← Telegram framework
└── openai      ← LLM client (OpenRouter/DeepSeek)
```

## License

MIT

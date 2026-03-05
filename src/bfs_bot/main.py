"""BFS Log Bot — Telegram setup helper for betfunsports MCP agent.

Start the bot, send /start in Telegram → notifications enabled.
Config saved to ~/.bfs-mcp/telegram.json, read by bfs-mcp on each tool call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command

log = logging.getLogger(__name__)

TG_TOKEN = os.environ["BFS_TG_TOKEN"]
CONFIG_DIR = Path.home() / ".bfs-mcp"
TG_CONFIG = CONFIG_DIR / "telegram.json"
CREDS_FILE = CONFIG_DIR / "credentials.json"

bot = Bot(token=TG_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


def _save_tg_config(chat_id: int) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if TG_CONFIG.exists():
        try:
            config = json.loads(TG_CONFIG.read_text())
        except Exception:
            pass

    config["token"] = TG_TOKEN
    chat_ids = set(config.get("chat_ids", []))
    chat_ids.add(chat_id)
    config["chat_ids"] = sorted(chat_ids)

    TG_CONFIG.write_text(json.dumps(config, indent=2))
    log.info("config saved: %s (chats: %s)", TG_CONFIG, config["chat_ids"])


@router.message(Command("start"))
async def h_start(msg: Message):
    cid = msg.chat.id
    _save_tg_config(cid)

    await msg.answer(
        "\u2705 <b>Notifications enabled!</b>\n\n"
        f"Chat ID: <code>{cid}</code>\n"
        f"Config: <code>~/.bfs-mcp/telegram.json</code>\n\n"
        "Your MCP agent will now send logs here:\n"
        "logins, bets, errors, screenshots.\n\n"
        "<b>Commands:</b>\n"
        "/status \u2014 who's logged in\n"
        "/chatid \u2014 show chat ID",
        parse_mode="HTML",
    )


@router.message(Command("chatid"))
async def h_chatid(msg: Message):
    await msg.answer(f"Chat ID: <code>{msg.chat.id}</code>", parse_mode="HTML")


@router.message(Command("status"))
async def h_status(msg: Message):
    for path in (CREDS_FILE, TG_CONFIG):
        if path.exists():
            try:
                data = json.loads(path.read_text())
                email = data.get("email") or data.get("logged_in_as")
                if not email:
                    continue
                eur = data.get("balance_eur", "")
                bfs = data.get("balance_bfs", "")
                balance = f"\nEUR: {eur} | BFS: {bfs}" if eur or bfs else ""
                await msg.answer(
                    f"\ud83d\udd11 Logged in as: <code>{email}</code>{balance}",
                    parse_mode="HTML",
                )
                return
            except Exception:
                pass
    await msg.answer("No saved credentials. Agent hasn't logged in yet.")


async def _main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log.info("starting — send /start in Telegram to enable notifications")
    try:
        await dp.start_polling(bot)
    except Exception:
        pass


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()

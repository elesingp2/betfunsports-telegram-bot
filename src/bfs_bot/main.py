"""BFS Log Bot — lightweight Telegram bot for monitoring betting activity.

Runs a Telegram bot + local HTTP API.  The MCP agent (or any automation)
POSTs log entries / screenshots to the HTTP API; they get forwarded to Telegram.

No LLM, no browser — just a fast notification channel.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command

log = logging.getLogger(__name__)

TG_TOKEN = os.environ["BFS_TG_TOKEN"]
API_HOST = os.environ.get("BFS_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("BFS_API_PORT", "9867"))
MAX_LOGS = int(os.environ.get("BFS_MAX_LOGS", "500"))

STATE_FILE = Path(os.environ.get("BFS_STATE_FILE", "bfs-bot-state.json"))

bot = Bot(token=TG_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

_logs: list[dict[str, Any]] = []
_stats = {"bets_placed": 0, "bets_won": 0, "bets_lost": 0, "errors": 0}
_last_screenshot: bytes | None = None
_chat_ids: set[int] = set()

LEVEL_ICONS = {
    "info": "\u2139\ufe0f",
    "success": "\u2705",
    "error": "\u274c",
    "warning": "\u26a0\ufe0f",
    "bet": "\ud83c\udfaf",
    "win": "\ud83c\udfc6",
    "loss": "\ud83d\udcc9",
}


# ── State persistence ───────────────────────────────────────────────

def _save_state() -> None:
    try:
        STATE_FILE.write_text(json.dumps({
            "chat_ids": list(_chat_ids),
            "stats": _stats,
        }, ensure_ascii=False))
    except Exception as e:
        log.error("save state: %s", e)


def _load_state() -> None:
    if not STATE_FILE.exists():
        return
    try:
        data = json.loads(STATE_FILE.read_text())
        _chat_ids.update(data.get("chat_ids", []))
        _stats.update(data.get("stats", {}))
        log.info("loaded state: %d chats, %d bets", len(_chat_ids), _stats["bets_placed"])
    except Exception as e:
        log.error("load state: %s", e)


# ── Helpers ─────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_log(entry: dict) -> None:
    entry.setdefault("ts", _now())
    _logs.append(entry)
    if len(_logs) > MAX_LOGS:
        _logs[:] = _logs[-MAX_LOGS:]


def _format_log(entry: dict) -> str:
    level = entry.get("level", "info")
    icon = LEVEL_ICONS.get(level, "\u2139\ufe0f")
    ts = entry.get("ts", "")[:19].replace("T", " ")
    text = entry.get("text", "")

    parts = [f"{icon} <b>{level.upper()}</b>  <i>{ts}</i>"]
    if text:
        parts.append(text)

    if "bet" in entry:
        b = entry["bet"]
        if "coupon" in b:
            parts.append(f"Coupon: {b['coupon']}")
        if "selections" in b:
            parts.append(f"Selections: {b['selections']}")
        if "stake" in b:
            parts.append(f"Stake: {b['stake']}")
        if "room" in b:
            parts.append(f"Room: {b['room']}")
        if "result" in b:
            parts.append(f"Result: {b['result']}")

    return "\n".join(parts)


async def _broadcast(text: str, photo: bytes | None = None) -> None:
    for cid in list(_chat_ids):
        try:
            if photo:
                await bot.send_photo(
                    cid,
                    BufferedInputFile(photo, filename="screen.png"),
                    caption=text[:1024],
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(cid, text[:4096], parse_mode="HTML")
        except Exception as e:
            log.error("broadcast to %s: %s", cid, e)


# ── HTTP API ────────────────────────────────────────────────────────

async def api_health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "logs": len(_logs),
        "chats": len(_chat_ids),
        "stats": _stats,
    })


async def api_log(request: web.Request) -> web.Response:
    """POST /api/log  {"level": "info|success|error|warning", "text": "..."}"""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    level = data.get("level", "info")
    text = data.get("text", "")
    if not text:
        return web.json_response({"error": "text is required"}, status=400)

    if level == "error":
        _stats["errors"] += 1
        _save_state()

    entry = {"level": level, "text": text, "ts": _now()}
    _add_log(entry)
    await _broadcast(_format_log(entry))
    return web.json_response({"ok": True})


async def api_screenshot(request: web.Request) -> web.Response:
    """POST /api/screenshot  {"image": "<base64>", "caption": "..."}  or raw PNG body."""
    global _last_screenshot

    if "json" in (request.content_type or ""):
        data = await request.json()
        image = base64.b64decode(data.get("image", ""))
        caption = data.get("caption", "")
    else:
        image = await request.read()
        caption = request.query.get("caption", "")

    if not image:
        return web.json_response({"error": "no image data"}, status=400)

    _last_screenshot = image
    label = f"\ud83d\udcf8 {caption}" if caption else "\ud83d\udcf8 Screenshot"
    entry = {"level": "info", "text": label, "ts": _now()}
    _add_log(entry)
    await _broadcast(label, photo=image)
    return web.json_response({"ok": True})


async def api_bet(request: web.Request) -> web.Response:
    """POST /api/bet  {
        "coupon": "...", "selections": {...}, "stake": "5",
        "room": "Wooden", "status": "placed|won|lost|error",
        "text": "...", "screenshot": "<base64>"
    }"""
    global _last_screenshot

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    status = data.get("status", "placed")
    level_map = {"placed": "bet", "won": "win", "lost": "loss", "error": "error"}
    level = level_map.get(status, "bet")

    if status == "placed":
        _stats["bets_placed"] += 1
    elif status == "won":
        _stats["bets_won"] += 1
    elif status == "lost":
        _stats["bets_lost"] += 1
    if status == "error" or level == "error":
        _stats["errors"] += 1
    _save_state()

    entry = {
        "level": level,
        "text": data.get("text", ""),
        "bet": {k: v for k, v in data.items() if k not in ("text", "screenshot")},
        "ts": _now(),
    }
    _add_log(entry)

    photo = None
    if "screenshot" in data:
        photo = base64.b64decode(data["screenshot"])
        _last_screenshot = photo

    await _broadcast(_format_log(entry), photo=photo)
    return web.json_response({"ok": True})


# ── Telegram commands ───────────────────────────────────────────────

@router.message(Command("start"))
async def h_start(msg: Message):
    cid = msg.chat.id
    registered = cid not in _chat_ids

    if registered:
        _chat_ids.add(cid)
        _save_state()

    status = f"\u2705 Chat <code>{cid}</code> registered for logs.\n\n" if registered else ""

    await msg.answer(
        f"{status}"
        "<b>BFS Log Bot</b> \u2014 betting activity monitor\n\n"
        "This bot receives logs from your MCP agent and "
        "forwards them here: bets, errors, screenshots.\n\n"
        "<b>Setup MCP integration:</b>\n"
        "Replace <code>bfs-mcp</code> with <code>bfs-bot-mcp</code> in your MCP config \u2014 "
        "all agent actions will auto-log here.\n\n"
        "<b>Commands:</b>\n"
        "/logs \u2014 recent log entries\n"
        "/logs N \u2014 last N entries\n"
        "/stats \u2014 betting statistics\n"
        "/screen \u2014 last screenshot\n"
        "/chatid \u2014 show chat ID\n\n"
        f"<b>HTTP API:</b> <code>http://{API_HOST}:{API_PORT}</code>",
        parse_mode="HTML",
    )


@router.message(Command("chatid"))
async def h_chatid(msg: Message):
    await msg.answer(f"Chat ID: <code>{msg.chat.id}</code>", parse_mode="HTML")


@router.message(Command("logs"))
async def h_logs(msg: Message):
    args = (msg.text or "").split()
    n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    n = min(n, 50)

    if not _logs:
        await msg.answer("No logs yet. Waiting for events from your agent...")
        return

    recent = _logs[-n:]
    lines = [_format_log(e) for e in recent]
    text = "\n\n".join(lines)

    for chunk_start in range(0, len(text), 4096):
        await msg.answer(text[chunk_start:chunk_start + 4096], parse_mode="HTML")


@router.message(Command("stats"))
async def h_stats(msg: Message):
    total = _stats["bets_placed"]
    won = _stats["bets_won"]
    lost = _stats["bets_lost"]
    errors = _stats["errors"]
    winrate = f"{won / total * 100:.0f}%" if total > 0 else "\u2014"

    await msg.answer(
        f"\ud83d\udcca <b>Statistics</b>\n\n"
        f"Bets placed: {total}\n"
        f"Won: {won}  |  Lost: {lost}\n"
        f"Win rate: {winrate}\n"
        f"Errors: {errors}\n"
        f"Log entries: {len(_logs)}",
        parse_mode="HTML",
    )


@router.message(Command("screen"))
async def h_screen(msg: Message):
    if _last_screenshot:
        await msg.answer_photo(
            BufferedInputFile(_last_screenshot, filename="screen.png"),
        )
    else:
        await msg.answer("No screenshots yet.")


# ── Main ────────────────────────────────────────────────────────────

async def _main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_state()

    app = web.Application()
    app.router.add_get("/api/health", api_health)
    app.router.add_post("/api/log", api_log)
    app.router.add_post("/api/screenshot", api_screenshot)
    app.router.add_post("/api/bet", api_bet)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, API_HOST, API_PORT)
    await site.start()
    log.info("API: http://%s:%s", API_HOST, API_PORT)

    log.info("Telegram polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()

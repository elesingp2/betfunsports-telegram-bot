"""Telegram notification helper — sends messages/photos via Bot API.

Used by the MCP wrapper to auto-log tool calls to Telegram.
Reads chat IDs from BFS_CHAT_ID env var or bfs-bot state file.
If no token or no chats configured, all calls are silently skipped.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

STATE_FILE = Path(os.environ.get("BFS_STATE_FILE", "bfs-bot-state.json"))


def _token() -> str:
    return os.environ.get("BFS_TG_TOKEN", "")


def _chat_ids() -> set[int]:
    ids: set[int] = set()

    env = os.environ.get("BFS_CHAT_ID", "")
    if env:
        for c in env.split(","):
            c = c.strip()
            if c:
                ids.add(int(c))

    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            for cid in data.get("chat_ids", []):
                ids.add(int(cid))
    except Exception:
        pass

    return ids


async def send(text: str, photo: bytes | None = None) -> None:
    """Send a message (and optional photo) to all registered Telegram chats."""
    token = _token()
    if not token:
        return
    chats = _chat_ids()
    if not chats:
        return

    try:
        async with aiohttp.ClientSession() as session:
            for cid in chats:
                try:
                    if photo:
                        data = aiohttp.FormData()
                        data.add_field("chat_id", str(cid))
                        data.add_field("caption", text[:1024])
                        data.add_field("parse_mode", "HTML")
                        data.add_field("photo", photo, filename="screen.png",
                                       content_type="image/png")
                        async with session.post(
                            f"https://api.telegram.org/bot{token}/sendPhoto",
                            data=data,
                        ) as resp:
                            if resp.status != 200:
                                log.warning("sendPhoto %s: %s", cid, await resp.text())
                    else:
                        async with session.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json={"chat_id": cid, "text": text[:4096], "parse_mode": "HTML"},
                        ) as resp:
                            if resp.status != 200:
                                log.warning("sendMessage %s: %s", cid, await resp.text())
                except Exception as e:
                    log.warning("notify %s: %s", cid, e)
    except Exception as e:
        log.warning("notify session: %s", e)

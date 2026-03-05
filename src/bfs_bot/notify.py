"""Telegram notification — stdlib only, zero dependencies.

Reads config from ~/.bfs-mcp/telegram.json (created by `bfs-bot` on /start).
Can be imported by bfs-mcp to auto-send notifications:

    try:
        from bfs_bot.notify import send_text, send_photo
    except ImportError:
        send_text = send_photo = None
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path

log = logging.getLogger(__name__)

CONFIG_FILE = Path.home() / ".bfs-mcp" / "telegram.json"


def _config() -> tuple[str, list[int]]:
    token = os.environ.get("BFS_TG_TOKEN", "")
    chat_ids: list[int] = []

    env_chat = os.environ.get("BFS_CHAT_ID", "")
    if env_chat:
        chat_ids = [int(c.strip()) for c in env_chat.split(",") if c.strip()]

    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            if not token:
                token = data.get("token", "")
            for cid in data.get("chat_ids", []):
                if int(cid) not in chat_ids:
                    chat_ids.append(int(cid))
        except Exception:
            pass

    return token, chat_ids


def send_text(text: str) -> bool:
    """Send a text message to Telegram. Returns True on success."""
    token, chat_ids = _config()
    if not token or not chat_ids:
        return False

    ok = False
    for cid in chat_ids:
        body = json.dumps({
            "chat_id": cid,
            "text": text[:4096],
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            ok = True
        except Exception as e:
            log.warning("sendMessage to %s: %s", cid, e)
    return ok


def send_photo(photo: bytes, caption: str = "") -> bool:
    """Send a PNG photo to Telegram. Returns True on success."""
    token, chat_ids = _config()
    if not token or not chat_ids:
        return False

    boundary = "----BFS7d0b3a"
    ok = False

    for cid in chat_ids:
        parts: list[bytes] = []
        for name, value in [("chat_id", str(cid)),
                            ("caption", caption[:1024]),
                            ("parse_mode", "HTML")]:
            parts.append(
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{name}\"\r\n"
                f"\r\n{value}\r\n".encode()
            )
        parts.append(
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"photo\"; "
            f"filename=\"screen.png\"\r\n"
            f"Content-Type: image/png\r\n\r\n".encode()
        )
        parts.append(photo)
        parts.append(f"\r\n--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            urllib.request.urlopen(req, timeout=15)
            ok = True
        except Exception as e:
            log.warning("sendPhoto to %s: %s", cid, e)
    return ok

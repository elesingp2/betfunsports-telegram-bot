"""bfs-log — send notifications to Telegram from the command line.

Reads config from ~/.bfs-mcp/telegram.json (created by `bfs-bot` on /start).

Examples:
    bfs-log "Agent started"
    bfs-log -l error "Login failed: invalid credentials"
    bfs-log -l success "Bet placed on Team A vs Team B"
    bfs-log -s screenshot.png "Error on checkout page"
"""

from __future__ import annotations

import argparse
import sys

from .notify import send_text, send_photo

ICONS = {
    "info": "\u2139\ufe0f",
    "success": "\u2705",
    "error": "\u274c",
    "warning": "\u26a0\ufe0f",
}


def main():
    p = argparse.ArgumentParser(prog="bfs-log", description="Send notification to Telegram")
    p.add_argument("text", nargs="?", default="", help="message text")
    p.add_argument("-l", "--level", default="info",
                   choices=["info", "success", "error", "warning"])
    p.add_argument("-s", "--screenshot", metavar="FILE", help="attach a PNG screenshot")
    args = p.parse_args()

    if not args.text and not args.screenshot:
        p.error("provide text or --screenshot")

    icon = ICONS.get(args.level, "")
    text = f"{icon} {args.text}" if args.text else ""

    if args.screenshot:
        try:
            with open(args.screenshot, "rb") as f:
                photo = f.read()
        except FileNotFoundError:
            print(f"File not found: {args.screenshot}", file=sys.stderr)
            sys.exit(1)
        ok = send_photo(photo, caption=text)
    else:
        ok = send_text(text)

    if ok:
        print("sent")
    else:
        print("not sent (no config? run bfs-bot and send /start)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

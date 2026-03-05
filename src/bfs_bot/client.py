"""bfs-log — CLI for sending log entries to BFS Log Bot.

Uses only stdlib (urllib) so it works without installing extra dependencies.

Examples:
    bfs-log "Agent started, connecting to betfunsports.com"
    bfs-log -l error "Login failed: invalid credentials"
    bfs-log -l success "Bet placed on Team A vs Team B"
    bfs-log -s screenshot.png "Error on checkout page"
    bfs-log --bet-coupon "/football/123" --bet-status placed --bet-stake 5 --bet-room Wooden
    bfs-log -s result.png --bet-status won "Won 12.5 EUR"
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.request
import urllib.error


def _post(url: str, data: dict) -> dict:
    body = json.dumps(data, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        print("Is bfs-bot running?", file=sys.stderr)
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(
        prog="bfs-log",
        description="Send log entries to BFS Log Bot",
    )
    p.add_argument("text", nargs="?", default="", help="log message text")
    p.add_argument("-l", "--level", default="info",
                   choices=["info", "success", "error", "warning"],
                   help="log level (default: info)")
    p.add_argument("-s", "--screenshot", metavar="FILE",
                   help="attach a screenshot PNG")
    p.add_argument("--url", default="http://127.0.0.1:9867",
                   help="bot API URL (default: http://127.0.0.1:9867)")

    g = p.add_argument_group("bet logging")
    g.add_argument("--bet-coupon", metavar="PATH", help="coupon path")
    g.add_argument("--bet-status", choices=["placed", "won", "lost", "error"],
                   help="bet status")
    g.add_argument("--bet-stake", metavar="AMT", help="stake amount")
    g.add_argument("--bet-room", metavar="ROOM", help="room name")
    g.add_argument("--bet-selections", metavar="JSON",
                   help='selections as JSON, e.g. \'{"1": "8"}\'')

    args = p.parse_args()

    if args.bet_coupon or args.bet_status:
        data: dict = {"text": args.text, "status": args.bet_status or "placed"}
        if args.bet_coupon:
            data["coupon"] = args.bet_coupon
        if args.bet_stake:
            data["stake"] = args.bet_stake
        if args.bet_room:
            data["room"] = args.bet_room
        if args.bet_selections:
            data["selections"] = json.loads(args.bet_selections)
        if args.screenshot:
            with open(args.screenshot, "rb") as f:
                data["screenshot"] = base64.b64encode(f.read()).decode()
        result = _post(f"{args.url}/api/bet", data)

    elif args.screenshot:
        with open(args.screenshot, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        result = _post(f"{args.url}/api/screenshot", {
            "image": img_b64,
            "caption": args.text,
        })

    else:
        if not args.text:
            p.error("text is required (or use --screenshot / --bet-*)")
        result = _post(f"{args.url}/api/log", {
            "level": args.level,
            "text": args.text,
        })

    print(json.dumps(result))


if __name__ == "__main__":
    main()

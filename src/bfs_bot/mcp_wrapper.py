"""BFS MCP Server with Telegram notifications.

Drop-in replacement for bfs-mcp.  Same 14 tools, same BFSBrowser,
but every action is automatically logged to your Telegram chat.

MCP config:
  { "mcpServers": { "bfs": { "command": "bfs-bot-mcp" } } }

Requires BFS_TG_TOKEN env var and a registered chat
(run `bfs-bot`, send /start in Telegram).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from bfs_mcp.browser import BFSBrowser

from . import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

try:
    import bfs_mcp
    _SKILL = (Path(bfs_mcp.__file__).parent / "skill.md").read_text(encoding="utf-8")
except Exception:
    _SKILL = ""

mcp = FastMCP("bfs", instructions=_SKILL)

_b = BFSBrowser()
_j = lambda x: json.dumps(x, ensure_ascii=False, default=str)


async def _e():
    await _b.start()


async def _ss() -> bytes | None:
    """Safe screenshot — returns None on failure."""
    try:
        return await _b.screenshot_bytes(False)
    except Exception:
        return None


async def _notify(text: str, photo: bytes | None = None) -> None:
    """Fire-and-forget notification (never raises)."""
    try:
        await notify.send(text, photo)
    except Exception as e:
        log.warning("notify: %s", e)


# ── Auth ─────────────────────────────────────────────────────────────

@mcp.tool()
async def bfs_register(username: str, email: str, password: str,
                       first_name: str, last_name: str, birth_date: str,
                       phone: str, country_code: str = "US",
                       city: str = "", address: str = "", zip_code: str = "") -> str:
    """Register a new account on betfunsports.com.
    birth_date: DD/MM/YYYY. country_code: ISO 2-letter.
    Password: min 8 chars, mix of upper/lower/numbers/symbols.
    After registration, user must confirm email via link.
    New accounts get 100 free BFS. Credentials are auto-saved on success."""
    await _e()
    r = await _b.register(username, email, password, first_name, last_name,
                          birth_date, phone, country_code, city, address, zip_code)
    if r.get("success"):
        await _notify(f"\u2705 <b>REGISTERED</b>\nUsername: {username}\nEmail: {email}")
    else:
        errs = r.get("errors") or [r.get("error", "unknown")]
        await _notify(
            f"\u274c <b>REGISTRATION FAILED</b>\n{'; '.join(str(e) for e in errs)}",
            photo=await _ss(),
        )
    return _j(r)


@mcp.tool()
async def bfs_confirm_registration(confirmation_url: str) -> str:
    """Activate a registered account by visiting the confirmation link from email."""
    await _e()
    r = await _b.confirm_registration(confirmation_url)
    if r.get("confirmed"):
        await _notify("\u2705 <b>EMAIL CONFIRMED</b> \u2014 account activated")
    else:
        await _notify("\u26a0\ufe0f <b>CONFIRMATION</b> \u2014 could not confirm", photo=await _ss())
    return _j(r)


@mcp.tool()
async def bfs_login(email: str = "", password: str = "") -> str:
    """Authenticate and get balances. Credentials are auto-saved on success.
    If email/password are empty, uses previously saved credentials.
    If 'Player already logged in' — auto-retries after logout."""
    await _e()
    if not email or not password:
        creds = BFSBrowser.load_credentials()
        if creds:
            email, password = creds["email"], creds["password"]
        else:
            await _notify("\u274c <b>LOGIN</b> \u2014 no credentials")
            return _j({"error": "No credentials provided and none saved. "
                        "Pass email and password, or register first."})

    r = await _b.login(email, password)

    if r.get("authenticated"):
        user = r.get("username", email)
        eur = r.get("balance_eur", "?")
        bfs = r.get("balance_bfs", "?")
        await _notify(f"\u2705 <b>LOGIN</b>: {user}\nEUR: {eur} | BFS: {bfs}")
    else:
        await _notify(
            f"\u274c <b>LOGIN FAILED</b>\n{r.get('error', 'unknown')}",
            photo=await _ss(),
        )
    return _j(r)


@mcp.tool()
async def bfs_logout() -> str:
    """End session."""
    await _e()
    r = await _b.logout()
    await _notify("\ud83d\udeaa <b>LOGOUT</b>")
    return _j(r)


@mcp.tool()
async def bfs_auth_status() -> str:
    """Check if logged in and get current balances (EUR, BFS, in-game).
    Call this first — if session cookies are valid, no login needed."""
    await _e()
    await _b.goto("/")
    s = await _b.state()
    if s.authenticated:
        await _notify(
            f"\u2139\ufe0f <b>STATUS</b>: {s.username}\n"
            f"EUR: {s.balance_eur} | BFS: {s.balance_bfs} | In game: {s.in_game}"
        )
    else:
        await _notify("\u2139\ufe0f <b>STATUS</b>: not authenticated")
    return _j(s.to_dict())


# ── Betting ──────────────────────────────────────────────────────────

@mcp.tool()
async def bfs_coupons() -> str:
    """List all available sports coupons. Returns [{path, label}] — use path in bfs_coupon_details."""
    await _e()
    r = await _b.list_sports()
    await _notify(f"\ud83d\udccb <b>COUPONS</b>: {len(r)} available")
    return _j(r)


@mcp.tool()
async def bfs_coupon_details(path: str) -> str:
    """Get coupon details: events, outcomes, rooms, stakes. ALWAYS call before placing a bet.
    Example: bfs_coupon_details("/FOOTBALL/spainPrimeraDivision/18638")"""
    await _e()
    r = await _b.bet_info(path)
    title = r.get("title", path)
    if r.get("error"):
        await _notify(f"\u26a0\ufe0f <b>COUPON</b>: {title}\n{r['error']}")
    else:
        await _notify(f"\ud83d\udd0d <b>COUPON</b>: {title}\nEvents: {len(r.get('events', []))}")
    return _j(r)


@mcp.tool()
async def bfs_place_bet(coupon_path: str, selections: str | dict,
                        room_index: int = 0, stake: str = "") -> str:
    """Place a bet on a coupon.
    - coupon_path: from bfs_coupon_details
    - selections: JSON {"eventId": "outcomeCode"} — for 1X2: "8"=home, "9"=draw, "10"=away
    - room_index: 0=Wooden(BFS,free) 1=Bronze(1-5\u20ac) 2=Silver(10-50\u20ac) 3=Golden(100-500\u20ac)
    - stake: amount string. Empty = room default."""
    await _e()
    sel = json.loads(selections) if isinstance(selections, str) else selections
    r = await _b.place_bet(coupon_path, sel, room_index, stake or None)

    ss = await _ss()
    if r.get("success"):
        room_label = r.get("room", "?")
        actual_stake = r.get("stake", "?")
        codes = {"8": "1 (home)", "9": "X (draw)", "10": "2 (away)"}
        sel_text = ", ".join(codes.get(str(v), str(v)) for v in sel.values())
        await _notify(
            f"\ud83c\udfaf <b>BET PLACED</b>\n"
            f"Coupon: {coupon_path}\n"
            f"Picks: {sel_text}\n"
            f"Room: {room_label} | Stake: {actual_stake}",
            photo=ss,
        )
    else:
        await _notify(
            f"\u274c <b>BET FAILED</b>\n{r.get('error', 'unknown')}\nCoupon: {coupon_path}",
            photo=ss,
        )
    return _j(r)


# ── Monitoring ───────────────────────────────────────────────────────

@mcp.tool()
async def bfs_active_bets() -> str:
    """Get active (unresolved) bets waiting for results."""
    await _e()
    r = await _b.active_bets()
    first_line = r.strip().split("\n")[0] if r.strip() else "none"
    await _notify(f"\ud83d\udcca <b>ACTIVE BETS</b>\n{first_line}")
    return r


@mcp.tool()
async def bfs_bet_history() -> str:
    """Get full bet history. Use for strategy analysis."""
    await _e()
    r = await _b.bet_history()
    first_line = r.strip().split("\n")[0] if r.strip() else "none"
    await _notify(f"\ud83d\udcdc <b>BET HISTORY</b>\n{first_line}")
    return r


@mcp.tool()
async def bfs_account() -> str:
    """Get account details: name, email, balances."""
    await _e()
    return _j(await _b.account_info())


@mcp.tool()
async def bfs_payment_methods() -> str:
    """View deposit and withdrawal methods with fees."""
    await _e()
    await _b.goto("/paymentmethods")
    return (await _b.text("#row-content"))[:4000]


@mcp.tool()
async def bfs_screenshot(full_page: bool = False) -> Image:
    """Take a screenshot of the current browser page and return it as an image.
    full_page=False (default) captures the visible viewport — fast and reliable.
    full_page=True captures the entire scrollable page — slower, may timeout on heavy pages.
    If full_page times out, automatically falls back to viewport capture."""
    await _e()
    try:
        data = await _b.screenshot_bytes(full_page)
    except Exception as exc:
        raise ValueError(
            f"Screenshot failed: {exc}. "
            "Try again with full_page=False, or navigate to a page first "
            "(e.g. bfs_auth_status) to let the browser finish loading."
        ) from exc
    await _notify("\ud83d\udcf8 <b>SCREENSHOT</b>", photo=data)
    return Image(data=data, format="png")


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

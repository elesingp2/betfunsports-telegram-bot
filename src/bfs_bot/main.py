"""BFS Telegram Bot — LLM agent that drives betfunsports.com via headless browser."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import traceback
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from openai import AsyncOpenAI

from bfs_mcp.browser import BFSBrowser

log = logging.getLogger(__name__)

TG_TOKEN = os.environ["BFS_TG_TOKEN"]
LLM_KEY = os.environ["BFS_LLM_KEY"]
LLM_BASE = os.environ.get("BFS_LLM_BASE", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("BFS_LLM_MODEL", "deepseek/deepseek-chat")
MAX_HISTORY = int(os.environ.get("BFS_MAX_HISTORY", "30"))
MAX_ITER = int(os.environ.get("BFS_MAX_ITER", "8"))

bot = Bot(token=TG_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
bm = BFSBrowser()
llm = AsyncOpenAI(base_url=LLM_BASE, api_key=LLM_KEY)
conversations: dict[int, list[dict]] = {}


def _td(name: str, desc: str, props: dict[str, Any] | None = None, req: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": {}}
    for k, v in (props or {}).items():
        schema["properties"][k] = {"type": v} if isinstance(v, str) else v
    if req:
        schema["required"] = req
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": schema}}


TOOLS = [
    _td("bfs_register",
        "Register a new account. New users get 100 free BFS. Password: min 8 chars, mixed case+numbers+symbols. birth_date: DD/MM/YYYY. "
        "After registration, user must confirm email via link.",
        {"username": "string", "email": "string", "password": "string",
         "first_name": "string", "last_name": "string", "birth_date": "string",
         "phone": "string", "country_code": {"type": "string", "default": "US"},
         "city": {"type": "string", "default": ""}, "address": {"type": "string", "default": ""},
         "zip_code": {"type": "string", "default": ""}},
        ["username", "email", "password", "first_name", "last_name", "birth_date", "phone"]),
    _td("bfs_confirm_registration",
        "Activate account by visiting the confirmation URL from the email.",
        {"confirmation_url": "string"}, ["confirmation_url"]),
    _td("bfs_login", "Authenticate. Returns balances. Auto-retries if 'Player already logged in'.",
        {"email": "string", "password": "string"}, ["email", "password"]),
    _td("bfs_logout", "End session."),
    _td("bfs_state", "Check auth + balances (EUR, BFS, in-game). ALWAYS call first."),
    _td("bfs_active_bets", "Get active (unresolved) bets."),
    _td("bfs_list_sports", "List available coupons. Returns [{path, label}]."),
    _td("bfs_bet_info", "Get coupon details: events, outcomes, rooms. ALWAYS call before betting.",
        {"path": "string"}, ["path"]),
    _td("bfs_place_bet",
        "Place a bet. selections={eventId: outcomeCode}. 1X2: '8'=home, '9'=draw, '10'=away. "
        "Rooms: 0=Wooden(free) 1=Bronze(1-5EUR) 2=Silver(10-50EUR) 3=Golden(100-500EUR).",
        {"coupon_path": "string",
         "selections": {"type": "object", "additionalProperties": {"type": "string"}},
         "room_index": {"type": "integer", "default": 0},
         "stake": {"type": "string", "default": ""}},
        ["coupon_path", "selections"]),
    _td("bfs_bet_history", "Get full bet history. Use for analysis."),
    _td("bfs_account", "Get account details."),
    _td("bfs_screenshot", "Take a screenshot and send it to the user.",
        {"full_page": {"type": "boolean", "default": False}}),
]

SYSTEM = """\
Ты — AI-агент платформы Betfunsports. Используй tool calls для ВСЕХ действий.
Отвечай на русском, кратко.

## Betfunsports
P2P платформа спортивных прогнозов. Ставки формируют призовой пул, 100% распределяется между победителями.
- 50% ставок выигрывают (по точности 0-100 баллов)
- Выигрыш = точность * ставка (мин. коэфф. 1.3)
- 100 баллов = всегда выигрыш

## Столы
- Wooden (0) — BFS бесплатно, 1-10, 0%
- Bronze (1) — EUR, 1-5, 10%
- Silver (2) — EUR, 10-50, 7.5%
- Golden (3) — EUR, 100-500, 5%

## 1X2 коды: "8"=дом, "9"=ничья, "10"=гость

## Порядок
1. bfs_state → auth?
2. bfs_login → если надо
3. bfs_list_sports → купоны
4. bfs_bet_info(path) → ОБЯЗАТЕЛЬНО перед ставкой
5. bfs_place_bet → ставка
6. bfs_state → баланс

## Правила
- Новичкам → Wooden (бесплатно)
- Закрытый купон → предложи другой
- Скриншот только по запросу пользователя"""


async def _exec(name: str, args: dict) -> tuple[str, bytes | None]:
    await bm.start()
    j = lambda x: json.dumps(x, ensure_ascii=False, default=str)

    match name:
        case "bfs_register":
            return j(await bm.register(
                args["username"], args["email"], args["password"],
                args["first_name"], args["last_name"], args["birth_date"],
                args["phone"], args.get("country_code", "US"),
                args.get("city", ""), args.get("address", ""), args.get("zip_code", ""),
            )), None
        case "bfs_confirm_registration":
            return j(await bm.confirm_registration(args["confirmation_url"])), None
        case "bfs_login":
            return j(await bm.login(args["email"], args["password"])), None
        case "bfs_logout":
            return j(await bm.logout()), None
        case "bfs_state":
            return j((await bm.state()).to_dict()), None
        case "bfs_active_bets":
            return (await bm.active_bets())[:4000], None
        case "bfs_list_sports":
            return j(await bm.list_sports())[:4000], None
        case "bfs_bet_info":
            return j(await bm.bet_info(args["path"]))[:4000], None
        case "bfs_place_bet":
            r = await bm.place_bet(args["coupon_path"], args["selections"],
                                   args.get("room_index", 0), args.get("stake") or None)
            return j(r)[:4000], None
        case "bfs_bet_history":
            return (await bm.bet_history())[:4000], None
        case "bfs_account":
            return j(await bm.account_info())[:4000], None
        case "bfs_screenshot":
            return "[screenshot]", await bm.screenshot_bytes(args.get("full_page", False))
        case _:
            return f"unknown tool: {name}", None


async def _agent(chat_id: int, user_text: str, msg: Message) -> None:
    hist = conversations.setdefault(chat_id, [])
    hist.append({"role": "user", "content": user_text})
    if len(hist) > MAX_HISTORY:
        hist[:] = hist[-MAX_HISTORY:]

    msgs = [{"role": "system", "content": SYSTEM}] + hist
    screenshot: bytes | None = None
    status_msg = await msg.answer("\u2026")
    final = ""

    for i in range(MAX_ITER):
        try:
            resp = await llm.chat.completions.create(
                model=LLM_MODEL, messages=msgs, tools=TOOLS,
                tool_choice="auto", max_tokens=1024, temperature=0.3,
            )
        except Exception as e:
            log.error("LLM: %s", e)
            await status_msg.edit_text(f"LLM error: {e}")
            return

        choice = resp.choices[0].message
        msgs.append(choice.model_dump(exclude_none=True))

        if not choice.tool_calls:
            final = choice.content or ""
            hist.append({"role": "assistant", "content": final})
            break

        for tc in choice.tool_calls:
            fn = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            log.info("tool: %s(%s)", fn, json.dumps(args, ensure_ascii=False)[:150])
            try:
                txt, ss = await _exec(fn, args)
                if ss:
                    screenshot = ss
            except Exception as e:
                txt = f"error: {e}"
                log.error("tool error: %s", traceback.format_exc())
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": txt[:4000]})

        try:
            await status_msg.edit_text(f"\u2026 {i+1}/{MAX_ITER}")
        except Exception:
            pass
    else:
        final = "\u041b\u0438\u043c\u0438\u0442 \u0438\u0442\u0435\u0440\u0430\u0446\u0438\u0439."
        hist.append({"role": "assistant", "content": final})

    try:
        await status_msg.edit_text(final[:4096])
    except Exception:
        for c in range(0, len(final), 4096):
            await msg.answer(final[c:c+4096])

    if screenshot:
        try:
            await msg.answer_photo(BufferedInputFile(screenshot, filename="screen.png"))
        except Exception as e:
            log.error("photo: %s", e)


@router.message(Command("start"))
async def h_start(msg: Message):
    await msg.answer(
        "BFS Agent \u2014 \u0443\u043f\u0440\u0430\u0432\u043b\u044f\u044e betfunsports.com\n\n"
        "\u041f\u0440\u0438\u043c\u0435\u0440\u044b:\n"
        "\u2022 \u00ab\u0417\u0430\u043b\u043e\u0433\u0438\u043d\u044c\u0441\u044f \u043a\u0430\u043a user@mail.com \u043f\u0430\u0440\u043e\u043b\u044c\u00bb\n"
        "\u2022 \u00ab\u041a\u0430\u043a\u0438\u0435 \u043a\u0443\u043f\u043e\u043d\u044b \u0435\u0441\u0442\u044c?\u00bb\n"
        "\u2022 \u00ab\u041f\u043e\u0441\u0442\u0430\u0432\u044c \u043d\u0430 \u043f\u043e\u0431\u0435\u0434\u0443 \u0445\u043e\u0437\u044f\u0435\u0432\u00bb\n"
        "\u2022 \u00ab\u041c\u043e\u0439 \u0431\u0430\u043b\u0430\u043d\u0441\u00bb\n\n"
        "/clear \u2014 \u0441\u0431\u0440\u043e\u0441  /screen \u2014 \u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442",
    )


@router.message(Command("clear"))
async def h_clear(msg: Message):
    conversations.pop(msg.chat.id, None)
    await msg.answer("\u2705 \u0418\u0441\u0442\u043e\u0440\u0438\u044f \u043e\u0447\u0438\u0449\u0435\u043d\u0430.")


@router.message(Command("screen"))
async def h_screen(msg: Message):
    await bm.start()
    await msg.answer_photo(BufferedInputFile(await bm.screenshot_bytes(), filename="s.png"))


@router.message()
async def h_msg(msg: Message):
    if msg.text:
        await _agent(msg.chat.id, msg.text, msg)


async def _main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("starting (model=%s)", LLM_MODEL)
    await bm.start()
    await bm.goto("/")
    log.info("polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bm.stop()


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()

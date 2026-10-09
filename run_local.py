"""Локальный автозапуск бота на вашем ПК.

Запустите двойным кликом по «Запуск бота.bat» (или `py -3 run_local.py`):
бот сам проверяет цены каждые CHECK_INTERVAL_MINUTES минут и присылает
в Telegram только новые выгодные предложения. Уведомления об изменении
цен убраны — только сделки.

Если Telegram недоступен (блок сети) — уведомления уходят в Discord
(вебхук в .env: DISCORD_WEBHOOK_URL). Можно также включить свой
VPN/прокси-клиент: бот найдёт его сам (порты 10809/10808/7890/7897...)
или задайте PROXY_URL в файле .env — тогда сообщения пойдут в Telegram.
Если недоступны оба канала, сделки копятся в очереди и отправятся позже.

`py -3 run_local.py --once` — ровно одна проверка и выход (для тестов).
"""
import asyncio
import socket
import sys
import time

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import requests

import bot
from bot import format_deal_card, run_check
from config import (
    BOT_TOKEN, PROXY_URL, GAMES, CHECK_INTERVAL_MINUTES,
    PRICE_THRESHOLD_PERCENT, NOTIFY_USER_IDS, DISCORD_WEBHOOK_URL,
)

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Кандидаты на локальный прокси (v2rayN, NekoRay, Clash и т.п.)
PROXY_CANDIDATES = [
    "http://127.0.0.1:10809",     # v2rayN / NekoRay — HTTP
    "socks5://127.0.0.1:10808",   # v2rayN / NekoRay — SOCKS
    "http://127.0.0.1:7890",      # Clash
    "http://127.0.0.1:7897",      # Clash Verge
    "http://127.0.0.1:1080",      # классический HTTP
    "socks5://127.0.0.1:1080",    # классический SOCKS
]

proxy = None          # рабочий прокси текущей сессии (None = напрямую)
telegram_up = False   # есть ли сейчас связь с Telegram
greeted = False


def _proxies(p):
    return {"http": p, "https": p} if p else None


def _tg_reachable(p, timeout=6) -> bool:
    """Есть ли связь с Telegram (getMe) выбранным способом."""
    try:
        r = requests.get(f"{TG_API}/getMe", proxies=_proxies(p), timeout=timeout)
        return bool(r.json().get("ok"))
    except Exception:
        return False


def _port_open(host, port) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def detect_proxy() -> str:
    """Найти способ достучаться до Telegram: .env -> напрямую -> локальный прокси."""
    global proxy, telegram_up
    # 1) явный PROXY_URL в .env — пробуем первым
    if PROXY_URL:
        if _tg_reachable(PROXY_URL):
            proxy, telegram_up = PROXY_URL, True
            print(f"✅ Telegram через PROXY_URL: {PROXY_URL}")
            return proxy
        print(f"⚠️ PROXY_URL={PROXY_URL} не отвечает — пробую другие варианты...")
    # 2) напрямую (например, включённый VPN в режиме TUN)
    if _tg_reachable(None):
        proxy, telegram_up = None, True
        print("✅ Telegram доступен напрямую")
        return None
    # 3) локальные порты прокси-клиентов
    for cand in PROXY_CANDIDATES:
        host_port = cand.rsplit("//", 1)[-1]
        host, port = host_port.split(":")
        if not _port_open(host, int(port)):
            continue
        if _tg_reachable(cand):
            proxy, telegram_up = cand, True
            print(f"✅ Telegram через локальный прокси: {cand}")
            return cand
    proxy, telegram_up = None, False
    if DISCORD_WEBHOOK_URL:
        print("⏳ Telegram недоступен — уведомления пойдут в Discord.")
        print("   Включите VPN/прокси-клиент — бот снова сможет писать в Telegram.")
    else:
        print("⏳ Telegram недоступен: включите свой VPN/прокси-клиент")
        print("   или задайте DISCORD_WEBHOOK_URL в файле .env.")
        print("   Сделки не потеряются — накопятся и отправятся позже.")
    return None


def tg_send(chat_id: int, text: str) -> bool:
    """Отправить сообщение. False — Telegram недоступен (сделка останется в очереди)."""
    try:
        r = requests.post(
            f"{TG_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            proxies=_proxies(proxy),
            timeout=20,
        )
        data = r.json()
        if data.get("ok"):
            return True
        desc = data.get("description", "")
        print(f"  ❌ Telegram отклонил сообщение для {chat_id}: {desc}")
        if "chat not found" in desc or "bot was blocked" in desc:
            print("  ⚠️ Напишите боту /start в Telegram — иначе он не сможет вам писать!")
        return False
    except Exception as e:
        print(f"  ⚠️ Ошибка отправки для {chat_id}: {e}")
        return False


def _discord_chunks(s: str, limit: int = 1900):
    """Разбить длинный текст на части не длиннее лимита Discord (2000 символов)."""
    parts, cur = [], ""
    for para in s.split("\n\n"):
        cand = para if not cur else cur + "\n\n" + para
        if len(cand) > limit and cur:
            parts.append(cur)
            cur = para
        else:
            cur = cand
        while len(cur) > limit:
            parts.append(cur[:limit])
            cur = cur[limit:]
    if cur:
        parts.append(cur)
    return parts


def discord_send(text: str) -> bool:
    """Отправить сообщение в Discord-вебхук (запасной канал, если Telegram лежит)."""
    if not DISCORD_WEBHOOK_URL:
        return False
    # у Telegram **bold** пишется как *bold*, у Discord — как **bold**
    text = text.replace("*", "**")
    for part in _discord_chunks(text):
        try:
            r = requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": part, "allowed_mentions": {"parse": []}},
                timeout=20,
            )
            if r.status_code not in (200, 204):
                print(f"  ❌ Discord отклонил сообщение ({r.status_code}): {r.text[:150]}")
                return False
        except Exception as e:
            print(f"  ⚠️ Ошибка Discord: {e}")
            return False
    return True


async def maybe_greet():
    """Приветствие при первом запуске — подтверждает, что сообщения уходят."""
    global greeted
    if greeted or not NOTIFY_USER_IDS:
        return
    if await bot.db.count_deals(notified=True) > 0:
        greeted = True
        return
    hello = (
        "✅ *Бот запущен и следит за ценами!*\n\n"
        f"🎮 Игры: {', '.join(g.get('name', k) for k, g in GAMES.items())}\n"
        "🏪 Источники: GGSel, FunPay, PlayerOK\n"
        f"🔔 Пришлю, как только появится лот дешевле цен из config.py "
        f"(проверка каждые {CHECK_INTERVAL_MINUTES} мин).\n"
        "Изменения цен не рассылаю — только выгодные сделки."
    )
    if telegram_up:
        for user_id in NOTIFY_USER_IDS:
            if tg_send(user_id, hello):
                greeted = True
                print("✅ Приветствие отправлено в Telegram")
                return
    if discord_send(hello):
        greeted = True
        print("✅ Приветствие отправлено в Discord")


async def send_queue():
    """Отправить накопленные выгодные сделки. Возвращает (успешно, ошибок)."""
    ok = fail = 0
    for game_key in GAMES:
        deals = await bot.db.get_unnotified_deals(game_key, PRICE_THRESHOLD_PERCENT)
        if not deals:
            continue
        deals = deals[:5]  # не больше 5 карточек на игру за рассылку
        game_name = GAMES.get(game_key, {}).get("name", game_key)
        text = f"🔥 *Выгодные предложения — {game_name}:*\n\n"
        for deal in deals:
            text += format_deal_card(deal)

        delivered = False
        via_discord = False
        if telegram_up:
            for user_id in NOTIFY_USER_IDS:
                if tg_send(user_id, text):
                    ok += 1
                    delivered = True
                else:
                    fail += 1
        # Telegram не работает — отправляем в Discord
        if not delivered and discord_send(text):
            ok += 1
            delivered = True
            via_discord = True
        if delivered:
            for deal in deals:
                await bot.db.mark_as_notified(deal["id"])
            chan = "Discord" if via_discord else "Telegram"
            print(f"  📨 Отправлено в {chan} ({game_name}): {len(deals)}")
        else:
            print(f"  ⏳ Отложено ({game_name}): {len(deals)} — ни Telegram, ни Discord недоступны")
    return ok, fail


async def main() -> int:
    once = "--once" in sys.argv
    print("=" * 62)
    print("🤖 Roblox-бот: локальная проверка выгодных предложений")
    print(f"🎮 Игры: {', '.join(g.get('name', k) for k, g in GAMES.items())}")
    print(f"⏱ Проверка: каждые {CHECK_INTERVAL_MINUTES} минут")
    print(f"📨 Уведомления: {NOTIFY_USER_IDS or 'НЕ ЗАДАНЫ — заполните NOTIFY_USER_IDS в config.py'}")
    print(f"💬 Discord-вебхук: {'задан' if DISCORD_WEBHOOK_URL else 'не задан (DISCORD_WEBHOOK_URL в .env)'}")
    if once:
        print("⚙️ Режим --once: ровно одна проверка и выход")
    print("=" * 62)

    if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_СЮДА":
        print("❌ Укажите BOT_TOKEN в файле .env")
        return 1

    await bot.db.init()
    detect_proxy()
    await maybe_greet()

    cycle = 0
    while True:
        cycle += 1
        print(f"\n--- Проверка №{cycle} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---")
        try:
            added = await run_check()
            print(f"Новых выгодных предложений: {len(added)}")
            for d in added:
                print(f"  + [{d['source']}] {d['item_name']}: {d['price']:.0f} ₽"
                      + (f" (моя цена {d['target_price']:.0f} ₽)" if d.get('target_price') else "")
                      + f" {d['url']}")
            await maybe_greet()
            sent, fail = await send_queue()
            print(f"📨 Отправлено: {sent}, ошибок: {fail}")
            if fail or not telegram_up:
                detect_proxy()  # вдруг VPN включили или выключили
        except Exception as e:
            print(f"❌ Ошибка проверки: {e}")
        if once:
            break
        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n⏹ Бот остановлен. Запустите снова, когда понадобится.")
        sys.exit(0)

"""Одна проверка для GitHub Actions: парсинг -> БД -> отправка -> выход.

Запускается workflow'ом каждые 5 минут. Без long-polling: только уведомления.
Подписки и списки хранятся в deals.db (коммитится в репозиторий),
пользовательский список также редактируется в config.py прямо на GitHub.
"""
import asyncio
import sys

# Корректный вывод эмодзи в логах CI
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import requests

import bot
from bot import _md, format_deal_card, run_check
from config import (
    BOT_TOKEN, GAMES, NOTIFY_USER_IDS, PRICE_THRESHOLD_PERCENT, DB_PATH,
)


def tg_send(chat_id: int, text: str) -> bool:
    """Отправить сообщение через Telegram Bot API напрямую (без polling)"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=30,
        )
        data = r.json()
        if data.get("ok"):
            return True
        print(f"  Telegram отклонил сообщение для {chat_id}: {data.get('description')}")
    except Exception as e:
        print(f"  Ошибка отправки для {chat_id}: {e}")
    return False


async def main() -> int:
    print("=== Проверка выгодных предложений (GitHub Actions) ===")

    if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_СЮДА":
        print("❌ BOT_TOKEN не задан! Добавьте секрет BOT_TOKEN в Settings -> Secrets -> Actions")
        return 1

    if not NOTIFY_USER_IDS:
        print("⚠️ NOTIFY_USER_IDS пуст в config.py — некому слать уведомления")

    await bot.db.init()

    # Основная проверка: парсинг ggsel, рынок, сделки, история цен
    added = await run_check()
    print(f"Новых выгодных предложений: {len(added)}")
    for d in added:
        print(f"  + {d['item_name']}: {d['price']:.0f} ₽ (рынок {d['market_price']:.0f} ₽, "
              f"-{d['discount_percent']:.1f}%) {d['url']}")

    # Отправляем все неуведомленные сделки (в т.ч. если прошлая отправка падала)
    sent_ok, send_fail = 0, 0
    for game_key in GAMES:
        deals = await bot.db.get_unnotified_deals(game_key, PRICE_THRESHOLD_PERCENT)
        if not deals:
            continue
        deals = deals[:5]  # не больше 5 карточек на игру за рассылку

        game_name = GAMES.get(game_key, {}).get('name', game_key)
        text = f"🔥 *Выгодные предложения — {game_name}:*\n\n"
        for deal in deals:
            text += format_deal_card(deal)

        delivered = False
        for user_id in NOTIFY_USER_IDS:
            if tg_send(user_id, text):
                delivered = True
                sent_ok += 1
            else:
                send_fail += 1

        if delivered:
            for deal in deals:
                await bot.db.mark_as_notified(deal['id'])
        else:
            print(f"  Не удалось отправить сделки по игре {game_key} — останутся в очереди")

    # Оповещения о резких изменениях цен (>=15% за сутки)
    alerts = await bot.price_tracker.get_price_alerts(change_threshold=15)
    for alert in alerts[:5]:
        emoji = "📈" if alert['change_percent'] > 0 else "📉"
        text = (
            f"{emoji} *Изменение цены!*\n\n"
            f"📦 Предмет: {_md(alert['item_name'])}\n"
            f"🎮 Игра: {alert['game_name']}\n"
            f"📉 Изменение: {alert['change_percent']:+.1f}%\n"
            f"💰 Средняя цена: {alert['price']:.0f} ₽"
        )
        for user_id in NOTIFY_USER_IDS:
            if tg_send(user_id, text):
                sent_ok += 1

    print(f"Отправлено сообщений: {sent_ok}, ошибок отправки: {send_fail}")
    print(f"База: {DB_PATH}")

    # Сделки есть, а Telegram недоступен — даём красный крест в Actions
    if added and sent_ok == 0 and NOTIFY_USER_IDS:
        print("❌ Есть сделки, но ни одно сообщение не ушло — проверьте секрет BOT_TOKEN")
        return 1
    print("=== Готово ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Одна проверка для GitHub Actions: парсинг -> БД -> отправка -> выход.

Запускается workflow'ом по кнопке Run workflow. Без long-polling: только уведомления.
Подписки и списки хранятся в deals.db (коммитится в репозиторий),
пользовательский список также редактируется в config.py прямо на GitHub.

Итог каждого запуска пишется в last_run_report.txt (коммитится в репозиторий) —
по нему видно, что происходило, даже без доступа к логам Actions.
"""
import asyncio
import sys
from datetime import datetime, timezone

# Корректный вывод эмодзи в логах CI
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import requests

import bot
from bot import format_deal_card, run_check
from config import (
    BOT_TOKEN, GAMES, NOTIFY_USER_IDS, PRICE_THRESHOLD_PERCENT, DB_PATH,
)

REPORT_PATH = "last_run_report.txt"
report: list = []


def log(line: str = ""):
    """Печать в лог CI и запись в отчёт"""
    print(line)
    report.append(line)


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
        desc = data.get("description", "")
        log(f"  Telegram отклонил сообщение для {chat_id}: {desc}")
        if "chat not found" in desc or "bot was blocked" in desc:
            log("  ⚠️ Напишите боту /start в Telegram — иначе он не сможет вам писать!")
    except Exception as e:
        log(f"  Ошибка отправки для {chat_id}: {e}")
    return False


async def main() -> int:
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log(f"=== Проверка выгодных предложений (GitHub Actions) — {started} ===")

    if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_СЮДА":
        log("❌ BOT_TOKEN не задан! Добавьте секрет BOT_TOKEN в Settings -> Secrets -> Actions")
        open(REPORT_PATH, "w", encoding="utf-8").write("\n".join(report))
        return 1

    if not NOTIFY_USER_IDS:
        log("⚠️ NOTIFY_USER_IDS пуст в config.py — некому слать уведомления")

    await bot.db.init()

    # Основная проверка: парсинг (GGSel + FunPay + PlayerOK), рынок, сделки
    added = await run_check()
    log(f"Новых выгодных предложений: {len(added)}")
    for d in added:
        log(f"  + [{d['source']}] {d['item_name']}: {d['price']:.0f} ₽"
            + (f" (моя цена {d['target_price']:.0f} ₽)" if d.get('target_price') else "")
            + f" {d['url']}")

    # Диагностика: сколько сделок по источникам в базе вообще
    by_source = await bot.db.count_deals_by_source()
    total = await bot.db.count_deals()
    log(f"Всего сделок в базе: {total}" + (f" | по источникам: {by_source}" if by_source else ""))

    sent_ok, send_fail = 0, 0

    # Первый запуск: приветствие + проверка, что бот вообще может писать.
    # Если пользователь не нажал /start — Telegram вернёт «chat not found»,
    # и это будет видно в отчёте.
    notified_ever = await bot.db.count_deals(notified=True)
    if notified_ever == 0 and NOTIFY_USER_IDS:
        hello = (
            "✅ *Бот запущен и следит за ценами!*\n\n"
            f"🎮 Игры: {', '.join(g.get('name', k) for k, g in GAMES.items())}\n"
            f"🏪 Источники: GGSel, FunPay, PlayerOK\n"
            "🔔 Пришлю, как только появится лот дешевле цен из config.py.\n\n"
            "Свой список товаров: правьте config.py на GitHub "
            "(файл → ✏️ → Commit changes)."
        )
        for user_id in NOTIFY_USER_IDS:
            if tg_send(user_id, hello):
                sent_ok += 1
                log(f"Приветствие отправлено пользователю {user_id}")
            else:
                send_fail += 1

    # Отправляем все неуведомленные сделки (в т.ч. если прошлая отправка падала)
    # — каждое предложение отдельным сообщением
    for game_key in GAMES:
        deals = await bot.db.get_unnotified_deals(game_key, PRICE_THRESHOLD_PERCENT)
        if not deals:
            continue

        game_name = GAMES.get(game_key, {}).get('name', game_key)
        for deal in deals:
            text = f"🔥 *Новое предложение — {game_name}:*\n\n" + format_deal_card(deal)
            delivered = False
            for user_id in NOTIFY_USER_IDS:
                if tg_send(user_id, text):
                    delivered = True
                    sent_ok += 1
                else:
                    send_fail += 1

            if delivered:
                await bot.db.mark_as_notified(deal['id'])
                log(f"Отправлено: {deal['item_name']} {deal['price']:.0f} ₽ ({game_name})")
            else:
                log(f"  Не удалось отправить {deal['item_name']} — останется в очереди")

    log(f"Отправлено сообщений: {sent_ok}, ошибок отправки: {send_fail}")
    log(f"База: {DB_PATH}")

    # Сохраняем отчёт (его коммитит workflow — виден в репозитории)
    log("=== Готово ===")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    # Сделки есть, а ни одно сообщение не ушло — красный крест в Actions
    if (added or total) and sent_ok == 0 and send_fail > 0 and NOTIFY_USER_IDS:
        log("❌ Есть сделки, но сообщения не уходят — вероятно, боту не написали /start")
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(report))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Финальный тест бота: команды, run_check, рассылка уведомлений"""
import asyncio
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import bot
from config import GAMES, WHITELIST_USERS


async def main():
    user_id = WHITELIST_USERS[0]

    # 1) Инициализация
    await bot.db.init()
    print("[1] БД инициализирована")

    # 2) Пользовательский товар (как /additem mm2 Icepiercer 400 — уже есть в конфиге,
    #    добавим уникальный: blox Dough)
    await bot.db.add_user_item(user_id, 'blox_fruits', 'Dough', 60)
    all_items = await bot.db.get_all_user_items()
    print(f"[2] Пользовательских товаров: {all_items}")

    # 3) Подписки на все игры
    for g in GAMES:
        await bot.db.add_user_subscription(user_id, g, 20)
    users = await bot.db.get_subscribed_users('mm2')
    print(f"[3] Подписчики mm2: {users}")

    # 4) Полная проверка (реальный сетевой парсинг)
    added = await bot.run_check()
    print(f"[4] Новых сделок: {len(added)}")
    for d in added[:5]:
        card = bot.format_deal_card(d)
        print("    --- карточка ---")
        for line in card.strip().split("\n"):
            print("    " + line)

    # 5) Рассылка подписчикам (фейковый отправитель)
    sent_messages = []

    async def fake_send(chat_id, text):
        sent_messages.append((chat_id, text))

    sent = await bot.send_deals(fake_send, added)
    print(f"[5] Отправлено сообщений: {sent}, в списке: {len(sent_messages)}")
    if sent_messages:
        chat_id, text = sent_messages[0]
        assert chat_id == user_id
        print(f"    первое сообщение: {len(text)} символов, карточек: {text.count('━━━') // 2}")

    # 6) Сделки отправлены -> помечены уведомленными
    unnotified = 0
    for g in GAMES:
        unnotified += len(await bot.db.get_unnotified_deals(g, 20))
    print(f"[6] Неуведомленных сделок после рассылки (карточки >5 на игру могли остаться): {unnotified}")

    # 7) Дубли: повторная обработка тех же сделок
    dupes = 0
    for d in added:
        if await bot.db.deal_exists(d['url'], d['price']):
            dupes += 1
    print(f"[7] Сделок уже в БД (анти-дубль): {dupes}/{len(added)}")

    # 8) История цен и тренды
    tracker = bot.price_tracker
    trend = await tracker.get_price_trend('mm2', 'Icepiercer', days=7)
    alerts = await tracker.get_price_alerts(change_threshold=0)
    print(f"[8] Тренд Icepiercer: {trend} | записей истории: {len(alerts)}")

    # 9) Формат списка товаров
    print("[9] " + bot.format_user_items(await bot.db.get_user_items(user_id)))

    # 10) Проверка, что все команды зарегистрированы
    import inspect
    src = inspect.getsource(bot.main)
    for cmd in ('start', 'help', 'subscribe', 'unsubscribe', 'check',
                'deals', 'myitems', 'additem', 'adduser'):
        key = f'CommandHandler("{cmd}"'
        assert key in src, f"команда /{cmd} не зарегистрирована"
    print("[10] Все команды зарегистрированы: OK")

    print("\n✅ ФИНАЛЬНЫЙ ТЕСТ ПРОЙДЕН")


if __name__ == '__main__':
    asyncio.run(main())

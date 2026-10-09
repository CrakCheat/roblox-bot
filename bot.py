import asyncio
import logging
import re
import sys
import time

# Корректный вывод эмодзи в консоли Windows
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from database import Database
from parsers import parse_all_games, init_market_prices_with_api
from price_tracker import PriceTracker
from config import (
    BOT_TOKEN, PROXY_URL, DB_PATH, GAMES, CHECK_INTERVAL_MINUTES, PRICE_THRESHOLD_PERCENT,
    REQUIRE_TARGET_PRICE,
    SUGGEST_ITEM_ENABLED, SUGGEST_ITEM_MIN_COUNT, SUGGEST_ITEM_MIN_PRICE, 
    SUGGEST_ITEM_MAX_PRICE, WHITELIST_ENABLED, WHITELIST_USERS, ADMIN_IDS
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация
db = Database(DB_PATH)
price_tracker = PriceTracker(db)

def is_user_allowed(user_id: int) -> bool:
    """Проверка, разрешен ли пользователь"""
    if not WHITELIST_ENABLED:
        return True
    return user_id in WHITELIST_USERS


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


# Синтаксис команды /additem: короткие названия игр
GAME_ALIASES = {
    'blox': 'blox_fruits', 'bloxfruits': 'blox_fruits', 'blox_fruits': 'blox_fruits',
    'bf': 'blox_fruits', 'мм2': 'mm2', 'mm2': 'mm2', 'yba': 'yba',
}


def format_user_items(items) -> str:
    """Текст списка товаров пользователя"""
    if not items:
        return "📋 *Ваши товары:*\n\nУ вас пока нет товаров в списке."
    text = "📋 *Ваши товары:*\n\n"
    for item in items:
        game_info = GAMES.get(item['game'])
        game_name = game_info['name'] if game_info else item['game']
        text += f"• {_md(item['item_name'])} ({game_name}) - от {item['min_price']:.0f} ₽\n"
    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Проверка белого списка
    if not is_user_allowed(user.id):
        await update.message.reply_text(
            "⛔ Извините, у вас нет доступа к этому боту.\n\n"
            "Для получения доступа обратитесь к администратору."
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("🎮 Blox Fruits", callback_data='game_blox_fruits')],
        [InlineKeyboardButton("🔪 MM2", callback_data='game_mm2')],
        [InlineKeyboardButton("⭐ YBA", callback_data='game_yba')],
        [InlineKeyboardButton("📊 Мои подписки", callback_data='my_subscriptions')],
        [InlineKeyboardButton("📋 Мои товары", callback_data='my_items')],
        [InlineKeyboardButton("🔍 Проверить цены", callback_data='check_prices')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я бот для отслеживания выгодных предложений по предметам из Roblox.\n"
        f"Я помогу найти лучшие цены на предметы из:\n"
        f"• Blox Fruits\n"
        f"• Murder Mystery 2 (MM2)\n"
        f"• Your Bizarre Adventure (YBA)\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    user = update.effective_user
    
    # Проверка белого списка
    if not is_user_allowed(user.id):
        await update.message.reply_text(
            "⛔ Извините, у вас нет доступа к этому боту.\n\n"
            "Для получения доступа обратитесь к администратору."
        )
        return
    
    help_text = """
📚 *Доступные команды:*

/start - Главное меню
/help - Помощь
/subscribe - Подписаться на уведомления
/unsubscribe - Отписаться от уведомлений
/check - Проверить текущие цены
/deals - Показать последние выгодные предложения
/myitems - Показать мои товары
/additem - Добавить товар в список

📊 *Как это работает:*
1. Я проверяю цены на маркетплейсе GGSel (реальные лоты)
2. Сравниваю с рыночной ценой
3. Если нахожу выгодное предложение (дешевле на 20%+), отправляю уведомление

💡 *Советы:*
• Подпишитесь на интересующие игры
• Установите минимальный процент скидки
• Проверяйте цены регулярно
• Добавляйте свои товары в список

🎯 *Автоматическое предложение:*
Если я часто вижу товар с ценой 100-2000 ₽, я предложу добавить его в ваш список.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на уведомления"""
    user = update.effective_user
    
    # Проверка белого списка
    if not is_user_allowed(user.id):
        await update.message.reply_text(
            "⛔ Извините, у вас нет доступа к этому боту.\n\n"
            "Для получения доступа обратитесь к администратору."
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("🎮 Blox Fruits", callback_data='sub_blox_fruits')],
        [InlineKeyboardButton("🔪 MM2", callback_data='sub_mm2')],
        [InlineKeyboardButton("⭐ YBA", callback_data='sub_yba')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите игру для подписки:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Проверка белого списка
    if not is_user_allowed(user.id):
        await query.edit_message_text(
            "⛔ Извините, у вас нет доступа к этому боту.\n\n"
            "Для получения доступа обратитесь к администратору."
        )
        return
    
    data = query.data
    
    if data.startswith('game_'):
        game_key = data.replace('game_', '')
        game_info = GAMES.get(game_key)
        
        if game_info:
            # Получаем текущие предложения по игре
            deals = await db.get_unnotified_deals(game_key, PRICE_THRESHOLD_PERCENT)
            
            if deals:
                text = f"🎮 *{game_info['name']}* - Найдено {len(deals)} выгодных предложений:\n\n"
                
                for deal in deals[:5]:  # Показываем первые 5
                    text += format_deal_card(deal)
                
                if len(deals) > 5:
                    text += f"_...и ещё {len(deals) - 5} предложений_"
            else:
                text = f"🎮 *{game_info['name']}*\n\nПока нет выгодных предложений. Попробуйте позже."
            
            await query.edit_message_text(text, parse_mode='Markdown')
    
    elif data.startswith('sub_'):
        game_key = data.replace('sub_', '')
        game_info = GAMES.get(game_key)
        
        if game_info:
            # Добавляем подписку
            await db.add_user_subscription(
                query.from_user.id,
                game_key,
                PRICE_THRESHOLD_PERCENT
            )
            
            await query.edit_message_text(
                f"✅ Вы подписались на уведомления по игре *{game_info['name']}*!\n\n"
                f"Я буду отправлять вам уведомления, когда появятся предложения "
                f"со скидкой от {PRICE_THRESHOLD_PERCENT}%.",
                parse_mode='Markdown'
            )
    
    elif data == 'my_subscriptions':
        subscriptions = await db.get_user_subscriptions(query.from_user.id)
        
        if subscriptions:
            text = "📋 *Ваши подписки:*\n\n"
            for sub in subscriptions:
                game_info = GAMES.get(sub['game'])
                if game_info:
                    text += f"• {game_info['name']} (скидка от {sub['min_discount_percent']}%)\n"
        else:
            text = "📋 *Ваши подписки:*\n\nУ вас пока нет подписок."
        
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif data == 'my_items':
        items = await db.get_user_items(query.from_user.id)
        await query.edit_message_text(format_user_items(items), parse_mode='Markdown')
    
    elif data == 'check_prices':
        await query.edit_message_text(
            "🔍 Проверяю цены на GGSel.net...\nЭто может занять около минуты."
        )
        
        try:
            added = await run_check()
            sent = await send_deals(lambda chat_id, text: context.bot.send_message(
                chat_id=chat_id, text=text, parse_mode='Markdown'
            ), added)
            await query.edit_message_text(
                f"✅ Проверка завершена!\n\n"
                f"🏪 Источник: GGSel.net (реальные цены)\n"
                f"🎮 Игр: {len(GAMES)}\n"
                f"💰 Новых выгодных предложений: {len(added)}\n"
                f"📨 Отправлено сообщений: {sent}"
            )
        except Exception as e:
            logger.error(f"Ошибка ручной проверки: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка при проверке цен. Попробуйте позже."
            )
    
    elif data == 'help':
        help_text = """
📚 *Помощь:*

Я бот для отслеживания цен на предметы из Roblox.

*Доступные функции:*
• Подписка на уведомления по играм
• Проверка текущих цен
• Просмотр выгодных предложений
• Управление списком товаров

*Источники данных:*
• GGSel.net — реальные цены маркетплейса

*Как пользоваться:*
1. Подпишитесь на интересующие игры
2. Я автоматически буду проверять цены
3. При появлении выгодных предложений вы получите уведомление
        """
        await query.edit_message_text(help_text, parse_mode='Markdown')
    
    elif data == 'back':
        keyboard = [
            [InlineKeyboardButton("🎮 Blox Fruits", callback_data='game_blox_fruits')],
            [InlineKeyboardButton("🔪 MM2", callback_data='game_mm2')],
            [InlineKeyboardButton("⭐ YBA", callback_data='game_yba')],
            [InlineKeyboardButton("📊 Мои подписки", callback_data='my_subscriptions')],
            [InlineKeyboardButton("📋 Мои товары", callback_data='my_items')],
            [InlineKeyboardButton("🔍 Проверить цены", callback_data='check_prices')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "👋 Главное меню\n\nВыберите действие:",
            reply_markup=reply_markup
        )
    
    # === Обработка предложения новых товаров ===
    elif data.startswith('suggest_yes|'):
        _, game, item_name = data.split('|', 2)
        game_info = GAMES.get(game)
        
        if game_info and item_name in game_info['items']:
            min_price = game_info['items'][item_name]
            await db.add_user_item(query.from_user.id, game, item_name, min_price)
            
            await query.edit_message_text(
                f"✅ Товар *{item_name}* добавлен в ваш список!\n\n"
                f"🎮 Игра: {game_info['name']}\n"
                f"💰 Минимальная цена: {min_price} ₽",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Товар не найден в списке отслеживаемых.")
    
    elif data.startswith('suggest_no|'):
        _, game, item_name = data.split('|', 2)
        
        # Отмечаем как предложенный, чтобы не предлагать снова
        await db.mark_item_as_suggested(game, item_name)
        
        await query.edit_message_text(
            f"❌ Товар *{item_name}* не добавлен в список.",
            parse_mode='Markdown'
        )


def _md(text) -> str:
    """Очистка внешнего текста от спецсимволов Markdown"""
    return re.sub(r'[*_`\[\]]+', '', str(text))


def format_deal_card(deal) -> str:
    """Форматирование карточки предложения"""
    card = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *{_md(deal['item_name'])}*\n"
    )
    # Полное название лота от продавца (как на маркетплейсе)
    if deal.get('offer_name'):
        card += f"🏷 {_md(deal['offer_name'])}\n"
    card += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Цена: *{deal['price']:.0f} ₽*\n"
    )
    # Цена из config.py, ниже которой мы и уведомляем
    if deal.get('target_price'):
        card += f"🎯 Моя цена: {deal['target_price']:.0f} ₽ — лот дешевле ✅\n"
    card += (
        f"📊 Рыночная цена: {deal['market_price']:.0f} ₽\n"
        f"📉 Скидка: *{deal['discount_percent']:.1f}%*\n"
        f"🏪 Источник: {deal['source']}\n"
        f"🔗 [Купить на маркетплейсе]({deal['url']})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    return card


async def run_check() -> list:
    """Одна полная проверка цен: парсинг ggsel + сохранение сделок.

    Возвращает список новых выгодных предложений (с ID в БД).
    """
    offers = await parse_all_games(GAMES)

    # Товары, добавленные пользователями через /additem
    user_items = await db.get_all_user_items()
    if user_items:
        extra = {}
        for ui in user_items:
            if ui['game'] in GAMES and ui['item_name'] not in GAMES[ui['game']]['items']:
                extra.setdefault(ui['game'], {'items': {}})['items'][ui['item_name']] = ui['min_price']
        if extra:
            offers += await parse_all_games(extra, reset_cache=False)

    # Обновляем рыночные цены и историю изменений цен
    seen = {}
    for offer in offers:
        seen[(offer['game'], offer['item_name'])] = offer
    for (game_key, item_name), offer in seen.items():
        await price_tracker.record(
            game_key, item_name,
            offer['market_price'], offer['min_price'], offer['max_price']
        )

    # Сохраняем сделки и частоту появления товаров
    added = []
    for offer in offers:
        await db.update_item_frequency(offer['game'], offer['item_name'])
        if offer['is_deal'] and not await db.deal_exists(offer['url'], offer['price']):
            offer['id'] = await db.add_deal(
                offer['game'], offer['item_name'], offer['price'],
                offer['market_price'], offer['discount_percent'],
                offer['source'], offer['seller'], offer['url'],
                offer.get('offer_name', ''), offer.get('target_price', 0)
            )
            added.append(offer)
    return added


async def send_deals(send_func, deals: list) -> int:
    """Отправить новые сделки подписчикам игр.

    Одно сообщение с карточками на каждую игру (максимум 5 карточек).
    Сделки без подписчиков остаются в базе для меню игры.
    Возвращает количество отправленных сообщений.
    """
    if not deals:
        return 0

    by_game = {}
    for deal in deals:
        by_game.setdefault(deal['game'], []).append(deal)

    sent = 0
    for game_key, lst in by_game.items():
        users = await db.get_subscribed_users(game_key)
        if not users:
            continue
        lst = lst[:5]
        game_name = GAMES.get(game_key, {}).get('name', game_key)
        text = f"🔥 *Выгодные предложения — {game_name}:*\n\n"
        for deal in lst:
            text += format_deal_card(deal)
        for user_id in users:
            try:
                await send_func(user_id, text)
                sent += 1
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
        for deal in lst:
            await db.mark_as_notified(deal['id'])
    return sent


async def check_deals(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача: проверка предложений на маркетплейсе ggsel"""
    logger.info("Запуск фоновой проверки цен (ggsel)...")
    try:
        added = await run_check()
        logger.info(f"Новых выгодных предложений: {len(added)}")

        await send_deals(lambda chat_id, text: context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode='Markdown'
        ), added)

        # === Проверка и предложение новых товаров ===
        if SUGGEST_ITEM_ENABLED:
            await suggest_new_items(context)

        # === Проверка изменений цен ===
        await check_price_changes(context)
    except Exception as e:
        logger.error(f"Ошибка проверки цен: {e}")


async def check_price_changes(context: ContextTypes.DEFAULT_TYPE):
    """Проверка значительных изменений цен"""
    alerts = await price_tracker.get_price_alerts(change_threshold=15)
    
    for alert in alerts:
        subscribed_users = await db.get_subscribed_users(alert['game'])
        
        for user_id in subscribed_users:
            try:
                trend_emoji = "📈" if alert['change_percent'] > 0 else "📉"
                
                text = (
                    f"{trend_emoji} *Изменение цены!*\n\n"
                    f"📦 Предмет: {_md(alert['item_name'])}\n"
                    f"🎮 Игра: {alert['game_name']}\n"
                    f"📉 Изменение: {alert['change_percent']:+.1f}%\n"
                    f"💰 Средняя цена: {alert['price']:.0f} ₽"
                )
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления об изменении цены: {e}")


async def suggest_new_items(context: ContextTypes.DEFAULT_TYPE):
    """Предложение новых товаров для добавления в список"""
    for game_key, game_info in GAMES.items():
        # Получаем часто появляющиеся товары
        frequent_items = await db.get_frequent_items(game_key, SUGGEST_ITEM_MIN_COUNT)
        
        for item in frequent_items:
            item_name = item['item_name']
            
            # Проверяем цену
            market_price = await db.get_market_price(game_key, item_name)
            if market_price:
                price = market_price['avg_price']
                if SUGGEST_ITEM_MIN_PRICE <= price <= SUGGEST_ITEM_MAX_PRICE:
                    # Получаем пользователей, подписанных на эту игру
                    subscribed_users = await db.get_subscribed_users(game_key)
                    
                    for user_id in subscribed_users:
                        try:
                            keyboard = [
                                [
                                    InlineKeyboardButton("✅ Да", callback_data=f'suggest_yes|{game_key}|{item_name}'),
                                    InlineKeyboardButton("❌ Нет", callback_data=f'suggest_no|{game_key}|{item_name}')
                                ]
                            ]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=(
                                    f"💡 *Предложение нового товара!*\n\n"
                                    f"Я часто вижу этот товар на маркетплейсах:\n\n"
                                    f"📦 *{item_name}*\n"
                                    f"🎮 Игра: {game_info['name']}\n"
                                    f"💰 Средняя цена: {price:.0f} ₽\n"
                                    f"📊 Встречается: {item['count']} раз\n\n"
                                    f"Хотите добавить в ваш список?"
                                ),
                                reply_markup=reply_markup,
                                parse_mode='Markdown'
                            )
                            
                        except Exception as e:
                            logger.error(f"Ошибка при отправке предложения пользователю {user_id}: {e}")


async def add_user_to_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление пользователя в белый список (только для админа)"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("⛔ У вас нет прав для выполнения этой команды.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /adduser <user_id>\n"
            "Пример: /adduser 123456789"
        )
        return
    
    try:
        new_user_id = int(context.args[0])
        if new_user_id not in WHITELIST_USERS:
            WHITELIST_USERS.append(new_user_id)
            await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен в белый список.")
        else:
            await update.message.reply_text(f"ℹ️ Пользователь {new_user_id} уже в белом списке.")
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя.")


async def remove_user_from_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление пользователя из белого списка (только для админа)"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("⛔ У вас нет прав для выполнения этой команды.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /removeuser <user_id>\n"
            "Пример: /removeuser 123456789"
        )
        return
    
    try:
        user_id = int(context.args[0])
        if user_id in WHITELIST_USERS:
            WHITELIST_USERS.remove(user_id)
            await update.message.reply_text(f"✅ Пользователь {user_id} удален из белого списка.")
        else:
            await update.message.reply_text(f"ℹ️ Пользователь {user_id} не найден в белом списке.")
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя.")


async def show_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать белый список (только для админа)"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("⛔ У вас нет прав для выполнения этой команды.")
        return
    
    if WHITELIST_USERS:
        text = "📋 Белый список пользователей:\n\n"
        for user_id in WHITELIST_USERS:
            text += f"• {user_id}\n"
    else:
        text = "📋 Белый список пуст."
    
    await update.message.reply_text(text)


async def toggle_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включить/выключить белый список (только для админа)"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("⛔ У вас нет прав для выполнения этой команды.")
        return
    
    global WHITELIST_ENABLED
    WHITELIST_ENABLED = not WHITELIST_ENABLED
    
    status = "включен" if WHITELIST_ENABLED else "выключен"
    await update.message.reply_text(f"✅ Белый список {status}.")


async def init_market_prices():
    """Инициализация рыночных цен через API"""
    await init_market_prices_with_api(db)


# ================================================================ команды меню

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /unsubscribe — отписаться от уведомлений по всем играм"""
    user = update.effective_user
    if not is_user_allowed(user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return

    removed = await db.remove_user_subscriptions(user.id)
    if removed:
        await update.message.reply_text(
            f"✅ Вы отписались от уведомлений по {removed} игре(ам).\n"
            f"Команда /subscribe — чтобы подписаться снова."
        )
    else:
        await update.message.reply_text("ℹ️ У вас не было подписок.")


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /check — ручная проверка цен"""
    user = update.effective_user
    if not is_user_allowed(user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return

    msg = await update.message.reply_text(
        "🔍 Проверяю цены на GGSel.net...\nЭто может занять около минуты."
    )
    try:
        added = await run_check()
        sent = await send_deals(lambda chat_id, text: context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode='Markdown'
        ), added)
        await msg.edit_text(
            f"✅ Проверка завершена!\n\n"
            f"💰 Новых выгодных предложений: {len(added)}\n"
            f"📨 Отправлено сообщений: {sent}"
        )
    except Exception as e:
        logger.error(f"Ошибка ручной проверки: {e}")
        await msg.edit_text("❌ Произошла ошибка при проверке цен. Попробуйте позже.")


async def deals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /deals — последние выгодные предложения"""
    user = update.effective_user
    if not is_user_allowed(user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return

    text = "🔥 *Последние выгодные предложения:*\n\n"
    count = 0
    for game_key in GAMES:
        for deal in (await db.get_unnotified_deals(game_key, 0))[:3]:
            text += format_deal_card(deal)
            count += 1

    if count == 0:
        text = ("Пока нет выгодных предложений.\n\n"
                "Нажмите «🔍 Проверить цены» или подождите "
                "автоматической проверки (каждые 5 минут).")
    await update.message.reply_text(text, parse_mode='Markdown')


async def my_items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /myitems — список товаров пользователя"""
    user = update.effective_user
    if not is_user_allowed(user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return

    items = await db.get_user_items(user.id)
    await update.message.reply_text(format_user_items(items), parse_mode='Markdown')


async def add_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /additem — добавить свой товар для отслеживания"""
    user = update.effective_user
    if not is_user_allowed(user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Использование: /additem <игра> <название> <цена>\n\n"
            "Примеры:\n"
            "  /additem mm2 Harvester 500\n"
            "  /additem blox Dought Fruit 45\n"
            "  /additem yba Lucky Arrow 6\n\n"
            "Игры: blox, mm2, yba"
        )
        return

    game_key = GAME_ALIASES.get(args[0].lower())
    if not game_key or game_key not in GAMES:
        await update.message.reply_text("❌ Неизвестная игра. Доступно: blox, mm2, yba")
        return

    try:
        price = float(args[-1])
    except ValueError:
        await update.message.reply_text("❌ Цена должна быть числом — укажите её последним аргументом.")
        return

    item_name = " ".join(args[1:-1]).strip()
    if not item_name:
        await update.message.reply_text("❌ Укажите название товара.")
        return

    await db.add_user_item(user.id, game_key, item_name, price)
    game_name = GAMES[game_key]['name']
    await update.message.reply_text(
        f"✅ Товар добавлен в ваш список!\n\n"
        f"🎮 Игра: {game_name}\n"
        f"📦 Предмет: {_md(item_name)}\n"
        f"💰 Целевая цена: {price:.0f} ₽\n\n"
        + (
            f"Я сообщу, как только появится лот дешевле {price:.0f} ₽."
            if REQUIRE_TARGET_PRICE else
            f"Я сообщу, когда появится предложение дешевле рынка "
            f"на {PRICE_THRESHOLD_PERCENT}% или дешевле {price:.0f} ₽."
        ),
        parse_mode='Markdown'
    )


def main():
    """Запуск бота (авто-restart при сетевых сбоях Telegram)"""
    if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_СЮДА":
        print("❌ Укажите токен бота в файле .env:")
        print('   BOT_TOKEN=123456789:ABCdef... (получите у @BotFather)')
        return

    if WHITELIST_ENABLED and not WHITELIST_USERS:
        print("⚠️ Включен белый список, но не добавлены ID пользователей!")
        print("   Добавьте свой ID Telegram в config.py -> WHITELIST_USERS")

    # Инициализация базы данных и цен
    async def startup():
        await db.init()
        await init_market_prices()

    asyncio.run(startup())

    def build_application() -> Application:
        """Сборка приложения: настройка, обработчики, фоновая задача"""
        builder = Application.builder().token(BOT_TOKEN)
        if PROXY_URL:
            logger.info(f"Используется прокси для Telegram: {PROXY_URL}")
            builder = builder.proxy(PROXY_URL)
        app = builder.build()

        # Команды
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("subscribe", subscribe))
        app.add_handler(CommandHandler("unsubscribe", unsubscribe))
        app.add_handler(CommandHandler("check", check_command))
        app.add_handler(CommandHandler("deals", deals_command))
        app.add_handler(CommandHandler("myitems", my_items_command))
        app.add_handler(CommandHandler("additem", add_item_command))
        app.add_handler(CallbackQueryHandler(button_handler))

        # Команды администратора
        app.add_handler(CommandHandler("adduser", add_user_to_whitelist))
        app.add_handler(CommandHandler("removeuser", remove_user_from_whitelist))
        app.add_handler(CommandHandler("whitelist", show_whitelist))
        app.add_handler(CommandHandler("togglewhitelist", toggle_whitelist))

        # Фоновая задача для проверки предложений
        job_queue = app.job_queue
        if job_queue:
            job_queue.run_repeating(check_deals, interval=CHECK_INTERVAL_MINUTES * 60, first=10)
        else:
            logger.warning(
                "JobQueue недоступна! Установите: pip install \"python-telegram-bot[job-queue]>=22.8\""
            )
        return app

    # Запуск с повторными попытками при недоступности Telegram
    logger.info("Бот запущен!")
    while True:
        try:
            application = build_application()
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            break
        except KeyboardInterrupt:
            logger.info("Остановлено пользователем")
            break
        except Exception as e:
            logger.error(f"Сбой Telegram API: {e}. Повтор через 30 секунд...")
            time.sleep(30)


if __name__ == "__main__":
    main()

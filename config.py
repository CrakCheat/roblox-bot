import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token (получить у @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_СЮДА")

# HTTP(S)-прокси для Telegram API — на случай, если сеть блокирует Telegram.
# Пример: PROXY_URL=socks5://127.0.0.1:1080 (обычно пусто)
PROXY_URL = os.getenv("PROXY_URL", "").strip()

# Discord вебхук — запасной канал уведомлений, когда Telegram недоступен.
# Хранится в .env (в git не попадает): DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

# Настройки базы данных (в облаке можно переопределить: DB_PATH=/data/deals.db)
DB_PATH = os.getenv("DB_PATH", "deals.db")

# Настройки парсинга
CHECK_INTERVAL_MINUTES = 1  # Как часто проверять (1 — почти моментально)
PRICE_THRESHOLD_PERCENT = 20  # Скидка от медианы рынка, ниже которой лот тоже считается выгодным

# Только лоты дешевле цен из GAMES (см. ниже) попадают в уведомления.
#   True  — присылать ТОЛЬКО если цена лота <= цены из config (то, что вы указали)
#   False — плюс присылать лоты со скидкой >= PRICE_THRESHOLD_PERCENT от рынка
REQUIRE_TARGET_PRICE = True

# Источники лотов (можно отключить любой, убрав из списка):
#   "ggsel"    — поиск ggsel.net
#   "funpay"   — страницы лотов игр funpay.com
#   "playerok" — каталог playerok.com (REST API)
# Рыночная цена (медиана) считается по лотам всех включённых источников.
SOURCES = ["ggsel", "funpay", "playerok"]

# Настройки предложения новых товаров
# (товар часто выставляют: N появлений подряд, стоит 100–2000 ₽,
#  не отслеживается — присылаем подсказку, каждый товар не больше одного раза)
SUGGEST_ITEM_ENABLED = True  # Включить предложение новых товаров
SUGGEST_ITEM_MIN_COUNT = 10  # Мин. число появлений («слишком часто выставляют»)
SUGGEST_ITEM_MIN_PRICE = 100  # Минимальная цена для предложения
SUGGEST_ITEM_MAX_PRICE = 2000  # Максимальная цена для предложения
SUGGEST_ITEM_MAX_PER_DAY = 10  # Не больше N подсказок в день (защита от спама)

# Настройки белого списка (только эти пользователи могут использовать бота)
WHITELIST_ENABLED = True  # Включить белый список
WHITELIST_USERS = [
    8680512428,  # Ваш ID Telegram
    # Добавьте другие ID по необходимости:
    # 987654321,
]

# ID администратора (может управлять ботом)
ADMIN_IDS = [
    8680512428,  # Ваш ID Telegram
]

# Кому слать уведомления в режиме GitHub Actions (там нет команд и подписок).
# Можно указать несколько ID. В интерактивном режиме (bot.py) работают подписки.
NOTIFY_USER_IDS = [
    8680512428,
]

# Игры для отслеживания с РЕАЛЬНЫМИ ценами
GAMES = {
    "blox_fruits": {
        "name": "Blox Fruits",
        "items": {
            # Название: МАКСИМАЛЬНАЯ цена в ₽ — уведомление приходит только
            # когда лот дешевле этой цены. Поднимите цену, если хотите ловить
            # предложения почаще, опустите — если хотите только thật дешёвое.
            "Dought Fruit": 45,
            "Dragon Fruit": 1000,
            "Yeti": 65,
            "Fiend Yeti": 550,
            "Runic Fiend Yeti": 700,
            "Magnet Fruit": 450,
            "Arcsteel Magnet": 1000,
            "Kitsune Fruit": 250,
            "Lighting Fruit": 45,
            "Red Lighting": 1000,
            "Purple Lighting": 1500,
            "Yellow Lighting": 75,
            "Green Lighting": 140,
        }
    },
    "yba": {
        "name": "Your Bizarre Adventure",
        "items": {
            "Lucky Arrow": 6,
            "Chopper Crazy Diamond Requiem": 850,
            "The Waifu V1": 250,
            "Crazy Idol Requiem": 1100,
            "Go/Jo STW": 210,
            "Diamondhead YBA CDR": 400,
            "Ghost The World": 230,
            "Mirage of Phantoms": 240,
        }
    },
    "mm2": {
        "name": "Murder Mystery 2",
        "items": {
            "Harvester": 500,
            "Icepiercer": 400,
            "Flowerwood Set": 1200,
            "Suntrise": 1900,
        }
    }
}

# Источник цен — реальный маркетплейс (см. parsers.py)
SOURCE_NAME = "GGSel.net + FunPay + PlayerOK"

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token (получить у @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_СЮДА")

# HTTP(S)-прокси для Telegram API — на случай, если сеть блокирует Telegram.
# Пример: PROXY_URL=socks5://127.0.0.1:1080 (обычно пусто)
PROXY_URL = os.getenv("PROXY_URL", "").strip()

# Настройки базы данных (в облаке можно переопределить: DB_PATH=/data/deals.db)
DB_PATH = os.getenv("DB_PATH", "deals.db")

# Настройки парсинга
CHECK_INTERVAL_MINUTES = 5  # Как часто проверять новые предложения
PRICE_THRESHOLD_PERCENT = 20  # На сколько % цена должна быть ниже рынка

# Источники лотов (можно отключить любой, убрав из списка):
#   "ggsel"    — поиск ggsel.net
#   "funpay"   — страницы лотов игр funpay.com
#   "playerok" — каталог playerok.com (REST API)
# Рыночная цена (медиана) считается по лотам всех включённых источников.
SOURCES = ["ggsel", "funpay", "playerok"]

# Настройки предложения новых товаров
SUGGEST_ITEM_ENABLED = True  # Включить предложение новых товаров
SUGGEST_ITEM_MIN_COUNT = 3  # Минимальное количество появлений для предложения
SUGGEST_ITEM_MIN_PRICE = 100  # Минимальная цена для предложения
SUGGEST_ITEM_MAX_PRICE = 2000  # Максимальная цена для предложения

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
            # Название: целевая цена в ₽ (лот дешевле = выгодное предложение)
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

import aiosqlite
import asyncio
from datetime import datetime
from typing import List, Dict, Optional

class Database:
    def __init__(self, db_path: str = "deals.db"):
        self.db_path = db_path

    async def init(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица для хранения предложений
            await db.execute("""
                CREATE TABLE IF NOT EXISTS deals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    market_price REAL NOT NULL,
                    discount_percent REAL NOT NULL,
                    source TEXT NOT NULL,
                    seller TEXT,
                    url TEXT,
                    offer_name TEXT,
                    target_price REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_notified INTEGER DEFAULT 0
                )
            """)

            # Миграция старых баз: добавляем новые колонки, если их нет
            cursor = await db.execute("PRAGMA table_info(deals)")
            deal_cols = {row[1] for row in await cursor.fetchall()}
            if "offer_name" not in deal_cols:
                await db.execute("ALTER TABLE deals ADD COLUMN offer_name TEXT")
            if "target_price" not in deal_cols:
                await db.execute("ALTER TABLE deals ADD COLUMN target_price REAL DEFAULT 0")
            
            # Таблица для хранения рыночных цен
            await db.execute("""
                CREATE TABLE IF NOT EXISTS market_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    avg_price REAL NOT NULL,
                    min_price REAL NOT NULL,
                    max_price REAL NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(game, item_name)
                )
            """)
            
            # Таблица для подписок пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    min_discount_percent REAL DEFAULT 20,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, game)
                )
            """)
            
            # Таблица для отслеживания частоты появления товаров
            await db.execute("""
                CREATE TABLE IF NOT EXISTS item_frequency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    suggested INTEGER DEFAULT 0,
                    suggested_at TIMESTAMP,
                    UNIQUE(game, item_name)
                )
            """)
            
            # Таблица для пользовательских списков товаров
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    min_price REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, game, item_name)
                )
            """)
            
            await db.commit()

    async def add_deal(self, game: str, item_name: str, price: float, 
                       market_price: float, discount_percent: float, 
                       source: str, seller: str = None, url: str = None,
                       offer_name: str = "", target_price: float = 0) -> int:
        """Добавление нового предложения, возвращает ID записи"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO deals (game, item_name, price, market_price, 
                                 discount_percent, source, seller, url,
                                 offer_name, target_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (game, item_name, price, market_price, discount_percent, source, seller, url, offer_name, target_price))
            await db.commit()
            return cursor.lastrowid

    async def get_unnotified_deals(self, game: str = None, min_discount: float = 20) -> List[Dict]:
        """Получение неуведомленных предложений"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if game:
                cursor = await db.execute("""
                    SELECT * FROM deals 
                    WHERE is_notified = 0 AND game = ? AND discount_percent >= ?
                    ORDER BY discount_percent DESC
                """, (game, min_discount))
            else:
                cursor = await db.execute("""
                    SELECT * FROM deals 
                    WHERE is_notified = 0 AND discount_percent >= ?
                    ORDER BY discount_percent DESC
                """, (min_discount,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def deal_exists(self, url: str, price: float) -> bool:
        """Есть ли уже такое предложение (анти-дубль уведомлений)"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 1 FROM deals WHERE url = ? AND price = ? LIMIT 1
            """, (url, price))
            return await cursor.fetchone() is not None

    async def count_deals(self, notified: bool = None) -> int:
        """Всего сделок (при notified=None) или по флагу уведомления"""
        async with aiosqlite.connect(self.db_path) as db:
            if notified is None:
                cursor = await db.execute("SELECT COUNT(*) FROM deals")
            else:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM deals WHERE is_notified = ?",
                    (1 if notified else 0,))
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def count_deals_by_source(self) -> Dict[str, int]:
        """Сколько сделок найдено по каждому источнику"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT source, COUNT(*) FROM deals GROUP BY source")
            rows = await cursor.fetchall()
            return {(src or "?"): cnt for src, cnt in rows}

    async def mark_as_notified(self, deal_id: int):
        """Отметить предложение как уведомленное"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE deals SET is_notified = 1 WHERE id = ?
            """, (deal_id,))
            await db.commit()

    async def update_market_price(self, game: str, item_name: str, 
                                  avg_price: float, min_price: float, max_price: float):
        """Обновление рыночной цены"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO market_prices 
                (game, item_name, avg_price, min_price, max_price, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (game, item_name, avg_price, min_price, max_price, datetime.now()))
            await db.commit()

    async def get_market_price(self, game: str, item_name: str) -> Optional[Dict]:
        """Получение рыночной цены"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM market_prices WHERE game = ? AND item_name = ?
            """, (game, item_name))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def add_user_subscription(self, user_id: int, game: str, min_discount: float = 20):
        """Добавление подписки пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO user_subscriptions 
                (user_id, game, min_discount_percent)
                VALUES (?, ?, ?)
            """, (user_id, game, min_discount))
            await db.commit()

    async def remove_user_subscriptions(self, user_id: int) -> int:
        """Удалить все подписки пользователя, возвращает число удаленных"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM user_subscriptions WHERE user_id = ?
            """, (user_id,))
            await db.commit()
            return cursor.rowcount

    async def get_user_subscriptions(self, user_id: int) -> List[Dict]:
        """Получение подписок пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM user_subscriptions WHERE user_id = ?
            """, (user_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_subscribed_users(self, game: str) -> List[int]:
        """Получение пользователей, подписанных на игру"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT user_id FROM user_subscriptions WHERE game = ?
            """, (game,))
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    # === Новые методы для отслеживания частоты товаров ===
    
    async def update_item_frequency(self, game: str, item_name: str):
        """Обновление частоты появления товара"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем, есть ли уже запись
            cursor = await db.execute("""
                SELECT id, count FROM item_frequency 
                WHERE game = ? AND item_name = ?
            """, (game, item_name))
            row = await cursor.fetchone()
            
            if row:
                # Обновляем счетчик
                await db.execute("""
                    UPDATE item_frequency 
                    SET count = count + 1, last_seen = ?
                    WHERE game = ? AND item_name = ?
                """, (datetime.now(), game, item_name))
            else:
                # Создаем новую запись
                await db.execute("""
                    INSERT INTO item_frequency (game, item_name, count, last_seen)
                    VALUES (?, ?, 1, ?)
                """, (game, item_name, datetime.now()))
            
            await db.commit()

    async def get_frequent_items(self, game: str, min_count: int = 3) -> List[Dict]:
        """Получение часто появляющихся товаров"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM item_frequency 
                WHERE game = ? AND count >= ? AND suggested = 0
                ORDER BY count DESC
            """, (game, min_count))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_item_as_suggested(self, game: str, item_name: str):
        """Отметить товар как предложенный"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE item_frequency 
                SET suggested = 1, suggested_at = ?
                WHERE game = ? AND item_name = ?
            """, (datetime.now(), game, item_name))
            await db.commit()

    # === Методы для пользовательских списков ===
    
    async def add_user_item(self, user_id: int, game: str, item_name: str, min_price: float):
        """Добавление товара в пользовательский список"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO user_items 
                (user_id, game, item_name, min_price)
                VALUES (?, ?, ?, ?)
            """, (user_id, game, item_name, min_price))
            await db.commit()

    async def get_user_items(self, user_id: int, game: str = None) -> List[Dict]:
        """Получение товаров пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if game:
                cursor = await db.execute("""
                    SELECT * FROM user_items WHERE user_id = ? AND game = ?
                """, (user_id, game))
            else:
                cursor = await db.execute("""
                    SELECT * FROM user_items WHERE user_id = ?
                """, (user_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_user_items(self) -> List[Dict]:
        """Все уникальные товары всех пользователей (для парсинга)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT game, item_name, MIN(min_price) AS min_price
                FROM user_items
                GROUP BY game, item_name
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def remove_user_item(self, user_id: int, game: str, item_name: str):
        """Удаление товара из пользовательского списка"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                DELETE FROM user_items 
                WHERE user_id = ? AND game = ? AND item_name = ?
            """, (user_id, game, item_name))
            await db.commit()

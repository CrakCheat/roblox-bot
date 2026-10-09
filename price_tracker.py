"""Отслеживание изменения цен со временем.

Записывает средние рыночные цены в price_history при каждой проверке,
строит тренды и отдаёт оповещения о резких изменениях цен.
"""
import aiosqlite
from typing import Dict, List

from database import Database
from config import GAMES


class PriceTracker:
    def __init__(self, db: Database):
        self.db = db

    async def record(self, game: str, item_name: str,
                     avg_price: float, min_price: float, max_price: float) -> float:
        """Сохранить среднюю цену предмета и вернуть % изменения к прошлой"""
        old = await self.db.get_market_price(game, item_name)
        await self.db.update_market_price(game, item_name, avg_price, min_price, max_price)

        change = 0.0
        first_record = not (old and old.get("avg_price"))
        if not first_record:
            change = ((avg_price - old["avg_price"]) / old["avg_price"]) * 100

        # Первую цену сохраняем как отправную точку, дальше — заметные изменения
        if first_record or abs(change) >= 0.5:
            await self._save_history(game, item_name, avg_price, change)
        return change

    async def _save_history(self, game: str, item_name: str,
                            price: float, change_percent: float):
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute("""
                INSERT INTO price_history (game, item_name, price, change_percent)
                VALUES (?, ?, ?, ?)
            """, (game, item_name, price, change_percent))
            await db.commit()

    async def get_price_trend(self, game: str, item_name: str, days: int = 7) -> Dict:
        """Тренд цены за период"""
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT price, change_percent, recorded_at
                FROM price_history
                WHERE game = ? AND item_name = ?
                  AND recorded_at >= datetime('now', ?)
                ORDER BY recorded_at ASC
            """, (game, item_name, f'-{days} days'))
            rows = await cursor.fetchall()

        if not rows:
            return {"direction": "flat", "change_percent": 0, "points": 0}

        prices = [r["price"] for r in rows]
        change = prices[-1] - prices[0]
        pct = (change / prices[0] * 100) if prices[0] else 0

        if pct > 3:
            direction = "up"
        elif pct < -3:
            direction = "down"
        else:
            direction = "flat"

        return {"direction": direction, "change_percent": round(pct, 1), "points": len(prices)}

    async def get_price_alerts(self, game: str = None,
                               change_threshold: float = 10) -> List[Dict]:
        """Предупреждения о значительном изменении цены с последней проверки"""
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            if game:
                cursor = await db.execute("""
                    SELECT game, item_name, price, change_percent, recorded_at
                    FROM price_history
                    WHERE game = ? AND ABS(change_percent) >= ?
                      AND recorded_at >= datetime('now', '-1 day')
                    ORDER BY ABS(change_percent) DESC
                    LIMIT 10
                """, (game, change_threshold))
            else:
                cursor = await db.execute("""
                    SELECT game, item_name, price, change_percent, recorded_at
                    FROM price_history
                    WHERE ABS(change_percent) >= ?
                      AND recorded_at >= datetime('now', '-1 day')
                    ORDER BY ABS(change_percent) DESC
                    LIMIT 20
                """, (change_threshold,))
            rows = await cursor.fetchall()

        alerts = []
        for row in rows:
            alerts.append({
                "game": row["game"],
                "game_name": GAMES.get(row["game"], {}).get("name", row["game"]),
                "item_name": row["item_name"],
                "price": row["price"],
                "change_percent": row["change_percent"],
                "recorded_at": row["recorded_at"],
            })
        return alerts

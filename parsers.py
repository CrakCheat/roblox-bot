"""Реальный парсер цен с маркетплейса ggsel.net.

Ищет предложения по предметам Blox Fruits, MM2 и YBA через поиск
ggsel.net, сравнивает цены с рыночной средней и целевой ценой из
config.py и возвращает выгодные предложения со ссылками на лоты.
"""
import asyncio
import html as htmllib
import re
import time
from typing import Dict, List, Optional, Tuple

import requests

from config import GAMES, PRICE_THRESHOLD_PERCENT

BASE_URL = "https://ggsel.net"
SEARCH_URL = BASE_URL + "/search/{query}"
CATALOG_URL = BASE_URL + "/catalog/{slug}"

# Каталоги игр на ggsel (для быстрого первичного сбора рыночных цен)
CATALOG_SLUGS = {
    "blox_fruits": "roblox-blox-fruits",
    "mm2": "roblox-mm2",
    "yba": "roblox-yba",
}

# Слова-маркеры: по ним видно, к какой игре относится товар.
# Требуются для ВСЕХ предметов — иначе «Dragon Fruit» из King Legacy
# попадёт в список Blox Fruits. Слово «fruit» сюда не входит — оно
# общее для многих игр.
GAME_MARKERS = {
    "blox_fruits": ("blox", "bloxfruit", "фрукт", "bf"),
    "mm2": ("mm2", "мм2", "murder mystery"),
    "yba": ("yba", "bizarre", "бизарр"),
}

# Исправление опечаток в названиях предметов (и в запросах, и в сравнении)
WORD_ALIASES = {
    "dought": "dough",
    "suntrise": "sunrise",
    "lighting": "lightning",
}

# Товары «навсегда» / гифты не сравниваем с обычными версиями
PERMANENT_MARKERS = ("permanent", "постоян", "гифт")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

REQUEST_DELAY = 0.8   # пауза между запросами, сек
CACHE_TTL = 600       # кеш ответов, сек


# ---------------------------------------------------------------- утилиты

def _norm(text: str) -> List[str]:
    """Текст -> список нормализованных слов"""
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text)
    return [w for w in text.split() if w]


def _fix_word(word: str) -> str:
    """Исправление опечатки в слове (dought -> dough и т.п.)"""
    return WORD_ALIASES.get(word, word)


def _levenshtein(a: str, b: str, max_dist: int = 1) -> int:
    """Расстояние Левенштейна с ограничением (для коротких слов)"""
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > max_dist:
            return max_dist + 1
        prev = cur
    return prev[-1]


def _word_matches(word: str, offer_words: set) -> bool:
    """Совпадение одного слова предмета с любым словом названия лота"""
    if word in offer_words:
        return True
    for ow in offer_words:
        # частичное совпадение: dough ~ dough fruit, sunrise ~ sunrisegp
        if len(word) >= 4 and len(ow) >= 4 and (word.startswith(ow) or ow.startswith(word)):
            return True
        # опечатка на 1 символ: fiend ~ friend, dought ~ dough
        if len(word) >= 5 and len(ow) >= 5 and _levenshtein(word, ow, 1) <= 1:
            return True
    return False


def _has_game_marker(offer_name: str, game_key: str) -> bool:
    """Есть ли в названии лота привязка к игре"""
    markers = GAME_MARKERS.get(game_key, ())
    words = set(_norm(offer_name))
    text = offer_name.lower().replace("ё", "е")
    for m in markers:
        if len(m) <= 3:
            if m in words:          # короткие маркеры (mm2, yba, bf) — только целым словом
                return True
        elif m in text:
            return True
    return False


def _matches_item(item_name: str, offer_name: str, game_key: str) -> bool:
    """Подходит ли лот под отслеживаемый предмет"""
    item_words = [_fix_word(w) for w in _norm(item_name)]
    if not item_words or not offer_name:
        return False
    offer_words = set(_norm(offer_name))
    if not offer_words:
        return False
    for w in item_words:
        if not _word_matches(w, offer_words):
            return False
    # Лот обязан быть привязан к игре маркером в названии —
    # так отсекаются чужие игры (King Legacy, Grow a Garden и т.п.)
    return _has_game_marker(offer_name, game_key)


def _is_relevant_offer(item_name: str, offer_name: str, game_key: str) -> bool:
    """Лот подходит по предмету и не является другой версией товара"""
    if not _matches_item(item_name, offer_name, game_key):
        return False
    item_l = item_name.lower()
    offer_l = offer_name.lower()
    item_perm = any(m in item_l for m in PERMANENT_MARKERS)
    offer_perm = any(m in offer_l for m in PERMANENT_MARKERS)
    # permanent-листинг не сравниваем с обычным предметом (и наоборот)
    if offer_perm and not item_perm:
        return False
    return True


def _query_variants(item_name: str) -> List[str]:
    """Варианты поисковых запросов: полное название -> отбрасывание слов"""
    words = [_fix_word(w) for w in _norm(item_name)]
    variants: List[str] = []
    for i in range(len(words), 0, -1):
        q = " ".join(words[:i])
        if q and q not in variants:
            variants.append(q)
    return variants


# ---------------------------------------------------------------- парсинг HTML

def parse_cards(page_html: str) -> List[Dict]:
    """Разбор карточек товаров на странице ggsel"""
    items: List[Dict] = []
    for chunk in page_html.split('data-testid="card" data-test="item"')[1:]:
        m_link = re.search(r'data-testid="card-link"[^>]*href="([^"]+)"', chunk)
        m_alt = re.search(r'<img alt="([^"]+)"', chunk)
        m_price = re.search(r'data-test="price">([\d\s\xa0]+)\s*₽', chunk)
        if not (m_link and m_price):
            continue
        price_str = re.sub(r"[^\d]", "", m_price.group(1))
        if not price_str:
            continue
        href = m_link.group(1)
        items.append({
            "name": htmllib.unescape(m_alt.group(1)) if m_alt else "",
            "price": float(price_str),
            "url": BASE_URL + href if href.startswith("/") else href,
        })
    return items


class GgselParser:
    """Клиент ggsel.net с кешем и ограничением частоты запросов"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last_request = 0.0
        self._cache: Dict[str, Tuple[float, List[Dict]]] = {}

    def reset(self):
        """Очистить кеш (новый цикл проверки — свежие цены)"""
        self._cache.clear()

    def _get(self, url: str) -> Optional[str]:
        wait = REQUEST_DELAY - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            try:
                self._last_request = time.time()
                r = self.session.get(url, timeout=20)
                if r.status_code == 200:
                    return r.text
                if r.status_code == 404:
                    return None
            except requests.RequestException:
                time.sleep(1 + attempt)
        return None

    def _cached(self, key: str) -> Optional[List[Dict]]:
        entry = self._cache.get(key)
        if entry and time.time() - entry[0] < CACHE_TTL:
            return entry[1]
        return None

    def search(self, query: str) -> List[Dict]:
        """Поиск товаров: /search/{запрос}"""
        key = "search:" + query.lower()
        cached = self._cached(key)
        if cached is not None:
            return cached
        url = SEARCH_URL.format(query=requests.utils.quote(query, safe=""))
        page = self._get(url)
        items = parse_cards(page) if page else []
        self._cache[key] = (time.time(), items)
        return items

    def catalog(self, game_key: str) -> List[Dict]:
        """Первая страница каталога игры"""
        slug = CATALOG_SLUGS.get(game_key)
        if not slug:
            return []
        key = "catalog:" + game_key
        cached = self._cached(key)
        if cached is not None:
            return cached
        page = self._get(CATALOG_URL.format(slug=slug))
        items = parse_cards(page) if page else []
        self._cache[key] = (time.time(), items)
        return items


parser = GgselParser()


# ---------------------------------------------------------------- поиск по предметам

def _median(values: List[float]) -> float:
    """Медиана — устойчива к выбросам (лотам-аномалиям по цене)"""
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    if n % 2:
        return float(ordered[n // 2])
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2


async def get_item_offers(game_key: str, item_name: str) -> List[Dict]:
    """Все подходящие лоты по предмету (поиск с запасными вариантами запроса)"""
    def work() -> List[Dict]:
        results: List[Dict] = []
        seen = set()
        for query in _query_variants(item_name):
            for offer in parser.search(query):
                if offer["url"] in seen:
                    continue
                if not _is_relevant_offer(item_name, offer["name"], game_key):
                    continue
                seen.add(offer["url"])
                results.append(offer)
            if results:
                break
        return results

    return await asyncio.to_thread(work)


async def parse_all_games(games: Optional[Dict] = None, reset_cache: bool = True) -> List[Dict]:
    """Проверить все предметы всех игр и вернуть предложения с рыночной статистикой.

    Каждое предложение содержит:
      price, market_price (медиана по лотам), min/max, discount_percent,
      is_deal (выгодно), target_hit (целевая цена из config достигнута),
      url, source, seller.
    """
    games = games if games is not None else GAMES
    if reset_cache:
        parser.reset()
    output: List[Dict] = []

    for game_key, info in games.items():
        for item_name, ref_price in (info.get("items") or {}).items():
            offers = await get_item_offers(game_key, item_name)
            if not offers:
                continue

            prices = [o["price"] for o in offers]
            med = _median(prices)          # рыночная цена по медиане лотов
            min_p, max_p = min(prices), max(prices)
            ref = float(ref_price or 0)

            for offer in offers:
                discount = ((med - offer["price"]) / med * 100) if med > 0 else 0.0
                target_hit = 0 < ref and offer["price"] <= ref
                is_deal = discount >= PRICE_THRESHOLD_PERCENT or target_hit
                # для сделок скидка не меньше порога — чтобы попасть в уведомления
                stored_discount = max(discount, float(PRICE_THRESHOLD_PERCENT)) if is_deal else discount
                output.append({
                    "game": game_key,
                    "item_name": item_name,
                    "offer_name": offer["name"],
                    "price": offer["price"],
                    "market_price": round(med),
                    "min_price": round(min_p),
                    "max_price": round(max_p),
                    "target_price": ref,
                    "discount_percent": round(stored_discount, 1),
                    "is_deal": is_deal,
                    "target_hit": target_hit,
                    "source": "GGSel",
                    "seller": "—",
                    "url": offer["url"],
                })
    return output


# ---------------------------------------------------------------- первичные рыночные цены

async def init_market_prices_with_api(db) -> int:
    """Быстрый первичный сбор рыночных цен из каталогов игр (3 запроса)"""
    def work() -> Dict[Tuple[str, str], Tuple[float, float, float]]:
        stats: Dict[Tuple[str, str], Tuple[float, float, float]] = {}
        for game_key in CATALOG_SLUGS:
            info = GAMES.get(game_key)
            if not info:
                continue
            cards = parser.catalog(game_key)
            if not cards:
                continue
            for item_name in (info.get("items") or {}):
                matched = [c for c in cards if _is_relevant_offer(item_name, c["name"], game_key)]
                if not matched:
                    continue
                prices = [c["price"] for c in matched]
                stats[(game_key, item_name)] = (
                    _median(prices), min(prices), max(prices),
                )
        return stats

    stats = await asyncio.to_thread(work)
    for (game_key, item_name), (avg, min_p, max_p) in stats.items():
        await db.update_market_price(game_key, item_name, round(avg), round(min_p), round(max_p))
    return len(stats)

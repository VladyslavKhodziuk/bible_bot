import json
import logging
import random
from datetime import date
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)

# Пути к данным
DATA_DIR = Path(__file__).parent.parent / "data"
BIBLES_DIR = DATA_DIR / "bibles"
BOOKS_FILE = DATA_DIR / "books.yaml"
VERSES_OF_DAY_FILE = DATA_DIR / "verses_of_day.yaml"

# Поддерживаемые переводы: код → имя файла
TRANSLATIONS = {
    "ru_synodal":   {"file": "ru_synodal.json",   "lang": "ru"},
    "ru_nrt":       {"file": "ru_nrt.json",        "lang": "ru"},
    "en_kjv":       {"file": "en_kjv.json",       "lang": "en"},
    "en_asv":       {"file": "en_asv.json",       "lang": "en"},
    "en_web":       {"file": "en_web.json",       "lang": "en"},
    "es_rvr":       {"file": "es_rvr.json",       "lang": "es"},
    "es_rvr1865":   {"file": "es_rvr1865.json",    "lang": "es"},
    "es_torres":    {"file": "es_torres.json",     "lang": "es"},
    "es_sagradas":  {"file": "es_sagradas.json",  "lang": "es"},
    "uk_ogienko":   {"file": "uk_ogienko.json", "lang": "uk"},
}

# Какой перевод по умолчанию для какого языка
DEFAULT_TRANSLATION_FOR_LANG = {
    "ru": "ru_synodal",
    "en": "en_kjv",
    "es": "es_rvr",
    "uk": "uk_ogienko",
}


class BibleService:
    """
    Сервис для работы с Библией.
    Все данные загружаются в память при старте — быстрый доступ.
    """

    _bibles: dict[str, list] = {}
    _books_meta: dict[str, dict] = {}
    _book_order: list[str] = []
    _daily_pool: list[tuple[str, int, int]] = []
    _loaded: bool = False

    @classmethod
    def load(cls) -> None:
        """Загружает все Библии и метаданные книг в память."""
        if cls._loaded:
            return

        logger.info("Загрузка Библий в память...")

        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            cls._books_meta = yaml.safe_load(f)

        cls._book_order = list(cls._books_meta.keys())
        logger.info(f"  Метаданные: {len(cls._book_order)} книг")

        for code, meta in TRANSLATIONS.items():
            path = BIBLES_DIR / meta["file"]
            if not path.exists():
                logger.warning(f"  Файл не найден: {path}")
                continue
            with open(path, "r", encoding="utf-8-sig") as f:
                cls._bibles[code] = json.load(f)
            logger.info(f"  {code}: {len(cls._bibles[code])} книг")

        cls._load_daily_pool()

        cls._loaded = True
        logger.info("Библии загружены")

    @classmethod
    def _load_daily_pool(cls) -> None:
        """Загружает курируемый пул стихов дня. Порядок перемешивается фиксированным
        seed — день года стабильно отображается на стих, но соседние дни берут стихи
        из разных книг, а не подряд."""
        if not VERSES_OF_DAY_FILE.exists():
            logger.warning(f"  Пул стихов дня не найден: {VERSES_OF_DAY_FILE}")
            return
        with open(VERSES_OF_DAY_FILE, "r", encoding="utf-8") as f:
            refs = yaml.safe_load(f).get("verses", [])
        pool = []
        for ref in refs:
            abbrev, cv = ref.rsplit(" ", 1)
            chapter, verse = cv.split(":")
            pool.append((abbrev, int(chapter), int(verse)))
        random.Random(20240101).shuffle(pool)
        cls._daily_pool = pool
        logger.info(f"  Пул стихов дня: {len(pool)} стихов")

    @classmethod
    def get_books(cls, testament: str | None = None) -> list[dict]:
        """Получить список книг (опционально по завету: 'ot' или 'nt')."""
        result = []
        for abbrev in cls._book_order:
            meta = cls._books_meta[abbrev]
            if testament and meta["testament"] != testament:
                continue
            result.append({"abbrev": abbrev, **meta})
        return result

    @classmethod
    def get_book_name(cls, abbrev: str, lang: str) -> str:
        """Локализованное название книги."""
        meta = cls._books_meta.get(abbrev)
        if not meta:
            return abbrev
        return meta.get(lang, meta.get("en", abbrev))

    @classmethod
    def get_book_index(cls, abbrev: str) -> int | None:
        """Порядковый номер книги (0..65)."""
        try:
            return cls._book_order.index(abbrev)
        except ValueError:
            return None

    @classmethod
    def get_chapters_count(cls, abbrev: str, translation: str) -> int:
        """Количество глав в книге."""
        book = cls._get_book_data(abbrev, translation)
        return len(book["chapters"]) if book else 0

    @classmethod
    def get_chapter(cls, abbrev: str, chapter: int, translation: str) -> list[str] | None:
        """Возвращает список стихов главы (без номеров, просто текст)."""
        bible = cls._bibles.get(translation)
        if not bible:
            return None
        for book_idx, book in enumerate(bible):
            if cls._book_order[book_idx] == abbrev:
                chapters = book.get("chapters", [])
                if 0 <= chapter - 1 < len(chapters):
                    return chapters[chapter - 1]
                return None
        return None

    @classmethod
    def get_verse(cls, abbrev: str, chapter: int, verse: int, translation: str) -> str | None:
        """Получить один стих."""
        verses = cls.get_chapter(abbrev, chapter, translation)
        if not verses:
            return None
        idx = verse - 1
        if idx < 0 or idx >= len(verses):
            return None
        return verses[idx]

    @classmethod
    def get_translation_for_lang(cls, lang: str) -> str:
        """Перевод по умолчанию для языка интерфейса.

        Если явно задан в DEFAULT_TRANSLATION_FOR_LANG — берём его.
        Иначе — первый доступный перевод этого языка.
        """
        if lang in DEFAULT_TRANSLATION_FOR_LANG:
            return DEFAULT_TRANSLATION_FOR_LANG[lang]
        # Fallback: первый перевод этого языка
        translations = cls.get_translations_for_lang(lang)
        if translations:
            return translations[0]
        # Последний fallback
        return "en_kjv"

    @classmethod
    def _get_book_data(cls, abbrev: str, translation: str) -> dict | None:
        """Внутренний метод: достать сырую книгу из JSON по аббревиатуре."""
        bible = cls._bibles.get(translation)
        if not bible:
            return None
        idx = cls.get_book_index(abbrev)
        if idx is None or idx >= len(bible):
            return None
        return bible[idx]

    @classmethod
    def get_random_verse(cls, translation: str) -> dict | None:
        """
        Случайный стих из Библии.
        Возвращает: {"abbrev": "jo", "chapter": 3, "verse": 16, "text": "..."}
        """
        bible = cls._bibles.get(translation)
        if not bible:
            return None

        # Выбираем случайную книгу
        book_idx = random.randrange(len(bible))
        book = bible[book_idx]
        abbrev = cls._book_order[book_idx]

        # Случайную главу
        chapter_idx = random.randrange(len(book["chapters"]))
        chapter_verses = book["chapters"][chapter_idx]

        # Случайный стих
        verse_idx = random.randrange(len(chapter_verses))

        return {
            "abbrev": abbrev,
            "chapter": chapter_idx + 1,
            "verse": verse_idx + 1,
            "text": chapter_verses[verse_idx],
        }

    @classmethod
    def get_verse_of_day(cls, translation: str, target_date: date | None = None) -> dict | None:
        """
        Стих дня — один и тот же в течение суток для всех. Берётся из курируемого
        пула по дню года, поэтому это всегда осмысленный стих, а не случайная
        родословная. Один и тот же reference для всех переводов; текст резолвится
        в переводе пользователя.
        """
        if target_date is None:
            target_date = date.today()

        if not cls._bibles.get(translation):
            return None

        pool = cls._daily_pool
        if not pool:
            return cls._random_verse(translation, target_date)

        # День года -> индекс в пуле. Если стих почему-то не резолвится в этом
        # переводе (разная версификация), детерминированно идём по пулу дальше.
        start = (target_date.timetuple().tm_yday - 1) % len(pool)
        for offset in range(len(pool)):
            abbrev, chapter, verse = pool[(start + offset) % len(pool)]
            text = cls.get_verse(abbrev, chapter, verse, translation)
            if text is not None:
                return {"abbrev": abbrev, "chapter": chapter, "verse": verse, "text": text}

        return cls._random_verse(translation, target_date)

    @classmethod
    def _random_verse(cls, translation: str, target_date: date) -> dict | None:
        """Запасной вариант: детерминированно случайный стих (если пул пуст/не сошёлся)."""
        bible = cls._bibles.get(translation)
        if not bible:
            return None
        rng = random.Random(target_date.toordinal())
        book_idx = rng.randrange(len(bible))
        abbrev = cls._book_order[book_idx]
        chapter_idx = rng.randrange(len(bible[book_idx]["chapters"]))
        chapter_verses = bible[book_idx]["chapters"][chapter_idx]
        verse_idx = rng.randrange(len(chapter_verses))
        return {
            "abbrev": abbrev,
            "chapter": chapter_idx + 1,
            "verse": verse_idx + 1,
            "text": chapter_verses[verse_idx],
        }

    @classmethod
    def paginate_chapter(
            cls,
            verses: list[str],
            max_chars: int = 3500
    ) -> list[tuple[int, int]]:
        """
        Разбивает главу на страницы так, чтобы каждая помещалась в Telegram.

        Возвращает список диапазонов: [(start_verse, end_verse), ...]
        Номера стихов — человеческие, с 1.

        Пример: [(1, 30), (31, 50)] — первая страница стихи 1-30, вторая 31-50.
        """
        if not verses:
            return []

        pages = []
        current_start = 1  # человеческий номер первого стиха страницы
        current_length = 0

        for i, verse in enumerate(verses, start=1):
            # Длина строки "**N** текст стиха\n"
            verse_length = len(f"**{i}.** {verse}\n")

            # Если добавив этот стих, превысим лимит — закрываем страницу
            if current_length + verse_length > max_chars and current_length > 0:
                pages.append((current_start, i - 1))
                current_start = i
                current_length = verse_length
            else:
                current_length += verse_length

        # Закрываем последнюю страницу
        pages.append((current_start, len(verses)))

        return pages

    @classmethod
    def get_translations_for_lang(cls, lang: str) -> list[str]:
        """Возвращает коды переводов, доступных на указанном языке."""
        return [code for code, meta in TRANSLATIONS.items() if meta["lang"] == lang]


    @classmethod
    def search(
            cls,
            query: str,
            translation: str,
            max_results: int = 200,
    ) -> list[dict]:
        """
        Поиск стихов по тексту в указанном переводе.

        query: строка для поиска (регистронезависимо)
        translation: код перевода (например, ru_synodal)
        max_results: ограничение для защиты от слишком частых слов ("и", "на")

        Возвращает список стихов:
            [{"abbrev": "gn", "chapter": 1, "verse": 1, "text": "..."}]
        """
        # Нормализуем запрос
        query_clean = query.strip().lower()
        if len(query_clean) < 2:
            return []

        bible = cls._bibles.get(translation)
        if not bible:
            return []

        results = []
        for book_idx, book in enumerate(bible):
            abbrev = cls._book_order[book_idx]
            for chapter_idx, chapter_verses in enumerate(book["chapters"]):
                for verse_idx, text in enumerate(chapter_verses):
                    if query_clean in text.lower():
                        results.append({
                            "abbrev": abbrev,
                            "chapter": chapter_idx + 1,
                            "verse": verse_idx + 1,
                            "text": text,
                        })
                        # Защита: если слово очень частое — не сканируем всю Библию
                        if len(results) >= max_results:
                            return results
        return results

    @classmethod
    def highlight(cls, text: str, query: str) -> str:
        """
        Подсветить найденный фрагмент в тексте через <b>...</b>.
        Регистронезависимо, но сохраняет оригинальный регистр в тексте.
        """
        if not query:
            return text

        query_clean = query.strip()
        if len(query_clean) < 2:
            return text

        # Регистронезависимый поиск, но подставляем оригинальный фрагмент текста
        text_lower = text.lower()
        query_lower = query_clean.lower()

        result = []
        i = 0
        while i < len(text):
            idx = text_lower.find(query_lower, i)
            if idx == -1:
                result.append(text[i:])
                break
            result.append(text[i:idx])
            result.append(f"<b>{text[idx:idx + len(query_lower)]}</b>")
            i = idx + len(query_lower)
        return "".join(result)


    @classmethod
    def filter_by_testament(cls, results: list[dict], testament: str | None) -> list[dict]:
        """
        Фильтрует список стихов по завету.
        testament: 'ot', 'nt' или None (вся Библия)
        """
        if testament is None:
            return results
        filtered = []
        for r in results:
            meta = cls._books_meta.get(r["abbrev"])
            if meta and meta.get("testament") == testament:
                filtered.append(r)
        return filtered


# Маппинг переводов → ожидаемый алфавит
TRANSLATION_ALPHABETS = {
    "ru_synodal":  "cyrillic",
    "ru_nrt":      "cyrillic",
    "uk_ogienko":  "cyrillic",
    "en_kjv":      "latin",
    "en_asv":      "latin",
    "en_web":      "latin",
    "es_rvr":      "latin",
    "es_rvr1865":  "latin",
    "es_torres":   "latin",
    "es_sagradas": "latin",
}


def detect_alphabet(text: str) -> str:
    """Определить, какой алфавит преобладает в тексте.

    Возвращает: 'cyrillic', 'latin', 'mixed', 'other'
    """
    cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    latin = sum(1 for c in text if c.isalpha() and ord(c) < 128)

    if cyrillic > latin * 2:
        return "cyrillic"
    if latin > cyrillic * 2:
        return "latin"
    if cyrillic > 0 and latin > 0:
        return "mixed"
    return "other"


def alphabet_matches_translation(query: str, translation: str) -> bool:
    """Проверяет, соответствует ли алфавит запроса алфавиту перевода."""
    query_alphabet = detect_alphabet(query)
    if query_alphabet == "other":
        # Только цифры/символы — пропускаем (хотя по факту поиск ничего не найдёт)
        return True
    expected = TRANSLATION_ALPHABETS.get(translation, "latin")
    if query_alphabet == "mixed":
        return True  # юзер может искать смешанное, разрешаем
    return query_alphabet == expected
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

# Поддерживаемые переводы: код → имя файла
TRANSLATIONS = {
    "ru_synodal":   {"file": "ru_synodal.json",   "lang": "ru"},
    "en_kjv":       {"file": "en_kjv.json",       "lang": "en"},
    "en_asv":       {"file": "en_asv.json",       "lang": "en"},
    "en_web":       {"file": "en_web.json",       "lang": "en"},
    "es_rvr":       {"file": "es_rvr.json",       "lang": "es"},
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

        cls._loaded = True
        logger.info("Библии загружены")

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
        """Получить главу как список стихов. chapter с 1."""
        book = cls._get_book_data(abbrev, translation)
        if not book:
            return None
        chapters = book["chapters"]
        idx = chapter - 1
        if idx < 0 or idx >= len(chapters):
            return None
        return chapters[idx]

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
        Стих дня — один и тот же в течение суток для всех с этим переводом.
        Использует дату как seed для рандома: одна дата = один и тот же стих.
        """
        if target_date is None:
            target_date = date.today()

        bible = cls._bibles.get(translation)
        if not bible:
            return None

        # Используем дату как seed — один день = один стих
        seed = target_date.toordinal()
        rng = random.Random(seed)

        book_idx = rng.randrange(len(bible))
        book = bible[book_idx]
        abbrev = cls._book_order[book_idx]

        chapter_idx = rng.randrange(len(book["chapters"]))
        chapter_verses = book["chapters"][chapter_idx]

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
            verse_length = len(f"**{i}** {verse}\n")

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
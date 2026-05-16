import json
import logging
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)

# Пути к данным
DATA_DIR = Path(__file__).parent.parent / "data"
BIBLES_DIR = DATA_DIR / "bibles"
BOOKS_FILE = DATA_DIR / "books.yaml"

# Поддерживаемые переводы: код → имя файла
TRANSLATIONS = {
    "ru_synodal": "ru_synodal.json",
    "en_kjv": "en_kjv.json",
    "es_rvr": "es_rvr.json",
}

# Какой перевод по умолчанию для какого языка
DEFAULT_TRANSLATION_FOR_LANG = {
    "ru": "ru_synodal",
    "en": "en_kjv",
    "es": "es_rvr",
}


class BibleService:
    """
    Сервис для работы с Библией.
    Все данные загружаются в память при старте — быстрый доступ.
    """

    # Кэш в памяти класса (один на весь процесс)
    _bibles: dict[str, list] = {}      # {"ru_synodal": [...книги], ...}
    _books_meta: dict[str, dict] = {}  # {"gn": {"testament": "ot", "ru": "Бытие", ...}, ...}
    _book_order: list[str] = []        # порядок книг: ["gn", "ex", ...]
    _loaded: bool = False

    @classmethod
    def load(cls) -> None:
        """Загружает все Библии и метаданные книг в память. Вызывать один раз при старте."""
        if cls._loaded:
            return

        logger.info("Загрузка Библий в память...")

        # 1. Загружаем метаданные книг
        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            cls._books_meta = yaml.safe_load(f)

        # Запоминаем порядок книг из YAML (он же канонический порядок)
        cls._book_order = list(cls._books_meta.keys())
        logger.info(f"  ✓ Метаданные: {len(cls._book_order)} книг")

        # 2. Загружаем все переводы Библии
        for code, filename in TRANSLATIONS.items():
            path = BIBLES_DIR / filename
            if not path.exists():
                logger.warning(f"  ✗ Файл не найден: {path}")
                continue

            with open(path, "r", encoding="utf-8-sig") as f:
                cls._bibles[code] = json.load(f)

            logger.info(f"  ✓ {code}: {len(cls._bibles[code])} книг")

        cls._loaded = True
        logger.info("Библии загружены ✅")

    # ============ Работа с книгами ============

    @classmethod
    def get_books(cls, testament: str | None = None) -> list[dict]:
        """
        Получить список книг.
        testament: 'ot' (Ветхий Завет), 'nt' (Новый Завет), None (все)
        Возвращает: [{"abbrev": "gn", "testament": "ot", "ru": "...", "en": "...", "es": "..."}]
        """
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
        """Порядковый номер книги (0..65). Нужен для поиска книги в JSON-массиве."""
        try:
            return cls._book_order.index(abbrev)
        except ValueError:
            return None

    # ============ Работа с главами и стихами ============

    @classmethod
    def get_chapters_count(cls, abbrev: str, translation: str) -> int:
        """Количество глав в книге."""
        book = cls._get_book_data(abbrev, translation)
        return len(book["chapters"]) if book else 0

    @classmethod
    def get_chapter(cls, abbrev: str, chapter: int, translation: str) -> list[str] | None:
        """
        Получить главу как список стихов.
        chapter: номер главы начиная с 1 (как у людей, а не с 0)
        Возвращает: ["1-й стих", "2-й стих", ...] или None
        """
        book = cls._get_book_data(abbrev, translation)
        if not book:
            return None
        chapters = book["chapters"]
        # Переводим человеческий номер (с 1) в индекс массива (с 0)
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

    # ============ Утилиты ============

    @classmethod
    def get_translation_for_lang(cls, lang: str) -> str:
        """Возвращает код перевода по умолчанию для языка интерфейса."""
        return DEFAULT_TRANSLATION_FOR_LANG.get(lang, "en_kjv")

    @classmethod
    def _get_book_data(cls, abbrev: str, translation: str) -> dict | None:
        """Внутренний метод: достать сырую книгу из JSON по аббревиатуре."""
        bible = cls._bibles.get(translation)
        if not bible:
            return None
        idx = cls.get_
"""Молитва дня: пул из data/prayers_of_day.yaml, выбор детерминирован по дате."""
import logging
import random
from datetime import date
from pathlib import Path
import yaml

from services.bible_service import BibleService

logger = logging.getLogger(__name__)

PRAYERS_FILE = Path(__file__).parent.parent / "data" / "prayers_of_day.yaml"


class PrayerService:
    """Пул молитв дня. Все пользователи в один день видят одну молитву на своём языке."""

    _prayers: list[dict] = []
    _loaded: bool = False

    @classmethod
    def load(cls) -> None:
        if cls._loaded:
            return

        if not PRAYERS_FILE.exists():
            logger.warning(f"Пул молитв дня не найден: {PRAYERS_FILE}")
            cls._loaded = True
            return

        with open(PRAYERS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []

        cls._prayers = [p for p in data if isinstance(p, dict)]
        # Фиксированное перемешивание — соседние дни не идут подряд по списку.
        random.Random(20240303).shuffle(cls._prayers)
        cls._loaded = True
        logger.info(f"Молитвы дня загружены: {len(cls._prayers)} молитв")

    @classmethod
    def get_prayer_of_day(
        cls,
        lang: str,
        translation: str,
        target_date: date | None = None,
    ) -> dict | None:
        """Возвращает молитву на сегодня для указанного языка.

        Структура:
          {
            "id": str,
            "title": str,
            "text": str,
            "ref": {"abbrev", "chapter", "verse", "book", "text"} | None,
          }
        """
        if not cls._prayers:
            return None

        d = target_date or date.today()
        rnd = random.Random(d.toordinal())
        prayer = rnd.choice(cls._prayers)

        title = (prayer.get("title") or {}).get(lang) or (prayer.get("title") or {}).get("en", "")
        text = (prayer.get("text") or {}).get(lang) or (prayer.get("text") or {}).get("en", "")

        ref_data = None
        ref_str = prayer.get("ref")
        if ref_str:
            try:
                abbrev, chapter_s, verse_s = ref_str.split(":")
                chapter = int(chapter_s)
                verse = int(verse_s)
                verse_text = BibleService.get_verse(abbrev, chapter, verse, translation)
                if verse_text:
                    ref_data = {
                        "abbrev": abbrev,
                        "chapter": chapter,
                        "verse": verse,
                        "book": BibleService.get_book_name(abbrev, lang),
                        "text": verse_text,
                    }
            except (ValueError, AttributeError) as e:
                logger.warning(f"Невалидный ref в молитве {prayer.get('id')}: {ref_str} ({e})")

        return {
            "id": prayer.get("id", ""),
            "title": title,
            "text": text,
            "ref": ref_data,
        }

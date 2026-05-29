"""Молитва дня: пул из data/prayers_of_day.yaml, выбор детерминирован по дате."""
import logging
import random
from datetime import date
from pathlib import Path
import yaml

from services.bible_service import BibleService

logger = logging.getLogger(__name__)

PRAYERS_FILE = Path(__file__).parent.parent / "data" / "prayers_of_day.yaml"
TOPICS_FILE = Path(__file__).parent.parent / "data" / "prayer_topics.yaml"


class PrayerService:
    """Пул молитв дня. Все пользователи в один день видят одну молитву на своём языке."""

    _prayers: list[dict] = []
    # Молитвы по темам (data/prayer_topics.yaml).
    _sections: list[dict] = []
    _topic_by_id: dict[str, dict] = {}
    # Сырые карточки фиксированных тем по их id (= topic_id) для get_prayer_by_id / избранного.
    _fixed_by_id: dict[str, dict] = {}
    _loaded: bool = False

    @classmethod
    def load(cls) -> None:
        if cls._loaded:
            return

        if not PRAYERS_FILE.exists():
            logger.warning(f"Пул молитв дня не найден: {PRAYERS_FILE}")
        else:
            with open(PRAYERS_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or []
            cls._prayers = [p for p in data if isinstance(p, dict)]
            # Фиксированное перемешивание — соседние дни не идут подряд по списку.
            random.Random(20240303).shuffle(cls._prayers)
            logger.info(f"Молитвы дня загружены: {len(cls._prayers)} молитв")

        cls._load_topics()
        cls._loaded = True

    @classmethod
    def _load_topics(cls) -> None:
        """Загружает раздел «По темам» и строит индексы тем и фиксированных молитв."""
        if not TOPICS_FILE.exists():
            logger.warning(f"Темы молитв не найдены: {TOPICS_FILE}")
            return

        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        cls._sections = [s for s in (data.get("sections") or []) if isinstance(s, dict)]
        for section in cls._sections:
            for topic in section.get("topics", []):
                topic_id = topic.get("id")
                if not topic_id:
                    continue
                cls._topic_by_id[topic_id] = topic
                if topic.get("kind") == "fixed":
                    raw = dict(topic.get("prayer") or {})
                    raw["id"] = topic_id  # id фикс-молитвы = id темы (для избранного)
                    cls._fixed_by_id[topic_id] = raw

        topic_count = sum(len(s.get("topics", [])) for s in cls._sections)
        logger.info(
            f"Темы молитв загружены: {len(cls._sections)} секций, {topic_count} тем"
        )

    @classmethod
    def _build_prayer_dict(cls, prayer: dict, lang: str, translation: str) -> dict:
        """Собирает карточку молитвы для отдачи в хендлеры.

        Структура:
          {
            "id": str,
            "title": str,
            "text": str,
            "ref": {"abbrev", "chapter", "verse", "book", "text"} | None,
          }
        """
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

    @classmethod
    def get_prayer_of_day(
        cls,
        lang: str,
        translation: str,
        target_date: date | None = None,
    ) -> dict | None:
        """Возвращает молитву на сегодня для указанного языка (детерминирована по дате)."""
        if not cls._prayers:
            return None

        d = target_date or date.today()
        rnd = random.Random(d.toordinal())
        prayer = rnd.choice(cls._prayers)
        return cls._build_prayer_dict(prayer, lang, translation)

    @classmethod
    def get_random_prayer(cls, lang: str, translation: str) -> dict | None:
        """Случайная молитва из пула (без сида по дате — каждый раз новая)."""
        if not cls._prayers:
            return None

        prayer = random.choice(cls._prayers)
        return cls._build_prayer_dict(prayer, lang, translation)

    @classmethod
    def get_prayer_by_id(cls, prayer_id: str, lang: str, translation: str) -> dict | None:
        """Молитва по её стабильному id (для избранного и перерисовки экрана).

        Ищет сперва среди фиксированных молитв тем, затем в пуле дня.
        """
        fixed = cls._fixed_by_id.get(prayer_id)
        if fixed:
            return cls._build_prayer_dict(fixed, lang, translation)

        for prayer in cls._prayers:
            if prayer.get("id") == prayer_id:
                return cls._build_prayer_dict(prayer, lang, translation)
        return None

    # ── Молитвы по темам ────────────────────────────────────
    @classmethod
    def get_sections(cls) -> list[dict]:
        """Секции раздела «По темам» (для рендера меню)."""
        return cls._sections

    @classmethod
    def get_topic(cls, topic_id: str) -> dict | None:
        """Метаданные темы по её id."""
        return cls._topic_by_id.get(topic_id)

    @classmethod
    def is_pool_topic(cls, topic_id: str) -> bool:
        """True, если тема черпает молитвы из пула (а не одна фиксированная)."""
        topic = cls._topic_by_id.get(topic_id)
        return bool(topic and topic.get("kind") == "pool")

    @classmethod
    def get_topic_prayer(
        cls,
        topic_id: str,
        lang: str,
        translation: str,
        *,
        random_pick: bool = False,
        target_date: date | None = None,
        exclude_id: str | None = None,
    ) -> dict | None:
        """Молитва для темы.

        fixed — заданная молитва темы. pool — выборка из пула дня по префиксам тем:
        детерминирована по (topic_id, дата), либо случайна при random_pick=True.
        exclude_id — id, который исключаем при случайной выборке (чтобы «Другая» не
        повторила текущую молитву; игнорируется, если кандидат остался один).
        """
        topic = cls._topic_by_id.get(topic_id)
        if not topic:
            return None

        if topic.get("kind") == "fixed":
            raw = cls._fixed_by_id.get(topic_id)
            return cls._build_prayer_dict(raw, lang, translation) if raw else None

        themes = set(topic.get("themes") or [])
        candidates = [
            p for p in cls._prayers
            if p.get("id") and p["id"].rsplit("_", 1)[0] in themes
        ]
        if not candidates:
            return None

        if random_pick:
            choices = [p for p in candidates if p.get("id") != exclude_id] or candidates
            raw = random.choice(choices)
        else:
            d = target_date or date.today()
            rnd = random.Random(f"{topic_id}:{d.toordinal()}")
            raw = rnd.choice(candidates)
        return cls._build_prayer_dict(raw, lang, translation)

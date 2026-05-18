import logging
from pathlib import Path
import yaml

from services.bible_service import BibleService

logger = logging.getLogger(__name__)

TOPICS_FILE = Path(__file__).parent.parent / "data" / "topics.yaml"


class TopicService:
    """Сервис подборок стихов по жизненным ситуациям."""

    _topics: dict[str, dict] = {}
    _topic_order: list[str] = []
    _loaded: bool = False

    @classmethod
    def load(cls) -> None:
        """Загружает темы при старте бота."""
        if cls._loaded:
            return

        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            cls._topics = yaml.safe_load(f)

        cls._topic_order = list(cls._topics.keys())
        cls._loaded = True
        logger.info(f"Темы подборок загружены: {len(cls._topic_order)} тем")

    @classmethod
    def get_topics(cls, lang: str) -> list[dict]:
        """
        Список всех тем с локализованными названиями.
        Возвращает: [{"id": "anxiety", "emoji": "😰", "name": "Тревога"}]
        """
        result = []
        for topic_id in cls._topic_order:
            topic = cls._topics[topic_id]
            result.append({
                "id": topic_id,
                "emoji": topic["emoji"],
                "name": topic["names"].get(lang, topic["names"].get("en", topic_id)),
            })
        return result

    @classmethod
    def get_topic(cls, topic_id: str, lang: str, translation: str) -> dict | None:
        """
        Получить тему с подгруженными текстами стихов.
        Возвращает:
        {
            "id": "anxiety",
            "emoji": "😰",
            "name": "Тревога",
            "intro": "Бог знает твою тревогу...",
            "verses": [
                {"abbrev": "ph", "chapter": 4, "verse": 6, "text": "Не заботьтесь..."},
                ...
            ]
        }
        """
        topic = cls._topics.get(topic_id)
        if not topic:
            return None

        intro = topic["intro"].get(lang, topic["intro"].get("en", ""))
        name = topic["names"].get(lang, topic["names"].get("en", topic_id))

        verses = []
        for ref in topic["verses"]:
            verse_data = cls._parse_and_load_verse(ref, translation)
            if verse_data:
                verses.append(verse_data)

        return {
            "id": topic_id,
            "emoji": topic["emoji"],
            "name": name,
            "intro": intro,
            "verses": verses,
        }

    @classmethod
    def _parse_and_load_verse(cls, ref: str, translation: str) -> dict | None:
        """
        Парсит ссылку 'ph:4:6' и подгружает текст стиха.
        Возвращает: {"abbrev": "ph", "chapter": 4, "verse": 6, "text": "..."}
        """
        try:
            parts = ref.split(":")
            abbrev = parts[0]
            chapter = int(parts[1])
            verse_num = int(parts[2])
        except (ValueError, IndexError):
            logger.warning(f"Невозможно распарсить ссылку на стих: {ref}")
            return None

        text = BibleService.get_verse(abbrev, chapter, verse_num, translation)
        if text is None:
            logger.warning(f"Стих не найден: {ref} в переводе {translation}")
            return None

        return {
            "abbrev": abbrev,
            "chapter": chapter,
            "verse": verse_num,
            "text": text,
        }
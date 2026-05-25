from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.topic_service import TopicService


def topics_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Сетка тем (эмоций/ситуаций) — по 2 в ряд."""
    builder = InlineKeyboardBuilder()

    topics = TopicService.get_topics(lang)
    for topic in topics:
        builder.button(
            text=f"{topic['emoji']} {topic['name']}",
            callback_data=f"topic:{topic['id']}"
        )

    builder.button(
        text=t("common.back", lang),
        callback_data="pray"
    )

    # Раскладка: темы по 2 в ряд, кнопка "Назад" одна
    topics_count = len(topics)
    rows = [2] * (topics_count // 2)
    if topics_count % 2:
        rows.append(1)
    rows.append(1)  # back to menu
    builder.adjust(*rows)

    return builder.as_markup()


def topic_view_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Клавиатура под подборкой стихов."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("topics.back_to_topics", lang),
        callback_data="topics"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()
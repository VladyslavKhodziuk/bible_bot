from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def verse_of_day_keyboard(abbrev: str, chapter: int, lang: str) -> InlineKeyboardMarkup:
    """Клавиатура под стихом дня."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("verse.open_chapter", lang),
        callback_data=f"read:ch:{abbrev}:{chapter}"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()


def random_verse_keyboard(abbrev: str, chapter: int, lang: str) -> InlineKeyboardMarkup:
    """Клавиатура под случайным стихом."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("verse.another", lang),
        callback_data="random"
    )
    builder.button(
        text=t("verse.open_chapter", lang),
        callback_data=f"read:ch:{abbrev}:{chapter}"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()
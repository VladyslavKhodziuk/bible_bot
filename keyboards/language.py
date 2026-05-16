from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def language_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора языка."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="setlang:ru")
    builder.button(text="🇺🇸 English", callback_data="setlang:en")
    builder.button(text="🇪🇸 Español", callback_data="setlang:es")
    builder.adjust(1)
    return builder.as_markup()
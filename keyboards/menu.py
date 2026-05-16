from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def welcome_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопка 'Открыть меню' после приветствия."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("welcome.button", lang),
        callback_data="open_menu"
    )
    return builder.as_markup()


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Главное меню с основными разделами бота."""
    builder = InlineKeyboardBuilder()

    builder.button(text=t("menu.read", lang), callback_data="read")
    builder.button(text=t("menu.search", lang), callback_data="search")
    builder.button(text=t("menu.topics", lang), callback_data="topics")
    builder.button(text=t("menu.verse_of_day", lang), callback_data="verse_of_day")
    builder.button(text=t("menu.random", lang), callback_data="random")
    builder.button(text=t("menu.bookmarks", lang), callback_data="bookmarks")
    builder.button(text=t("menu.plan", lang), callback_data="plan")
    builder.button(text=t("menu.share", lang), callback_data="share")
    builder.button(text=t("menu.settings", lang), callback_data="settings")
    builder.button(text=t("menu.donate", lang), callback_data="donate")

    # Раскладка: 1, 1, 1, 2, 2, 2, 1
    # Первые 3 кнопки — главные действия, по одной в ряд
    # Дальше попарно, кроме "Поддержать" — отдельно внизу
    builder.adjust(1, 1, 1, 2, 2, 2, 1)
    return builder.as_markup()
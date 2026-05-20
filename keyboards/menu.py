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
    builder.button(text=t("plan.menu_button", lang), callback_data="plan")
    builder.button(text=t("menu.ai_pastor", lang), callback_data="ai_pastor")
    builder.button(text=t("menu.cabinet", lang), callback_data="cabinet")
    builder.button(text=t("menu.donate", lang), callback_data="donate")

    # Раскладка: 1, 1, 1, 2, 2, 1, 1
    # 3 главных действия по одной, потом попарно, потом ЛК отдельно, потом донат
    builder.adjust(1, 1, 1, 2, 2, 1, 1)
    return builder.as_markup()
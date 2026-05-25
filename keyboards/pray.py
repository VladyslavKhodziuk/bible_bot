from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def pray_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Раздел «Помолиться» — обёртка над подбором стихов по настроению.

    Сюда позже добавятся другие молитвенные функции.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.topics", lang), callback_data="topics")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def cabinet_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Клавиатура личного кабинета."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("cabinet.bookmarks_button", lang),
        callback_data="bookmarks"
    )
    builder.button(
        text=t("cabinet.settings_button", lang),
        callback_data="settings"
    )
    builder.button(
        text=t("feedback.cabinet_review", lang),
        callback_data="fb:start:review"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Главный экран настроек."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("settings.change_language", lang),
        callback_data="settings:change_lang"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()


def language_settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Выбор языка из настроек — с кнопкой 'Назад'."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="changelang:ru")
    builder.button(text="🇺🇸 English", callback_data="changelang:en")
    builder.button(text="🇪🇸 Español", callback_data="changelang:es")
    builder.button(
        text=t("common.back", lang),
        callback_data="settings:open"
    )
    builder.adjust(1)
    return builder.as_markup()
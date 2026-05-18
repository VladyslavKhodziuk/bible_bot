from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.bible_service import BibleService


def settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Главный экран настроек."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("settings.change_language", lang),
        callback_data="settings:change_lang"
    )

    # Показываем кнопку выбора перевода только если их больше одного на языке
    if len(BibleService.get_translations_for_lang(lang)) > 1:
        builder.button(
            text=t("settings.change_translation", lang),
            callback_data="settings:change_translation"
        )

    builder.button(
        text=t("settings.change_notifications", lang),
        callback_data="notif:open"
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
    builder.button(text="🇪🇸 Español", callback_data="changelang:es")
    builder.button(text="🇺🇸 English", callback_data="changelang:en")
    builder.button(text="🇺🇦 Українська", callback_data="changelang:uk")
    builder.button(text="🇷🇺 Русский", callback_data="changelang:ru")
    builder.button(
        text=t("common.back", lang),
        callback_data="settings:open"
    )
    builder.adjust(1)
    return builder.as_markup()


def translation_settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Выбор перевода Библии — только переводы для текущего языка интерфейса."""
    builder = InlineKeyboardBuilder()
    for code in BibleService.get_translations_for_lang(lang):
        name = t(f"settings.translation_names.{code}", lang)
        builder.button(text=name, callback_data=f"changetrans:{code}")
    builder.button(
        text=t("common.back", lang),
        callback_data="settings:open"
    )
    builder.adjust(1)
    return builder.as_markup()
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.timezones import label as tz_label


def settings_keyboard(user, lang: str) -> InlineKeyboardMarkup:
    """Главный экран настроек. Ряды: язык | уведомления / пояс / идея | баг / назад."""
    builder = InlineKeyboardBuilder()
    layout = []

    # === Ряд 1: язык + уведомления ===
    builder.button(
        text=t("settings.btn_language", lang),
        callback_data="settings:change_lang"
    )

    builder.button(
        text=t("settings.btn_notif_hub", lang),
        callback_data="notif:hub"
    )
    layout.append(2)

    # === Ряд 2: часовой пояс (full-width) ===
    builder.button(
        text=t("settings.btn_timezone", lang, timezone=tz_label(user.timezone, lang)),
        callback_data="settings:tz"
    )
    layout.append(1)

    # === Ряд 3: обратная связь ===
    builder.button(
        text=t("feedback.cabinet_idea", lang),
        callback_data="fb:start:idea"
    )
    builder.button(
        text=t("feedback.cabinet_bug", lang),
        callback_data="fb:start:bug"
    )
    layout.append(2)

    # === Возврат ===
    builder.button(
        text=t("common.back", lang),
        callback_data="cabinet"
    )
    layout.append(1)

    builder.adjust(*layout)
    return builder.as_markup()


def language_settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Выбор языка из настроек — с кнопкой 'Назад'."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇪🇸 Español", callback_data="changelang:es")
    builder.button(text="🇺🇸 English", callback_data="changelang:en")
    builder.button(text="🇺🇦 Українська", callback_data="changelang:uk")
    builder.button(text="🌍 Русский", callback_data="changelang:ru")
    builder.button(
        text=t("common.back", lang),
        callback_data="settings:open"
    )
    builder.adjust(1)
    return builder.as_markup()
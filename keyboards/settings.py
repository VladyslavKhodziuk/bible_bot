from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def settings_keyboard(user, lang: str) -> InlineKeyboardMarkup:
    """Главный экран настроек. Сетка 2 в ряд: язык | уведомления, идея | баг, назад."""
    builder = InlineKeyboardBuilder()
    layout = []

    # === Ряд 1: язык + уведомления ===
    language_name = t(f"settings.language_names.{lang}", lang)
    builder.button(
        text=t("settings.btn_language", lang, language=language_name),
        callback_data="settings:change_lang"
    )

    if user.notifications_enabled:
        notif_text = t("settings.btn_notif_on", lang, time=user.notification_time)
    else:
        notif_text = t("settings.btn_notif_off", lang)
    builder.button(
        text=notif_text,
        callback_data="notif:open"
    )
    layout.append(2)

    # === Ряд 2: обратная связь ===
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
    builder.button(text="🇷🇺 Русский", callback_data="changelang:ru")
    builder.button(
        text=t("common.back", lang),
        callback_data="settings:open"
    )
    builder.adjust(1)
    return builder.as_markup()
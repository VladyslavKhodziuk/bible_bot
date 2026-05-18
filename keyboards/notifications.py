from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t

# Список временных слотов, из которых юзер выбирает
TIME_SLOTS = [
    "06:00", "07:00", "08:00",
    "09:00", "10:00", "12:00",
    "18:00", "20:00", "21:00",
]


def notifications_keyboard(enabled: bool, lang: str) -> InlineKeyboardMarkup:
    """Главный экран настроек уведомлений."""
    builder = InlineKeyboardBuilder()

    if enabled:
        builder.button(
            text=t("notifications.disable", lang),
            callback_data="notif:toggle:off"
        )
        builder.button(
            text=t("notifications.change_time", lang),
            callback_data="notif:time"
        )
    else:
        builder.button(
            text=t("notifications.enable", lang),
            callback_data="notif:toggle:on"
        )

    builder.button(
        text=t("common.back", lang),
        callback_data="settings:open"
    )
    builder.adjust(1)
    return builder.as_markup()


def time_picker_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Сетка времени для выбора."""
    builder = InlineKeyboardBuilder()
    for slot in TIME_SLOTS:
        builder.button(text=f"🕐 {slot}", callback_data=f"notif:settime:{slot}")
    builder.button(
        text=t("common.back", lang),
        callback_data="notif:open"
    )
    builder.adjust(3, 3, 3, 1)
    return builder.as_markup()
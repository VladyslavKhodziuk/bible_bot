from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from keyboards.notifications import TIME_SLOTS


def prayer_notifications_keyboard(enabled: bool, time: str, lang: str) -> InlineKeyboardMarkup:
    """Экран настроек напоминания о молитве — вкл/выкл и время."""
    builder = InlineKeyboardBuilder()

    if enabled:
        builder.button(
            text=t("pray.notif.btn_disable", lang),
            callback_data="pray_notif:toggle:off",
        )
        builder.button(
            text=t("pray.notif.btn_time", lang, time=time),
            callback_data="pray_notif:time",
        )
    else:
        builder.button(
            text=t("pray.notif.btn_enable", lang),
            callback_data="pray_notif:toggle:on",
        )

    builder.button(
        text=t("pray.back_to_card", lang),
        callback_data="pray",
    )
    builder.adjust(1)
    return builder.as_markup()


def prayer_time_picker_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Сетка времени для напоминания о молитве."""
    builder = InlineKeyboardBuilder()
    for slot in TIME_SLOTS:
        builder.button(text=f"🕐 {slot}", callback_data=f"pray_notif:settime:{slot}")
    builder.button(
        text=t("common.back", lang),
        callback_data="pray_notif:open",
    )
    builder.adjust(4, 4, 4, 4, 1, 1)
    return builder.as_markup()

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.timezones import SUPPORTED_TIMEZONES, label as tz_label, clock_emoji

# Список временных слотов, из которых юзер выбирает — каждый час с 06:00 до 22:00
TIME_SLOTS = [f"{hour:02d}:00" for hour in range(6, 23)]


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
        callback_data="notif:hub"
    )
    builder.adjust(1)
    return builder.as_markup()


def notifications_hub_keyboard(user, lang: str, has_active_plan: bool, plan_progress=None) -> InlineKeyboardMarkup:
    """Экран-хаб уведомлений с тремя секциями: стих / молитва / план."""
    builder = InlineKeyboardBuilder()

    # === Стих дня ===
    if user.notifications_enabled:
        verse_row = t("notif.hub.verse_on", lang, time=user.notification_time)
    else:
        verse_row = t("notif.hub.verse_off", lang)
    builder.button(text=verse_row, callback_data="notif:open")

    # === Молитва ===
    if user.prayer_notifications_enabled:
        prayer_row = t("notif.hub.prayer_on", lang, time=user.prayer_notification_time)
    else:
        prayer_row = t("notif.hub.prayer_off", lang)
    builder.button(text=prayer_row, callback_data="notif:prayer")

    # === План чтения ===
    if has_active_plan and plan_progress is not None:
        if plan_progress.notification_enabled:
            plan_row = t("notif.hub.plan_on", lang, time=plan_progress.notification_time)
        else:
            plan_row = t("notif.hub.plan_off", lang)
        builder.button(text=plan_row, callback_data="notif:plan")
    else:
        builder.button(
            text=t("notif.hub.plan_none", lang),
            callback_data="notif:plan:none"
        )

    builder.button(
        text=t("common.back", lang),
        callback_data="settings:open"
    )
    builder.adjust(1)
    return builder.as_markup()


def _tz_button_text(tz: str, lang: str, current_tz: str | None) -> str:
    """Подпись кнопки пояса. У текущей зоны вместо циферблата — ✅."""
    marker = "✅" if tz == current_tz else clock_emoji(tz)
    return f"{marker} {tz_label(tz, lang)}"


def timezone_picker_keyboard(lang: str, current_tz: str | None = None) -> InlineKeyboardMarkup:
    """Список часовых поясов для выбора. Подпись = город + текущее смещение.
    Активный пояс юзера помечается галочкой."""
    builder = InlineKeyboardBuilder()
    for tz in SUPPORTED_TIMEZONES:
        builder.button(text=_tz_button_text(tz, lang, current_tz), callback_data=f"settings:settz:{tz}")
    builder.button(
        text=t("common.back", lang),
        callback_data="settings:open"
    )
    builder.adjust(1)
    return builder.as_markup()


def onboarding_timezone_keyboard(lang: str, current_tz: str | None = None) -> InlineKeyboardMarkup:
    """Выбор часового пояса с экрана приветствия. Отдельный callback-префикс
    (onboard:settz:) после выбора возвращает на приветствие, а не в настройки.
    Активный пояс юзера помечается галочкой."""
    builder = InlineKeyboardBuilder()
    for tz in SUPPORTED_TIMEZONES:
        builder.button(text=_tz_button_text(tz, lang, current_tz), callback_data=f"onboard:settz:{tz}")
    builder.button(
        text=t("common.back", lang),
        callback_data="onboard:welcome"
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
    builder.adjust(4, 4, 4, 4, 1, 1)
    return builder.as_markup()
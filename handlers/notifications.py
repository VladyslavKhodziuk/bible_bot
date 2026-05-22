from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.i18n import t
from services.timezones import is_valid, label as tz_label
from keyboards.notifications import (
    notifications_keyboard,
    time_picker_keyboard,
    timezone_picker_keyboard,
)

router = Router()


def _build_notifications_text(user, lang: str) -> str:
    """Текст экрана уведомлений."""
    if user.notifications_enabled:
        status = t(
            "notifications.status_enabled",
            lang,
            time=user.notification_time
        )
    else:
        status = t("notifications.status_disabled", lang)
    # Показываем текущий часовой пояс — чтобы было понятно, в каком времени
    # трактуется выбранный час уведомления.
    tz_line = t("notifications.timezone_line", lang, timezone=tz_label(user.timezone))
    return t("notifications.title", lang, status=status) + "\n\n" + tz_line


@router.callback_query(F.data == "notif:open")
async def open_notifications(callback: CallbackQuery):
    """Открыть настройки уведомлений."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        _build_notifications_text(user, lang),
        reply_markup=notifications_keyboard(user.notifications_enabled, lang)
    )
    await callback.answer()


@router.callback_query(F.data == "notif:toggle:on")
async def enable_notifications(callback: CallbackQuery):
    """Включить уведомления."""
    await UserService.set_notifications(callback.from_user.id, enabled=True)

    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await callback.answer(
        t("notifications.enabled_message", lang),
        show_alert=False
    )
    await callback.message.edit_text(
        _build_notifications_text(user, lang),
        reply_markup=notifications_keyboard(True, lang)
    )


@router.callback_query(F.data == "notif:toggle:off")
async def disable_notifications(callback: CallbackQuery):
    """Выключить уведомления."""
    await UserService.set_notifications(callback.from_user.id, enabled=False)

    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await callback.answer(
        t("notifications.disabled_message", lang),
        show_alert=False
    )
    await callback.message.edit_text(
        _build_notifications_text(user, lang),
        reply_markup=notifications_keyboard(False, lang)
    )


@router.callback_query(F.data == "notif:time")
async def choose_time(callback: CallbackQuery):
    """Экран выбора времени."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("notifications.choose_time", lang),
        reply_markup=time_picker_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "notif:tz")
async def choose_timezone(callback: CallbackQuery):
    """Экран выбора часового пояса."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("notifications.choose_timezone", lang),
        reply_markup=timezone_picker_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("notif:settz:"))
async def set_timezone(callback: CallbackQuery):
    """Установить часовой пояс пользователя."""
    tz_name = callback.data.split(":", 2)[2]  # IANA-имя (может содержать '/')

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    if not is_valid(tz_name):
        await callback.answer("⚠️", show_alert=True)
        return

    await UserService.set_timezone(callback.from_user.id, tz_name)
    user = await UserService.get(callback.from_user.id)

    await callback.answer(
        t("notifications.timezone_changed", lang, timezone=tz_label(tz_name)),
        show_alert=False
    )
    await callback.message.edit_text(
        _build_notifications_text(user, lang),
        reply_markup=notifications_keyboard(user.notifications_enabled, lang)
    )


@router.callback_query(F.data.startswith("notif:settime:"))
async def set_time(callback: CallbackQuery):
    """Установить новое время."""
    time = callback.data.split(":", 2)[2]  # "HH:MM"

    await UserService.set_notifications(
        callback.from_user.id,
        enabled=True,  # автоматически включаем, если юзер выбрал время
        time=time
    )

    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await callback.answer(
        t("notifications.time_changed", lang, time=time),
        show_alert=False
    )
    await callback.message.edit_text(
        _build_notifications_text(user, lang),
        reply_markup=notifications_keyboard(True, lang)
    )
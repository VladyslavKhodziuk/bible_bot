"""Настройки персонального напоминания о «молитве на сегодня»."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.i18n import t
from keyboards.prayer_notifications import (
    prayer_notifications_keyboard,
    prayer_time_picker_keyboard,
)

router = Router()


def _build_status_text(user, lang: str) -> str:
    if user.prayer_notifications_enabled:
        status = t("pray.notif.status_enabled", lang, time=user.prayer_notification_time)
    else:
        status = t("pray.notif.status_disabled", lang)
    return t("pray.notif.title", lang, status=status)


@router.callback_query(F.data == "pray_notif:open")
async def open_prayer_notifications(callback: CallbackQuery):
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        _build_status_text(user, lang),
        reply_markup=prayer_notifications_keyboard(
            user.prayer_notifications_enabled,
            user.prayer_notification_time,
            lang,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "pray_notif:toggle:on")
async def enable_prayer_notifications(callback: CallbackQuery):
    await UserService.set_prayer_notifications(callback.from_user.id, enabled=True)
    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await callback.answer(t("pray.notif.enabled_message", lang), show_alert=False)
    await callback.message.edit_text(
        _build_status_text(user, lang),
        reply_markup=prayer_notifications_keyboard(True, user.prayer_notification_time, lang),
    )


@router.callback_query(F.data == "pray_notif:toggle:off")
async def disable_prayer_notifications(callback: CallbackQuery):
    await UserService.set_prayer_notifications(callback.from_user.id, enabled=False)
    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await callback.answer(t("pray.notif.disabled_message", lang), show_alert=False)
    await callback.message.edit_text(
        _build_status_text(user, lang),
        reply_markup=prayer_notifications_keyboard(False, user.prayer_notification_time, lang),
    )


@router.callback_query(F.data == "pray_notif:time")
async def choose_prayer_time(callback: CallbackQuery):
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("pray.notif.choose_time", lang),
        reply_markup=prayer_time_picker_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pray_notif:settime:"))
async def set_prayer_time(callback: CallbackQuery):
    time = callback.data.split(":", 2)[2]  # "HH:MM"

    # Выбор времени автоматически включает напоминание — так юзер не застрянет
    # в состоянии «время задано, но пуш не идёт».
    await UserService.set_prayer_notifications(
        callback.from_user.id,
        enabled=True,
        time=time,
    )
    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await callback.answer(t("pray.notif.time_changed", lang, time=time), show_alert=False)
    await callback.message.edit_text(
        _build_status_text(user, lang),
        reply_markup=prayer_notifications_keyboard(True, time, lang),
    )

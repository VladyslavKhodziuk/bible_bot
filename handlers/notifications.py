from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.plan_service import PlanService
from services.i18n import t
from keyboards.notifications import (
    notifications_keyboard,
    notifications_hub_keyboard,
    time_picker_keyboard,
)
from keyboards.prayer_notifications import (
    prayer_notifications_keyboard,
    prayer_time_picker_keyboard,
)
from keyboards.plan import notification_settings_keyboard as plan_notif_keyboard

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
    return t("notifications.title", lang, status=status)


@router.callback_query(F.data == "notif:hub")
async def open_notifications_hub(callback: CallbackQuery):
    """Экран-хаб уведомлений: стих, молитва, план — в одном месте."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    active_plan = await PlanService.get_active(callback.from_user.id)
    has_plan = active_plan is not None

    await callback.message.edit_text(
        t("notif.hub.title", lang),
        reply_markup=notifications_hub_keyboard(user, lang, has_plan, active_plan),
    )
    await callback.answer()


@router.callback_query(F.data == "notif:plan:none")
async def plan_none_hint(callback: CallbackQuery):
    """Подсказка, когда у юзера нет активного плана."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    await callback.answer(t("notif.hub.plan_none_alert", lang), show_alert=True)


@router.callback_query(F.data == "notif:prayer")
async def open_prayer_from_hub(callback: CallbackQuery):
    """Экран уведомлений молитвы из хаба — кнопка «Назад» ведёт в хаб."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    if user.prayer_notifications_enabled:
        status = t("pray.notif.status_enabled", lang, time=user.prayer_notification_time)
    else:
        status = t("pray.notif.status_disabled", lang)

    await callback.message.edit_text(
        t("pray.notif.title", lang, status=status),
        reply_markup=prayer_notifications_keyboard(
            user.prayer_notifications_enabled,
            user.prayer_notification_time,
            lang,
            back_callback="notif:hub",
            back_label_key="common.back",
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "notif:plan")
async def open_plan_from_hub(callback: CallbackQuery):
    """Экран уведомлений плана из хаба — кнопка «Назад» ведёт в хаб."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    active = await PlanService.get_active(callback.from_user.id)
    if not active:
        await callback.answer(t("notif.hub.plan_none_alert", lang), show_alert=True)
        return

    parts = [
        t("plan.notif_title", lang),
        "",
        t("plan.notif_intro", lang),
        "",
        t("plan.notif_current", lang, time=active.notification_time),
    ]
    if active.notification_enabled:
        parts.append(t("plan.notif_status_on", lang))
    else:
        parts.append(t("plan.notif_status_off", lang))

    await callback.message.edit_text(
        "\n".join(parts),
        reply_markup=plan_notif_keyboard(
            active.notification_enabled,
            lang,
            back_callback="notif:hub",
            back_label=t("common.back", lang),
        ),
    )
    await callback.answer()


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
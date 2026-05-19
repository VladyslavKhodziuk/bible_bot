import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.plan_service import PlanService
from services.bible_service import BibleService
from services.streak_service import StreakService
from services.streak_display import format_streak_indicator
from services.i18n import t
from keyboards.plan import (
    plan_list_keyboard,
    plan_preview_keyboard,
    active_plan_keyboard,
    change_confirm_keyboard,
    completed_keyboard,
    notification_settings_keyboard,
    time_picker_keyboard,
)
from keyboards.menu import main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()


# ============ Главный вход: /menu → 📚 План чтения ============

@router.callback_query(F.data == "plan")
async def open_plan(callback: CallbackQuery):
    """Главный вход в раздел плана.

    Поведение:
    - Если у юзера НЕТ активного плана → список доступных планов
    - Если ЕСТЬ активный план → экран прогресса
    """
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    active = await PlanService.get_active(callback.from_user.id)

    if not active:
        # Нет активного плана — показываем список доступных
        await _show_plan_list(callback, lang)
    else:
        # Есть активный план — показываем прогресс
        await _show_active_plan(callback, active, lang)


async def _show_plan_list(callback: CallbackQuery, lang: str):
    """Экран выбора плана."""
    text = (
        f"{t('plan.no_active_title', lang)}\n\n"
        f"{t('plan.no_active_intro', lang)}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=plan_list_keyboard(lang)
    )
    await callback.answer()


# ============ Превью плана перед активацией ============

@router.callback_query(F.data.startswith("plan:preview:"))
async def preview_plan(callback: CallbackQuery):
    """Показать описание плана с кнопкой 'Начать'."""
    plan_id = callback.data.split(":")[2]
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    plan = PlanService.get_plan(plan_id)
    if not plan:
        await callback.answer("⚠️", show_alert=True)
        return

    emoji = plan.get("emoji", "📖")
    name = PlanService.get_plan_name(plan_id, lang)
    description = PlanService.get_plan_description(plan_id, lang)
    duration = plan.get("duration_days", 0)

    # Первый день — для предпросмотра
    first_day_readings = PlanService.get_day_readings(plan_id, 1)
    first_day_lines = []
    for r in first_day_readings:
        book_name = BibleService.get_book_name(r["abbrev"], lang)
        first_day_lines.append(f"  • {book_name} {r['chapter']}")
    first_day_text = "\n".join(first_day_lines)

    parts = [
        t("plan.preview_title", lang, emoji=emoji, name=name),
        "",
        t("plan.preview_duration", lang, days=duration),
        "",
        t("plan.preview_description", lang, description=description),
        "",
        t("plan.preview_first_day", lang),
        first_day_text,
    ]
    text = "\n".join(parts)

    await callback.message.edit_text(
        text,
        reply_markup=plan_preview_keyboard(plan_id, lang)
    )
    await callback.answer()


# ============ Активация плана ============

@router.callback_query(F.data.startswith("plan:activate:"))
async def activate_plan(callback: CallbackQuery):
    """Активировать выбранный план."""
    plan_id = callback.data.split(":")[2]
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    plan = PlanService.get_plan(plan_id)
    if not plan:
        await callback.answer("⚠️", show_alert=True)
        return

    # Активируем (это автоматически делает предыдущий план abandoned)
    progress = await PlanService.activate(callback.from_user.id, plan_id)
    logger.info(f"Юзер {callback.from_user.id} активировал план {plan_id}")

    # Сразу показываем экран активного плана
    await _show_active_plan(callback, progress, lang)


# ============ Экран активного плана ============

async def _show_active_plan(callback: CallbackQuery, progress, lang: str):
    """Главный экран активного плана: прогресс + чтение на сегодня."""
    plan = PlanService.get_plan(progress.plan_id)
    if not plan:
        # План был удалён? Сбрасываем
        await PlanService.abandon(callback.from_user.id)
        await _show_plan_list(callback, lang)
        return

    emoji = plan.get("emoji", "📖")
    name = PlanService.get_plan_name(progress.plan_id, lang)
    progress_data = PlanService.calculate_progress(progress)

    # Чтение на сегодня
    today_readings = PlanService.get_day_readings(progress.plan_id, progress.current_day)

    # Подготовим словарь имён книг для клавиатуры
    book_names_map = {}
    for r in today_readings:
        if r["abbrev"] not in book_names_map:
            book_names_map[r["abbrev"]] = BibleService.get_book_name(r["abbrev"], lang)

    # Серия (если есть)
    user = await UserService.get(callback.from_user.id)
    streak_line = format_streak_indicator(user.current_streak, lang) if user else ""

    # Формируем текст
    parts = [
        t("plan.active_title", lang, emoji=emoji, name=name),
        "",
        t(
            "plan.active_progress", lang,
            completed=progress_data["completed_count"],
            total=progress_data["total_days"],
            percent=progress_data["percent"],
        ),
    ]
    if streak_line:
        parts.append(streak_line.replace("🔥", "🔥 ").replace("дней подряд", "дн.").strip())

    parts.append("")
    parts.append(t("plan.active_today_title", lang, day=progress.current_day))

    for r in today_readings:
        book_name = book_names_map[r["abbrev"]]
        parts.append(
            t("plan.active_today_reading", lang, book=book_name, chapter=r["chapter"])
        )

    text = "\n".join(parts)

    await callback.message.edit_text(
        text,
        reply_markup=active_plan_keyboard(today_readings, lang, book_names_map)
    )
    await callback.answer()


# ============ Отметить день как прочитанный ============

@router.callback_query(F.data == "plan:mark_done")
async def mark_done(callback: CallbackQuery):
    """Отметить текущий день плана как прочитанный."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    active = await PlanService.get_active(callback.from_user.id)
    if not active:
        await callback.answer("⚠️", show_alert=True)
        return

    completed_day = active.current_day

    # Засчитываем день в серию (как чтение)
    await StreakService.touch(callback.from_user.id)

    # Отмечаем день в плане
    success, is_completed = await PlanService.mark_day_complete(callback.from_user.id)

    if not success:
        await callback.answer("⚠️", show_alert=True)
        return

    if is_completed:
        # План завершён — поздравление
        plan = PlanService.get_plan(active.plan_id)
        name = PlanService.get_plan_name(active.plan_id, lang)
        days = plan.get("duration_days", 0) if plan else 0

        text = (
            f"{t('plan.completed_title', lang)}\n\n"
            f"{t('plan.completed_text', lang, name=name, days=days)}"
        )
        await callback.message.edit_text(
            text,
            reply_markup=completed_keyboard(lang)
        )
        await callback.answer(t("plan.marked_done", lang, day=completed_day))
        return

    # Перерисовываем экран с обновлённым прогрессом
    updated = await PlanService.get_active(callback.from_user.id)
    await _show_active_plan(callback, updated, lang)
    await callback.answer(t("plan.marked_done", lang, day=completed_day))


# ============ Смена плана ============

@router.callback_query(F.data == "plan:change")
async def change_plan_confirm(callback: CallbackQuery):
    """Подтверждение смены плана."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    active = await PlanService.get_active(callback.from_user.id)
    if not active:
        # Нет активного — просто открываем список
        await _show_plan_list(callback, lang)
        return

    name = PlanService.get_plan_name(active.plan_id, lang)

    text = (
        f"{t('plan.change_confirm_title', lang)}\n\n"
        f"{t('plan.change_confirm_text', lang, name=name)}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=change_confirm_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "plan:change_yes")
async def change_plan_confirmed(callback: CallbackQuery):
    """Юзер подтвердил смену плана — отказываемся от текущего и показываем список."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await PlanService.abandon(callback.from_user.id)
    logger.info(f"Юзер {callback.from_user.id} отказался от активного плана")

    await _show_plan_list(callback, lang)


# ============ Уведомления плана ============

@router.callback_query(F.data == "plan:notif")
async def notification_settings(callback: CallbackQuery):
    """Экран настроек уведомлений плана."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    active = await PlanService.get_active(callback.from_user.id)
    if not active:
        await callback.answer("⚠️", show_alert=True)
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

    text = "\n".join(parts)

    await callback.message.edit_text(
        text,
        reply_markup=notification_settings_keyboard(active.notification_enabled, lang)
    )
    await callback.answer()


@router.callback_query(F.data == "plan:notif:set_time")
async def choose_notif_time(callback: CallbackQuery):
    """Выбор времени уведомления — сетка часов."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    text = (
        f"{t('plan.notif_title', lang)}\n\n"
        f"{t('plan.notif_choose_time', lang)}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=time_picker_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("plan:notif:time:"))
async def set_notif_time(callback: CallbackQuery):
    """Юзер выбрал время — сохраняем."""
    time_str = callback.data.split(":", 3)[3]  # формат "HH:MM"

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    success = await PlanService.set_notification_time(callback.from_user.id, time_str)
    if not success:
        await callback.answer("⚠️", show_alert=True)
        return

    await callback.answer(t("plan.notif_saved", lang, time=time_str))
    await notification_settings(callback)  # перерисовываем экран настроек


@router.callback_query(F.data == "plan:notif:disable")
async def disable_notif(callback: CallbackQuery):
    """Выключить уведомления плана."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await PlanService.toggle_notification(callback.from_user.id, enabled=False)
    await callback.answer(t("plan.notif_disabled", lang))
    await notification_settings(callback)


@router.callback_query(F.data == "plan:notif:enable")
async def enable_notif(callback: CallbackQuery):
    """Включить уведомления плана."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    active = await PlanService.get_active(callback.from_user.id)
    if not active:
        await callback.answer("⚠️", show_alert=True)
        return

    await PlanService.toggle_notification(callback.from_user.id, enabled=True)
    await callback.answer(t("plan.notif_enabled_at", lang, time=active.notification_time))
    await notification_settings(callback)
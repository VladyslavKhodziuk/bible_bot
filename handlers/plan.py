import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.plan_service import PlanService, render_progress_bar
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
    reading_mode_keyboard,
    day_done_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()


# ============ Главный вход ============

@router.callback_query(F.data == "plan")
async def open_plan(callback: CallbackQuery):
    """Открыть план: список или активный."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    active = await PlanService.get_active(callback.from_user.id)

    if not active:
        await _show_plan_list(callback, lang)
    else:
        await _show_active_plan(callback, active, lang)


async def _show_plan_list(callback: CallbackQuery, lang: str):
    """Список доступных планов."""
    text = (
        f"{t('plan.no_active_title', lang)}\n\n"
        f"{t('plan.no_active_intro', lang)}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=plan_list_keyboard(lang)
    )
    await callback.answer()


# ============ Превью плана ============

@router.callback_query(F.data.startswith("plan:preview:"))
async def preview_plan(callback: CallbackQuery):
    """Описание плана перед активацией."""
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

    progress = await PlanService.activate(callback.from_user.id, plan_id)
    logger.info(f"Юзер {callback.from_user.id} активировал план {plan_id}")

    await _show_active_plan(callback, progress, lang)


# ============ Экран активного плана ============

async def _show_active_plan(callback: CallbackQuery, progress, lang: str):
    """Главный экран активного плана с прогресс-баром."""
    plan = PlanService.get_plan(progress.plan_id)
    if not plan:
        await PlanService.abandon(callback.from_user.id)
        await _show_plan_list(callback, lang)
        return

    emoji = plan.get("emoji", "📖")
    name = PlanService.get_plan_name(progress.plan_id, lang)
    progress_data = PlanService.calculate_progress(progress)

    today_readings = PlanService.get_day_readings(progress.plan_id, progress.current_day)

    book_names_map = {}
    for r in today_readings:
        if r["abbrev"] not in book_names_map:
            book_names_map[r["abbrev"]] = BibleService.get_book_name(r["abbrev"], lang)

    user = await UserService.get(callback.from_user.id)
    streak_line = format_streak_indicator(user.current_streak, lang) if user else ""

    # Прогресс-бар
    progress_bar = render_progress_bar(progress_data["percent"])

    parts = [
        t("plan.active_title", lang, emoji=emoji, name=name),
        "",
        t(
            "plan.active_progress", lang,
            completed=progress_data["completed_count"],
            total=progress_data["total_days"],
            percent=progress_data["percent"],
        ),
        f"<code>{progress_bar}</code>",
    ]
    if streak_line:
        parts.append(streak_line)

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


# ============ Изолированный режим чтения ============

@router.callback_query(F.data.startswith("plan:read:"))
async def read_in_plan_mode(callback: CallbackQuery):
    """
    Открыть главу плана в изолированном режиме.
    callback_data: plan:read:N (N — индекс чтения)
    """
    try:
        reading_idx = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("⚠️", show_alert=True)
        return

    await _show_reading(callback, reading_idx)


@router.callback_query(F.data == "plan:next_reading")
async def next_reading(callback: CallbackQuery):
    """Переход к следующей главе текущего дня."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return

    progress = await PlanService.get_active(callback.from_user.id)
    if not progress:
        await callback.answer("⚠️", show_alert=True)
        return

    today_readings = PlanService.get_day_readings(progress.plan_id, progress.current_day)
    next_idx = progress.current_reading_idx + 1

    # Если вышли за границы — переходим на последнюю
    if next_idx >= len(today_readings):
        next_idx = len(today_readings) - 1

    await _show_reading(callback, next_idx)


async def _show_reading(callback: CallbackQuery, reading_idx: int):
    """
    Внутренняя функция показа главы плана. Используется и при прямом клике
    на главу, и при переходе "следующая глава".

    Защита: если день уже отмечен сегодня — не пускаем, показываем toast.
    """
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    progress = await PlanService.get_active(callback.from_user.id)
    if not progress:
        await callback.answer("⚠️", show_alert=True)
        return

    # Защита: день уже отмечен сегодня
    can_read = await PlanService.can_complete_today(callback.from_user.id)
    if not can_read:
        await callback.answer(
            t("plan.already_today_alert", lang),
            show_alert=True,
        )
        return

    today_readings = PlanService.get_day_readings(progress.plan_id, progress.current_day)
    if not today_readings:
        await callback.answer("⚠️", show_alert=True)
        return

    if reading_idx < 0 or reading_idx >= len(today_readings):
        await callback.answer("⚠️", show_alert=True)
        return

    reading = today_readings[reading_idx]
    abbrev = reading["abbrev"]
    chapter = reading["chapter"]

    # Обновляем индекс в БД
    if progress.current_reading_idx != reading_idx:
        from sqlalchemy import select
        from database import async_session
        from models import PlanProgress
        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == callback.from_user.id,
                    PlanProgress.status == "active",
                    )
            )
            p = result.scalar_one_or_none()
            if p:
                p.current_reading_idx = reading_idx
                await session.commit()

    chapter_data = BibleService.get_chapter(abbrev, chapter, user.translation)
    if not chapter_data:
        await callback.answer("⚠️", show_alert=True)
        return

    plan = PlanService.get_plan(progress.plan_id)
    plan_name = PlanService.get_plan_name(progress.plan_id, lang)
    total_days = plan.get("duration_days", 0) if plan else 0
    book_name = BibleService.get_book_name(abbrev, lang)

    separator = t("plan.read_separator", lang)
    header = t("plan.read_header", lang, day=progress.current_day, total=total_days, plan_name=plan_name)
    chapter_title = f"<b>{book_name} {chapter}</b>"
    progress_line = t("plan.read_reading_progress", lang,
                      current=reading_idx + 1, total_readings=len(today_readings))

    verses_text = "\n".join(
        f"<b>{i + 1}</b> {v}" for i, v in enumerate(chapter_data)
    )

    parts = [
        header,
        progress_line,
        separator,
        "",
        chapter_title,
        "",
        verses_text,
        "",
        separator,
    ]
    text = "\n".join(parts)

    if len(text) > 4000:
        text = text[:3997] + "..."

    is_last = (reading_idx == len(today_readings) - 1)

    await callback.message.edit_text(
        text,
        reply_markup=reading_mode_keyboard(reading_idx, len(today_readings), is_last, lang)
    )
    await callback.answer()


# ============ Отметить день как прочитанный ============

@router.callback_query(F.data == "plan:mark_done")
async def mark_done(callback: CallbackQuery):
    """Отметить день — финальная кнопка."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    # Засчитываем серию
    await StreakService.touch(callback.from_user.id)

    # Отмечаем день в плане
    result, current_day, total_days = await PlanService.mark_day_complete(callback.from_user.id)

    if result == "no_active":
        await callback.answer("⚠️", show_alert=True)
        return

    if result == "already_today":
        # Уже отмечал сегодня — toast и остаёмся на месте
        await callback.answer(
            t("plan.already_today_alert", lang),
            show_alert=True,
        )
        return

    if result == "plan_finished":
        # Поздравление с завершением плана
        active = await PlanService.get_active(callback.from_user.id)
        # active уже None, потому что статус completed
        # Берём имя из последней записи
        from sqlalchemy import select
        from database import async_session
        from models import PlanProgress
        async with async_session() as session:
            res = await session.execute(
                select(PlanProgress)
                .where(
                    PlanProgress.user_id == callback.from_user.id,
                    PlanProgress.status == "completed",
                )
                .order_by(PlanProgress.completed_at.desc())
                .limit(1)
            )
            finished = res.scalar_one_or_none()

        plan_id = finished.plan_id if finished else ""
        plan = PlanService.get_plan(plan_id)
        name = PlanService.get_plan_name(plan_id, lang)
        days = plan.get("duration_days", 0) if plan else 0

        text = (
            f"{t('plan.completed_title', lang)}\n\n"
            f"{t('plan.completed_text', lang, name=name, days=days)}"
        )
        await callback.message.edit_text(
            text,
            reply_markup=completed_keyboard(lang)
        )
        await callback.answer()
        return

    # result == "completed" — день засчитан, план продолжается
    # Получаем обновлённый прогресс
    updated = await PlanService.get_active(callback.from_user.id)
    progress_data = PlanService.calculate_progress(updated)
    progress_bar = render_progress_bar(progress_data["percent"])

    # Следующий день — какие чтения
    next_day = updated.current_day
    next_readings = PlanService.get_day_readings(updated.plan_id, next_day)

    parts = [
        t("plan.day_done_title", lang),
        "",
        t("plan.day_done_today", lang, day=current_day),
        "",
        t(
            "plan.day_done_progress", lang,
            completed=progress_data["completed_count"],
            total=progress_data["total_days"],
        ),
        f"<code>{progress_bar}</code>",
        "",
        t("plan.day_done_tomorrow", lang, next_day=next_day),
    ]
    for r in next_readings:
        book_name = BibleService.get_book_name(r["abbrev"], lang)
        parts.append(t("plan.day_done_tomorrow_reading", lang, book=book_name, chapter=r["chapter"]))

    text = "\n".join(parts)

    await callback.message.edit_text(
        text,
        reply_markup=day_done_keyboard(lang)
    )
    await callback.answer()


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
    """Юзер подтвердил смену плана."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await PlanService.abandon(callback.from_user.id)
    logger.info(f"Юзер {callback.from_user.id} отказался от плана")

    await _show_plan_list(callback, lang)


# ============ Уведомления плана ============

@router.callback_query(F.data == "plan:notif")
async def notification_settings(callback: CallbackQuery):
    """Настройки уведомлений плана."""
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
    time_str = callback.data.split(":", 3)[3]

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    success = await PlanService.set_notification_time(callback.from_user.id, time_str)
    if not success:
        await callback.answer("⚠️", show_alert=True)
        return

    await callback.answer(t("plan.notif_saved", lang, time=time_str))
    await notification_settings(callback)


@router.callback_query(F.data == "plan:notif:disable")
async def disable_notif(callback: CallbackQuery):
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await PlanService.toggle_notification(callback.from_user.id, enabled=False)
    await callback.answer(t("plan.notif_disabled", lang))
    await notification_settings(callback)


@router.callback_query(F.data == "plan:notif:enable")
async def enable_notif(callback: CallbackQuery):
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    active = await PlanService.get_active(callback.from_user.id)
    if not active:
        await callback.answer("⚠️", show_alert=True)
        return

    await PlanService.toggle_notification(callback.from_user.id, enabled=True)
    await callback.answer(t("plan.notif_enabled_at", lang, time=active.notification_time))
    await notification_settings(callback)


# ============ История планов ============

@router.callback_query(F.data == "plan:history")
async def show_history(callback: CallbackQuery):
    """Экран 'Мои планы': завершённые, активный, отложенные."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    history = await PlanService.get_history(callback.from_user.id)

    # Если пусто
    if not history:
        text = (
            f"{t('plan.history_title', lang)}\n\n"
            f"{t('plan.history_empty', lang)}"
        )
        builder = InlineKeyboardBuilder()
        builder.button(
            text=t("plan.history_back", lang),
            callback_data="cabinet"
        )
        builder.adjust(1)
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        return

    # Разделяем по статусам
    completed = [p for p in history if p.status == "completed"]
    active = [p for p in history if p.status == "active"]
    abandoned = [p for p in history if p.status == "abandoned"]

    parts = [t("plan.history_title", lang), ""]

    # === Завершённые ===
    if completed:
        parts.append(t("plan.history_completed", lang, count=len(completed)))
        for p in completed:
            plan = PlanService.get_plan(p.plan_id)
            if not plan:
                continue
            emoji = plan.get("emoji", "📖")
            name = PlanService.get_plan_name(p.plan_id, lang)
            days = plan.get("duration_days", 0)
            # Дата завершения
            date_str = p.completed_at.strftime("%d.%m.%Y") if p.completed_at else "—"
            parts.append(
                t("plan.history_item_completed", lang,
                  emoji=emoji, name=name, date=date_str, days=days)
            )
        parts.append("")

    # === Активный ===
    if active:
        parts.append(t("plan.history_active", lang))
        for p in active:
            plan = PlanService.get_plan(p.plan_id)
            if not plan:
                continue
            emoji = plan.get("emoji", "📖")
            name = PlanService.get_plan_name(p.plan_id, lang)
            total = plan.get("duration_days", 0)
            parts.append(
                t("plan.history_item_active", lang,
                  emoji=emoji, name=name, current=p.current_day, total=total)
            )
        parts.append("")

    # === Отложенные ===
    if abandoned:
        parts.append(t("plan.history_abandoned", lang, count=len(abandoned)))
        for p in abandoned:
            plan = PlanService.get_plan(p.plan_id)
            if not plan:
                continue
            emoji = plan.get("emoji", "📖")
            name = PlanService.get_plan_name(p.plan_id, lang)
            total = plan.get("duration_days", 0)
            parts.append(
                t("plan.history_item_abandoned", lang,
                  emoji=emoji, name=name, current=p.current_day, total=total)
            )
        parts.append("")

    text = "\n".join(parts)

    # Клавиатура: возможность возобновить отложенные планы + возврат
    builder = InlineKeyboardBuilder()

    # Если есть активный — нельзя возобновить (нужно сначала отказаться)
    # Поэтому кнопки "Возобновить" показываем только если активного нет
    if not active and abandoned:
        for p in abandoned:
            plan = PlanService.get_plan(p.plan_id)
            if not plan:
                continue
            name = PlanService.get_plan_name(p.plan_id, lang)
            # Обрезаем длинные имена для кнопки
            display_name = name if len(name) < 20 else name[:18] + "…"
            builder.button(
                text=t("plan.history_resume_button", lang, name=display_name),
                callback_data=f"plan:resume:{p.id}"
            )

    builder.button(
        text=t("plan.history_back", lang),
        callback_data="cabinet"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("plan:resume:"))
async def resume_plan(callback: CallbackQuery):
    """Возобновить отложенный план — снова делаем активным."""
    try:
        progress_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("⚠️", show_alert=True)
        return

    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("⚠️", show_alert=True)
        return
    lang = user.lang

    # Проверяем — действительно ли это план юзера и в статусе abandoned
    from sqlalchemy import select
    from database import async_session
    from models import PlanProgress

    async with async_session() as session:
        result = await session.execute(
            select(PlanProgress).where(
                PlanProgress.id == progress_id,
                PlanProgress.user_id == callback.from_user.id,
                PlanProgress.status == "abandoned",
            )
        )
        progress = result.scalar_one_or_none()
        if not progress:
            await callback.answer("⚠️", show_alert=True)
            return

        # Перед возобновлением убедимся, что нет активного плана
        active_check = await session.execute(
            select(PlanProgress).where(
                PlanProgress.user_id == callback.from_user.id,
                PlanProgress.status == "active",
            )
        )
        if active_check.scalar_one_or_none():
            # У юзера уже есть активный — отказ
            await callback.answer("⚠️", show_alert=True)
            return

        # Возобновляем
        progress.status = "active"
        await session.commit()

    logger.info(f"Юзер {callback.from_user.id} возобновил план id={progress_id}")

    # Открываем экран активного плана
    callback.data = "plan"
    await open_plan(callback)
import logging
from datetime import timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.plan_service import PlanService, render_progress_bar
from services.bible_service import BibleService
from services.streak_service import StreakService
from services.streak_display import format_streak_indicator, get_plan_milestone_message
from services.timezones import local_today
from services.bot_meta import get_bot_username
from services.share import build_share_url
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

    # Прогноз даты завершения, если начать сегодня (темп — день в сутки)
    tz = user.timezone if user else "UTC"
    finish_date = local_today(tz) + timedelta(days=duration)
    eta_str = finish_date.strftime("%d.%m.%Y")

    parts = [
        t("plan.preview_title", lang, emoji=emoji, name=name),
        "",
        t("plan.preview_duration", lang, days=duration),
        t("plan.preview_eta", lang, date=eta_str),
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
    tz = user.timezone if user else "UTC"
    streak_line = format_streak_indicator(user.current_streak, lang) if user else ""

    # День уже отмечен сегодня? Тогда экран в состоянии «на сегодня всё»,
    # а чтения current_day относятся уже к следующему дню — их не показываем.
    completed_today = not await PlanService.can_complete_today(
        callback.from_user.id, today=local_today(tz)
    )

    # Прогресс-бар + прогноз даты завершения
    progress_bar = render_progress_bar(progress_data["percent"])
    finish_str = PlanService.estimate_finish_date(progress, tz).strftime("%d.%m.%Y")

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
        t("plan.active_eta", lang, date=finish_str),
    ]
    if streak_line:
        parts.append(streak_line)

    parts.append("")

    if completed_today:
        # Сегодня всё прочитано — ждём следующего дня
        parts.append(t("plan.active_done_today", lang))
        parts.append(t("plan.active_done_next", lang, day=progress.current_day))
    else:
        parts.append(t("plan.active_today_title", lang, day=progress.current_day))
        for r in today_readings:
            book_name = book_names_map[r["abbrev"]]
            parts.append(
                t("plan.active_today_reading", lang, book=book_name, chapter=r["chapter"])
            )

    text = "\n".join(parts)

    await callback.message.edit_text(
        text,
        reply_markup=active_plan_keyboard(
            today_readings, lang, book_names_map, completed_today=completed_today
        )
    )
    await callback.answer()


# ============ Изолированный режим чтения ============

@router.callback_query(F.data.startswith("plan:read:"))
async def read_in_plan_mode(callback: CallbackQuery):
    """
    Открыть главу плана в изолированном режиме.
    callback_data: plan:read:N или plan:read:N:pP (N — индекс чтения, P — страница)
    """
    parts = callback.data.split(":")
    try:
        reading_idx = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("⚠️", show_alert=True)
        return

    page = 1
    if len(parts) >= 4 and parts[3].startswith("p"):
        try:
            page = int(parts[3][1:])
        except ValueError:
            page = 1

    await _show_reading(callback, reading_idx, page)


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


async def _show_reading(callback: CallbackQuery, reading_idx: int, page: int = 1):
    """
    Внутренняя функция показа главы плана. Используется и при прямом клике
    на главу, и при переходе "следующая глава".

    Чтение доступно всегда (в т.ч. по кнопке из старого пуша). Повторную
    *отметку* дня сдерживает mark_done, а не вход в текст.

    Длинные главы (напр. Псалом 119) листаются страницами через
    BibleService.paginate_chapter — так текст не обрезается и не рвёт HTML.
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

    # Запоминаем позицию чтения внутри дня
    await PlanService.set_reading_index(callback.from_user.id, reading_idx)

    chapter_data = BibleService.get_chapter(abbrev, chapter, user.translation)
    if not chapter_data:
        await callback.answer("⚠️", show_alert=True)
        return

    # Разбиваем главу на страницы под лимит Telegram
    pages = BibleService.paginate_chapter(chapter_data)
    if page < 1 or page > len(pages):
        page = 1
    start_v, end_v = pages[page - 1]

    plan = PlanService.get_plan(progress.plan_id)
    plan_name = PlanService.get_plan_name(progress.plan_id, lang)
    total_days = plan.get("duration_days", 0) if plan else 0
    book_name = BibleService.get_book_name(abbrev, lang)

    separator = t("plan.read_separator", lang)
    header = t("plan.read_header", lang, day=progress.current_day, total=total_days, plan_name=plan_name)
    progress_line = t("plan.read_reading_progress", lang,
                      current=reading_idx + 1, total_readings=len(today_readings))

    chapter_title = f"<b>{book_name} {chapter}</b>"
    if len(pages) > 1:
        chapter_title += (
            f"\n<i>{t('read.verses_range', lang, start=start_v, end=end_v)}</i>"
        )

    verses_text = "\n".join(
        f"<b>{i}.</b> {chapter_data[i - 1]}" for i in range(start_v, end_v + 1)
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

    is_last = (reading_idx == len(today_readings) - 1)

    await callback.message.edit_text(
        text,
        reply_markup=reading_mode_keyboard(
            reading_idx, len(today_readings), is_last, lang,
            page=page, total_pages=len(pages),
        )
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

    # Отмечаем день в плане (день считаем в зоне пользователя — как и стрик)
    result, current_day, total_days, milestone = await PlanService.mark_day_complete(
        callback.from_user.id, today=local_today(user.timezone)
    )

    if result == "no_active":
        await callback.answer("⚠️", show_alert=True)
        return

    if result == "already_today":
        # Уже отмечал сегодня — toast и остаёмся на месте (стрик не трогаем)
        await callback.answer(
            t("plan.already_today_alert", lang),
            show_alert=True,
        )
        return

    # День реально засчитан — теперь засчитываем серию
    await StreakService.touch(callback.from_user.id)

    if result == "plan_finished":
        # Поздравление с завершением плана
        finished = await PlanService.get_last_completed(callback.from_user.id)
        plan_id = finished.plan_id if finished else ""
        plan = PlanService.get_plan(plan_id)
        name = PlanService.get_plan_name(plan_id, lang)
        days = plan.get("duration_days", 0) if plan else 0

        text = (
            f"{t('plan.completed_title', lang)}\n\n"
            f"{t('plan.completed_text', lang, name=name, days=days)}"
        )

        # Декоративная кнопка «Поделиться» (если username бота доступен)
        bot_username = await get_bot_username(callback.bot)
        share_url = None
        if bot_username:
            share_text = t("plan.completed_share_text", lang, name=name)
            share_url = build_share_url(share_text, f"https://t.me/{bot_username}")

        await callback.message.edit_text(
            text,
            reply_markup=completed_keyboard(lang, share_url=share_url)
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
    ]

    # Поздравление с прохождением вехи 25/50/75 %
    if milestone:
        milestone_msg = get_plan_milestone_message(milestone, lang)
        if milestone_msg:
            parts.append("")
            parts.append(milestone_msg)

    parts += [
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

    # Возобновляем (проверки внутри: план юзера, статус abandoned, нет активного)
    ok = await PlanService.resume(callback.from_user.id, progress_id)
    if not ok:
        await callback.answer("⚠️", show_alert=True)
        return

    logger.info(f"Юзер {callback.from_user.id} возобновил план id={progress_id}")

    # Открываем экран активного плана
    callback.data = "plan"
    await open_plan(callback)
"""Планировщик уведомлений: стих дня + план чтения."""
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from database import async_session
from models import User, PlanProgress
from services.bible_service import BibleService
from services.plan_service import PlanService
from services.streak_service import StreakService
from services.streak_display import format_streak_indicator, get_milestone_message
from services.i18n import t

logger = logging.getLogger(__name__)


# ============ Утилиты ============

def _get_time_of_day(time_str: str) -> str:
    """Возвращает категорию времени суток по строке HH:MM.

    Категории: morning / day / evening / night
    """
    try:
        hour = int(time_str.split(":")[0])
    except (ValueError, IndexError):
        return "day"

    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 18:
        return "day"
    elif 18 <= hour < 23:
        return "evening"
    return "night"


# ============ Отправка стиха дня ============

async def _send_verse_to_user(bot: Bot, user: User) -> None:
    """Отправить стих дня одному юзеру. Также засчитывает день серии."""
    verse = BibleService.get_verse_of_day(user.translation)
    if not verse:
        return

    # Засчитываем день серии
    streak_result = await StreakService.touch(user.tg_id)

    book_name = BibleService.get_book_name(verse["abbrev"], user.lang)
    reference = t(
        "verse.reference",
        user.lang,
        book=book_name,
        chapter=verse["chapter"],
        verse=verse["verse"],
    )

    name = user.first_name or "друг"

    # === Особые сообщения: ободрение или заморозка ===
    if streak_result.returned_after_loss:
        try:
            await bot.send_message(
                chat_id=user.tg_id,
                text=t("streak.encouragement", user.lang, name=name),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить ободрение юзеру {user.tg_id}: {e}")
    elif streak_result.freeze_used:
        try:
            await bot.send_message(
                chat_id=user.tg_id,
                text=t(
                    "streak.freeze_used", user.lang,
                    name=name,
                    streak=streak_result.current_streak,
                    freezes=streak_result.freezes_available,
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о заморозке юзеру {user.tg_id}: {e}")

    # === Основное сообщение со стихом ===
    time_of_day = _get_time_of_day(user.notification_time)
    greeting = t(f"greetings.{time_of_day}", user.lang, name=name)
    streak_line = format_streak_indicator(streak_result.current_streak, user.lang)

    parts = [greeting]
    if streak_line:
        parts.append(streak_line)
    parts.append("")
    parts.append(reference)
    parts.append("")
    parts.append(f"<i>{verse['text']}</i>")
    text = "\n".join(parts)

    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("verse.open_chapter", user.lang),
        callback_data=f"read:ch:{verse['abbrev']}:{verse['chapter']}"
    )
    builder.button(
        text=t("common.back_to_menu", user.lang),
        callback_data="open_menu"
    )
    builder.adjust(1)

    try:
        await bot.send_message(
            chat_id=user.tg_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        logger.info(f"Стих дня отправлен юзеру {user.tg_id}")
    except Exception as e:
        logger.warning(f"Не удалось отправить стих дня юзеру {user.tg_id}: {e}")

    # === Поздравление с милстоуном (отдельным сообщением) ===
    if streak_result.milestone_reached:
        msg = get_milestone_message(streak_result.milestone_reached, user.lang)
        if msg:
            builder = InlineKeyboardBuilder()
            builder.button(
                text=t("streak.onboarding_button", user.lang),
                callback_data="streak:onboarding_done"
            )
            try:
                await bot.send_message(
                    chat_id=user.tg_id,
                    text=msg,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить милстоун юзеру {user.tg_id}: {e}")


# ============ Отправка плана чтения ============

async def _send_plan_to_user(bot: Bot, user: User, progress: PlanProgress) -> None:
    """Отправить юзеру уведомление о плане чтения на сегодня."""
    plan = PlanService.get_plan(progress.plan_id)
    if not plan:
        return

    readings = PlanService.get_day_readings(progress.plan_id, progress.current_day)
    if not readings:
        return

    name = user.first_name or "друг"
    plan_name = PlanService.get_plan_name(progress.plan_id, user.lang)

    # Приветствие по времени плана
    time_of_day = _get_time_of_day(progress.notification_time)
    greeting = t(f"greetings.{time_of_day}", user.lang, name=name)

    parts = [
        greeting,
        "",
        t("plan.push_title", user.lang, name=plan_name),
        "",
        t("plan.push_today", user.lang, day=progress.current_day),
    ]

    for r in readings:
        book_name = BibleService.get_book_name(r["abbrev"], user.lang)
        parts.append(t("plan.push_reading", user.lang, book=book_name, chapter=r["chapter"]))

    text = "\n".join(parts)

    # Кнопки: открыть каждую главу в изолированном режиме плана + переход на план
    builder = InlineKeyboardBuilder()
    for idx, r in enumerate(readings):
        book_name = BibleService.get_book_name(r["abbrev"], user.lang)
        builder.button(
            text=f"📖 {book_name} {r['chapter']}",
            callback_data=f"plan:read:{idx}"
        )
    builder.button(
        text=t("plan.menu_button", user.lang),
        callback_data="plan"
    )
    builder.adjust(1)

    try:
        await bot.send_message(
            chat_id=user.tg_id,
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        logger.info(
            f"План отправлен юзеру {user.tg_id} "
            f"(план: {progress.plan_id}, день: {progress.current_day})"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить план юзеру {user.tg_id}: {e}")


# ============ Главная функция планировщика (каждую минуту) ============

async def send_daily_verses(bot: Bot):
    """
    Запускается каждую минуту. Проверяет:
    1. Кому пора слать стих дня
    2. Кому пора слать план чтения
    """
    current_time = datetime.now().strftime("%H:%M")

    # === 1. Стих дня ===
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.notifications_enabled == True,
                User.notification_time == current_time,
            )
        )
        verse_users = result.scalars().all()

    for user in verse_users:
        try:
            await _send_verse_to_user(bot, user)
        except Exception as e:
            logger.warning(f"Ошибка стиха дня для {user.tg_id}: {e}")

    # === 2. План чтения ===
    async with async_session() as session:
        result = await session.execute(
            select(PlanProgress, User)
            .join(User, User.tg_id == PlanProgress.user_id)
            .where(
                PlanProgress.status == "active",
                PlanProgress.notification_enabled == True,
                PlanProgress.notification_time == current_time,
            )
        )
        plan_rows = result.all()

    for progress, user in plan_rows:
        try:
            await _send_plan_to_user(bot, user, progress)
        except Exception as e:
            logger.warning(f"Ошибка плана для {user.tg_id}: {e}")


# ============ Регистрация планировщика ============

def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создаёт и запускает планировщик задач."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_verses,
        trigger="cron",
        minute="*",  # каждую минуту
        args=[bot],
    )
    scheduler.start()
    logger.info("Планировщик запущен (каждую минуту)")
    return scheduler
"""Планировщик уведомлений: стих дня + план чтения."""
import html
import logging
from datetime import datetime

import psutil

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramServerError, TelegramRetryAfter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from database import async_session
from models import User, PlanProgress
from services.bible_service import BibleService
from services.plan_service import PlanService
from services.prayer_service import PrayerService
from services.streak_service import StreakService
from services.streak_display import (
    format_streak_indicator,
    get_milestone_message,
    get_daily_progress_message,
    build_dismiss_keyboard,
    build_milestone_keyboard,
    with_donate_addendum,
)
from services.analytics_service import AnalyticsService
from services.alert_service import AlertService
from services.ai_pastor_service import AIPastorService
from services.timezones import local_hhmm
from services.i18n import t
from config import (
    REPORT_CHAT_ID, REPORT_TIME, ADMIN_IDS, MONTHLY_REPORT_DAY, CLEANUP_DAY,
    ALERT_MEM_THRESHOLD, ALERT_DISK_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Сбои Telegram, означающие проблему инфраструктуры (а не «юзер заблокировал
# бота» — то нормально и алерта не требует). Только эти классы дают алерт.
_INFRA_TG_ERRORS = (TelegramNetworkError, TelegramServerError, TelegramRetryAfter)


async def _alert_if_infra(exc: Exception, context: str) -> None:
    """Шлёт алерт, только если сбой отправки относится к инфраструктуре."""
    if isinstance(exc, _INFRA_TG_ERRORS):
        await AlertService.alert_error(
            key=f"telegram_infra:{type(exc).__name__}",
            title="Сбой отправки в Telegram",
            detail=f"{context}: {type(exc).__name__}: {exc}",
        )


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

    name = html.escape(user.first_name or "друг")

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
        AnalyticsService.record(user.tg_id, "notif_verse", "notif")
    except Exception as e:
        logger.warning(f"Не удалось отправить стих дня юзеру {user.tg_id}: {e}")
        AnalyticsService.record(user.tg_id, "notif_verse", "error")
        await _alert_if_infra(e, "рассылка стиха дня")

    # === Поздравление с милстоуном (отдельным сообщением) ===
    # На milestone-днях к тексту добавляется блок поддержки проекта + кнопка.
    if streak_result.milestone_reached:
        msg = get_milestone_message(streak_result.milestone_reached, user.lang)
        if msg:
            try:
                await bot.send_message(
                    chat_id=user.tg_id,
                    text=with_donate_addendum(msg, user.lang),
                    reply_markup=build_milestone_keyboard(
                        user.lang, dismiss_key="streak.onboarding_button"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить милстоун юзеру {user.tg_id}: {e}")
    # === Daily-progress в обычные дни роста серии ===
    elif streak_result.streak_grew and not streak_result.is_first_time:
        try:
            await bot.send_message(
                chat_id=user.tg_id,
                text=get_daily_progress_message(streak_result.current_streak, user.lang),
                reply_markup=build_dismiss_keyboard(
                    user.lang, dismiss_key="streak.onboarding_button"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить daily-progress юзеру {user.tg_id}: {e}")


# ============ Отправка молитвы дня ============

async def _send_prayer_to_user(bot: Bot, user: User) -> None:
    """Отправить юзеру карточку «молитвы на сегодня» с кнопкой «Аминь» и share-ссылкой."""
    # Локальный импорт — иначе циклический (handlers/pray импортирует services/i18n,
    # а scheduler не нуждается в pray до этой точки).
    from handlers.pray import _share_link_html
    from services.bot_meta import get_bot_username

    prayer = PrayerService.get_prayer_of_day(user.lang, user.translation)
    if not prayer:
        return

    greeting = t("pray.notif.push_greeting", user.lang)
    bot_username = await get_bot_username(bot)

    parts = [
        greeting,
        "",
        f"<b>{html.escape(prayer['title'])}</b>",
        "",
        f"<i>«{prayer['text']}»</i>",
    ]
    if prayer.get("ref"):
        ref = prayer["ref"]
        parts.append("")
        parts.append(t(
            "pray.verse_line",
            user.lang,
            book=ref["book"],
            chapter=ref["chapter"],
            verse=ref["verse"],
            verse_text=ref["text"],
        ))
    share = _share_link_html(prayer, user.lang, bot_username)
    if share:
        parts.append("")
        parts.append(share)
    text_body = "\n".join(parts)

    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("pray.amen_btn", user.lang),
        callback_data="pray:amen",
    )
    builder.button(
        text=t("pray.notif.push_open", user.lang),
        callback_data="pray",
    )
    builder.button(
        text=t("common.back_to_menu", user.lang),
        callback_data="open_menu",
    )
    builder.adjust(1)

    try:
        await bot.send_message(
            chat_id=user.tg_id,
            text=text_body,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info(f"Молитва дня отправлена юзеру {user.tg_id}")
        AnalyticsService.record(user.tg_id, "notif_prayer", "notif")
    except Exception as e:
        logger.warning(f"Не удалось отправить молитву дня юзеру {user.tg_id}: {e}")
        AnalyticsService.record(user.tg_id, "notif_prayer", "error")
        await _alert_if_infra(e, "рассылка молитвы дня")


# ============ Отправка плана чтения ============

async def _send_plan_to_user(bot: Bot, user: User, progress: PlanProgress) -> None:
    """Отправить юзеру уведомление о плане чтения на сегодня."""
    plan = PlanService.get_plan(progress.plan_id)
    if not plan:
        return

    readings = PlanService.get_day_readings(progress.plan_id, progress.current_day)
    if not readings:
        return

    name = html.escape(user.first_name or "друг")
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
        AnalyticsService.record(user.tg_id, "notif_plan", "notif")
    except Exception as e:
        logger.warning(f"Не удалось отправить план юзеру {user.tg_id}: {e}")
        AnalyticsService.record(user.tg_id, "notif_plan", "error")
        await _alert_if_infra(e, "рассылка плана чтения")


# ============ Health-check ресурсов ============

async def _health_check() -> None:
    """Раз в минуту проверяет RAM и диск; алертит при превышении порога.

    Троттлинг алертов (по ключу) живёт в AlertService, поэтому при длительной
    перегрузке админ получит одно сообщение, а не по одному каждую минуту.
    """
    try:
        mem_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage(".").percent
    except Exception as e:
        logger.warning(f"Health-check не смог прочитать метрики: {e}")
        return

    if mem_percent >= ALERT_MEM_THRESHOLD:
        await AlertService.alert_error(
            key="health_mem",
            title="Высокая нагрузка на память",
            detail=f"RAM занято {mem_percent:.0f}% (порог {ALERT_MEM_THRESHOLD:.0f}%)",
        )
    if disk_percent >= ALERT_DISK_THRESHOLD:
        await AlertService.alert_error(
            key="health_disk",
            title="Заканчивается место на диске",
            detail=f"Диск занят {disk_percent:.0f}% (порог {ALERT_DISK_THRESHOLD:.0f}%)",
        )


# ============ Главная функция планировщика (каждую минуту) ============

async def send_daily_verses(bot: Bot):
    """
    Запускается каждую минуту. Проверяет:
    1. Кому пора слать стих дня
    2. Кому пора слать план чтения
    """
    # current_time — локальное время сервера. Используем его только для отчётов
    # (это ops-задача в одном поясе). Уведомления юзерам матчим по ИХ поясу.
    current_time = datetime.now().strftime("%H:%M")

    # === 1. Стих дня (по часовому поясу пользователя) ===
    # Берём различные пояса среди подписанных юзеров и для каждого считаем его
    # локальное HH:MM — так фильтрация остаётся в SQL по индексам, без выгрузки
    # всех подписчиков каждую минуту.
    verse_users = []
    async with async_session() as session:
        tzs = (await session.execute(
            select(User.timezone)
            .where(User.notifications_enabled == True)
            .distinct()
        )).scalars().all()
        for tz in tzs:
            local_time = local_hhmm(tz)
            rows = (await session.execute(
                select(User).where(
                    User.notifications_enabled == True,
                    User.timezone == tz,
                    User.notification_time == local_time,
                )
            )).scalars().all()
            verse_users.extend(rows)

    for user in verse_users:
        try:
            await _send_verse_to_user(bot, user)
        except Exception as e:
            logger.warning(f"Ошибка стиха дня для {user.tg_id}: {e}")

    # === 2. План чтения (по часовому поясу пользователя) ===
    plan_rows = []
    async with async_session() as session:
        tzs = (await session.execute(
            select(User.timezone)
            .join(PlanProgress, PlanProgress.user_id == User.tg_id)
            .where(
                PlanProgress.status == "active",
                PlanProgress.notification_enabled == True,
            )
            .distinct()
        )).scalars().all()
        for tz in tzs:
            local_time = local_hhmm(tz)
            rows = (await session.execute(
                select(PlanProgress, User)
                .join(User, User.tg_id == PlanProgress.user_id)
                .where(
                    PlanProgress.status == "active",
                    PlanProgress.notification_enabled == True,
                    PlanProgress.notification_time == local_time,
                    User.timezone == tz,
                )
            )).all()
            plan_rows.extend(rows)

    for progress, user in plan_rows:
        try:
            await _send_plan_to_user(bot, user, progress)
        except Exception as e:
            logger.warning(f"Ошибка плана для {user.tg_id}: {e}")

    # === 3. Молитва дня (по часовому поясу пользователя) ===
    prayer_users = []
    async with async_session() as session:
        tzs = (await session.execute(
            select(User.timezone)
            .where(User.prayer_notifications_enabled == True)
            .distinct()
        )).scalars().all()
        for tz in tzs:
            local_time = local_hhmm(tz)
            rows = (await session.execute(
                select(User).where(
                    User.prayer_notifications_enabled == True,
                    User.timezone == tz,
                    User.prayer_notification_time == local_time,
                )
            )).scalars().all()
            prayer_users.extend(rows)

    for user in prayer_users:
        try:
            await _send_prayer_to_user(bot, user)
        except Exception as e:
            logger.warning(f"Ошибка молитвы дня для {user.tg_id}: {e}")

    # === 4. Аналитика: сбрасываем буфер событий в БД ===
    await AnalyticsService.flush()

    # === 4.5. Health-check ресурсов сервера ===
    await _health_check()

    # === 5. Отчёты и обслуживание (раз в сутки, в REPORT_TIME) ===
    if current_time == REPORT_TIME:
        today = datetime.now().day
        await send_activity_report(bot)  # ежедневный за 24ч
        if today == MONTHLY_REPORT_DAY:
            await send_activity_report(bot, monthly=True)
        if today == CLEANUP_DAY:
            await AnalyticsService.cleanup_old_aggregates()
        # Приватность: чистим старые тексты AI-запросов. После отчётов, чтобы
        # месячный отчёт успел учесть запросы до их удаления.
        await AIPastorService.cleanup_old_requests()


# ============ Отчёты активности ============

def _report_targets() -> list[int]:
    """Куда слать отчёт: группа REPORT_CHAT_ID или личка администраторам."""
    return [REPORT_CHAT_ID] if REPORT_CHAT_ID else list(ADMIN_IDS)


async def send_activity_report(bot: Bot, monthly: bool = False):
    """Строит и шлёт сводку активности (за сутки или за месяц) в REPORT_CHAT_ID
    (или в личку администраторам, если группа не задана)."""
    try:
        if monthly:
            text = await AnalyticsService.build_monthly_report()
        else:
            text = await AnalyticsService.build_daily_report()
    except Exception as e:
        logger.error(f"Не удалось построить отчёт активности (monthly={monthly}): {e}")
        return

    targets = _report_targets()
    if not targets:
        logger.warning("Отчёт не отправлен: не задан REPORT_CHAT_ID и нет ADMIN_IDS")
        return

    for chat_id in targets:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            logger.info(f"Отчёт активности отправлен в {chat_id} (monthly={monthly})")
        except Exception as e:
            logger.warning(f"Не удалось отправить отчёт в {chat_id}: {e}")


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
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from services.user_service import UserService
from services.bible_service import BibleService
from services.i18n import t

logger = logging.getLogger(__name__)

# Глобальный планировщик
scheduler = AsyncIOScheduler()


async def send_daily_verses(bot: Bot) -> None:
    """
    Задача, которая выполняется каждую минуту.
    Проверяет, кому пора прислать стих дня, и отправляет.
    """
    now = datetime.now()
    time_str = now.strftime("%H:%M")

    users = await UserService.get_users_for_notification(time_str)

    if not users:
        return

    logger.info(f"⏰ {time_str} — отправка стиха дня для {len(users)} юзеров")

    for user in users:
        try:
            await _send_verse_to_user(bot, user)
        except Exception as e:
            logger.warning(
                f"Не удалось отправить стих юзеру {user.tg_id}: {e}"
            )


async def _send_verse_to_user(bot: Bot, user) -> None:
    """Отправить стих дня конкретному юзеру. Засчитывает день серии."""
    from services.streak_service import StreakService
    from services.streak_display import format_streak_indicator, get_milestone_message

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

    # === Особые случаи: ободрение или заморозка ===
    name = user.first_name or "друг"

    if streak_result.returned_after_loss:
        # Серия сгорела недавно, юзер вернулся — отправляем ободрение
        await bot.send_message(
            chat_id=user.tg_id,
            text=t("streak.encouragement", user.lang, name=name),
            parse_mode="HTML",
        )
    elif streak_result.freeze_used:
        # Сработала заморозка — отправляем уведомление об этом
        await bot.send_message(
            chat_id=user.tg_id,
            text=t(
                "streak.freeze_used",
                user.lang,
                name=name,
                streak=streak_result.current_streak,
                freezes=streak_result.freezes_available,
            ),
            parse_mode="HTML",
        )

    # === Основное сообщение со стихом дня ===
    greeting = t("notifications.daily_greeting", user.lang)
    streak_line = format_streak_indicator(streak_result.current_streak, user.lang)

    parts = [greeting]
    if streak_line:
        parts.append(streak_line)
    parts.append("")
    parts.append(reference)
    parts.append("")
    parts.append(f"<i>{verse['text']}</i>")
    text = "\n".join(parts)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("verse.open_chapter", user.lang),
        callback_data=f"read:ch:{verse['abbrev']}:{verse['chapter']}"
    )
    builder.button(
        text=t("menu.title", user.lang).split("\n")[0].replace("<b>", "").replace("</b>", ""),
        callback_data="open_menu"
    )
    builder.adjust(1)

    await bot.send_message(
        chat_id=user.tg_id,
        text=text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )

    # === Поздравление с милстоуном ===
    if streak_result.milestone_reached:
        msg = get_milestone_message(streak_result.milestone_reached, user.lang)
        if msg:
            await bot.send_message(
                chat_id=user.tg_id,
                text=msg,
                parse_mode="HTML",
            )


def start_scheduler(bot: Bot) -> None:
    """Запустить планировщик. Вызывать один раз при старте бота."""
    scheduler.add_job(
        send_daily_verses,
        trigger="cron",
        minute="*",  # каждую минуту
        args=[bot],
        id="daily_verses",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("📅 Планировщик уведомлений запущен")
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
    """Отправить стих дня конкретному юзеру."""
    verse = BibleService.get_verse_of_day(user.translation)
    if not verse:
        return

    book_name = BibleService.get_book_name(verse["abbrev"], user.lang)
    reference = t(
        "verse.reference",
        user.lang,
        book=book_name,
        chapter=verse["chapter"],
        verse=verse["verse"],
    )

    greeting = t("notifications.daily_greeting", user.lang)
    text = f"{greeting}\n\n{reference}\n\n<i>{verse['text']}</i>"

    # Клавиатура: открыть главу + меню
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
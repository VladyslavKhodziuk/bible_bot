import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database import init_db
from handlers import start, menu, settings, read, verse, topics, bookmarks, notifications, cabinet, feedback, search, plan
from services.plan_service import PlanService
from services.schelduler import start_scheduler
from services.bible_service import BibleService
from services.topic_service import TopicService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    """Устанавливает список команд, отображаемых в меню Telegram (синяя кнопка)."""
    commands = [
        BotCommand(command="start", description="Начать / Start / Iniciar"),
        BotCommand(command="menu", description="Меню / Menu / Menú"),
    ]
    await bot.set_my_commands(commands)


async def main():
    await init_db()
    logger.info("База данных готова")

    BibleService.load()
    TopicService.load()
    PlanService.load()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Подключаем роутеры
    dp.include_router(feedback.router)
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(settings.router)
    dp.include_router(read.router)
    dp.include_router(verse.router)
    dp.include_router(topics.router)
    dp.include_router(bookmarks.router)
    dp.include_router(notifications.router)
    dp.include_router(cabinet.router)
    dp.include_router(search.router)
    dp.include_router(plan.router)

    await set_bot_commands(bot)
    logger.info("Команды бота установлены")

    start_scheduler(bot)

    logger.info("Бот запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database import init_db
from handlers import start, menu, settings, read, verse, topics, pray, prayer_notifications, bookmarks, notifications, cabinet, feedback, search, plan, donate, ai_pastor, chatid
from handlers import help as help_cmd
from services.plan_service import PlanService
from services.scheduler import setup_scheduler
from services.bible_service import BibleService
from services.topic_service import TopicService
from services.prayer_service import PrayerService
from services.alert_service import AlertService
from services.analytics_service import AnalyticsService
from services import bot_meta
from middlewares.analytics import AnalyticsMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot):
    """Устанавливает список команд, отображаемых в меню Telegram (синяя кнопка)."""
    commands = [
        BotCommand(command="start", description="Iniciar / Почати / Начать"),
        BotCommand(command="menu", description="Menú / Меню / Меню"),
        BotCommand(command="verse", description="Versículo del día / Вірш дня / Стих дня"),
        BotCommand(command="settings", description="Ajustes / Налаштування / Настройки"),
        BotCommand(command="help", description="Ayuda / Допомога / Помощь"),
    ]
    await bot.set_my_commands(commands)


async def main():
    await init_db()
    logger.info("База данных готова")

    BibleService.load()
    TopicService.load()
    PlanService.load()
    PrayerService.load()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Алерты админу о сбоях — сохраняем bot, чтобы notify работал отовсюду
    AlertService.init(bot)

    # Аналитика + throttling: один middleware видит каждое обновление
    dp.update.outer_middleware(AnalyticsMiddleware())

    # Подключаем роутеры
    dp.include_router(feedback.router)
    dp.include_router(donate.router)
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(help_cmd.router)
    dp.include_router(settings.router)
    dp.include_router(read.router)
    dp.include_router(verse.router)
    dp.include_router(topics.router)
    dp.include_router(pray.router)
    dp.include_router(prayer_notifications.router)
    dp.include_router(bookmarks.router)
    dp.include_router(notifications.router)
    dp.include_router(cabinet.router)
    dp.include_router(search.router)
    dp.include_router(plan.router)
    dp.include_router(ai_pastor.router)
    # chatid — последним, чтобы не перехватывать обычные сообщения/пересылки
    dp.include_router(chatid.router)

    # Команды и username — best-effort: кратковременный сетевой обрыв на старте
    # не должен мешать боту подняться (start_polling сам переподключится).
    try:
        await set_bot_commands(bot)
        logger.info("Команды бота установлены")
    except Exception as e:
        logger.warning(f"Не удалось установить команды бота (сеть?): {type(e).__name__}: {e}")

    # Прогреваем кэш username для share-ссылок (не бросает при сбое).
    await bot_meta.prewarm(bot)

    # Запускаем планировщик ДО старта polling
    scheduler = setup_scheduler(bot)
    logger.info("Планировщик запущен")

    logger.info("Бот запускается...")
    try:
        # drop_pending_updates: после простоя/рестарта отбрасываем накопившуюся
        # очередь апдейтов, чтобы бот не «оживал» пачкой устаревших нажатий.
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        # Чистое завершение: останавливаем планировщик, дописываем накопленную
        # в памяти аналитику текущего часа и закрываем HTTP-сессию бота.
        logger.info("Останавливаем бот...")
        scheduler.shutdown(wait=False)
        try:
            await AnalyticsService.flush()
        except Exception as e:
            logger.warning(f"Не удалось дописать аналитику при остановке: {e}")
        await bot.session.close()
        logger.info("Бот остановлен корректно")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
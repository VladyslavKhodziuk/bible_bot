"""Однократный сброс счётчиков прогресса в 0 для всех пользователей.

После перехода со «стриков подряд» на «накопительные счётчики всего дней»
старые значения семантически некорректны (дни подряд ≠ всего дней), поэтому
стартуем всех с чистого листа.

Сбрасывает для каждого User:
    current_streak = 0, current_prayer_streak = 0,
    last_activity_date = NULL, last_prayer_date = NULL,
    streak_explained = 0  (чтобы новый онбординг счётчика показался один раз всем)

Запуск (после бэкапа bot.db):
    python -m scripts.reset_counters

Запускается вручную один раз после деплоя кода.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text  # noqa: E402

from database import async_session  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    async with async_session() as session:
        result = await session.execute(
            text(
                "UPDATE users SET "
                "current_streak = 0, "
                "current_prayer_streak = 0, "
                "last_activity_date = NULL, "
                "last_prayer_date = NULL, "
                "streak_explained = 0"
            )
        )
        await session.commit()
        logger.info("Счётчики сброшены для %s пользователей", result.rowcount)


if __name__ == "__main__":
    asyncio.run(main())

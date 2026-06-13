"""Однократная миграция: добавить колонки prayer_notifications_enabled и
prayer_notification_time в таблицу users.

В проекте нет Alembic — Base.metadata.create_all добавляет только новые
таблицы, не колонки. Поэтому при изменении схемы users её нужно докинуть
руками через ALTER TABLE.

Запуск:
    python -m scripts.migrate_prayer_notifications

Скрипт идемпотентен: если колонка уже есть, пропускает её без ошибок.
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


COLUMNS = [
    ("prayer_notifications_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
    ("prayer_notification_time", "VARCHAR(5) NOT NULL DEFAULT '08:00'"),
    # Молитвенный стрик
    ("current_prayer_streak", "INTEGER NOT NULL DEFAULT 0"),
    ("longest_prayer_streak", "INTEGER NOT NULL DEFAULT 0"),
    ("last_prayer_date", "DATE"),
]


async def column_exists(session, column_name: str) -> bool:
    """В SQLite список колонок таблицы выдаёт PRAGMA table_info."""
    rows = (await session.execute(text("PRAGMA table_info(users)"))).all()
    return any(row[1] == column_name for row in rows)


async def main() -> None:
    async with async_session() as session:
        added = []
        skipped = []
        for column, ddl in COLUMNS:
            if await column_exists(session, column):
                skipped.append(column)
                continue
            await session.execute(text(f"ALTER TABLE users ADD COLUMN {column} {ddl}"))
            added.append(column)
        await session.commit()

        if added:
            logger.info("Добавлены колонки: %s", ", ".join(added))
        if skipped:
            logger.info("Уже существуют (пропущены): %s", ", ".join(skipped))
        if not added and not skipped:
            logger.warning("Колонки не определены — проверь конфигурацию миграции")


if __name__ == "__main__":
    asyncio.run(main())

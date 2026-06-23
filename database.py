import logging

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL, DATA_DIR

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


# Движок подключения к БД
engine = create_async_engine(DATABASE_URL, echo=False)


# WAL: читатели не блокируют писателя и наоборот — критично, т.к. flush
# аналитики (раз в минуту), стрики, AI-запросы и хендлеры пишут параллельно.
# busy_timeout: вместо мгновенной ошибки "database is locked" ждём до 5 сек.
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# Фабрика сессий
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    from models import User, Bookmark, PrayerFavorite, Feedback, PlanProgress, AIRequest, AIConsent, Donation, ActivityHourly, FeedbackRelay  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Sentinel-файл рядом с bot.db (в DATA_DIR — на Railway это Volume, иначе CWD).
# Каждая запись — выполненная миграция (одна на строку). Так миграции
# идемпотентны: при следующем старте уже выполненные пропускаются.
_MIGRATIONS_SENTINEL = DATA_DIR / "migrations_applied.txt"


def _applied_migrations() -> set[str]:
    if not _MIGRATIONS_SENTINEL.exists():
        return set()
    return {line.strip() for line in _MIGRATIONS_SENTINEL.read_text(encoding="utf-8").splitlines() if line.strip()}


def _mark_migration(key: str) -> None:
    with _MIGRATIONS_SENTINEL.open("a", encoding="utf-8") as f:
        f.write(f"{key}\n")


async def run_migrations():
    """Выполняет одноразовые SQL-миграции, которых нет в Base.metadata."""
    applied = _applied_migrations()

    # 2026-06: молитва по умолчанию включена в 10:00, план — в 20:00.
    # Старые юзеры были созданы с дефолтами False/08:00 и 19:00; приводим к новым.
    key = "2026-06_notification_defaults"
    if key not in applied:
        async with engine.begin() as conn:
            await conn.execute(text(
                "UPDATE users SET prayer_notifications_enabled = 1, prayer_notification_time = '10:00'"
            ))
            await conn.execute(text(
                "UPDATE plan_progress SET notification_time = '20:00'"
            ))
        _mark_migration(key)
        logger.info("Миграция '%s' применена: дефолты уведомлений выставлены всем существующим юзерам/планам", key)
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL


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
    from models import User, Bookmark, Feedback, PlanProgress, AIRequest, AIConsent, Donation, ActivityHourly  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
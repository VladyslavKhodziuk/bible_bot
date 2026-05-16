from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


# Движок подключения к БД
engine = create_async_engine(DATABASE_URL, echo=False)

# Фабрика сессий
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Создаёт все таблицы в БД при старте бота."""
    # Импортируем модели здесь, чтобы они зарегистрировались в Base.metadata
    from models import User  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
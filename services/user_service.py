from sqlalchemy import select

from database import async_session
from models import User


class UserService:
    """Работа с пользователями: создание, получение, обновление."""

    @staticmethod
    async def get(tg_id: int) -> User | None:
        """Получить пользователя по Telegram ID. Вернёт None, если нет."""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def create(
        tg_id: int,
        username: str | None,
        first_name: str | None,
        lang: str = "ru"
    ) -> User:
        """Создать нового пользователя."""
        async with async_session() as session:
            user = User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                lang=lang
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    @staticmethod
    async def set_language(tg_id: int, lang: str) -> None:
        """Изменить язык пользователя."""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.lang = lang
                await session.commit()
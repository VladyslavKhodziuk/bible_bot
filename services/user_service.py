from sqlalchemy import select

from database import async_session
from models import User
from services.bible_service import BibleService


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
        """Создать нового пользователя. Перевод Библии подбирается под язык."""
        translation = BibleService.get_translation_for_lang(lang)
        async with async_session() as session:
            user = User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                lang=lang,
                translation=translation,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    @staticmethod
    async def set_language(tg_id: int, lang: str) -> None:
        """Сменить язык пользователя.

        Перевод Библии автоматически переключается на соответствующий языку.
        """
        new_translation = BibleService.get_translation_for_lang(lang)
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.lang = lang
                user.translation = new_translation  # всегда меняем
                await session.commit()

    @staticmethod
    async def set_translation(tg_id: int, translation: str) -> None:
        """Сменить только перевод Библии (язык интерфейса не трогаем).

        Понадобится позже, когда добавим в настройки выбор перевода.
        """
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.translation = translation
                await session.commit()

    @staticmethod
    async def set_notifications(
            tg_id: int,
            enabled: bool | None = None,
            time: str | None = None,
    ) -> None:
        """Включить/выключить уведомления и/или изменить время."""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return
            if enabled is not None:
                user.notifications_enabled = enabled
            if time is not None:
                user.notification_time = time
            await session.commit()

    @staticmethod
    async def get_users_for_notification(time_str: str) -> list[User]:
        """Получить всех юзеров, которым сейчас нужно отправить уведомление.

        time_str: текущее время в формате 'HH:MM'.
        """
        async with async_session() as session:
            result = await session.execute(
                select(User).where(
                    User.notifications_enabled == True,
                    User.notification_time == time_str,
                )
            )
            return list(result.scalars().all())
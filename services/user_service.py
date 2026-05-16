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

        Также автоматически меняет перевод Библии на соответствующий языку,
        если у юзера сейчас стоит дефолтный перевод предыдущего языка.
        """
        new_translation = BibleService.get_translation_for_lang(lang)
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            if user:
                # Меняем перевод только если у юзера сейчас "стандартный"
                # перевод его текущего языка (значит, он не выбирал свой)
                current_default = BibleService.get_translation_for_lang(user.lang)
                if user.translation == current_default:
                    user.translation = new_translation
                user.lang = lang
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
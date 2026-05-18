from sqlalchemy import select, delete, func

from database import async_session
from models import Bookmark


class BookmarkService:
    """Работа с закладками пользователя."""

    @staticmethod
    async def add(user_id: int, abbrev: str, chapter: int, verse: int) -> Bookmark:
        """Добавить закладку. Если уже есть — вернёт существующую."""
        existing = await BookmarkService.get(user_id, abbrev, chapter, verse)
        if existing:
            return existing

        async with async_session() as session:
            bookmark = Bookmark(
                user_id=user_id,
                abbrev=abbrev,
                chapter=chapter,
                verse=verse,
            )
            session.add(bookmark)
            await session.commit()
            await session.refresh(bookmark)
            return bookmark

    @staticmethod
    async def remove(user_id: int, abbrev: str, chapter: int, verse: int) -> bool:
        """Удалить закладку. Вернёт True, если что-то удалили."""
        async with async_session() as session:
            result = await session.execute(
                delete(Bookmark).where(
                    Bookmark.user_id == user_id,
                    Bookmark.abbrev == abbrev,
                    Bookmark.chapter == chapter,
                    Bookmark.verse == verse,
                )
            )
            await session.commit()
            return result.rowcount > 0

    @staticmethod
    async def get(
        user_id: int, abbrev: str, chapter: int, verse: int
    ) -> Bookmark | None:
        """Получить конкретную закладку."""
        async with async_session() as session:
            result = await session.execute(
                select(Bookmark).where(
                    Bookmark.user_id == user_id,
                    Bookmark.abbrev == abbrev,
                    Bookmark.chapter == chapter,
                    Bookmark.verse == verse,
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def is_bookmarked(
        user_id: int, abbrev: str, chapter: int, verse: int
    ) -> bool:
        """Проверить, есть ли закладка."""
        bookmark = await BookmarkService.get(user_id, abbrev, chapter, verse)
        return bookmark is not None

    @staticmethod
    async def list_for_user(
        user_id: int, limit: int = 5, offset: int = 0
    ) -> list[Bookmark]:
        """Список закладок юзера с пагинацией. Свежие сверху."""
        async with async_session() as session:
            result = await session.execute(
                select(Bookmark)
                .where(Bookmark.user_id == user_id)
                .order_by(Bookmark.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    @staticmethod
    async def count_for_user(user_id: int) -> int:
        """Общее количество закладок юзера."""
        async with async_session() as session:
            result = await session.execute(
                select(func.count(Bookmark.id)).where(Bookmark.user_id == user_id)
            )
            return result.scalar_one()
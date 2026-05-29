from sqlalchemy import select, delete, func

from database import async_session
from models import PrayerFavorite

MAX_PRAYER_FAVORITES = 10


class PrayerFavoriteService:
    """Избранные молитвы пользователя. Ключ — (user_id, prayer_id)."""

    @staticmethod
    async def add(user_id: int, prayer_id: str) -> PrayerFavorite | None:
        """Добавить молитву в избранное. Если уже есть — вернёт существующую.

        None — если достигнут лимит MAX_PRAYER_FAVORITES (новую не сохраняем).
        """
        existing = await PrayerFavoriteService.get(user_id, prayer_id)
        if existing:
            return existing

        if await PrayerFavoriteService.count_for_user(user_id) >= MAX_PRAYER_FAVORITES:
            return None

        async with async_session() as session:
            favorite = PrayerFavorite(user_id=user_id, prayer_id=prayer_id)
            session.add(favorite)
            await session.commit()
            await session.refresh(favorite)
            return favorite

    @staticmethod
    async def remove(user_id: int, prayer_id: str) -> bool:
        """Убрать молитву из избранного. Вернёт True, если что-то удалили."""
        async with async_session() as session:
            result = await session.execute(
                delete(PrayerFavorite).where(
                    PrayerFavorite.user_id == user_id,
                    PrayerFavorite.prayer_id == prayer_id,
                )
            )
            await session.commit()
            return result.rowcount > 0

    @staticmethod
    async def get(user_id: int, prayer_id: str) -> PrayerFavorite | None:
        """Получить конкретную избранную молитву."""
        async with async_session() as session:
            result = await session.execute(
                select(PrayerFavorite).where(
                    PrayerFavorite.user_id == user_id,
                    PrayerFavorite.prayer_id == prayer_id,
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def is_favorite(user_id: int, prayer_id: str) -> bool:
        """Проверить, в избранном ли молитва."""
        favorite = await PrayerFavoriteService.get(user_id, prayer_id)
        return favorite is not None

    @staticmethod
    async def list_for_user(
        user_id: int, limit: int = 5, offset: int = 0
    ) -> list[PrayerFavorite]:
        """Список избранных молитв юзера с пагинацией. Свежие сверху."""
        async with async_session() as session:
            result = await session.execute(
                select(PrayerFavorite)
                .where(PrayerFavorite.user_id == user_id)
                .order_by(PrayerFavorite.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    @staticmethod
    async def count_for_user(user_id: int) -> int:
        """Общее количество избранных молитв юзера."""
        async with async_session() as session:
            result = await session.execute(
                select(func.count(PrayerFavorite.id)).where(
                    PrayerFavorite.user_id == user_id
                )
            )
            return result.scalar_one()

import logging

from sqlalchemy import select, func

from database import async_session
from models import Donation

logger = logging.getLogger(__name__)


class DonateService:
    """Сервис для работы с донатами через Telegram Stars."""

    @staticmethod
    async def add(
        user_id: int,
        username: str | None,
        first_name: str | None,
        amount: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None = None,
    ) -> Donation:
        """Сохранить донат в БД."""
        async with async_session() as session:
            donation = Donation(
                user_id=user_id,
                username=username,
                first_name=first_name,
                amount=amount,
                telegram_payment_charge_id=telegram_payment_charge_id,
                provider_payment_charge_id=provider_payment_charge_id,
            )
            session.add(donation)
            await session.commit()
            await session.refresh(donation)

        logger.info(f"Новый донат: {amount}⭐ от {user_id}")
        return donation

    @staticmethod
    async def get_total_by_user(user_id: int) -> int:
        """Общая сумма донатов пользователя (в звёздах)."""
        async with async_session() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(Donation.amount), 0))
                .where(Donation.user_id == user_id)
            )
            return result.scalar_one()

    @staticmethod
    async def count_all() -> int:
        """Общее количество донатов (для статистики)."""
        async with async_session() as session:
            result = await session.execute(
                select(func.count(Donation.id))
            )
            return result.scalar_one()

import logging

from sqlalchemy import select, func

from database import async_session
from models import Feedback, FeedbackRelay

logger = logging.getLogger(__name__)

# Допустимые типы фидбека
KIND_IDEA = "idea"
KIND_BUG = "bug"
KIND_REVIEW = "review"
KIND_QUESTION = "question"
ALL_KINDS = {KIND_IDEA, KIND_BUG, KIND_REVIEW, KIND_QUESTION}


class FeedbackService:
    """Сервис для работы с обратной связью."""

    @staticmethod
    async def add(
        user_id: int,
        username: str | None,
        first_name: str | None,
        lang: str,
        kind: str,
        text: str,
        rating: int | None = None,
    ) -> Feedback:
        """Сохранить фидбек в БД."""
        if kind not in ALL_KINDS:
            raise ValueError(f"Неизвестный тип фидбека: {kind}")

        async with async_session() as session:
            feedback = Feedback(
                user_id=user_id,
                username=username,
                first_name=first_name,
                lang=lang,
                kind=kind,
                rating=rating,
                text=text[:2000],  # обрезаем длинные тексты
            )
            session.add(feedback)
            await session.commit()
            await session.refresh(feedback)

        logger.info(f"Новый фидбек {kind} от {user_id}: {text[:100]}...")
        return feedback

    @staticmethod
    async def count_by_kind(kind: str) -> int:
        """Подсчёт фидбека определённого типа (для статистики админа)."""
        async with async_session() as session:
            result = await session.execute(
                select(func.count(Feedback.id)).where(Feedback.kind == kind)
            )
            return result.scalar_one()

    @staticmethod
    async def save_relay(
        group_chat_id: int,
        group_message_id: int,
        user_tg_id: int,
        kind: str,
    ) -> None:
        """Сохранить маппинг сообщения в группе → юзер, чтобы reply админа долетел до автора."""
        async with async_session() as session:
            session.add(FeedbackRelay(
                group_chat_id=group_chat_id,
                group_message_id=group_message_id,
                user_tg_id=user_tg_id,
                kind=kind,
            ))
            await session.commit()

    @staticmethod
    async def find_relay(group_chat_id: int, group_message_id: int) -> FeedbackRelay | None:
        """Найти запись relay по координатам сообщения в группе."""
        async with async_session() as session:
            result = await session.execute(
                select(FeedbackRelay).where(
                    FeedbackRelay.group_chat_id == group_chat_id,
                    FeedbackRelay.group_message_id == group_message_id,
                )
            )
            return result.scalar_one_or_none()
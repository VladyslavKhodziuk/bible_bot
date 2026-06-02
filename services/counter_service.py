import logging
from datetime import date

from sqlalchemy import select

from database import async_session
from models import User
from services.timezones import local_today

logger = logging.getLogger(__name__)

# Накопительные вехи «всего дней со Словом» — поздравляем и зовём поддержать проект
MILESTONES = [3, 7, 30, 100, 200, 365, 500, 1000]


class CounterResult:
    """Результат обновления счётчика — что произошло и нужно ли что-то сказать юзеру."""

    def __init__(self):
        self.count: int = 0
        self.is_first_time: bool = False        # самый первый засчитанный день
        self.already_explained: bool = False    # онбординг счётчика уже показывали
        self.same_day: bool = False             # уже засчитали сегодня, ничего нового
        self.streak_grew: bool = False          # счётчик вырос на 1
        self.milestone_reached: int | None = None  # достигли вехи (число дней)


class CounterService:
    """Сервис накопительного счётчика «дней со Словом» (только растёт, без сброса)."""

    @staticmethod
    async def touch(tg_id: int, today: date | None = None) -> CounterResult:
        """
        Главный метод. Вызывается при каждом значимом действии юзера.
        Засчитывает сегодняшний день (+1, если ещё не был засчитан) и
        возвращает CounterResult — что произошло.
        """
        result = CounterResult()

        async with async_session() as session:
            user_row = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = user_row.scalar_one_or_none()
            if user is None:
                return result

            # «Сегодня» — в часовом поясе пользователя, иначе у юзеров в других
            # TZ день засчитывался бы по времени сервера.
            if today is None:
                today = local_today(user.timezone)

            # Снимок флага онбординга ДО изменений. Гейт онбординга чтения именно
            # на нём (а не на is_first_time): touch() зовут из 6 мест, и день может
            # быть засчитан там, где extras не показываются (рассылка стиха, отметка
            # дня плана). Флаг гарантирует, что онбординг покажется ровно один раз
            # на первом интерактивном открытии, кто бы ни засчитал день первым.
            result.already_explained = bool(user.streak_explained)

            last = user.last_activity_date

            if last == today:
                # Уже засчитали сегодня — ничего не делаем
                result.same_day = True
            else:
                # last is None ИЛИ любой прошлый день — просто +1.
                # Пропуски не сбрасывают счётчик: он только растёт.
                result.is_first_time = last is None
                user.current_streak = (user.current_streak or 0) + 1
                user.last_activity_date = today
                result.streak_grew = True

            # Вехи — только если счётчик реально вырос сегодня. Иначе повторные
            # действия в тот же день слали бы поздравление снова и снова.
            if result.streak_grew and user.current_streak in MILESTONES:
                result.milestone_reached = user.current_streak

            result.count = user.current_streak

            await session.commit()

        if result.streak_grew:
            logger.info(
                f"Юзер {tg_id}: дней со Словом={result.count}, "
                f"first={result.is_first_time}, "
                f"milestone={result.milestone_reached}"
            )

        return result

    @staticmethod
    async def mark_explained(tg_id: int) -> None:
        """Пометить, что юзеру уже показали онбординг про счётчик."""
        async with async_session() as session:
            user_row = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = user_row.scalar_one_or_none()
            if user:
                user.streak_explained = True
                await session.commit()

    @staticmethod
    async def get_stats(tg_id: int) -> dict | None:
        """Получить статистику юзера для экрана 'Моя статистика'."""
        async with async_session() as session:
            user_row = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = user_row.scalar_one_or_none()
            if not user:
                return None
            return {
                "count": user.current_streak,
                "last_activity_date": user.last_activity_date,
                "explained": user.streak_explained,
            }

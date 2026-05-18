import logging
from datetime import date, timedelta

from sqlalchemy import select

from database import async_session
from models import User

logger = logging.getLogger(__name__)

# Дни, на которых поздравляем юзера
MILESTONES = [3, 7, 14, 30, 50, 100, 200, 365]

# Восполнение заморозок: каждые сколько дней растущей серии — +1 заморозка
FREEZE_REPLENISH_EVERY = 7

# Максимум заморозок в запасе
MAX_FREEZES = 2


class StreakResult:
    """Результат обновления серии — что произошло и нужно ли что-то сказать юзеру."""

    def __init__(self):
        self.current_streak: int = 0
        self.longest_streak: int = 0
        self.is_first_time: bool = False        # первый раз серия начинается → показать onboarding
        self.same_day: bool = False             # уже засчитали сегодня, ничего нового
        self.streak_grew: bool = False          # серия выросла на 1
        self.freeze_used: bool = False          # сработала заморозка
        self.streak_burned: bool = False        # серия сгорела (потеряна)
        self.milestone_reached: int | None = None  # достигли милстоуна (число дней)
        self.freezes_available: int = 0
        self.freeze_replenished: bool = False   # пополнили заморозку
        self.returned_after_loss: bool = False  # юзер вернулся после потери серии


class StreakService:
    """Сервис управления сериями (streaks) пользователей."""

    @staticmethod
    async def touch(tg_id: int, today: date | None = None) -> StreakResult:
        """
        Главный метод. Вызывается при каждом значимом действии юзера.
        Обновляет серию по правилам и возвращает StreakResult — что произошло.
        """
        if today is None:
            today = date.today()

        result = StreakResult()

        async with async_session() as session:
            user_row = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = user_row.scalar_one_or_none()
            if user is None:
                return result

            last = user.last_activity_date

            # === Случай 1: первый раз вообще ===
            if last is None:
                user.current_streak = 1
                user.longest_streak = max(user.longest_streak, 1)
                user.last_activity_date = today
                result.is_first_time = True
                result.streak_grew = True

            # === Случай 2: уже засчитывали сегодня — ничего не делаем ===
            elif last == today:
                result.same_day = True

            # === Случай 3: вчера — серия растёт ===
            elif last == today - timedelta(days=1):
                user.current_streak += 1
                user.longest_streak = max(user.longest_streak, user.current_streak)
                user.last_activity_date = today
                result.streak_grew = True

                # Каждые FREEZE_REPLENISH_EVERY дней растущей серии — +1 заморозка
                if (user.current_streak % FREEZE_REPLENISH_EVERY == 0
                        and user.freezes_available < MAX_FREEZES):
                    user.freezes_available += 1
                    result.freeze_replenished = True

            # === Случай 4: пропустил один день — пробуем заморозку ===
            elif last == today - timedelta(days=2):
                if user.freezes_available > 0:
                    user.freezes_available -= 1
                    user.current_streak += 1
                    user.longest_streak = max(user.longest_streak, user.current_streak)
                    user.last_activity_date = today
                    result.streak_grew = True
                    result.freeze_used = True
                else:
                    # Серия сгорела
                    user.current_streak = 1
                    user.last_activity_date = today
                    result.streak_burned = True
                    result.returned_after_loss = True

            # === Случай 5: пропустил 2+ дня — серия сгорает ===
            else:
                if user.current_streak > 0:
                    result.streak_burned = True
                    result.returned_after_loss = True
                user.current_streak = 1
                user.last_activity_date = today

            # Проверяем милстоуны
            if user.current_streak in MILESTONES:
                result.milestone_reached = user.current_streak

            # Первая серия в жизни юзера — нужно показать onboarding
            if (result.is_first_time
                    and not user.streak_explained):
                # Флаг ставим, но onboarding ещё не показан — хендлер увидит
                # is_first_time=True и сам поставит флаг после показа
                pass

            result.current_streak = user.current_streak
            result.longest_streak = user.longest_streak
            result.freezes_available = user.freezes_available

            await session.commit()

        if any([result.streak_grew, result.streak_burned, result.freeze_used]):
            logger.info(
                f"Юзер {tg_id}: streak={result.current_streak}, "
                f"freezes={result.freezes_available}, "
                f"grew={result.streak_grew}, "
                f"freeze_used={result.freeze_used}, "
                f"burned={result.streak_burned}"
            )

        return result

    @staticmethod
    async def mark_explained(tg_id: int) -> None:
        """Пометить, что юзеру уже показали onboarding про серии."""
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
                "current_streak": user.current_streak,
                "longest_streak": user.longest_streak,
                "last_activity_date": user.last_activity_date,
                "freezes_available": user.freezes_available,
                "streak_explained": user.streak_explained,
            }
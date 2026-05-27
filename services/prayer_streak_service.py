"""Молитвенный стрик — счётчик нажатий «Аминь» на карточке молитвы дня.

Упрощённая логика по сравнению со StreakService: без заморозок и без
onboarding-флага. Пропуск дня = сброс в 1.
"""
import logging
from datetime import date, timedelta

from sqlalchemy import select

from database import async_session
from models import User
from services.timezones import local_today

logger = logging.getLogger(__name__)

MILESTONES = [3, 7, 14, 30, 50, 100, 200, 365]


class PrayerStreakResult:
    """Что произошло при touch() молитвенного стрика."""

    def __init__(self):
        self.current_streak: int = 0
        self.longest_streak: int = 0
        self.is_first_time: bool = False
        self.same_day: bool = False
        self.streak_grew: bool = False
        self.streak_burned: bool = False
        self.milestone_reached: int | None = None


class PrayerStreakService:
    """Сервис молитвенного стрика."""

    @staticmethod
    async def touch(tg_id: int, today: date | None = None) -> PrayerStreakResult:
        """Засчитать нажатие «Аминь» на сегодня."""
        result = PrayerStreakResult()

        async with async_session() as session:
            user_row = await session.execute(
                select(User).where(User.tg_id == tg_id)
            )
            user = user_row.scalar_one_or_none()
            if user is None:
                return result

            if today is None:
                today = local_today(user.timezone)

            last = user.last_prayer_date

            if last is None:
                # Первый раз
                user.current_prayer_streak = 1
                user.longest_prayer_streak = max(user.longest_prayer_streak, 1)
                user.last_prayer_date = today
                result.is_first_time = True
                result.streak_grew = True

            elif last == today:
                # Уже засчитали сегодня
                result.same_day = True

            elif last == today - timedelta(days=1):
                # Вчера — растём
                user.current_prayer_streak += 1
                user.longest_prayer_streak = max(
                    user.longest_prayer_streak, user.current_prayer_streak
                )
                user.last_prayer_date = today
                result.streak_grew = True

            else:
                # Пропуск 1+ дней — без заморозок, сброс в 1
                if user.current_prayer_streak > 0:
                    result.streak_burned = True
                user.current_prayer_streak = 1
                user.last_prayer_date = today

            if result.streak_grew and user.current_prayer_streak in MILESTONES:
                result.milestone_reached = user.current_prayer_streak

            result.current_streak = user.current_prayer_streak
            result.longest_streak = user.longest_prayer_streak

            await session.commit()

        if result.streak_grew or result.streak_burned:
            logger.info(
                f"Юзер {tg_id}: prayer_streak={result.current_streak}, "
                f"grew={result.streak_grew}, burned={result.streak_burned}"
            )

        return result

    @staticmethod
    def synthetic_same_day(current_streak: int, longest_streak: int) -> PrayerStreakResult:
        """Результат «уже сегодня молились» — без обращения к БД.

        Используется в show_pray для идемпотентного показа экрана «Бог слышит»
        при повторном открытии раздела в тот же день.
        """
        r = PrayerStreakResult()
        r.same_day = True
        r.current_streak = current_streak
        r.longest_streak = longest_streak
        return r

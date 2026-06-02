"""Молитвенный счётчик — накопительные дни нажатий «Аминь» на карточке молитвы дня.

Логика идентична CounterService: счётчик только растёт, пропуск дня его не
сбрасывает. Без onboarding-флага: у молитвы единственное место touch()
(pray:amen), которое всегда показывает extras, поэтому гейт онбординга на
is_first_time здесь надёжен.
"""
import logging
from datetime import date

from sqlalchemy import select

from database import async_session
from models import User
from services.timezones import local_today

logger = logging.getLogger(__name__)

MILESTONES = [3, 7, 30, 100, 200, 365, 500, 1000]


class PrayerCounterResult:
    """Что произошло при touch() молитвенного счётчика."""

    def __init__(self):
        self.count: int = 0
        self.is_first_time: bool = False
        self.same_day: bool = False
        self.streak_grew: bool = False
        self.milestone_reached: int | None = None


class PrayerCounterService:
    """Сервис накопительного счётчика «дней в молитве» (только растёт)."""

    @staticmethod
    async def touch(tg_id: int, today: date | None = None) -> PrayerCounterResult:
        """Засчитать нажатие «Аминь» на сегодня."""
        result = PrayerCounterResult()

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

            if last == today:
                # Уже засчитали сегодня
                result.same_day = True
            else:
                # None ИЛИ любой прошлый день — просто +1. Пропуски не сбрасывают.
                result.is_first_time = last is None
                user.current_prayer_streak = (user.current_prayer_streak or 0) + 1
                user.last_prayer_date = today
                result.streak_grew = True

            if result.streak_grew and user.current_prayer_streak in MILESTONES:
                result.milestone_reached = user.current_prayer_streak

            result.count = user.current_prayer_streak

            await session.commit()

        if result.streak_grew:
            logger.info(
                f"Юзер {tg_id}: дней в молитве={result.count}, "
                f"first={result.is_first_time}, milestone={result.milestone_reached}"
            )

        return result

    @staticmethod
    def synthetic_same_day(count: int) -> PrayerCounterResult:
        """Результат «уже сегодня молились» — без обращения к БД.

        Используется в show_pray для идемпотентного показа экрана «Бог слышит»
        при повторном открытии раздела в тот же день.
        """
        r = PrayerCounterResult()
        r.same_day = True
        r.count = count
        return r

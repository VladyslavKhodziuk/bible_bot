import json
import logging
from pathlib import Path

import yaml
from sqlalchemy import select, delete

from database import async_session
from models import PlanProgress
from timeutils import utcnow

logger = logging.getLogger(__name__)

# Путь к папке с планами
PLANS_DIR = Path(__file__).parent.parent / "data" / "plans"


class PlanService:
    """Сервис управления планами чтения."""

    # Все доступные планы — загружаются один раз при старте
    _plans: dict[str, dict] = {}

    # ============ Загрузка планов ============

    @classmethod
    def load(cls) -> None:
        """Загружает все планы из data/plans/*.yaml в память."""
        cls._plans = {}
        if not PLANS_DIR.exists():
            logger.warning(f"Папка с планами не существует: {PLANS_DIR}")
            return

        for yaml_file in sorted(PLANS_DIR.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    plan = yaml.safe_load(f)
                if not plan or "id" not in plan:
                    logger.warning(f"Невалидный план: {yaml_file}")
                    continue
                cls._plans[plan["id"]] = plan
                logger.info(
                    f"План загружен: {plan['id']} "
                    f"({plan.get('duration_days', '?')} дней)"
                )
            except Exception as e:
                logger.error(f"Ошибка загрузки {yaml_file}: {e}")

        logger.info(f"Всего планов загружено: {len(cls._plans)}")

    # ============ Список планов ============

    @classmethod
    def get_all_plans(cls) -> list[dict]:
        """Возвращает все планы в фиксированном порядке для UI."""
        # Желаемый порядок: НЗ, Псалмы, Жизнь Иисуса, Притчи, Библия за год
        order = ["nt_30", "psalms_30", "life_of_jesus", "proverbs_31", "bible_year"]
        result = []
        for plan_id in order:
            if plan_id in cls._plans:
                result.append(cls._plans[plan_id])
        # Если есть планы вне порядка — добавим в конец
        for plan_id, plan in cls._plans.items():
            if plan_id not in order:
                result.append(plan)
        return result

    @classmethod
    def get_plan(cls, plan_id: str) -> dict | None:
        """Получить план по id."""
        return cls._plans.get(plan_id)

    @classmethod
    def get_plan_name(cls, plan_id: str, lang: str) -> str:
        """Локализованное имя плана."""
        plan = cls._plans.get(plan_id)
        if not plan:
            return plan_id
        names = plan.get("names", {})
        return names.get(lang) or names.get("en") or plan_id

    @classmethod
    def get_plan_description(cls, plan_id: str, lang: str) -> str:
        """Локализованное описание плана."""
        plan = cls._plans.get(plan_id)
        if not plan:
            return ""
        descs = plan.get("descriptions", {})
        return descs.get(lang) or descs.get("en") or ""

    @classmethod
    def get_day_readings(cls, plan_id: str, day: int) -> list[dict]:
        """Список чтений для конкретного дня плана.

        Возвращает: [{"abbrev": "mt", "chapter": 1}, ...]
        """
        plan = cls._plans.get(plan_id)
        if not plan:
            return []
        for entry in plan.get("schedule", []):
            if entry.get("day") == day:
                return entry.get("readings", [])
        return []

    # ============ Работа с прогрессом юзера ============

    @staticmethod
    async def get_active(user_id: int) -> PlanProgress | None:
        """Получить активный план юзера (если есть)."""
        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == user_id,
                    PlanProgress.status == "active",
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def activate(user_id: int, plan_id: str) -> PlanProgress:
        """Активировать план для юзера. Если уже есть активный — старый помечается abandoned."""
        async with async_session() as session:
            # Деактивируем все предыдущие активные планы
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == user_id,
                    PlanProgress.status == "active",
                )
            )
            for old in result.scalars().all():
                old.status = "abandoned"

            # Создаём новый
            new_progress = PlanProgress(
                user_id=user_id,
                plan_id=plan_id,
                started_at=utcnow(),
                current_day=1,
                completed_days="[]",
                status="active",
                notification_enabled=True,
                notification_time="19:00",
            )
            session.add(new_progress)
            await session.commit()
            await session.refresh(new_progress)

        logger.info(f"План активирован: user={user_id}, plan={plan_id}")
        return new_progress

    @staticmethod
    async def abandon(user_id: int) -> bool:
        """Отказаться от активного плана. True если был активный."""
        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == user_id,
                    PlanProgress.status == "active",
                )
            )
            progress = result.scalar_one_or_none()
            if not progress:
                return False
            progress.status = "abandoned"
            await session.commit()

        logger.info(f"План отменён: user={user_id}")
        return True

    @staticmethod
    async def mark_day_complete(user_id: int) -> tuple[str, int, int]:
        """
        Отметить текущий день плана как прочитанный.

        Возвращает: (result, current_day, total_days)
            result: "completed" — день засчитан, план не закончен
                    "plan_finished" — день засчитан, план завершён
                    "already_today" — уже отмечал сегодня, отказ
                    "no_active" — нет активного плана
            current_day: текущий день (для UI)
            total_days: общее количество дней в плане
        """
        from datetime import date as date_cls
        today = date_cls.today()

        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == user_id,
                    PlanProgress.status == "active",
                    )
            )
            progress = result.scalar_one_or_none()
            if not progress:
                return "no_active", 0, 0

            # Защита от мультикликов: один день = один клик
            if progress.last_completion_date == today:
                plan = PlanService.get_plan(progress.plan_id)
                total = plan.get("duration_days", 0) if plan else 0
                return "already_today", progress.current_day, total

            # Парсим список завершённых дней
            try:
                completed = json.loads(progress.completed_days)
            except (json.JSONDecodeError, TypeError):
                completed = []

            current_day = progress.current_day
            if current_day not in completed:
                completed.append(current_day)
                completed.sort()
                progress.completed_days = json.dumps(completed)

            # Обновляем дату последнего отметки
            progress.last_completion_date = today
            # Сбрасываем индекс чтения для следующего дня
            progress.current_reading_idx = 0

            # Проверяем — план завершён?
            plan = PlanService.get_plan(progress.plan_id)
            total_days = plan.get("duration_days", 0) if plan else 0

            if current_day >= total_days:
                progress.status = "completed"
                progress.completed_at = utcnow()
                await session.commit()
                logger.info(f"План завершён: user={user_id}, plan={progress.plan_id}")
                return "plan_finished", current_day, total_days

                # Идём на следующий день
            progress.current_day = current_day + 1
            await session.commit()
            return "completed", current_day, total_days  # возвращаем завершённый день, не следующий

    @staticmethod
    async def get_completed_days(user_id: int) -> list[int]:
        """Получить список дней, отмеченных как прочитанные."""
        progress = await PlanService.get_active(user_id)
        if not progress:
            return []
        try:
            return json.loads(progress.completed_days)
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    async def set_notification_time(user_id: int, time_str: str) -> bool:
        """Установить время уведомления плана. Формат: HH:MM"""
        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == user_id,
                    PlanProgress.status == "active",
                )
            )
            progress = result.scalar_one_or_none()
            if not progress:
                return False
            progress.notification_time = time_str
            progress.notification_enabled = True
            await session.commit()
        logger.info(f"Время уведомления плана установлено: user={user_id}, time={time_str}")
        return True

    @staticmethod
    async def toggle_notification(user_id: int, enabled: bool) -> bool:
        """Включить/выключить уведомления плана."""
        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == user_id,
                    PlanProgress.status == "active",
                )
            )
            progress = result.scalar_one_or_none()
            if not progress:
                return False
            progress.notification_enabled = enabled
            await session.commit()
        return True

    # ============ Вспомогательные методы ============

    @classmethod
    def calculate_progress(cls, progress: PlanProgress) -> dict:
        """
        Рассчитать прогресс юзера по активному плану.

        Возвращает:
            {
                "current_day": 7,
                "total_days": 30,
                "completed_count": 6,
                "percent": 23,
            }
        """
        plan = cls._plans.get(progress.plan_id)
        total_days = plan.get("duration_days", 0) if plan else 0

        try:
            completed = json.loads(progress.completed_days)
        except (json.JSONDecodeError, TypeError):
            completed = []

        completed_count = len(completed)
        percent = round(completed_count / total_days * 100) if total_days else 0

        return {
            "current_day": progress.current_day,
            "total_days": total_days,
            "completed_count": completed_count,
            "percent": percent,
        }


    @staticmethod
    async def advance_reading_index(user_id: int) -> int | None:
        """
        Сдвинуть указатель на следующее чтение дня.
        Возвращает новый индекс, или None если активного плана нет.
        """
        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == user_id,
                    PlanProgress.status == "active",
                    )
            )
            progress = result.scalar_one_or_none()
            if not progress:
                return None
            progress.current_reading_idx += 1
            await session.commit()
            return progress.current_reading_idx

    @staticmethod
    async def reset_reading_index(user_id: int) -> None:
        """Сбросить индекс чтения дня в 0 (когда юзер хочет начать день заново)."""
        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress).where(
                    PlanProgress.user_id == user_id,
                    PlanProgress.status == "active",
                    )
            )
            progress = result.scalar_one_or_none()
            if not progress:
                return
            progress.current_reading_idx = 0
            await session.commit()

    @staticmethod
    async def can_complete_today(user_id: int) -> bool:
        """Проверка — можно ли отметить день сегодня (не отмечал ли уже)."""
        from datetime import date as date_cls
        progress = await PlanService.get_active(user_id)
        if not progress:
            return False
        return progress.last_completion_date != date_cls.today()

    @staticmethod
    async def get_history(user_id: int) -> list[PlanProgress]:
        """История всех планов юзера (завершённые + отложенные)."""
        async with async_session() as session:
            result = await session.execute(
                select(PlanProgress)
                .where(PlanProgress.user_id == user_id)
                .order_by(PlanProgress.started_at.desc())
            )
            return list(result.scalars().all())


def render_progress_bar(percent: int, width: int = 20) -> str:
    """Рисует прогресс-бар псевдографикой."""
    filled = round(width * percent / 100)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty} {percent}%"
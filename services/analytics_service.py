"""Аналитика активности: почасовые агрегаты вместо строки-на-клик.

Принципы:
- События НЕ пишутся в БД по одному. Счётчики текущего часа копятся в памяти
  и апсертятся одной строкой `activity_hourly` раз в минуту (flush из
  планировщика). Объём БД растёт ~24 строки в сутки, а не тысячами.
- Throttling частоты запросов на юзера держится в памяти (скользящее окно).
- Время — локальное (datetime.now()), как и cron планировщика, чтобы пиковый
  час в отчёте совпадал с тем, что видит админ.

Сознательно НЕ храним сырые timestamp'ы и список юзеров: метрики «сессии» и
точный unique-active за сутки недоступны — для мониторинга нагрузки не нужны.
На границе часа события, пришедшие между сменой часа и ближайшим flush
(<1 мин), относятся к завершившемуся часу — погрешность мониторинга приемлема.
"""
import json
import time
import logging
from collections import deque, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, func, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import async_session
from models import ActivityHourly, User, AIRequest, Donation
from timeutils import utcnow
from config import THROTTLE_MAX_EVENTS, THROTTLE_WINDOW_SEC, MONTHLY_REPORT_DAY

logger = logging.getLogger(__name__)

# Успешные действия юзера (для счётчика категорий и активных юзеров).
USER_KINDS = {"message", "callback"}
# Входящая нагрузка (для пика запросов в минуту).
INBOUND_KINDS = {"message", "callback", "throttled"}

# Префикс callback-data → понятная категория действия.
_CALLBACK_CATEGORY = {
    "read": "reading", "verse_of_day": "reading", "random": "reading",
    "search": "search",
    "ai_pastor": "ai",
    "plan": "plan",
    "bm": "bookmarks", "bookmarks": "bookmarks",
    "topic": "topics", "topics": "topics",
    "donate": "donate",
    "fb": "feedback",
    "notif": "settings", "settings": "settings", "setlang": "settings",
    "changelang": "settings", "changetrans": "settings",
    "streak": "streak",
    "cabinet": "menu", "open_menu": "menu", "menu": "menu",
}

# Человекочитаемые подписи категорий для отчёта.
_CATEGORY_LABEL = {
    "reading": "📖 Чтение",
    "search": "🔍 Поиск",
    "ai": "🤖 AI Пастырь",
    "plan": "🗓 Планы",
    "bookmarks": "🔖 Закладки",
    "topics": "🏷 Темы",
    "donate": "⭐ Донаты",
    "feedback": "💬 Фидбек",
    "settings": "⚙️ Настройки",
    "streak": "🔥 Серии",
    "menu": "🏠 Меню",
    "start": "🚀 /start",
    "text": "✍️ Текст",
    "other": "❓ Прочее",
}


class AnalyticsService:
    """Стейтлес-сервис: аккумулятор текущего часа + throttling в памяти."""

    _throttle: dict[int, deque] = {}

    # Аккумулятор текущего часа.
    _hour: datetime | None = None
    _by_kind: defaultdict = defaultdict(int)
    _by_category: defaultdict = defaultdict(int)
    _per_minute: defaultdict = defaultdict(int)
    _active: set[int] = set()

    # ── Throttling ──────────────────────────────────────────
    @classmethod
    def allow(cls, tg_id: int) -> bool:
        """True, если юзеру можно обработать ещё одно действие сейчас."""
        now = time.monotonic()
        dq = cls._throttle.setdefault(tg_id, deque())
        while dq and now - dq[0] > THROTTLE_WINDOW_SEC:
            dq.popleft()
        if len(dq) >= THROTTLE_MAX_EVENTS:
            return False
        dq.append(now)
        return True

    # ── Категоризация ───────────────────────────────────────
    @staticmethod
    def classify_callback(data: str | None) -> str | None:
        """Категория по callback-data. None — событие игнорируется."""
        if not data:
            return "other"
        prefix = data.split(":", 1)[0]
        if prefix == "noop":
            return None
        return _CALLBACK_CATEGORY.get(prefix, "other")

    @staticmethod
    def classify_message(text: str | None) -> str:
        """Категория текстового сообщения."""
        if text and text.startswith("/"):
            cmd = text[1:].split()[0].split("@")[0].lower()
            return cmd if cmd in ("start", "menu") else "other"
        return "text"

    # ── Сбор событий (только в память) ──────────────────────
    @classmethod
    def record(cls, tg_id: int, event_type: str, kind: str) -> None:
        """Учесть событие в аккумуляторе текущего часа (без записи в БД).

        Сброс аккумулятора при смене часа делает flush, а не record — чтобы не
        потерять последнюю минуту завершившегося часа.
        """
        now = datetime.now()
        if cls._hour is None:
            cls._hour = now.replace(minute=0, second=0, microsecond=0)
        cls._by_kind[kind] += 1
        if kind in INBOUND_KINDS:
            cls._per_minute[now.strftime("%H:%M")] += 1
        if kind in USER_KINDS:
            cls._by_category[event_type] += 1
            cls._active.add(tg_id)

    @classmethod
    async def flush(cls) -> None:
        """Апсертит строку текущего часа; на смене часа фиксирует прошлый."""
        cls._prune_throttle()
        if cls._hour is None:
            return
        bucket = datetime.now().replace(minute=0, second=0, microsecond=0)
        try:
            await cls._persist(cls._hour)
        except Exception as e:
            logger.error(f"Не удалось записать почасовой агрегат: {e}")
        if cls._hour != bucket:
            cls._reset(bucket)

    @classmethod
    async def _persist(cls, bucket: datetime) -> None:
        """Апсерт (INSERT ... ON CONFLICT) строки агрегата за `bucket`."""
        values = {
            "hour_bucket": bucket,
            "events": sum(cls._by_category.values()),
            "peak_per_min": max(cls._per_minute.values(), default=0),
            "active_users": len(cls._active),
            "errors": cls._by_kind.get("error", 0),
            "throttled": cls._by_kind.get("throttled", 0),
            "notifs": cls._by_kind.get("notif", 0),
            "by_category": json.dumps(dict(cls._by_category), ensure_ascii=False),
        }
        stmt = sqlite_insert(ActivityHourly).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["hour_bucket"],
            set_={k: v for k, v in values.items() if k != "hour_bucket"},
        )
        async with async_session() as session:
            await session.execute(stmt)
            await session.commit()

    @classmethod
    def _reset(cls, bucket: datetime) -> None:
        """Начать новый час: обнулить счётчики."""
        cls._hour = bucket
        cls._by_kind = defaultdict(int)
        cls._by_category = defaultdict(int)
        cls._per_minute = defaultdict(int)
        cls._active = set()

    @classmethod
    def _prune_throttle(cls) -> None:
        """Чистим память от юзеров без свежих действий, чтобы dict не рос."""
        now = time.monotonic()
        stale = [
            uid for uid, dq in cls._throttle.items()
            if not dq or now - dq[-1] > THROTTLE_WINDOW_SEC
        ]
        for uid in stale:
            del cls._throttle[uid]

    # ── Отчёт ───────────────────────────────────────────────
    @staticmethod
    def _shift_month(ref: datetime, day: int) -> datetime:
        """Возвращает `day`-е число предыдущего календарного месяца, 00:00."""
        year, month = ref.year, ref.month
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1
        return datetime(year, month, day, 0, 0, 0)

    @classmethod
    async def build_daily_report(cls) -> str:
        """Сводка активности за последние 24 часа (HTML-текст)."""
        now = datetime.now()
        return await cls._build_report(
            local_start=now - timedelta(hours=24),
            local_end=now + timedelta(seconds=2),
            title="📊 <b>Отчёт активности за 24 часа</b>",
        )

    @classmethod
    async def build_monthly_report(cls) -> str:
        """Сводка за отчётный цикл [прошлый 25-го → этот 25-го)."""
        now = datetime.now()
        period_end = datetime(now.year, now.month, MONTHLY_REPORT_DAY, 0, 0, 0)
        period_start = cls._shift_month(period_end, MONTHLY_REPORT_DAY)
        return await cls._build_report(
            local_start=period_start,
            local_end=period_end,
            title="🗓 <b>Месячный отчёт активности</b>",
        )

    @classmethod
    async def cleanup_old_aggregates(cls) -> int:
        """Удаляет почасовые строки старше начала последнего отчётного цикла."""
        cutoff = cls._shift_month(datetime.now(), MONTHLY_REPORT_DAY)
        async with async_session() as session:
            result = await session.execute(
                delete(ActivityHourly).where(ActivityHourly.hour_bucket < cutoff)
            )
            await session.commit()
        deleted = result.rowcount or 0
        logger.info(f"Очистка activity_hourly: удалено {deleted} строк старше {cutoff:%d.%m.%Y}")
        return deleted

    @classmethod
    async def _build_report(cls, local_start: datetime, local_end: datetime, title: str) -> str:
        """Ядро отчёта за окно [local_start, local_end) в локальном времени."""
        # Сначала добиваем текущий час, чтобы отчёт учитывал свежие события.
        await cls.flush()

        # created_at юзеров/донатов/AI хранится в UTC — переводим границы окна.
        utc_offset = datetime.now() - utcnow()
        utc_start = local_start - utc_offset
        utc_end = local_end - utc_offset

        async with async_session() as session:
            rows = (await session.execute(
                select(ActivityHourly).where(
                    ActivityHourly.hour_bucket >= local_start,
                    ActivityHourly.hour_bucket < local_end,
                )
            )).scalars().all()

            total_users = (await session.execute(
                select(func.count(User.id))
            )).scalar() or 0

            new_users = (await session.execute(
                select(func.count(User.id)).where(
                    User.created_at >= utc_start, User.created_at < utc_end
                )
            )).scalar() or 0

            ai_total = (await session.execute(
                select(func.count(AIRequest.id)).where(
                    AIRequest.created_at >= utc_start, AIRequest.created_at < utc_end
                )
            )).scalar() or 0
            ai_crisis = (await session.execute(
                select(func.count(AIRequest.id)).where(
                    AIRequest.created_at >= utc_start, AIRequest.created_at < utc_end,
                    AIRequest.is_crisis == True
                )
            )).scalar() or 0

            don_count = (await session.execute(
                select(func.count(Donation.id)).where(
                    Donation.created_at >= utc_start, Donation.created_at < utc_end
                )
            )).scalar() or 0
            don_stars = (await session.execute(
                select(func.coalesce(func.sum(Donation.amount), 0)).where(
                    Donation.created_at >= utc_start, Donation.created_at < utc_end
                )
            )).scalar() or 0

        # ── Агрегации по почасовым строкам ──
        user_actions = sum(r.events for r in rows)
        errors = sum(r.errors for r in rows)
        throttled = sum(r.throttled for r in rows)
        notif_sent = sum(r.notifs for r in rows)
        peak_min_cnt = max((r.peak_per_min for r in rows), default=0)
        peak_active_hour = max((r.active_users for r in rows), default=0)

        by_category: dict[str, int] = defaultdict(int)
        for r in rows:
            try:
                for cat, cnt in json.loads(r.by_category).items():
                    by_category[cat] += cnt
            except (ValueError, TypeError):
                continue

        # Пиковый час — строка с максимумом действий.
        peak_row = max(rows, key=lambda r: r.events, default=None)
        if peak_row is not None and peak_row.events > 0:
            h = peak_row.hour_bucket.hour
            peak_str = f"{h:02d}:00–{h + 1:02d}:00 ({peak_row.events} действий)"
        else:
            peak_str = "—"

        # ── Сборка текста ──
        lines = [
            title,
            f"<i>{local_start.strftime('%d.%m %H:%M')} — {local_end.strftime('%d.%m %H:%M')}</i>",
            "",
            "👥 <b>Пользователи</b>",
            f"• Новых за период: <b>{new_users}</b>",
            f"• Всего в базе: <b>{total_users}</b>",
            f"• Пик активных за час: <b>{peak_active_hour}</b>",
            "",
            "⏱ <b>Использование</b>",
            f"• Действий: <b>{user_actions}</b>",
        ]

        if by_category:
            top = sorted(by_category.items(), key=lambda x: -x[1])
            cat_lines = [
                f"• {_CATEGORY_LABEL.get(cat, cat)}: {cnt}" for cat, cnt in top
            ]
            lines += ["", "📈 <b>По типам действий</b>", *cat_lines]

        lines += [
            "",
            "🔥 <b>Нагрузка</b>",
            f"• Пиковый час: <b>{peak_str}</b>",
            f"• Максимум в минуту: <b>{peak_min_cnt}</b> запр.",
            f"• Уведомлений отправлено: {notif_sent}",
            f"• Ошибок: <b>{errors}</b>",
            f"• Заблокировано throttling: {throttled}",
            "",
            "🤖 <b>AI Пастырь</b>",
            f"• Запросов: {ai_total} (кризисных: {ai_crisis})",
            "",
            "⭐ <b>Донаты</b>",
            f"• {don_count} шт. на {don_stars} ⭐",
        ]

        return "\n".join(lines)

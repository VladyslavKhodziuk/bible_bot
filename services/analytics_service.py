"""Аналитика активности: сбор событий в память, батч-запись в БД и
построение ежедневного отчёта.

Принципы:
- События НЕ пишутся в БД по одному — копятся в памяти и сбрасываются батчем
  (flush) раз в минуту из планировщика. Это снимает нагрузку с SQLite.
- Throttling частоты запросов на юзера держится в памяти (скользящее окно).
- Время событий — локальное (datetime.now()), как и cron планировщика.
"""
import time
import logging
from collections import deque, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, func, delete

from database import async_session
from models import ActivityEvent, User, AIRequest, Donation
from config import THROTTLE_MAX_EVENTS, THROTTLE_WINDOW_SEC, MONTHLY_REPORT_DAY

logger = logging.getLogger(__name__)

# Действия, инициированные юзером (для подсчёта активных и сессий).
USER_KINDS = {"message", "callback"}

# Разрыв между событиями, после которого начинается новая «сессия».
SESSION_GAP = timedelta(minutes=30)

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

_LANG_LABEL = {"ru": "🇷🇺 RU", "en": "🇬🇧 EN", "es": "🇪🇸 ES", "uk": "🇺🇦 UK"}


class AnalyticsService:
    """Стейтлес-сервис с буфером событий и состоянием throttling в памяти."""

    _buffer: list[dict] = []
    _throttle: dict[int, deque] = {}

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

    # ── Сбор событий ────────────────────────────────────────
    @classmethod
    def record(cls, tg_id: int, event_type: str, kind: str) -> None:
        """Добавить событие в буфер (без записи в БД)."""
        cls._buffer.append({
            "tg_id": tg_id,
            "event_type": event_type,
            "kind": kind,
            "created_at": datetime.now(),
        })

    @classmethod
    async def flush(cls) -> None:
        """Сбросить накопленные события в БД одним батчем."""
        if not cls._buffer:
            cls._prune_throttle()
            return
        pending, cls._buffer = cls._buffer, []
        try:
            async with async_session() as session:
                session.add_all([ActivityEvent(**e) for e in pending])
                await session.commit()
        except Exception as e:
            logger.error(f"Не удалось сбросить {len(pending)} событий в БД: {e}")
        cls._prune_throttle()

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
    async def cleanup_old_events(cls) -> int:
        """Удаляет уже отчётанные события: всё старше начала текущего цикла.

        Запускается через ~10 дней после месячного отчёта. На дату очистки
        граница = MONTHLY_REPORT_DAY-е число предыдущего месяца (конец того
        цикла, что попал в последний отчёт). Свежий, ещё не отчётанный цикл
        сохраняется.
        """
        cutoff = cls._shift_month(datetime.now(), MONTHLY_REPORT_DAY)
        async with async_session() as session:
            result = await session.execute(
                delete(ActivityEvent).where(ActivityEvent.created_at < cutoff)
            )
            await session.commit()
        deleted = result.rowcount or 0
        logger.info(f"Очистка activity_events: удалено {deleted} записей старше {cutoff:%d.%m.%Y}")
        return deleted

    @classmethod
    async def _build_report(cls, local_start: datetime, local_end: datetime, title: str) -> str:
        """Ядро отчёта за окно [local_start, local_end) в локальном времени."""
        # Сначала добиваем буфер, чтобы отчёт учитывал самые свежие события.
        await cls.flush()

        # created_at юзеров/донатов/AI хранится в UTC — переводим границы окна.
        utc_offset = datetime.now() - datetime.utcnow()
        utc_start = local_start - utc_offset
        utc_end = local_end - utc_offset

        async with async_session() as session:
            rows = (await session.execute(
                select(
                    ActivityEvent.tg_id,
                    ActivityEvent.event_type,
                    ActivityEvent.kind,
                    ActivityEvent.created_at,
                ).where(
                    ActivityEvent.created_at >= local_start,
                    ActivityEvent.created_at < local_end,
                )
            )).all()

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

            # Языки активных юзеров.
            active_ids = {r.tg_id for r in rows if r.kind in USER_KINDS}
            lang_counts: dict[str, int] = defaultdict(int)
            if active_ids:
                lang_rows = (await session.execute(
                    select(User.lang, func.count(User.id))
                    .where(User.tg_id.in_(active_ids))
                    .group_by(User.lang)
                )).all()
                for lang, cnt in lang_rows:
                    lang_counts[lang] = cnt

        # ── Агрегации в памяти ──
        by_kind: dict[str, int] = defaultdict(int)
        by_category: dict[str, int] = defaultdict(int)
        per_user_events: dict[int, list[datetime]] = defaultdict(list)
        per_hour: dict[int, int] = defaultdict(int)
        per_minute: dict[str, int] = defaultdict(int)

        for r in rows:
            by_kind[r.kind] += 1
            if r.kind in USER_KINDS:
                by_category[r.event_type] += 1
                per_user_events[r.tg_id].append(r.created_at)
                per_hour[r.created_at.hour] += 1
                per_minute[r.created_at.strftime("%Y-%m-%d %H:%M")] += 1

        active_count = len(active_ids)
        returning = max(active_count - new_users, 0)
        user_actions = sum(by_category.values())

        # Сессии.
        sessions, total_session_sec = cls._compute_sessions(per_user_events)
        avg_session_min = (total_session_sec / sessions / 60) if sessions else 0
        avg_events_per_session = (user_actions / sessions) if sessions else 0

        # Пики.
        peak_hour, peak_hour_cnt = (max(per_hour.items(), key=lambda x: x[1])
                                    if per_hour else (None, 0))
        peak_min_cnt = max(per_minute.values()) if per_minute else 0

        notif_sent = by_kind.get("notif", 0)
        errors = by_kind.get("error", 0)
        throttled = by_kind.get("throttled", 0)

        # ── Сборка текста ──
        lines = [
            title,
            f"<i>{local_start.strftime('%d.%m %H:%M')} — {local_end.strftime('%d.%m %H:%M')}</i>",
            "",
            "👥 <b>Пользователи</b>",
            f"• Активных: <b>{active_count}</b> (новых {new_users}, вернувшихся {returning})",
            f"• Всего в базе: <b>{total_users}</b>",
        ]

        if lang_counts:
            lang_str = "  ".join(
                f"{_LANG_LABEL.get(l, l)}: {c}"
                for l, c in sorted(lang_counts.items(), key=lambda x: -x[1])
            )
            lines += ["", "🌍 <b>Языки активных</b>", f"• {lang_str}"]

        lines += [
            "",
            "⏱ <b>Использование</b>",
            f"• Действий: <b>{user_actions}</b>",
            f"• Сессий: <b>{sessions}</b>",
            f"• Средняя сессия: <b>{avg_session_min:.1f}</b> мин ({avg_events_per_session:.1f} действий)",
        ]

        if by_category:
            top = sorted(by_category.items(), key=lambda x: -x[1])
            cat_lines = [
                f"• {_CATEGORY_LABEL.get(cat, cat)}: {cnt}" for cat, cnt in top
            ]
            lines += ["", "📈 <b>По типам действий</b>", *cat_lines]

        peak_str = (f"{peak_hour:02d}:00–{peak_hour + 1:02d}:00 ({peak_hour_cnt} соб.)"
                    if peak_hour is not None else "—")
        lines += [
            "",
            "🔥 <b>Нагрузка</b>",
            f"• Пиковый час: <b>{peak_str}</b>",
            f"• Максимум в минуту: <b>{peak_min_cnt}</b> соб.",
            f"• Уведомлений отправлено: {notif_sent}",
            f"• Ошибок: <b>{errors}</b>",
            f"• Заблокировано throttling: {throttled}",
        ]

        lines += [
            "",
            "🤖 <b>AI Пастырь</b>",
            f"• Запросов: {ai_total} (кризисных: {ai_crisis})",
            "",
            "⭐ <b>Донаты</b>",
            f"• {don_count} шт. на {don_stars} ⭐",
        ]

        return "\n".join(lines)

    @staticmethod
    def _compute_sessions(per_user_events: dict[int, list[datetime]]) -> tuple[int, float]:
        """Считает число сессий и суммарную их длительность (в секундах).

        Сессия — цепочка действий юзера с разрывом не больше SESSION_GAP.
        Длительность одиночной сессии (1 действие) = 0.
        """
        total_sessions = 0
        total_seconds = 0.0
        for times in per_user_events.values():
            times.sort()
            session_start = prev = times[0]
            total_sessions += 1
            for t in times[1:]:
                if t - prev > SESSION_GAP:
                    total_seconds += (prev - session_start).total_seconds()
                    total_sessions += 1
                    session_start = t
                prev = t
            total_seconds += (prev - session_start).total_seconds()
        return total_sessions, total_seconds

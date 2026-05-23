from datetime import datetime, date
from sqlalchemy import BigInteger, String, Integer, DateTime, Date, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
from timeutils import utcnow
from config import DEFAULT_TZ


class User(Base):
    """Модель пользователя бота."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lang: Mapped[str] = mapped_column(String(5), default="ru")
    translation: Mapped[str] = mapped_column(String(20), default="ru_synodal")
    notifications_enabled: Mapped[bool] = mapped_column(default=True)  # стих дня вкл по умолчанию
    notification_time: Mapped[str] = mapped_column(String(5), default="09:00")  # формат "HH:MM"
    timezone: Mapped[str] = mapped_column(String(64), default=DEFAULT_TZ)  # IANA-зона юзера
    # Серии (streaks)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    freezes_available: Mapped[int] = mapped_column(Integer, default=2)
    streak_explained: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<User tg_id={self.tg_id} lang={self.lang}>"


class Bookmark(Base):
    """Закладка пользователя на стих или отрывок."""
    __tablename__ = "bookmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)  # tg_id юзера
    abbrev: Mapped[str] = mapped_column(String(10))
    chapter: Mapped[int] = mapped_column()
    verse: Mapped[int] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<Bookmark user={self.user_id} ref={self.abbrev} {self.chapter}:{self.verse}>"


class Feedback(Base):
    """Обратная связь от пользователей: идеи, баги, отзывы."""
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)  # tg_id юзера
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lang: Mapped[str] = mapped_column(String(5))
    kind: Mapped[str] = mapped_column(String(20))  # idea / bug / review
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # для review
    text: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<Feedback {self.kind} from {self.user_id}>"


class PlanProgress(Base):
    """Прогресс пользователя по активному плану чтения."""
    __tablename__ = "plan_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    plan_id: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # когда план завершён
    current_day: Mapped[int] = mapped_column(Integer, default=1)
    current_reading_idx: Mapped[int] = mapped_column(Integer, default=0)  # позиция в чтениях дня (0, 1, 2...)
    completed_days: Mapped[str] = mapped_column(String(2000), default="[]")
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # для защиты от мультикликов

    # Уведомления
    notification_enabled: Mapped[bool] = mapped_column(default=True)
    notification_time: Mapped[str] = mapped_column(String(5), default="19:00")

    def __repr__(self) -> str:
        return f"<PlanProgress user={self.user_id} plan={self.plan_id} day={self.current_day}>"


class Donation(Base):
    """История донатов через Telegram Stars."""
    __tablename__ = "donations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)  # tg_id
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)  # кол-во звёзд
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(255))
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<Donation user={self.user_id} amount={self.amount}>"


class AIRequest(Base):
    """Запросы юзера к AI Пастырю — для лимитов и истории."""
    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    request_text: Mapped[str] = mapped_column(String(2000))
    response_text: Mapped[str] = mapped_column(String(2000))
    lang: Mapped[str] = mapped_column(String(5))
    is_crisis: Mapped[bool] = mapped_column(default=False)  # был ли определён как кризисный
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def __repr__(self) -> str:
        return f"<AIRequest user={self.user_id} at={self.created_at}>"


class AIConsent(Base):
    """Согласие юзера с правилами AI Пастыря (одноразовое)."""
    __tablename__ = "ai_consent"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ActivityHourly(Base):
    """Почасовой агрегат активности — одна строка на час вместо строки на клик.

    Счётчики копятся в памяти (см. AnalyticsService) и апсертятся в строку
    текущего часа раз в минуту, поэтому БД не нагружается потоком событий, а
    объём растёт ~24 строки в сутки. Сознательно НЕ храним сырые timestamp'ы и
    список юзеров, поэтому метрики «сессии» и точный unique-active за сутки
    недоступны — для мониторинга нагрузки они не нужны.

    hour_bucket — начало часа в локальном времени сервера (datetime.now()),
    как и cron планировщика: пиковый час совпадает с тем, что видит админ.
    """
    __tablename__ = "activity_hourly"

    id: Mapped[int] = mapped_column(primary_key=True)
    hour_bucket: Mapped[datetime] = mapped_column(DateTime, unique=True, index=True)
    events: Mapped[int] = mapped_column(Integer, default=0)         # действий юзеров (message/callback)
    peak_per_min: Mapped[int] = mapped_column(Integer, default=0)   # макс. входящих за минуту в этот час
    active_users: Mapped[int] = mapped_column(Integer, default=0)   # уникальных юзеров за этот час
    errors: Mapped[int] = mapped_column(Integer, default=0)
    throttled: Mapped[int] = mapped_column(Integer, default=0)
    notifs: Mapped[int] = mapped_column(Integer, default=0)
    by_category: Mapped[str] = mapped_column(Text, default="{}")    # JSON: {"reading": 12, ...}

    def __repr__(self) -> str:
        return f"<ActivityHourly {self.hour_bucket:%Y-%m-%d %H:00} events={self.events}>"
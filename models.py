from datetime import datetime, date

from sqlalchemy import BigInteger, String, DateTime, Date, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    """Модель пользователя бота."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lang: Mapped[str] = mapped_column(String(5), default="ru")
    translation: Mapped[str] = mapped_column(String(20), default="ru_synodal")
    notifications_enabled: Mapped[bool] = mapped_column(default=False)  # ← новое
    notification_time: Mapped[str] = mapped_column(String(5), default="09:00")  # ← новое, формат "HH:MM"
    # Серии (streaks)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    freezes_available: Mapped[int] = mapped_column(Integer, default=2)
    streak_explained: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Feedback {self.kind} from {self.user_id}>"


class PlanProgress(Base):
    """Прогресс пользователя по активному плану чтения."""
    __tablename__ = "plan_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    plan_id: Mapped[str] = mapped_column(String(50))  # "nt_30", "psalms_30", ...
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    current_day: Mapped[int] = mapped_column(Integer, default=1)  # на каком дне план
    completed_days: Mapped[str] = mapped_column(String(2000), default="[]")  # JSON [1, 2, 4, ...]
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / completed / abandoned

    # Время push-уведомления для плана
    notification_enabled: Mapped[bool] = mapped_column(default=True)
    notification_time: Mapped[str] = mapped_column(String(5), default="19:00")  # "HH:MM"

    def __repr__(self) -> str:
        return f"<PlanProgress user={self.user_id} plan={self.plan_id} day={self.current_day}>"
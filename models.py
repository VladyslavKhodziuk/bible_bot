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
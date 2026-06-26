import json
import logging
from datetime import datetime, timezone

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL, DATA_DIR

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


# Движок подключения к БД
engine = create_async_engine(DATABASE_URL, echo=False)


# WAL: читатели не блокируют писателя и наоборот — критично, т.к. flush
# аналитики (раз в минуту), стрики, AI-запросы и хендлеры пишут параллельно.
# busy_timeout: вместо мгновенной ошибки "database is locked" ждём до 5 сек.
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# Фабрика сессий
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    from models import User, Bookmark, PrayerFavorite, Feedback, PlanProgress, AIRequest, AIConsent, Donation, ActivityHourly, FeedbackRelay  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Sentinel-файл рядом с bot.db (в DATA_DIR — на Railway это Volume, иначе CWD).
# Каждая запись — выполненная миграция (одна на строку). Так миграции
# идемпотентны: при следующем старте уже выполненные пропускаются.
_MIGRATIONS_SENTINEL = DATA_DIR / "migrations_applied.txt"


def _applied_migrations() -> set[str]:
    if not _MIGRATIONS_SENTINEL.exists():
        return set()
    return {line.strip() for line in _MIGRATIONS_SENTINEL.read_text(encoding="utf-8").splitlines() if line.strip()}


def _mark_migration(key: str) -> None:
    with _MIGRATIONS_SENTINEL.open("a", encoding="utf-8") as f:
        f.write(f"{key}\n")


async def run_migrations():
    """Выполняет одноразовые SQL-миграции, которых нет в Base.metadata."""
    applied = _applied_migrations()

    # 2026-06: молитва по умолчанию включена в 10:00, план — в 20:00.
    # Старые юзеры были созданы с дефолтами False/08:00 и 19:00; приводим к новым.
    key = "2026-06_notification_defaults"
    if key not in applied:
        async with engine.begin() as conn:
            await conn.execute(text(
                "UPDATE users SET prayer_notifications_enabled = 1, prayer_notification_time = '10:00'"
            ))
            await conn.execute(text(
                "UPDATE plan_progress SET notification_time = '20:00'"
            ))
        _mark_migration(key)
        logger.info("Миграция '%s' применена: дефолты уведомлений выставлены всем существующим юзерам/планам", key)


# ── Persistence sentinel ────────────────────────────────────
# Защита от тихой потери БД: после инцидента 2026-06-26 (на Railway отвалился
# Volume, бот стартовал с пустой bot.db и никто этого не заметил) — храним
# рядом с БД sentinel-файл с последним известным числом юзеров. На каждом
# старте сравниваем: если было N>0 юзеров, а стало 0 — кричим алертом.
_PERSISTENCE_SENTINEL = DATA_DIR / "persistence_sentinel.json"


def _read_persistence_sentinel() -> dict | None:
    """Читает sentinel с прошлого старта. None — если файла нет или он битый."""
    if not _PERSISTENCE_SENTINEL.exists():
        return None
    try:
        return json.loads(_PERSISTENCE_SENTINEL.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("persistence_sentinel.json повреждён, игнорируем: %s", e)
        return None


def _write_persistence_sentinel(user_count: int, boot_count: int) -> None:
    payload = {
        "last_user_count": user_count,
        "last_boot_at": datetime.now(timezone.utc).isoformat(),
        "boot_count": boot_count,
    }
    _PERSISTENCE_SENTINEL.write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


async def verify_persistence() -> None:
    """Сверка состояния БД с прошлым стартом. Алерт админам, если данные пропали.

    Идея: персистентность определяется тем, что sentinel-файл (на том же
    Volume, что bot.db) пережил рестарт. Если файл показывает «было N юзеров,
    стало 0» — почти наверняка Volume отвалился / не примонтирован, и бот
    стартует с эфемерной ФС. Это уже произошло один раз (2026-06-26).

    Гард в config.py (BOT_DATA_DIR обязателен на Railway) ловит самый частый
    случай — пустую env var. Этот sentinel ловит остальное: detach Volume,
    смену mount path, пересоздание Volume.

    Вызывается из main.py после AlertService.init(bot) — чтобы alert умел
    отправиться. Никогда не бросает: ошибка проверки не должна валить старт.
    """
    # Локальный импорт — иначе циклический (alert_service → config → database
    # на уровне модулей у нас нет, но конвенция как в scheduler.py).
    from services.alert_service import AlertService

    try:
        async with async_session() as session:
            row = await session.execute(text("SELECT COUNT(*) FROM users"))
            current_users = int(row.scalar() or 0)
    except Exception as e:
        logger.warning("verify_persistence: не смог посчитать users: %s", e)
        return

    prior = _read_persistence_sentinel()
    boot_count = (prior.get("boot_count", 0) if prior else 0) + 1

    if prior and prior.get("last_user_count", 0) > 0 and current_users == 0:
        # КРИТИЧНО: были юзеры, стали 0 — потеря персистентности.
        last_n = prior.get("last_user_count")
        last_at = prior.get("last_boot_at", "?")
        logger.critical(
            "DB persistence lost: было %s юзеров (sentinel от %s), сейчас 0. "
            "DATA_DIR=%s. Volume не примонтирован?",
            last_n, last_at, DATA_DIR,
        )
        await AlertService.alert_error(
            key="db_persistence_lost",
            title="БД пуста после рестарта — Volume отвалился?",
            detail=(
                f"Было {last_n} юзеров (sentinel от {last_at}), сейчас 0. "
                f"DATA_DIR={DATA_DIR}. НЕ пушь обновления — потеряешь и "
                f"свежую БД. Проверь Railway → Settings → Volumes."
            ),
        )
        # Sentinel НЕ перезаписываем — оставляем старый, чтобы повторный
        # рестарт с тем же симптомом не «забил» исходные значения нулями
        # и алерт можно было повторить (с учётом cooldown в AlertService).
        return

    # Обычный путь: всё ок, либо первый старт ever, либо легитимный 0→0.
    try:
        _write_persistence_sentinel(current_users, boot_count)
    except OSError as e:
        logger.warning("verify_persistence: не смог записать sentinel: %s", e)
    logger.info(
        "Persistence OK: users=%d, boot=%d, DATA_DIR=%s",
        current_users, boot_count, DATA_DIR,
    )
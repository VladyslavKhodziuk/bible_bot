import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")

DATABASE_URL = "sqlite+aiosqlite:///bot.db"

DEFAULT_LANG = "uk"
SUPPORTED_LANGS = ["ru", "en", "es", "uk"]

# Часовой пояс по умолчанию (IANA). Используется для новых пользователей и как
# fallback, если у юзера сохранён неизвестный/битый пояс. Уведомления и стрики
# считаются в личном часовом поясе пользователя (см. services/timezones.py).
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Europe/Kyiv")

# ID администраторов — получают уведомления о фидбеке
_admins_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _admins_raw.split(",") if x.strip()]


# ── Группы для уведомлений о фидбеке ────────────────────────
# ID Telegram-групп (число вида -100..., бот должен быть участником группы).
# Если ID не задан — соответствующий фидбек уходит админам в личку (ADMIN_IDS).
def _parse_chat_id(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


FEEDBACK_CHAT_IDS = {
    "review": _parse_chat_id(os.getenv("FEEDBACK_REVIEW_CHAT_ID", "")),
    "bug": _parse_chat_id(os.getenv("FEEDBACK_BUG_CHAT_ID", "")),
    "idea": _parse_chat_id(os.getenv("FEEDBACK_IDEA_CHAT_ID", "")),
}

# ── Донаты ──────────────────────────────────────────────
# Внешние ссылки: кнопка показывается только если URL задан
DONATE_MONOBANK_URL = os.getenv("DONATE_MONOBANK_URL", "https://send.monobank.ua/jar/8ELwuMGBLh")
DONATE_MONOBANK_CARD = os.getenv("DONATE_MONOBANK_CARD", "4874 1000 3813 2323")
DONATE_REVOLUT_URL = os.getenv("DONATE_REVOLUT_URL", "https://revolut.me/vladysqu8c")
DONATE_PAYPAL_URL = os.getenv("DONATE_PAYPAL_URL", "")
DONATE_CRYPTO_URL = os.getenv("DONATE_CRYPTO_URL", "")

# Пресеты для Telegram Stars (сумма → примерный USD)
DONATE_STAR_PRESETS = [
    (50, 1),
    (200, 4),
    (500, 10),
    (1000, 20),
]
DONATE_STARS_MIN = 1
DONATE_STARS_MAX = 2500 # ограничение Telegram на один платёж

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY не задан в .env")


# ── Аналитика и ежедневный отчёт ─────────────────────────
# ID группы, куда раз в сутки в REPORT_TIME уходит сводка активности.
# Если не задан — отчёт уходит в личку администраторам (ADMIN_IDS).
REPORT_CHAT_ID = _parse_chat_id(os.getenv("REPORT_CHAT_ID", ""))
REPORT_TIME = os.getenv("REPORT_TIME", "22:00")  # формат "HH:MM", локальное время сервера

# Месячный отчёт: шлётся в REPORT_TIME в день MONTHLY_REPORT_DAY и покрывает
# цикл [прошлый MONTHLY_REPORT_DAY → этот MONTHLY_REPORT_DAY).
# Очистка старых событий запускается в день CLEANUP_DAY (≈10 дней спустя):
# удаляются записи старше начала последнего отчётного цикла (уже отчётанные).
MONTHLY_REPORT_DAY = int(os.getenv("MONTHLY_REPORT_DAY", "25"))
CLEANUP_DAY = int(os.getenv("CLEANUP_DAY", "5"))

# Throttling: не больше THROTTLE_MAX_EVENTS действий от одного юзера
# за THROTTLE_WINDOW_SEC секунд. Превышение — действие отбрасывается.
THROTTLE_MAX_EVENTS = int(os.getenv("THROTTLE_MAX_EVENTS", "15"))
THROTTLE_WINDOW_SEC = float(os.getenv("THROTTLE_WINDOW_SEC", "3"))

# Хранение текстов AI-запросов (приватность). Строки AIRequest старше стольких
# дней удаляются ежедневным обслуживанием. Тексты содержат чувствительные данные
# (в т.ч. кризисные), поэтому срок ограничен. Лимиты и контекст сессии работают
# в пределах суток, так что на функциональность это не влияет.
# ВАЖНО: значение >= 45 сохраняет точность месячного отчёта (он смотрит до ~31
# дня назад). Меньшее значение → старые AI-запросы в месячном отчёте могут
# недосчитываться.
AI_REQUEST_RETENTION_DAYS = int(os.getenv("AI_REQUEST_RETENTION_DAYS", "90"))


# ── Алерты администратору (мониторинг) ───────────────────
# Срочные уведомления о сбоях уходят в личку ADMIN_IDS. Чтобы при краш-цикле
# не прилетали сотни сообщений, одинаковые алерты (по ключу) шлются не чаще,
# чем раз в ALERT_COOLDOWN_SEC секунд.
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "300"))

# Пороги health-check (в процентах). При превышении — алерт.
ALERT_MEM_THRESHOLD = float(os.getenv("ALERT_MEM_THRESHOLD", "90"))
ALERT_DISK_THRESHOLD = float(os.getenv("ALERT_DISK_THRESHOLD", "90"))
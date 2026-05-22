import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")

DATABASE_URL = "sqlite+aiosqlite:///bot.db"

DEFAULT_LANG = "uk"
SUPPORTED_LANGS = ["ru", "en", "es", "uk"]

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
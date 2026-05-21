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

# ── Донаты ──────────────────────────────────────────────
# Внешние ссылки: кнопка показывается только если URL задан
DONATE_BUYMEACOFFEE_URL = os.getenv("DONATE_BUYMEACOFFEE_URL", "")
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
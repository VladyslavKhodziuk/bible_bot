import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")

DATABASE_URL = "sqlite+aiosqlite:///bot.db"

DEFAULT_LANG = "uk"
SUPPORTED_LANGS = ["ru", "en", "es", "uk"]

# ID администраторов — получают уведомления о фидбеке
ADMIN_IDS = [1778315709]  # твой Telegram ID
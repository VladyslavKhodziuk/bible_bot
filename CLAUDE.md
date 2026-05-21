# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Multilingual Telegram Bible bot ("Bible Way") built on **aiogram 3.13** with async **SQLAlchemy 2.0 + aiosqlite**. Supports 4 UI languages (ru/en/es/uk) and 7 Bible translations. Features: chapter reading, search, topics, bookmarks, reading plans with notifications, streaks (Duolingo-style), Telegram Stars donations, and an AI Pastor backed by Gemini.

## Commands

```powershell
# Setup
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run the bot (long-poll, blocks)
python main.py
```

Required env vars in `.env` (loaded by `config.py`):
- `BOT_TOKEN` — Telegram bot token (required, raises on missing)
- `GEMINI_API_KEY` — Google Gemini API key for AI Pastor (required, raises on missing)
- `ADMIN_IDS` — comma-separated tg IDs that receive feedback notifications (optional)
- `DONATE_BUYMEACOFFEE_URL`, `DONATE_PAYPAL_URL`, `DONATE_CRYPTO_URL` — external donation URLs; the button only renders if its URL is set

No tests, lint config, or build system are present. `bot.db` (SQLite) is auto-created in the working directory on first run by `init_db()`.

## Architecture

### Wiring (`main.py`)
1. `init_db()` creates SQLAlchemy tables.
2. `BibleService.load()`, `TopicService.load()`, `PlanService.load()` read all YAML/JSON data files into class-level memory caches — these are loaded **once at startup** and shared across all requests.
3. A single `Dispatcher` is built and every handler module's `router` is `include_router()`ed. **Order matters** for FSM/middleware priority: `feedback` and `donate` are registered first because they use FSM states that must intercept text input before other handlers.
4. `setup_scheduler(bot)` starts an `AsyncIOScheduler` that ticks **every minute** (see Scheduler below).
5. `dp.start_polling(bot)` begins long-poll.

When adding a new feature module under `handlers/`, you must both import it in `main.py` and `dp.include_router(...)` it — there is no auto-discovery.

### Layering
- **`handlers/<feature>.py`** — each module exports a `router = Router()` and registers aiogram message/callback handlers. Callback-data uses `:` as separator (e.g. `read:ch:<abbrev>:<chapter>`, `setlang:<code>`). Handlers are thin: they resolve the user, call services, then render via keyboards + i18n.
- **`services/<feature>_service.py`** — all business logic, DB access, and external API calls. Services are **stateless static/classmethod** classes; data caches (Bibles, plans, topics) live as class-level dicts populated by `.load()`.
- **`keyboards/<feature>.py`** — builders that return `InlineKeyboardMarkup`. Most callback-data shapes are defined here implicitly; if you change a prefix, grep both `keyboards/` and `handlers/`.
- **`locales/{ru,en,es,uk}.yaml`** — translations consumed via `services.i18n.t("dotted.key", lang, **fmt_kwargs)`. Missing keys return the bracketed key (`[menu.read]`) for visible debugging, never an exception.
- **`models.py`** — all SQLAlchemy models in one file (`User`, `Bookmark`, `Feedback`, `PlanProgress`, `Donation`, `AIRequest`, `AIConsent`). `database.py` provides `async_session` (an `async_sessionmaker`) and `Base`. There is **no migration tool** — schema changes happen via `Base.metadata.create_all` on startup, which only adds tables. Column changes require manual SQL or deleting `bot.db`.
- **`data/`** — read-only content shipped with the repo:
  - `bibles/<code>.json` — full text per translation (7 files). Loaded into `BibleService._bibles[code]`.
  - `books.yaml` — canonical 66-book metadata; `data["abbrev"]` order defines `_book_order`, the index used to align translations. **All Bible JSONs must use the same book order as `books.yaml`.**
  - `plans/*.yaml` — reading plans (id, names per lang, day → readings).
  - `topics.yaml` — themed verse collections.

### Key cross-cutting patterns

**Bible data model.** `BibleService` keeps every translation as `list[Book]` where `Book.chapters = list[list[str]]` (chapters → verses). Books are aligned across translations purely by **list index**, mapped to abbreviations through `_book_order` from `books.yaml`. Never look up by name across translations; always go via `abbrev` → `get_book_index`.

**Verse of the day.** `BibleService.get_verse_of_day()` seeds `random.Random` with `date.toordinal()` so every user on the same translation sees the same verse for a given UTC date. Do not introduce per-user randomness here.

**Streaks (`services/streak_service.py`).** Call `StreakService.touch(tg_id)` from any handler that should count as "engagement" (reading a chapter, opening verse of day, completing a plan day). It returns a `StreakResult` describing what happened (grew / froze / burned / milestone / returned-after-loss); the caller is responsible for surfacing celebratory or freeze-used messages to the user. The scheduler calls `touch()` when delivering the daily verse.

**Scheduler (`services/scheduler.py`).** Single APScheduler cron job runs `send_daily_verses()` every minute. It compares `datetime.now().strftime("%H:%M")` against `User.notification_time` and `PlanProgress.notification_time` and dispatches messages to matching rows. Times are stored as `"HH:MM"` strings in the user's local intent (no timezone awareness — the server clock is the reference). Failures per user are caught and logged so one bad chat doesn't block the batch.

**AI Pastor (`services/ai_pastor_service.py`).** Uses `google-genai` with model `gemini-2.5-flash`. Hard daily limit `DAILY_LIMIT = 3` per user (enforced via `AIRequest` row count for the calendar day). User must accept terms once (`AIConsent` row) before the first request. The system prompt instructs the model to append `[CRISIS]` or `[NORMAL]` on its own line; `send_request()` parses and strips this marker before returning `(text, is_crisis)`. Network/5xx errors retry up to 3× with exponential backoff; permanent 4xx returns a localized fallback string immediately. Session context = last 3 request/response pairs from today, sent as Gemini `Content` history.

**Donations.** Telegram Stars flow lives in `handlers/donate.py` and `services/donate_service.py`. `PreCheckoutQuery` must always be answered with `ok=True` for Stars to clear; successful payments insert a `Donation` row and notify `ADMIN_IDS`. External-URL buttons (BMC/PayPal/Crypto) are gated on the env var being non-empty — see `keyboards/donate.py`.

**i18n contract.** All user-facing strings go through `t()`. The 4 locale files must stay in sync — if you add a key in `ru.yaml`, add it to `en.yaml`, `es.yaml`, `uk.yaml` too, or users on other languages will see `[key.path]`. Format placeholders use Python `str.format` syntax (`{name}`, `{count}`).

**User language vs translation.** `User.lang` is the **UI** language (one of 4); `User.translation` is the **Bible** translation code (one of 7, e.g. `ru_synodal`). These are independent — a Ukrainian-UI user may read the KJV. `BibleService.get_translation_for_lang()` picks a sensible default when first creating a user.

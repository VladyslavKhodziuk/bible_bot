# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Multilingual Telegram Bible bot ("Bible Way") built on **aiogram 3.13** with async **SQLAlchemy 2.0 + aiosqlite**. Supports 4 UI languages (ru/en/es/uk) and 7 Bible translations. Features: chapter reading, search, topics, bookmarks, reading plans with notifications, prayer of the day, dual streaks (reading + prayer, Duolingo-style), per-user timezones, Telegram Stars donations, an AI Pastor backed by Gemini, and an in-process analytics/alerting stack.

## Commands

```powershell
# Setup
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run the bot (long-poll, blocks)
python main.py
```

Env vars (loaded by `config.py` via `python-dotenv`):
- `BOT_TOKEN` — Telegram bot token (**required**, raises on missing).
- `GEMINI_API_KEY` — Google Gemini key for AI Pastor (**required**, raises on missing).
- `ADMIN_IDS` — comma-separated tg IDs for feedback notifications and admin alerts (optional).
- `DEFAULT_TZ` — IANA zone used for new users / unknown-zone fallback (default `Europe/Madrid`).
- `FEEDBACK_REVIEW_CHAT_ID` / `FEEDBACK_BUG_CHAT_ID` / `FEEDBACK_IDEA_CHAT_ID` — group chats per feedback kind; missing → falls back to ADMIN_IDS DM.
- `DONATE_MONOBANK_URL` / `DONATE_MONOBANK_CARD` / `DONATE_REVOLUT_URL` / `DONATE_PAYPAL_URL` / `DONATE_CRYPTO_URL` — external donation links; a button only renders if its URL is set.
- `REPORT_CHAT_ID` / `REPORT_TIME` — daily analytics report destination + send time (HH:MM, server local). Falls back to ADMIN_IDS DM.
- `MONTHLY_REPORT_DAY` (default 25) / `CLEANUP_DAY` (default 5) — day-of-month for the monthly report and for purging old `activity_hourly` rows.
- `THROTTLE_MAX_EVENTS` (default 15) / `THROTTLE_WINDOW_SEC` (default 3) — per-user rate limit enforced by `AnalyticsMiddleware`.
- `ALERT_COOLDOWN_SEC` (default 300) / `ALERT_MEM_THRESHOLD` / `ALERT_DISK_THRESHOLD` — alert dedup window and resource thresholds.
- `AI_REQUEST_RETENTION_DAYS` (default 90) — AI request texts are purged after this many days (privacy). Keep ≥ 45 so monthly reports stay accurate.

No tests, lint config, or build system are present. `bot.db` (SQLite) is auto-created on first run by `init_db()`.

## Architecture

### Wiring (`main.py`)
1. `init_db()` creates SQLAlchemy tables (`Base.metadata.create_all` — adds tables only, never alters columns).
2. `BibleService.load()`, `TopicService.load()`, `PlanService.load()`, `PrayerService.load()` read all YAML/JSON data files into class-level in-memory caches — loaded **once at startup**, shared across requests.
3. `AlertService.init(bot)` stashes the `Bot` so any code (services, scheduler, middleware) can DM admins without passing `bot` around.
4. `AnalyticsMiddleware` is registered as an **outer** middleware on `dp.update` — it sees every update, does throttling, records analytics, and converts handler exceptions into admin alerts before re-raising.
5. Every handler module's `router` is `include_router()`ed on a single `Dispatcher`. **Order matters**: `feedback` and `donate` are registered first because they own FSM states that must intercept text input before plain-text handlers; `chatid` is registered **last** so it doesn't swallow normal messages/forwards.
6. `setup_scheduler(bot)` starts an `AsyncIOScheduler` cron job that ticks every minute (see Scheduler below).
7. `dp.start_polling(bot, drop_pending_updates=True)` — pending updates are dropped on (re)start so the bot doesn't replay a stale backlog.
8. On shutdown: scheduler stops, `AnalyticsService.flush()` writes any buffered hour aggregate, then `bot.session.close()`.

When adding a new feature module under `handlers/`, you must both import it in `main.py` and `dp.include_router(...)` it — there is no auto-discovery.

### Layering
- **`handlers/<feature>.py`** — each module exports `router = Router()` and registers aiogram message/callback handlers. Callback-data uses `:` as separator (e.g. `read:ch:<abbrev>:<chapter>`, `setlang:<code>`, `pray:amen`). Handlers stay thin: resolve user → call services → render via keyboards + i18n. `noop` callbacks are explicitly ignored by analytics.
- **`services/<feature>_service.py`** — all business logic, DB access, and external API calls. Services are **stateless static/classmethod** classes; data caches (Bibles, plans, topics, prayers) live as class-level dicts populated by `.load()`. Cross-cutting helpers live alongside: `i18n.py`, `timezones.py`, `streak_display.py`, `menu_text.py`.
- **`keyboards/<feature>.py`** — builders returning `InlineKeyboardMarkup`. Callback-data shapes are defined here implicitly; if you change a prefix, grep both `keyboards/` and `handlers/` **and** update `_CALLBACK_CATEGORY` in `services/analytics_service.py` so the new prefix is categorized.
- **`middlewares/analytics.py`** — the single outer middleware: throttling, analytics recording, and exception → admin-alert conversion.
- **`locales/{ru,en,es,uk}.yaml`** — translations consumed via `services.i18n.t("dotted.key", lang, **fmt_kwargs)`. Missing keys return the bracketed key (`[menu.read]`) for visible debugging, never an exception.
- **`models.py`** — all SQLAlchemy models: `User`, `Bookmark`, `Feedback`, `PlanProgress`, `Donation`, `AIRequest`, `AIConsent`, `ActivityHourly`. `database.py` provides `async_session` (an `async_sessionmaker`) and `Base`. **No migration tool** — schema changes require manual SQL or deleting `bot.db`. The `bot.db.backup-*` files in the repo root are ad-hoc snapshots from `scripts/migrate_prayer_notifications.py`.
- **`data/`** — read-only content shipped with the repo:
  - `bibles/<code>.json` — full text per translation (7 files). Loaded into `BibleService._bibles[code]`.
  - `books.yaml` — canonical 66-book metadata; `data["abbrev"]` order defines `_book_order`, the index used to align translations. **All Bible JSONs must use the same book order as `books.yaml`.**
  - `plans/*.yaml` — reading plans (id, names per lang, day → readings).
  - `topics.yaml` — themed verse collections.
  - `prayers_of_day.yaml`, `verses_of_day.yaml`, `wisdom_of_day.yaml` — daily-rotation content.

### Key cross-cutting patterns

**Bible data model.** `BibleService` keeps every translation as `list[Book]` where `Book.chapters = list[list[str]]` (chapters → verses). Books are aligned across translations purely by **list index**, mapped to abbreviations through `_book_order` from `books.yaml`. Never look up by name across translations; always go via `abbrev` → `get_book_index`.

**Verse of the day.** `BibleService.get_verse_of_day()` seeds `random.Random` with `date.toordinal()` so every user on the same translation sees the same verse for a given UTC date. Do not introduce per-user randomness here.

**Per-user timezones.** `User.timezone` holds an IANA zone (default from `DEFAULT_TZ`). All "what time is it for this user?" logic flows through `services/timezones.py` — `local_hhmm(tz)`, `local_today(tz)`, `local_now(tz)`. The scheduler matches `User.notification_time` against the user's *local* HH:MM, **not** server time, by iterating distinct zones and matching per-zone in SQL (keeps the query bounded). When adding new daily/scheduled features, always compare against `local_hhmm(user.timezone)`, never `datetime.now()`.

**Reading streak (`services/streak_service.py`).** Call `StreakService.touch(tg_id)` from any handler that should count as "engagement" (reading a chapter, opening verse of day, completing a plan day). Returns a `StreakResult` describing what happened (grew / froze / burned / milestone / returned-after-loss); the caller is responsible for surfacing celebratory or freeze-used messages — `services/streak_display.py` builds those (`get_milestone_message`, `get_daily_progress_message`, `with_donate_addendum`, `build_milestone_keyboard`, `build_dismiss_keyboard`). Milestones append a donate prompt; ordinary growth days get a dismissible progress message. The scheduler calls `touch()` when delivering the daily verse.

**Prayer streak (`services/prayer_streak_service.py`).** Separate counter (`User.current_prayer_streak` / `longest_prayer_streak` / `last_prayer_date`) that grows **only** when the user taps "Аминь" on the daily prayer card. No freezes — a missed day resets to 1. Do not conflate with the reading streak.

**Scheduler (`services/scheduler.py`).** Single APScheduler cron job runs `send_daily_verses()` every minute and dispatches, in order: (1) verse of the day to `User.notifications_enabled` users at their local `notification_time`, (2) reading-plan pushes for active `PlanProgress` rows at their local `notification_time`, (3) prayer-of-the-day to users with `prayer_notifications_enabled` (opt-in, default off) at their local `prayer_notification_time`, (4) `AnalyticsService.flush()` (persists the current hour's aggregate row), (5) RAM/disk health-check, (6) if server-local HH:MM matches `REPORT_TIME`: daily activity report (and monthly on `MONTHLY_REPORT_DAY`, and `activity_hourly` cleanup on `CLEANUP_DAY`, plus AI-request retention purge). Per-user failures are caught and logged so one bad chat never blocks the batch; only `TelegramNetworkError` / `TelegramServerError` / `TelegramRetryAfter` trigger admin alerts (user-blocked-bot is normal and silent).

**Analytics (`services/analytics_service.py` + `models.ActivityHourly`).** Hourly aggregates only — no per-event rows. Counters accumulate in class-level memory and are upserted into the row for the current hour each minute by `flush()`. Throttling state (`THROTTLE_MAX_EVENTS` per `THROTTLE_WINDOW_SEC`) is also in-memory; throttled callbacks get a `⏳` answer and the handler is never invoked. Categories come from callback-data prefix via `_CALLBACK_CATEGORY` — **if you add a new callback prefix, register it there** or it will be bucketed as `other`. Times are server-local because the report is an ops view in one zone.

**Admin alerts (`services/alert_service.py`).** `AlertService.alert_error(key, title, detail)` DMs every admin in `ADMIN_IDS`. Identical `key`s are deduped to one message per `ALERT_COOLDOWN_SEC` so crash loops don't flood. The middleware uses `handler_error:<category>` as its key; the scheduler uses `telegram_infra:<ExceptionClass>` and `health_mem` / `health_disk`. Pick stable, low-cardinality keys when adding new alert sites.

**AI Pastor (`services/ai_pastor_service.py`).** Uses `google-genai` with model `gemini-2.5-flash`. Hard daily limit `DAILY_LIMIT = 3` per user (enforced via `AIRequest` row count for the calendar day). User must accept terms once (`AIConsent` row) before the first request. The system prompt instructs the model to append `[CRISIS]` or `[NORMAL]` on its own line; `send_request()` parses and strips this marker before returning `(text, is_crisis)`. Network/5xx errors retry up to 3× with exponential backoff; permanent 4xx returns a localized fallback string immediately. Session context = last 3 request/response pairs from today, sent as Gemini `Content` history. `AIPastorService.cleanup_old_requests()` runs daily from the scheduler to purge texts older than `AI_REQUEST_RETENTION_DAYS` (privacy).

**Donations.** Telegram Stars flow lives in `handlers/donate.py` and `services/donate_service.py`. `PreCheckoutQuery` must always be answered with `ok=True` for Stars to clear; successful payments insert a `Donation` row and notify `ADMIN_IDS`. External-URL buttons (Monobank / Revolut / PayPal / Crypto) are each gated on their env var being non-empty — see `keyboards/donate.py`.

**i18n contract.** All user-facing strings go through `t()`. The 4 locale files must stay in sync — if you add a key in `ru.yaml`, add it to `en.yaml`, `es.yaml`, `uk.yaml` too, or users on other languages will see `[key.path]`. Format placeholders use Python `str.format` syntax (`{name}`, `{count}`). `DEFAULT_LANG` is `uk`.

**User language vs translation.** `User.lang` is the **UI** language (one of 4); `User.translation` is the **Bible** translation code (one of 7, e.g. `ru_synodal`). These are independent — a Ukrainian-UI user may read the KJV. `BibleService.get_translation_for_lang()` picks a sensible default when first creating a user.

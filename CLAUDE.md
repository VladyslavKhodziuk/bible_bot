# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Multilingual Telegram Bible bot ("Bible Way") built on **aiogram 3.13** with async **SQLAlchemy 2.0 + aiosqlite**. Supports 4 UI languages (ru/en/es/uk) and 7 Bible translations. Features: chapter reading, search, topics, bookmarks, reading plans with notifications, prayer of the day, prayer favorites, dual "days-with-the-Word" counters (reading + prayer — only grow, never reset), per-user timezones, Telegram Stars donations, a notifications hub, an FAQ + "ask the author" flow, an AI Pastor backed by Gemini, and an in-process analytics/alerting stack.

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
- `DONATE_MONOBANK_URL` / `DONATE_MONOBANK_CARD` / `DONATE_REVOLUT_URL` / `DONATE_PAYPAL_URL` / `DONATE_CRYPTO_URL` / `DONATE_BIZUM_PHONE` — external donation links/numbers; a button only renders if its env var is set.
- `REPORT_CHAT_ID` / `REPORT_TIME` — daily analytics report destination + send time (HH:MM, server local). Falls back to ADMIN_IDS DM.
- `MONTHLY_REPORT_DAY` (default 25) / `CLEANUP_DAY` (default 5) — day-of-month for the monthly report and for purging old `activity_hourly` rows.
- `THROTTLE_MAX_EVENTS` (default 15) / `THROTTLE_WINDOW_SEC` (default 3) — per-user rate limit enforced by `AnalyticsMiddleware`.
- `ALERT_COOLDOWN_SEC` (default 300) / `ALERT_MEM_THRESHOLD` / `ALERT_DISK_THRESHOLD` — alert dedup window and resource thresholds.
- `AI_REQUEST_RETENTION_DAYS` (default 90) — AI request texts are purged after this many days (privacy). Keep ≥ 45 so monthly reports stay accurate.

No tests, lint config, or build system are present. `bot.db` (SQLite) is auto-created on first run by `init_db()`.

## Architecture

### Wiring (`main.py`)
1. `init_db()` creates SQLAlchemy tables (`Base.metadata.create_all` — adds tables only, never alters columns).
2. `run_migrations()` applies one-shot SQL migrations that can't be expressed in `create_all` (e.g. backfilling new column defaults onto existing rows). See "Migrations" below.
3. `BibleService.load()`, `TopicService.load()`, `PlanService.load()`, `PrayerService.load()` read all YAML/JSON data files into class-level in-memory caches — loaded **once at startup**, shared across requests.
4. `AlertService.init(bot)` stashes the `Bot` so any code (services, scheduler, middleware) can DM admins without passing `bot` around.
5. `AnalyticsMiddleware` is registered as an **outer** middleware on `dp.update` — it sees every update, does throttling, records analytics, converts handler exceptions into admin alerts before re-raising, and resets the freetext strike counter on any successful interaction.
6. `set_bot_commands(bot)` and `bot_meta.prewarm(bot)` run best-effort (network blips at boot don't block startup).
7. Every handler module's `router` is `include_router()`ed on a single `Dispatcher`. **Order matters** (see below).
8. `setup_scheduler(bot)` starts an `AsyncIOScheduler` cron job that ticks every minute (see Scheduler below).
9. `dp.start_polling(bot, drop_pending_updates=True)` — pending updates are dropped on (re)start so the bot doesn't replay a stale backlog.
10. On shutdown: scheduler stops, `AnalyticsService.flush()` writes any buffered hour aggregate, then `bot.session.close()`.

**Router order** in `main.py` (top to bottom):
- `reply_menu` — **first**. The persistent reply-keyboard buttons ("Main menu / Settings / FAQ / Support") arrive as plain text; matching them with an exact-label filter here lets them work as a global FSM-escape even when feedback/donate are awaiting input.
- `feedback`, `donate` — own FSM states that intercept text input; must come before plain-text catch-alls.
- `start`, `menu`, `help`, `settings`, `read`, `verse`, `topics`, `pray`, `prayer_notifications`, `prayer_favorites`, `bookmarks`, `notifications`, `cabinet`, `search`, `plan`, `ai_pastor` — normal feature routers.
- `chatid` — **before** `freetext`, so forwarded messages (`F.forward_origin`) reach the chat-id reveal before the catch-all.
- `freetext` — **last**. Catches all unhandled text and runs the soft escalation prompt (see "Freetext catch-all").

When adding a new feature module under `handlers/`, you must both import it in `main.py` and `dp.include_router(...)` it — there is no auto-discovery.

### Layering
- **`handlers/<feature>.py`** — each module exports `router = Router()` and registers aiogram message/callback handlers. Callback-data uses `:` as separator (e.g. `read:ch:<abbrev>:<chapter>`, `setlang:<code>`, `pray:amen`, `faq:q:<id>`). Handlers stay thin: resolve user → call services → render via keyboards + i18n. `noop` callbacks are explicitly ignored by analytics.
- **`services/<feature>_service.py`** — all business logic, DB access, and external API calls. Services are **stateless static/classmethod** classes; data caches (Bibles, plans, topics, prayers) live as class-level dicts populated by `.load()`. Cross-cutting helpers live alongside: `i18n.py`, `timezones.py`, `counter_display.py`, `menu_text.py`, `share.py`, `bot_meta.py`.
- **`keyboards/<feature>.py`** — builders returning `InlineKeyboardMarkup` (plus `keyboards/reply.py` for the persistent `ReplyKeyboardMarkup` shown under the input box). Callback-data shapes are defined here implicitly; if you change a prefix, grep both `keyboards/` and `handlers/` **and** update `_CALLBACK_CATEGORY` in `services/analytics_service.py` so the new prefix is categorized.
- **`middlewares/analytics.py`** — the single outer middleware: throttling, analytics recording, exception → admin-alert conversion, and freetext-strike reset on success.
- **`locales/{ru,en,es,uk}.yaml`** — translations consumed via `services.i18n.t("dotted.key", lang, **fmt_kwargs)`. Missing keys return the bracketed key (`[menu.read]`) for visible debugging, never an exception.
- **`models.py`** — all SQLAlchemy models: `User`, `Bookmark`, `PrayerFavorite`, `Feedback`, `FeedbackRelay`, `PlanProgress`, `Donation`, `AIRequest`, `AIConsent`, `ActivityHourly`. `database.py` provides `async_session` (an `async_sessionmaker`) and `Base`.
- **`timeutils.py`** — `utcnow()` helper; use it instead of `datetime.utcnow()` for column defaults.
- **`data/`** — read-only content shipped with the repo:
  - `bibles/<code>.json` — full text per translation (7 files). Loaded into `BibleService._bibles[code]`.
  - `books.yaml` — canonical 66-book metadata; `data["abbrev"]` order defines `_book_order`, the index used to align translations. **All Bible JSONs must use the same book order as `books.yaml`.**
  - `plans/*.yaml` — reading plans (id, names per lang, day → readings).
  - `topics.yaml` — themed verse collections.
  - `prayers_of_day.yaml`, `verses_of_day.yaml`, `wisdom_of_day.yaml` — daily-rotation content.
- **`scripts/`** — ad-hoc one-shot scripts. `scripts/archive/` holds retired migration scripts kept for history; don't run them.

### Migrations

There's no Alembic. Two paths:
- **New tables / new columns with safe defaults on a fresh DB** — just add to `models.py`; `init_db()` picks them up on next start. `create_all` never alters existing tables, so existing rows get the SQLAlchemy-level default when read.
- **Backfilling defaults onto existing rows or other one-shot SQL** — add a block to `run_migrations()` in `database.py`. The key (e.g. `"2026-06_notification_defaults"`) is written to `migrations_applied.txt` (sibling of `bot.db`) once executed, so the next start skips it. Pick stable, dated keys; never edit or remove a past block (delete the sentinel line instead if you really need a replay).

### SQLite tuning

`database.py` installs a `connect` listener that runs on every new connection:
- `journal_mode=WAL` — readers don't block the writer; required because the scheduler flush, streak/counter writes, AI requests, and handlers all write concurrently.
- `busy_timeout=5000` — wait up to 5s for a contested write instead of erroring with "database is locked".
- `synchronous=NORMAL` — WAL-safe and significantly faster than `FULL`.

### Key cross-cutting patterns

**Bible data model.** `BibleService` keeps every translation as `list[Book]` where `Book.chapters = list[list[str]]` (chapters → verses). Books are aligned across translations purely by **list index**, mapped to abbreviations through `_book_order` from `books.yaml`. Never look up by name across translations; always go via `abbrev` → `get_book_index`.

**Verse of the day.** `BibleService.get_verse_of_day()` seeds `random.Random` with `date.toordinal()` so every user on the same translation sees the same verse for a given UTC date. Do not introduce per-user randomness here.

**Per-user timezones.** `User.timezone` holds an IANA zone (default from `DEFAULT_TZ`). All "what time is it for this user?" logic flows through `services/timezones.py` — `local_hhmm(tz)`, `local_today(tz)`, `local_now(tz)`. The scheduler matches `User.notification_time` against the user's *local* HH:MM, **not** server time, by iterating distinct zones and matching per-zone in SQL (keeps the query bounded). When adding new daily/scheduled features, always compare against `local_hhmm(user.timezone)`, never `datetime.now()`.

**Reading counter (`services/counter_service.py`).** Cumulative "days with the Word" — **only grows, never resets, no freezes**. Call `CounterService.touch(tg_id)` from any handler that should count as "engagement" (reading a chapter, opening verse of day, completing a plan day). It returns a `CounterResult` (`is_first_time`, `same_day`, `streak_grew`, `milestone_reached`, `already_explained`). The caller renders any UI through `services/counter_display.py` — `format_counter_indicator()` for the inline header, `build_counter_extra()` for the optional follow-up message (onboarding card on first day, milestone card with donate prompt, or a dismissible growth message). After showing onboarding the caller must call `CounterService.mark_explained(tg_id)` so it isn't shown again. The scheduler calls `touch()` when delivering the daily verse.

> Historical note: the `User.longest_streak`, `freezes_available`, and `streak_explained` columns date from the old Duolingo-style streak (with burns and freezes). That model was removed; the columns remain only because we don't drop columns from SQLite. `streak_explained` is still actively used as the onboarding-shown flag. The others are dead — see comments in `models.py`.

**Prayer counter (`services/prayer_counter_service.py`).** Independent counter (`User.current_prayer_streak`, `last_prayer_date`) that grows only when the user taps "Аминь" on the daily prayer card. Same "only-grows" semantics as the reading counter; no separate onboarding flag because `pray:amen` is the single touch site. Do not conflate with the reading counter.

**Scheduler (`services/scheduler.py`).** Single APScheduler cron job runs `send_daily_verses()` every minute and dispatches, in order: (1) verse of the day to `User.notifications_enabled` users at their local `notification_time`, (2) reading-plan pushes for active `PlanProgress` rows at their local `notification_time` (with a soft "we miss you" nudge after `_PLAN_NUDGE_AFTER_DAYS` idle days), (3) prayer-of-the-day to users with `prayer_notifications_enabled` (default **on** at 10:00) at their local `prayer_notification_time`, (4) `AnalyticsService.flush()` (persists the current hour's aggregate row), (5) RAM/disk health-check, (6) if server-local HH:MM matches `REPORT_TIME`: daily activity report (and monthly on `MONTHLY_REPORT_DAY`, and `activity_hourly` cleanup on `CLEANUP_DAY`, plus AI-request retention purge). Per-user failures are caught and logged so one bad chat never blocks the batch; only `TelegramNetworkError` / `TelegramServerError` / `TelegramRetryAfter` trigger admin alerts (user-blocked-bot is normal and silent).

**Analytics (`services/analytics_service.py` + `models.ActivityHourly`).** Hourly aggregates only — no per-event rows. Counters accumulate in class-level memory and are upserted into the row for the current hour each minute by `flush()`. Throttling state (`THROTTLE_MAX_EVENTS` per `THROTTLE_WINDOW_SEC`) is also in-memory; throttled callbacks get a `⏳` answer and the handler is never invoked. Categories come from callback-data prefix via `_CALLBACK_CATEGORY` — **if you add a new callback prefix, register it there** or it will be bucketed as `other`. Current prefixes include `read`, `verse_of_day`, `random`, `search`, `ai_pastor`, `plan`, `bm`/`bookmarks`, `pray`/`pray_notif`/`pf`, `topic`/`topics`, `donate`, `fb`, `notif`/`settings`/`setlang`/`changelang`/`changetrans`, `counter`, `cabinet`/`open_menu`/`menu`/`faq`. Times are server-local because the report is an ops view in one zone.

**Admin alerts (`services/alert_service.py`).** `AlertService.alert_error(key, title, detail)` DMs every admin in `ADMIN_IDS`. Identical `key`s are deduped to one message per `ALERT_COOLDOWN_SEC` so crash loops don't flood. The middleware uses `handler_error:<category>` as its key; the scheduler uses `telegram_infra:<ExceptionClass>` and `health_mem` / `health_disk`. Pick stable, low-cardinality keys when adding new alert sites.

**AI Pastor (`services/ai_pastor_service.py`).** Uses `google-genai` with model `gemini-2.5-flash`. Hard daily limit `DAILY_LIMIT = 3` per user (enforced via `AIRequest` row count for the calendar day). User must accept terms once (`AIConsent` row) before the first request. The system prompt instructs the model to append `[CRISIS]` or `[NORMAL]` on its own line; `send_request()` parses and strips this marker before returning `(text, is_crisis)`. Network/5xx errors retry up to 3× with exponential backoff; permanent 4xx returns a localized fallback string immediately. Session context = last 3 request/response pairs from today, sent as Gemini `Content` history. `AIPastorService.cleanup_old_requests()` runs daily from the scheduler to purge texts older than `AI_REQUEST_RETENTION_DAYS` (privacy).

**Donations.** Telegram Stars flow lives in `handlers/donate.py` and `services/donate_service.py`. `PreCheckoutQuery` must always be answered with `ok=True` for Stars to clear; successful payments insert a `Donation` row and notify `ADMIN_IDS`. The donate screen shows all methods directly — no region-selection step. `donate_main_keyboard(lang, in_spain)` gates each button: **Monobank** for uk/ru UI users, **Bizum** for users in a Spanish timezone (`SPAIN_ZONES` = Madrid/Canary, defined in `handlers/donate.py`), **Revolut/PayPal/Crypto** for everyone. Every external-URL button is additionally gated on its env var being non-empty — see `keyboards/donate.py`. Donation links/card/phone live only in `.env`; `config.py` defaults to empty so no secrets are committed.

**Feedback / FAQ / "Ask the author".** Four feedback kinds in `services/feedback_service.py`: `idea`, `bug`, `review`, `question`. The first three flow from cabinet → FSM → `Feedback` row + group/admin notification. `question` is the "ask the author" entry inside the FAQ rubric (`faq:menu` → `faq:ask` → FSM), routed to the `question` feedback group if set, otherwise to the `idea` group, otherwise to `ADMIN_IDS` DMs. The `FeedbackRelay` table maps the bot's notification message (in either a feedback group **or** an admin's DM) back to the user's tg_id, so when an admin replies (reply-to-message) to it, the bot DMs the reply to the original user. The persistent reply-keyboard button "FAQ" opens the inline question list; question answers come from `faq.a.<id>` translation keys.

**Notifications hub.** `handlers/notifications.py` + `keyboards/notifications.py` consolidate three independent toggles into one screen (`notif:hub`): verse-of-day, prayer-of-day, and the active reading plan. Each routes to its own time-picker / toggle. When adding a new daily push, surface it here so users don't have to dig.

**Freetext catch-all (`handlers/freetext.py`).** Anything that escapes every other router lands here. A per-user in-memory strike counter (`_strikes`) escalates the reply across four steps: hint → stronger hint → "use feedback?" → main menu, then resets. `AnalyticsMiddleware` and `reply_menu` call `reset_strikes(tg_id)` whenever the user does something structured, so the escalation only fires for genuine streaks of free-text messages.

**Share links.** Decorative `t.me/share/url` buttons depend on the bot's username. `services/bot_meta.get_bot_username(bot)` caches it per-process and **never raises** — on network failure it returns `None` and callers simply omit the share line. `bot_meta.prewarm(bot)` runs at startup to warm the cache. `services/share.build_share_url(text, link_url)` constructs the URL with `quote` (not `quote_plus`) so spaces become `%20` and literal `+` survives intact.

**i18n contract.** All user-facing strings go through `t()`. The 4 locale files must stay in sync — if you add a key in `ru.yaml`, add it to `en.yaml`, `es.yaml`, `uk.yaml` too, or users on other languages will see `[key.path]`. Format placeholders use Python `str.format` syntax (`{name}`, `{count}`). `DEFAULT_LANG` is `uk`.

**User language vs translation.** `User.lang` is the **UI** language (one of 4); `User.translation` is the **Bible** translation code (one of 7, e.g. `ru_synodal`). These are independent — a Ukrainian-UI user may read the KJV. `BibleService.get_translation_for_lang()` picks a sensible default when first creating a user.

"""Раздел «Помолиться»: карточка «Молитва на сегодня» + кнопка «Аминь»."""
import html
import urllib.parse
from datetime import date

from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.bot_meta import get_bot_username
from services.prayer_service import PrayerService
from services.prayer_streak_service import (
    PrayerStreakService,
    PrayerStreakResult,
)
from services.streak_display import (
    format_prayer_streak_indicator,
    get_prayer_milestone_message,
    get_prayer_daily_progress_message,
    build_dismiss_keyboard,
    build_milestone_keyboard,
    with_donate_addendum,
)
from services.timezones import local_today
from services.i18n import t, t_list
from keyboards.pray import (
    pray_keyboard,
    pray_after_amen_keyboard,
    pray_stub_keyboard,
)

router = Router()


def _format_date(d: date, lang: str) -> str:
    """Форматирует дату как «26 мая» / «May 26» / «26 may» / «26 тра»."""
    months = t_list("pray.months.short", lang)
    if not months or len(months) < 12:
        return d.isoformat()
    month = months[d.month - 1]
    if lang == "en":
        return f"{month} {d.day}"
    return f"{d.day} {month}"


def _build_share_url(prayer: dict, lang: str, bot_username: str) -> str:
    """t.me/share/url с plain-text молитвой."""
    lines = [
        t("pray.share_header", lang),
        "",
        prayer["title"],
        "",
        f"«{prayer['text']}»",
    ]
    ref = prayer.get("ref")
    if ref:
        lines.append("")
        lines.append(f"— {ref['book']} {ref['chapter']}:{ref['verse']}")
    lines.append("")
    lines.append(t("pray.share_footer", lang))
    share_text = "\n".join(lines)

    bot_url = f"https://t.me/{bot_username}"
    params = urllib.parse.urlencode({"url": bot_url, "text": share_text})
    return f"https://t.me/share/url?{params}"


def _share_link_html(prayer: dict, lang: str, bot_username: str | None) -> str | None:
    """HTML-анкор «📤 Поделиться» — встраивается в текст сообщения.

    None, если username бота недоступен (сетевой сбой) — тогда ссылка просто
    не добавляется, а карточка молитвы показывается без неё."""
    if not bot_username:
        return None
    url = _build_share_url(prayer, lang, bot_username)
    href = html.escape(url, quote=True)
    return f'<a href="{href}">{t("pray.share_link", lang)}</a>'


def _prayer_card_block(prayer: dict, lang: str) -> list[str]:
    """Сама карточка молитвы (<blockquote> с заголовком, текстом и стихом).

    Возвращает список строк — вызывающий склеит их с собственным заголовком.
    """
    date_str = _format_date(date.today(), lang)
    header = t("pray.card_title", lang, date=date_str)

    parts = [
        f"<blockquote><b>{header}</b>",
        "",
        f"<b>{prayer['title']}</b>",
        f"<i>«{prayer['text']}»</i>",
    ]

    ref = prayer.get("ref")
    if ref:
        parts.append("")
        parts.append(t(
            "pray.verse_line",
            lang,
            book=ref["book"],
            chapter=ref["chapter"],
            verse=ref["verse"],
            verse_text=ref["text"],
        ))
    parts.append("</blockquote>")
    return parts


def _build_card_text(prayer: dict, lang: str, bot_username: str) -> str:
    """Карточка «Молитва на сегодня» с заголовком раздела и share-ссылкой."""
    parts = [t("pray.title", lang), ""]
    parts.extend(_prayer_card_block(prayer, lang))
    share = _share_link_html(prayer, lang, bot_username)
    if share:
        parts.append("")
        parts.append(share)
    return "\n".join(parts)


def _build_after_amen_text(
    prayer: dict,
    lang: str,
    streak_result: PrayerStreakResult,
    bot_username: str,
) -> str:
    """Экран после «Аминь»: благодарность + стрик + та же карточка + share.

    Onboarding и милстоуны идут отдельными сообщениями (см. _send_prayer_extras),
    чтобы не дублировать их в основной карточке.
    """
    parts = [t("pray.amen_title", lang)]

    streak_line = format_prayer_streak_indicator(streak_result.current_streak, lang)
    if streak_line:
        parts.append(streak_line)

    parts.append("")
    parts.extend(_prayer_card_block(prayer, lang))
    share = _share_link_html(prayer, lang, bot_username)
    if share:
        parts.append("")
        parts.append(share)
    return "\n".join(parts)


async def _send_prayer_extras(message, streak_result: PrayerStreakResult, lang: str) -> None:
    """Отдельные сообщения после «Аминь»: onboarding, милстоуны, daily-progress.

    Зеркало handlers.verse._send_streak_extras, но для молитвенного стрика.
    Поскольку у нас нет prayer_streak_explained-флага, онбординг показывается
    при каждом is_first_time (т.е. и при сбросе стрика).
    """
    if streak_result.is_first_time:
        await message.answer(
            t("pray.streak.onboarding", lang),
            reply_markup=build_dismiss_keyboard(
                lang, dismiss_key="pray.streak.onboarding_button"
            ),
        )
        return

    if streak_result.milestone_reached:
        msg = get_prayer_milestone_message(streak_result.milestone_reached, lang)
        if msg:
            await message.answer(
                with_donate_addendum(msg, lang),
                reply_markup=build_milestone_keyboard(
                    lang, dismiss_key="pray.streak.onboarding_button"
                ),
            )
        return

    if streak_result.streak_grew:
        await message.answer(
            get_prayer_daily_progress_message(streak_result.current_streak, lang),
            reply_markup=build_dismiss_keyboard(
                lang, dismiss_key="pray.streak.onboarding_button"
            ),
        )


@router.callback_query(F.data == "pray")
async def show_pray(callback: CallbackQuery):
    """Карточка «Молитва на сегодня».

    Идемпотентность: если сегодня «Аминь» уже нажат — сразу экран «Бог слышит».
    """
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    prayer = PrayerService.get_prayer_of_day(lang, translation)
    if not prayer:
        await callback.message.edit_text(
            t("pray.empty", lang),
            reply_markup=pray_after_amen_keyboard(lang),
        )
        await callback.answer()
        return

    bot_username = await get_bot_username(callback.bot)

    if user and user.last_prayer_date == local_today(user.timezone):
        # Уже молились сегодня — показываем благодарность с тем же стриком
        streak_result = PrayerStreakService.synthetic_same_day(
            user.current_prayer_streak,
            user.longest_prayer_streak,
        )
        await callback.message.edit_text(
            _build_after_amen_text(prayer, lang, streak_result, bot_username),
            reply_markup=pray_after_amen_keyboard(lang),
            disable_web_page_preview=True,
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        _build_card_text(prayer, lang, bot_username),
        reply_markup=pray_keyboard(lang),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "pray:amen")
async def amen(callback: CallbackQuery):
    """Засчитать «Аминь» в молитвенный стрик и показать благодарность."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    lang = user.lang
    translation = user.translation

    streak_result = await PrayerStreakService.touch(callback.from_user.id)
    prayer = PrayerService.get_prayer_of_day(lang, translation)
    if not prayer:
        await callback.answer()
        return

    bot_username = await get_bot_username(callback.bot)
    await callback.message.edit_text(
        _build_after_amen_text(prayer, lang, streak_result, bot_username),
        reply_markup=pray_after_amen_keyboard(lang),
        disable_web_page_preview=True,
    )
    await callback.answer()

    # Onboarding (первый раз) и милстоуны — отдельными сообщениями ниже карточки
    await _send_prayer_extras(callback.message, streak_result, lang)


@router.callback_query(F.data == "pray:topics")
async def open_prayer_topics(callback: CallbackQuery):
    """«По темам» — заглушка до отдельного PR с пулом молитвенных тем."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("pray.topics_soon", lang),
        reply_markup=pray_stub_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "pray:my")
async def open_my_prayers(callback: CallbackQuery):
    """«Мои молитвы» — заглушка до реализации сохранённых пользовательских молитв."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("pray.my_soon", lang),
        reply_markup=pray_stub_keyboard(lang),
    )
    await callback.answer()

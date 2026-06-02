"""Раздел «Помолиться»: карточка «Молитва на сегодня» + кнопка «Аминь»."""
import html
import urllib.parse
from datetime import date

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from services.user_service import UserService
from services.bot_meta import get_bot_username
from services.prayer_service import PrayerService
from services.prayer_favorite_service import PrayerFavoriteService
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
    pray_random_keyboard,
    pray_stub_keyboard,
    pray_topics_menu_keyboard,
    pray_topic_card_keyboard,
    pray_repentance_keyboard,
    pray_repentance_congrats_keyboard,
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


def _build_share_url(
    prayer: dict, lang: str, bot_username: str, header: str | None = None
) -> str:
    """t.me/share/url с plain-text молитвой.

    header — заголовок шара; по умолчанию «Молитва на сегодня». Случайная и
    сохранённая молитвы передают нейтральный заголовок, чтобы получатель не
    увидел «на сегодня» у не-сегодняшней молитвы.
    """
    lines = [
        header or t("pray.share_header", lang),
        "",
        prayer["title"],
        "",
        f"«{prayer['text']}»",
    ]
    ref = prayer.get("ref")
    if ref:
        lines.append("")
        lines.append(f"«{ref['text']}»")
        lines.append(f"— {ref['book']} {ref['chapter']}:{ref['verse']}")
    lines.append("")
    lines.append(t("pray.share_footer", lang))
    share_text = "\n".join(lines)

    bot_url = f"https://t.me/{bot_username}"
    # quote (а не quote_plus): пробел -> %20, не "+". t.me/share/url декодирует
    # только %xx и оставляет "+" буквально — иначе в части клиентов вылезают плюсы.
    params = urllib.parse.urlencode(
        {"url": bot_url, "text": share_text}, quote_via=urllib.parse.quote
    )
    return f"https://t.me/share/url?{params}"


def _share_link_html(
    prayer: dict, lang: str, bot_username: str | None, header: str | None = None
) -> str | None:
    """HTML-анкор «📤 Поделиться» — встраивается в текст сообщения.

    None, если username бота недоступен (сетевой сбой) — тогда ссылка просто
    не добавляется, а карточка молитвы показывается без неё."""
    if not bot_username:
        return None
    url = _build_share_url(prayer, lang, bot_username, header)
    href = html.escape(url, quote=True)
    return f'<a href="{href}">{t("pray.share_link", lang)}</a>'


def _daily_header(lang: str) -> str:
    """Заголовок карточки «Молитва на сегодня · дата»."""
    date_str = _format_date(date.today(), lang)
    return t("pray.card_title", lang, date=date_str)


def _prayer_card_block(prayer: dict, lang: str, header: str) -> list[str]:
    """Сама карточка молитвы (<blockquote> с заголовком, текстом и стихом).

    Возвращает список строк — вызывающий склеит их с собственным заголовком.
    """
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
    parts = [t("pray.title", lang), "", t("pray.year_headline", lang), ""]
    parts.extend(_prayer_card_block(prayer, lang, _daily_header(lang)))
    share = _share_link_html(prayer, lang, bot_username)
    if share:
        parts.append("")
        parts.append(share)
    parts.append("")
    parts.append(t("pray.repentance.teaser", lang))
    return "\n".join(parts)


def _build_random_text(prayer: dict, lang: str, bot_username: str) -> str:
    """Карточка случайной молитвы с собственным заголовком и share-ссылкой."""
    parts = [t("pray.title", lang), ""]
    parts.extend(_prayer_card_block(prayer, lang, t("pray.random_card_title", lang)))
    share = _share_link_html(
        prayer, lang, bot_username, header=t("pray.share_header_generic", lang)
    )
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
    parts.append(t("pray.year_headline", lang))
    parts.append("")
    parts.extend(_prayer_card_block(prayer, lang, _daily_header(lang)))
    share = _share_link_html(prayer, lang, bot_username)
    if share:
        parts.append("")
        parts.append(share)
    parts.append("")
    parts.append(t("pray.repentance.teaser", lang))
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
            reply_markup=pray_stub_keyboard(lang),
        )
        await callback.answer()
        return

    bot_username = await get_bot_username(callback.bot)
    is_fav = await PrayerFavoriteService.is_favorite(callback.from_user.id, prayer["id"])

    if user and user.last_prayer_date == local_today(user.timezone):
        # Уже молились сегодня — показываем благодарность с тем же стриком
        streak_result = PrayerStreakService.synthetic_same_day(
            user.current_prayer_streak,
            user.longest_prayer_streak,
        )
        await callback.message.edit_text(
            _build_after_amen_text(prayer, lang, streak_result, bot_username),
            reply_markup=pray_after_amen_keyboard(lang, prayer["id"], is_fav),
            disable_web_page_preview=True,
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        _build_card_text(prayer, lang, bot_username),
        reply_markup=pray_keyboard(lang, prayer["id"], is_fav),
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
    is_fav = await PrayerFavoriteService.is_favorite(callback.from_user.id, prayer["id"])
    await callback.message.edit_text(
        _build_after_amen_text(prayer, lang, streak_result, bot_username),
        reply_markup=pray_after_amen_keyboard(lang, prayer["id"], is_fav),
        disable_web_page_preview=True,
    )
    await callback.answer()

    # Onboarding (первый раз) и милстоуны — отдельными сообщениями ниже карточки
    await _send_prayer_extras(callback.message, streak_result, lang)


@router.callback_query(F.data == "pray:repentance")
async def show_repentance_prayer(callback: CallbackQuery):
    """Экран молитвы покаяния (фиксированный текст, без избранного)."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    await callback.message.edit_text(
        t("pray.repentance.card", lang),
        reply_markup=pray_repentance_keyboard(lang),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "pray:repentance:done")
async def repentance_done(callback: CallbackQuery):
    """Поздравительный экран после молитвы покаяния."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    await callback.message.edit_text(
        t("pray.repentance.congrats", lang),
        reply_markup=pray_repentance_congrats_keyboard(lang),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "pray:random")
async def show_random_prayer(callback: CallbackQuery):
    """Случайная молитва из пула — без «Аминь», только просмотр и сохранение."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    prayer = PrayerService.get_random_prayer(lang, translation)
    if not prayer:
        await callback.answer("⚠️", show_alert=True)
        return

    bot_username = await get_bot_username(callback.bot)
    is_fav = await PrayerFavoriteService.is_favorite(callback.from_user.id, prayer["id"])

    await callback.message.edit_text(
        _build_random_text(prayer, lang, bot_username),
        reply_markup=pray_random_keyboard(lang, prayer["id"], is_fav),
        disable_web_page_preview=True,
    )
    await callback.answer()


def _topics_menu_text(lang: str) -> str:
    """Текст меню «По темам»: заголовок и интро (кнопки тем — ниже)."""
    return f'{t("pray.topics_title", lang)}\n\n{t("pray.topics_intro", lang)}'


def _build_topic_text(
    prayer: dict, lang: str, bot_username: str, header: str, show_subtitle: bool
) -> str:
    """Карточка молитвы темы: <blockquote> с заголовком темы, текстом, стихом + share.

    show_subtitle — показывать ли собственный заголовок молитвы (для пул-тем он
    несёт смысл; у фиксированных он совпадает с названием темы, поэтому скрыт).
    """
    parts = [t("pray.title", lang), ""]
    block = [f"<blockquote><b>{header}</b>", ""]
    if show_subtitle and prayer["title"] and prayer["title"] != header:
        block.append(f"<b>{prayer['title']}</b>")
    block.append(f"<i>«{prayer['text']}»</i>")

    ref = prayer.get("ref")
    if ref:
        block.append("")
        block.append(t(
            "pray.verse_line",
            lang,
            book=ref["book"],
            chapter=ref["chapter"],
            verse=ref["verse"],
            verse_text=ref["text"],
        ))
    block.append("</blockquote>")
    parts.extend(block)

    share = _share_link_html(
        prayer, lang, bot_username, header=t("pray.share_header_generic", lang)
    )
    if share:
        parts.append("")
        parts.append(share)
    return "\n".join(parts)


@router.callback_query(F.data == "pray:topics")
async def open_prayer_topics(callback: CallbackQuery):
    """Меню «По темам»: секции с темами молитв по жизненным ситуациям."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    sections = PrayerService.get_sections()
    if not sections:
        await callback.message.edit_text(
            t("pray.empty", lang),
            reply_markup=pray_stub_keyboard(lang),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        _topics_menu_text(lang),
        reply_markup=pray_topics_menu_keyboard(sections, lang),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pray:tp:"))
async def show_topic_prayer(callback: CallbackQuery):
    """Карточка молитвы выбранной темы.

    Формат: pray:tp:<topic_id> | pray:tp:<topic_id>:r[:<current_id>] — другая молитва
    (для пул-тем), current_id исключается из выборки, чтобы «Другая» давала иную.
    """
    parts = callback.data.split(":")
    topic_id = parts[2]
    random_pick = len(parts) > 3 and parts[3] == "r"
    exclude_id = parts[4] if len(parts) > 4 else None
    await render_topic_prayer(
        callback, topic_id, random_pick=random_pick, exclude_id=exclude_id
    )


async def render_topic_prayer(
    callback: CallbackQuery,
    topic_id: str,
    *,
    random_pick: bool = False,
    exclude_id: str | None = None,
) -> None:
    """Отрисовать карточку молитвы темы. Общий код для хендлера и перерисовки избранного."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    topic = PrayerService.get_topic(topic_id)
    if not topic:
        await callback.answer("⚠️", show_alert=True)
        return

    prayer = PrayerService.get_topic_prayer(
        topic_id, lang, translation, random_pick=random_pick, exclude_id=exclude_id
    )
    if not prayer:
        await callback.answer("⚠️", show_alert=True)
        return

    is_pool = PrayerService.is_pool_topic(topic_id)
    name = (topic.get("names") or {}).get(lang) or (topic.get("names") or {}).get("en", "")
    header = f"{topic.get('emoji', '')} {name}".strip()

    bot_username = await get_bot_username(callback.bot)
    is_fav = await PrayerFavoriteService.is_favorite(callback.from_user.id, prayer["id"])

    try:
        await callback.message.edit_text(
            _build_topic_text(prayer, lang, bot_username, header, show_subtitle=is_pool),
            reply_markup=pray_topic_card_keyboard(
                lang, topic_id, prayer["id"], is_fav, is_pool=is_pool
            ),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as e:
        # Если выпала та же молитва — контент идентичен, Telegram отклоняет правку. Не ошибка.
        if "message is not modified" not in str(e):
            raise
    await callback.answer()

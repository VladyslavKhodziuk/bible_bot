"""Сборка текста главного меню: приветствие + карточка стиха дня + streak."""
import html
import urllib.parse
from datetime import date

from models import User
from services.bible_service import BibleService
from services.i18n import t, _load_lang
from services.streak_display import format_streak_indicator


_bot_username: str | None = None


async def _get_bot_username(bot) -> str:
    """Username бота (кэшируется на процесс) — нужен для t.me/share-ссылки."""
    global _bot_username
    if _bot_username is None:
        me = await bot.get_me()
        _bot_username = me.username
    return _bot_username


def _build_share_url(verse: dict, reference: str, lang: str, bot_username: str) -> str:
    """Готовая t.me/share/url-ссылка с plain-text стихом (HTML не сохраняется)."""
    share_text = "\n".join([
        t("menu.share_header", lang),
        "",
        f"«{verse['text']}»",
        f"— {reference}",
        "",
        t("verse.share_footer", lang),
    ])
    bot_url = f"https://t.me/{bot_username}"
    params = urllib.parse.urlencode({"url": bot_url, "text": share_text})
    return f"https://t.me/share/url?{params}"


def _format_today(lang: str) -> str:
    """Локализованная дата формата '21 мая' / 'May 21' / etc."""
    today = date.today()
    data = _load_lang(lang).get("menu", {})
    months = data.get("months")
    if not isinstance(months, list) or len(months) != 12:
        return today.strftime("%d.%m")
    month_name = months[today.month - 1]
    fmt = data.get("date_format", "{day} {month}")
    return fmt.format(day=today.day, month=month_name)


async def build_menu_text(user: User | None, lang: str, bot=None) -> str:
    """
    Текст главного меню: приветствие + подзаголовок + карточка стиха дня + streak.

    Если передан ``bot`` — под карточкой добавляется текстовая ссылка
    «Поделиться» (deep-link t.me/share/url с текущим стихом дня).
    """
    greeting = t("menu.greeting", lang)
    subtitle = t("menu.subtitle", lang)

    translation = user.translation if user else "ru_synodal"
    verse = BibleService.get_verse_of_day(translation)

    parts = [f"<b>{greeting}</b>", f"<i>{subtitle}</i>"]

    share_link: str | None = None
    if verse:
        book_name = BibleService.get_book_name(verse["abbrev"], lang)
        date_str = _format_today(lang)
        card_title = t("menu.verse_card_title", lang, date=date_str)
        reference = f"{book_name} {verse['chapter']}:{verse['verse']}"
        card = (
            f"<blockquote><b>{card_title}</b>\n"
            f"«{verse['text']}»\n"
            f"<i>{reference}</i></blockquote>"
        )
        parts.append("")
        parts.append(card)

        if bot is not None:
            share_url = _build_share_url(
                verse, reference, lang, await _get_bot_username(bot)
            )
            share_href = html.escape(share_url, quote=True)
            share_link = f'<a href="{share_href}">{t("menu.share_verse", lang)}</a>'

    if user is not None:
        streak_line = format_streak_indicator(user.current_streak, lang)
        if streak_line:
            parts.append("")
            parts.append(streak_line)

    if share_link:
        parts.append("")
        parts.append(share_link)

    return "\n".join(parts)

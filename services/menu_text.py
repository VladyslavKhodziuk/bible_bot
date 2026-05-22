"""Сборка текста главного меню: приветствие + карточка стиха дня + streak."""
from datetime import date

from models import User
from services.bible_service import BibleService
from services.i18n import t, _load_lang
from services.streak_display import format_streak_indicator


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


def build_menu_text(user: User | None, lang: str) -> str:
    """
    Текст главного меню: приветствие + подзаголовок + карточка стиха дня + streak.
    """
    greeting = t("menu.greeting", lang)
    subtitle = t("menu.subtitle", lang)

    translation = user.translation if user else "ru_synodal"
    verse = BibleService.get_verse_of_day(translation)

    parts = [f"<b>{greeting}</b>", f"<i>{subtitle}</i>"]

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

    if user is not None:
        streak_line = format_streak_indicator(user.current_streak, lang)
        if streak_line:
            parts.append("")
            parts.append(streak_line)

    return "\n".join(parts)

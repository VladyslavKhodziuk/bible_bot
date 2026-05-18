from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.bible_service import BibleService
from models import Bookmark

BOOKMARKS_PER_PAGE = 5


def bookmarks_list_keyboard(
        bookmarks: list[Bookmark],
        page: int,
        total: int,
        lang: str,
) -> InlineKeyboardMarkup:
    """Клавиатура списка закладок с пагинацией.

    Работает и для пустого списка — кнопки возврата всегда добавляются.
    """
    builder = InlineKeyboardBuilder()
    rows = []

    # Кнопки самих закладок (по одной в ряд)
    for bm in bookmarks:
        book_name = BibleService.get_book_name(bm.abbrev, lang)
        label = f"📖 {book_name} {bm.chapter}:{bm.verse}"
        builder.button(text=label, callback_data=f"bm:view:{bm.id}")
        rows.append(1)

    # Пагинация — только если есть закладки и больше одной страницы
    if total > 0:
        total_pages = (total + BOOKMARKS_PER_PAGE - 1) // BOOKMARKS_PER_PAGE
        nav_count = 0
        if page > 0:
            builder.button(text="◀️", callback_data=f"bm:list:{page - 1}")
            nav_count += 1
        if total_pages > 1:
            builder.button(text=f"{page + 1}/{total_pages}", callback_data="noop")
            nav_count += 1
        if page < total_pages - 1:
            builder.button(text="▶️", callback_data=f"bm:list:{page + 1}")
            nav_count += 1
        if nav_count > 0:
            rows.append(nav_count)

    # Возврат — всегда. И когда список пустой, и когда полный.
    builder.button(
        text=t("cabinet.back_to_cabinet", lang),
        callback_data="cabinet"
    )
    rows.append(1)

    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    rows.append(1)

    builder.adjust(*rows)
    return builder.as_markup()


def bookmark_view_keyboard(
    bookmark: Bookmark,
    lang: str,
) -> InlineKeyboardMarkup:
    """Просмотр одной закладки: открыть главу или удалить."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("bookmarks.open_chapter", lang),
        callback_data=f"read:ch:{bookmark.abbrev}:{bookmark.chapter}"
    )
    builder.button(
        text=t("bookmarks.delete", lang),
        callback_data=f"bm:del:{bookmark.id}"
    )
    builder.button(
        text="← " + t("bookmarks.title", lang).split("\n")[0].replace("<b>", "").replace("</b>", "").lstrip("⭐ "),
        callback_data="bm:list:0"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()


def bookmark_toggle_button(
    abbrev: str,
    chapter: int,
    verse: int,
    is_bookmarked: bool,
    lang: str,
    return_to: str,
) -> tuple[str, str]:
    """
    Возвращает (текст кнопки, callback_data) для тоггла закладки.
    return_to — куда возвращаться после действия (например, 'vod' для стиха дня, 'rnd' для рандома).
    """
    if is_bookmarked:
        text = t("bookmarks.remove_button", lang)
        action = "rm"
    else:
        text = t("bookmarks.add_button", lang)
        action = "add"
    return text, f"bm:{action}:{abbrev}:{chapter}:{verse}:{return_to}"
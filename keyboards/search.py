from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.bible_service import BibleService

# Сколько результатов на странице
RESULTS_PER_PAGE = 5


def cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены поиска."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("search.cancel", lang),
        callback_data="search:cancel"
    )
    return builder.as_markup()


def wrong_alphabet_keyboard(lang: str) -> InlineKeyboardMarkup:
    """После предупреждения о несоответствии алфавита."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("search.try_anyway", lang),
        callback_data="search:force"
    )
    builder.button(
        text=t("search.cancel", lang),
        callback_data="search:cancel"
    )
    builder.adjust(1)
    return builder.as_markup()


def no_results_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Когда ничего не найдено."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("search.new_search", lang),
        callback_data="search"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()


def scope_keyboard(counts: dict, lang: str) -> InlineKeyboardMarkup:
    """
    Экран выбора раздела поиска.
    counts: {"all": N, "ot": N, "nt": N}
    Кнопки с 0 результатов — не показываем.
    """
    builder = InlineKeyboardBuilder()
    layout = []

    # Кнопка "Вся Библия" — всегда (если total > 0, иначе сюда не попадаем)
    builder.button(
        text=t("search.scope_all", lang, count=counts["all"]),
        callback_data="search:scope:all"
    )
    layout.append(1)

    # ВЗ — только если что-то найдено
    if counts["ot"] > 0:
        builder.button(
            text=t("search.scope_ot", lang, count=counts["ot"]),
            callback_data="search:scope:ot"
        )
        layout.append(1)

    # НЗ — только если что-то найдено
    if counts["nt"] > 0:
        builder.button(
            text=t("search.scope_nt", lang, count=counts["nt"]),
            callback_data="search:scope:nt"
        )
        layout.append(1)

    # Действия
    builder.button(
        text=t("search.new_search", lang),
        callback_data="search"
    )
    layout.append(1)
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    layout.append(1)

    builder.adjust(*layout)
    return builder.as_markup()


def results_keyboard(
    filtered_results: list[dict],
    page: int,
    lang: str,
) -> InlineKeyboardMarkup:
    """
    Клавиатура результатов: только ссылки на стихи + пагинация + действия.
    Без табов (выбор раздела уже сделан на предыдущем экране).
    """
    builder = InlineKeyboardBuilder()
    layout = []

    # Кнопки-ссылки на стихи (только текущая страница)
    start = page * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    page_results = filtered_results[start:end]

    for i, v in enumerate(page_results):
        book_name = BibleService.get_book_name(v["abbrev"], lang)
        global_idx = start + i
        builder.button(
            text=f"📖 {book_name} {v['chapter']}:{v['verse']}",
            callback_data=f"search:open:{global_idx}"
        )
        layout.append(1)

    # Пагинация
    total = len(filtered_results)
    total_pages = max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
    nav_count = 0
    if page > 0:
        builder.button(text="◀️", callback_data=f"search:page:{page - 1}")
        nav_count += 1
    if total_pages > 1:
        builder.button(text=f"{page + 1}/{total_pages}", callback_data="noop")
        nav_count += 1
    if page < total_pages - 1:
        builder.button(text="▶️", callback_data=f"search:page:{page + 1}")
        nav_count += 1
    if nav_count:
        layout.append(nav_count)

    # Действия
    builder.button(
        text=t("search.change_scope", lang),
        callback_data="search:back_to_scope"
    )
    layout.append(1)
    builder.button(
        text=t("search.new_search", lang),
        callback_data="search"
    )
    layout.append(1)
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    layout.append(1)

    builder.adjust(*layout)
    return builder.as_markup()


def detail_keyboard(
    verse_idx: int,
    abbrev: str,
    chapter: int,
    is_bookmarked: bool,
    lang: str,
) -> InlineKeyboardMarkup:
    """Клавиатура детального экрана стиха."""
    builder = InlineKeyboardBuilder()

    if is_bookmarked:
        builder.button(
            text=t("bookmarks.remove_button", lang),
            callback_data=f"search:bm:{verse_idx}"
        )
    else:
        builder.button(
            text=t("bookmarks.add_button", lang),
            callback_data=f"search:bm:{verse_idx}"
        )

    builder.button(
        text=t("verse.open_chapter", lang),
        callback_data=f"read:ch:{abbrev}:{chapter}"
    )

    builder.button(
        text=t("search.back_to_results", lang),
        callback_data="search:back_to_results"
    )

    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )

    builder.adjust(1)
    return builder.as_markup()
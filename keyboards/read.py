from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.bible_service import BibleService

# Сколько книг показывать на одной странице (список книг длинный — 39 ВЗ)
BOOKS_PER_PAGE = 12

# Сколько кнопок-глав в одном ряду
CHAPTERS_PER_ROW = 5


def testament_keyboard(lang: str, translation: str) -> InlineKeyboardMarkup:
    """Выбор Ветхий / Новый Завет. Плюс кнопка перевода, если их больше одного."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("read.old_testament", lang), callback_data="read:ot:0")
    builder.button(text=t("read.new_testament", lang), callback_data="read:nt:0")
    layout = [1, 1]

    # Раздел второканонических книг — только если они есть в этом переводе
    if BibleService.translation_has_testament(translation, "dc"):
        builder.button(
            text=t("read.deuterocanonical", lang), callback_data="read:dc:0"
        )
        layout.append(1)

    # Кнопка выбора перевода — только если на языке больше одного перевода
    if len(BibleService.get_translations_for_lang(lang)) > 1:
        translation_name = t(f"settings.translation_names.{translation}", lang)
        builder.button(
            text=t("read.btn_translation", lang, translation=translation_name),
            callback_data="read:trans"
        )
        layout.append(1)

    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    layout.append(1)

    builder.adjust(*layout)
    return builder.as_markup()


def translation_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Выбор перевода Библии из меню чтения — только переводы текущего языка."""
    builder = InlineKeyboardBuilder()
    for code in BibleService.get_translations_for_lang(lang):
        name = t(f"settings.translation_names.{code}", lang)
        builder.button(text=name, callback_data=f"read:settrans:{code}")
    builder.button(text=t("read.back_to_testaments", lang), callback_data="read")
    builder.adjust(1)
    return builder.as_markup()


def books_keyboard(
    testament: str, page: int, lang: str, translation: str
) -> InlineKeyboardMarkup:
    """
    Список книг с пагинацией.
    testament: 'ot', 'nt' или 'dc'
    page: номер страницы с 0
    Показываются только книги, реально присутствующие в переводе.
    """
    builder = InlineKeyboardBuilder()
    books = BibleService.get_books_for_translation(translation, testament)

    start = page * BOOKS_PER_PAGE
    end = start + BOOKS_PER_PAGE
    page_books = books[start:end]

    # Кнопки книг — по 2 в ряд
    for book in page_books:
        name = book.get(lang, book["abbrev"])
        builder.button(text=name, callback_data=f"read:book:{book['abbrev']}:0")

    # Раскладка кнопок книг: 2 в ряд
    book_rows = [2] * ((len(page_books) + 1) // 2)

    # Пагинация: ◀️  страница X/Y  ▶️
    total_pages = (len(books) + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE
    nav_count = 0
    if page > 0:
        builder.button(text="◀️", callback_data=f"read:{testament}:{page - 1}")
        nav_count += 1
    if total_pages > 1:
        builder.button(
            text=t("read.page_indicator", lang, current=page + 1, total=total_pages),
            callback_data="noop"
        )
        nav_count += 1
    if page < total_pages - 1:
        builder.button(text="▶️", callback_data=f"read:{testament}:{page + 1}")
        nav_count += 1

    # Кнопка "Назад к разделам"
    builder.button(text=t("read.back_to_testaments", lang), callback_data="read:start")

    # Финальная раскладка: книги попарно, потом ряд с навигацией, потом "Назад"
    layout = book_rows
    if nav_count > 0:
        layout.append(nav_count)
    layout.append(1)
    builder.adjust(*layout)

    return builder.as_markup()


def chapters_keyboard(abbrev: str, translation: str, lang: str) -> InlineKeyboardMarkup:
    """Сетка глав книги."""
    builder = InlineKeyboardBuilder()

    total = BibleService.get_chapters_count(abbrev, translation)
    for ch in range(1, total + 1):
        builder.button(text=str(ch), callback_data=f"read:ch:{abbrev}:{ch}")

    # Кнопка возврата
    # Сначала вернёмся к списку книг того же завета
    book = BibleService._books_meta.get(abbrev, {})
    testament = book.get("testament", "ot")
    builder.button(
        text=t("read.back_to_books", lang),
        callback_data=f"read:{testament}:0"
    )

    # Раскладка: главы по CHAPTERS_PER_ROW в ряд, потом "Назад" отдельно
    rows = [CHAPTERS_PER_ROW] * (total // CHAPTERS_PER_ROW)
    remainder = total % CHAPTERS_PER_ROW
    if remainder:
        rows.append(remainder)
    rows.append(1)  # кнопка "Назад"
    builder.adjust(*rows)

    return builder.as_markup()


def chapter_view_keyboard(
    abbrev: str,
    chapter: int,
    translation: str,
    lang: str,
    page: int = 1,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """Клавиатура под текстом главы: навигация по страницам, главам, действия."""
    builder = InlineKeyboardBuilder()

    total_chapters = BibleService.get_chapters_count(abbrev, translation)

    # ====== Ряд 1: навигация ВНУТРИ главы (если есть страницы) ======
    page_nav_count = 0
    if total_pages > 1:
        if page > 1:
            builder.button(
                text="⬅️",
                callback_data=f"read:ch:{abbrev}:{chapter}:p{page - 1}"
            )
            page_nav_count += 1

        # Индикатор страницы
        builder.button(
            text=f"{page}/{total_pages}",
            callback_data="noop"
        )
        page_nav_count += 1

        if page < total_pages:
            builder.button(
                text="➡️",
                callback_data=f"read:ch:{abbrev}:{chapter}:p{page + 1}"
            )
            page_nav_count += 1

    # ====== Ряд 2: навигация МЕЖДУ главами ======
    chapter_nav_count = 0
    if chapter > 1:
        builder.button(
            text=f"◀️ {chapter - 1}",
            callback_data=f"read:ch:{abbrev}:{chapter - 1}"
        )
        chapter_nav_count += 1
    if chapter < total_chapters:
        builder.button(
            text=f"{chapter + 1} ▶️",
            callback_data=f"read:ch:{abbrev}:{chapter + 1}"
        )
        chapter_nav_count += 1

    # ====== Ряд 3-4: возврат ======
    builder.button(
        text=t("read.back_to_chapters", lang),
        callback_data=f"read:book:{abbrev}:0"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )

    # Раскладка
    layout = []
    if page_nav_count > 0:
        layout.append(page_nav_count)
    if chapter_nav_count > 0:
        layout.append(chapter_nav_count)
    layout.extend([1, 1])
    builder.adjust(*layout)

    return builder.as_markup()
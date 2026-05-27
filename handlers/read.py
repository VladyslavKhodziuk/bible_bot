from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.bible_service import BibleService
from services.streak_service import StreakService
from services.i18n import t
from keyboards.read import (
    testament_keyboard,
    translation_keyboard,
    books_keyboard,
    chapters_keyboard,
    chapter_view_keyboard,
)

router = Router()

# Максимальная длина сообщения в Telegram — 4096 символов
# Оставим запас на заголовок и форматирование
MAX_MESSAGE_LENGTH = 3800


# ============ Экран 1: Выбор Завета ============

@router.callback_query(F.data == "read")
async def read_start(callback: CallbackQuery):
    """Вход в раздел чтения из главного меню."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    await callback.message.edit_text(
        t("read.choose_testament", lang),
        reply_markup=testament_keyboard(lang, translation)
    )
    await callback.answer()


@router.callback_query(F.data == "read:start")
async def read_back_to_start(callback: CallbackQuery):
    """Возврат к выбору Завета (из списка книг)."""
    await read_start(callback)


# ============ Выбор перевода Библии ============

@router.callback_query(F.data == "read:trans")
async def choose_translation_screen(callback: CallbackQuery):
    """Экран выбора перевода Библии из меню чтения."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("settings.choose_translation", lang),
        reply_markup=translation_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("read:settrans:"))
async def apply_translation(callback: CallbackQuery):
    """Применение выбранного перевода и возврат к выбору Завета."""
    new_translation = callback.data.split(":")[2]
    await UserService.set_translation(callback.from_user.id, new_translation)

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.answer(t("settings.translation_changed", lang), show_alert=True)

    await callback.message.edit_text(
        t("read.choose_testament", lang),
        reply_markup=testament_keyboard(lang, new_translation)
    )


# ============ Экран 2: Список книг ============

@router.callback_query(
    F.data.startswith("read:ot:")
    | F.data.startswith("read:nt:")
    | F.data.startswith("read:dc:")
)
async def show_books(callback: CallbackQuery):
    """Показать список книг с пагинацией.
    Callback: read:ot:0, read:nt:1 или read:dc:0
    """
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    _, testament, page_str = callback.data.split(":")
    page = int(page_str)

    testament_name = {
        "ot": t("read.old_testament", lang),
        "nt": t("read.new_testament", lang),
        "dc": t("read.deuterocanonical", lang),
    }.get(testament, "")

    await callback.message.edit_text(
        t("read.choose_book", lang, testament=testament_name),
        reply_markup=books_keyboard(testament, page, lang, translation)
    )
    await callback.answer()


# ============ Экран 3: Список глав ============

@router.callback_query(F.data.startswith("read:book:"))
async def show_chapters(callback: CallbackQuery):
    """Показать сетку глав книги.
    Callback: read:book:gn:0
    Третий параметр (0) — зарезервирован для пагинации, пока не используется.
    """
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"
    # Засчитываем чтение главы в серию
    streak_result = await StreakService.touch(callback.from_user.id)

    parts = callback.data.split(":")
    abbrev = parts[2]

    book_name = BibleService.get_book_name(abbrev, lang)

    await callback.message.edit_text(
        t("read.choose_chapter", lang, book=book_name),
        reply_markup=chapters_keyboard(abbrev, translation, lang)
    )
    await callback.answer()

    # Дополнительные сообщения (onboarding, милстоуны)
    from handlers.verse import _send_streak_extras
    await _send_streak_extras(callback.message, callback.from_user.id, streak_result, lang)


# ============ Экран 4: Текст главы ============

@router.callback_query(F.data.startswith("read:ch:"))
async def show_chapter(callback: CallbackQuery):
    """Показать текст главы (или её часть, если глава длинная).

    Callbacks:
        read:ch:gn:1       — глава целиком (или первая страница)
        read:ch:gn:1:p2    — конкретная страница (p2 = page 2)
    """
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    parts = callback.data.split(":")
    # parts = ['read', 'ch', 'gn', '1']  или  ['read', 'ch', 'gn', '1', 'p2']
    abbrev = parts[2]
    chapter = int(parts[3])
    page = 1
    if len(parts) >= 5 and parts[4].startswith("p"):
        page = int(parts[4][1:])

    verses = BibleService.get_chapter(abbrev, chapter, translation)
    if not verses:
        await callback.answer("⚠️ Глава не найдена", show_alert=True)
        return

    # Разбиваем главу на страницы
    pages = BibleService.paginate_chapter(verses)
    if page < 1 or page > len(pages):
        page = 1
    start_v, end_v = pages[page - 1]

    # Заголовок: "📖 Бытие 1" + (если есть страницы) "(стихи 1-30)"
    book_name = BibleService.get_book_name(abbrev, lang)
    header = t("read.chapter_header", lang, book=book_name, chapter=chapter)

    if len(pages) > 1:
        header += f"\n<i>{t('read.verses_range', lang, start=start_v, end=end_v)}</i>"

    # Тело: только стихи текущей страницы
    text_body = "\n".join(
        f"<b>{i}.</b> {verses[i - 1]}"
        for i in range(start_v, end_v + 1)
    )

    full_text = f"{header}\n\n{text_body}"

    await callback.message.edit_text(
        full_text,
        reply_markup=chapter_view_keyboard(
            abbrev, chapter, translation, lang,
            page=page, total_pages=len(pages)
        )
    )
    await callback.answer()


# ============ Заглушка для no-op кнопок (индикатор страницы) ============

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    """Кнопка-индикатор страницы — ничего не делает."""
    await callback.answer()
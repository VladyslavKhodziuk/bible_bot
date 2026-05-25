from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select

from database import async_session
from models import Bookmark
from services.user_service import UserService
from services.bookmark_service import BookmarkService
from services.bible_service import BibleService
from services.i18n import t
from keyboards.bookmarks import (
    bookmarks_list_keyboard,
    bookmark_view_keyboard,
    BOOKMARKS_PER_PAGE,
)

router = Router()


# ============ Список закладок ============

@router.callback_query(F.data == "bookmarks")
async def show_bookmarks(callback: CallbackQuery):
    """Открыть список закладок (первая страница)."""
    await _show_bookmarks_page(callback, page=0)


@router.callback_query(F.data.startswith("bm:list:"))
async def show_bookmarks_page(callback: CallbackQuery):
    """Конкретная страница списка."""
    page = int(callback.data.split(":")[2])
    await _show_bookmarks_page(callback, page=page)


async def _show_bookmarks_page(callback: CallbackQuery, page: int):
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    total = await BookmarkService.count_for_user(callback.from_user.id)

    if total == 0:
        await callback.message.edit_text(
            t("bookmarks.empty", lang),
            reply_markup=bookmarks_list_keyboard([], 0, 0, lang)
        )
        await callback.answer()
        return

    bookmarks = await BookmarkService.list_for_user(
        callback.from_user.id,
        limit=BOOKMARKS_PER_PAGE,
        offset=page * BOOKMARKS_PER_PAGE,
    )

    text = t("bookmarks.title", lang, count=total)

    await callback.message.edit_text(
        text,
        reply_markup=bookmarks_list_keyboard(bookmarks, page, total, lang)
    )
    await callback.answer()


# ============ Просмотр одной закладки ============

@router.callback_query(F.data.startswith("bm:view:"))
async def view_bookmark(callback: CallbackQuery):
    """Просмотр одной закладки: текст стиха + кнопки."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    bookmark_id = int(callback.data.split(":")[2])

    async with async_session() as session:
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()

    if not bookmark or bookmark.user_id != callback.from_user.id:
        await callback.answer("⚠️", show_alert=True)
        return

    text = BibleService.get_verse(
        bookmark.abbrev, bookmark.chapter, bookmark.verse, translation
    )
    book_name = BibleService.get_book_name(bookmark.abbrev, lang)

    full_text = (
        f"<b>{book_name} {bookmark.chapter}:{bookmark.verse}</b>\n\n"
        f"<i>{text}</i>"
    )

    await callback.message.edit_text(
        full_text,
        reply_markup=bookmark_view_keyboard(bookmark, lang)
    )
    await callback.answer()


# ============ Удаление закладки ============

@router.callback_query(F.data.startswith("bm:del:"))
async def delete_bookmark(callback: CallbackQuery):
    """Удалить закладку по id."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    bookmark_id = int(callback.data.split(":")[2])

    async with async_session() as session:
        result = await session.execute(
            select(Bookmark).where(Bookmark.id == bookmark_id)
        )
        bookmark = result.scalar_one_or_none()
        if bookmark and bookmark.user_id == callback.from_user.id:
            await session.delete(bookmark)
            await session.commit()

    await callback.answer(t("bookmarks.removed", lang), show_alert=False)
    await _show_bookmarks_page(callback, page=0)


# ============ Добавление и удаление через тоггл (из стихов) ============

@router.callback_query(F.data.startswith("bm:add:"))
async def toggle_add_bookmark(callback: CallbackQuery):
    """Добавить стих в закладки (вызывается с экрана стиха дня / рандома / темы)."""
    # callback: bm:add:abbrev:chapter:verse:return_to
    parts = callback.data.split(":")
    abbrev = parts[2]
    chapter = int(parts[3])
    verse = int(parts[4])
    return_to = parts[5] if len(parts) > 5 else "menu"

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await BookmarkService.add(callback.from_user.id, abbrev, chapter, verse)
    await callback.answer(t("bookmarks.added", lang), show_alert=False)

    # Перерисовываем исходный экран с обновлённой кнопкой
    await _refresh_source_screen(callback, return_to, abbrev, chapter, verse)


@router.callback_query(F.data.startswith("bm:rm:"))
async def toggle_remove_bookmark(callback: CallbackQuery):
    """Убрать стих из закладок (через тоггл-кнопку)."""
    parts = callback.data.split(":")
    abbrev = parts[2]
    chapter = int(parts[3])
    verse = int(parts[4])
    return_to = parts[5] if len(parts) > 5 else "menu"

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await BookmarkService.remove(callback.from_user.id, abbrev, chapter, verse)
    await callback.answer(t("bookmarks.removed", lang), show_alert=False)

    await _refresh_source_screen(callback, return_to, abbrev, chapter, verse)


async def _refresh_source_screen(
    callback: CallbackQuery,
    return_to: str,
    abbrev: str,
    chapter: int,
    verse: int,
):
    """
    После добавления/удаления — перерисовать исходный экран с обновлённой кнопкой.
    return_to: 'vod' — стих дня, 'rnd' — рандом
    """
    # Импорты внутри функции, чтобы избежать циклических зависимостей
    from handlers.verse import show_verse_of_day, show_random_verse, show_wisdom_of_day

    if return_to == "vod":
        # Симулируем повторный вход в "стих дня"
        callback.data = "verse_of_day"
        await show_verse_of_day(callback)
    elif return_to == "wis":
        # Мудрость дня детерминирована по дате — повторный вход покажет тот же стих
        callback.data = "wisdom"
        await show_wisdom_of_day(callback)
    elif return_to == "rnd":
        # Для рандома — просто перерисуем тот же стих, не новый
        # Для этого мы должны передать те же abbrev/chapter/verse
        # Делаем через специальный callback, который покажет именно этот стих
        from services.bible_service import BibleService
        from services.i18n import t as _t
        from keyboards.bookmarks import bookmark_toggle_button
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        user = await UserService.get(callback.from_user.id)
        lang = user.lang if user else "ru"
        translation = user.translation if user else "ru_synodal"

        text_verse = BibleService.get_verse(abbrev, chapter, verse, translation)
        book_name = BibleService.get_book_name(abbrev, lang)
        ref = _t("verse.reference", lang, book=book_name, chapter=chapter, verse=verse)
        text = f"{_t('verse.random_title', lang)}\n\n{ref}\n\n<i>{text_verse}</i>"

        is_bm = await BookmarkService.is_bookmarked(
            callback.from_user.id, abbrev, chapter, verse
        )
        bm_text, bm_cb = bookmark_toggle_button(
            abbrev, chapter, verse, is_bm, lang, "rnd"
        )

        builder = InlineKeyboardBuilder()
        builder.button(text=bm_text, callback_data=bm_cb)
        builder.button(text=_t("verse.another", lang), callback_data="random")
        builder.button(
            text=_t("verse.open_chapter", lang),
            callback_data=f"read:ch:{abbrev}:{chapter}"
        )
        builder.button(
            text=_t("common.back_to_menu", lang),
            callback_data="open_menu"
        )
        builder.adjust(1)

        await callback.message.edit_text(text, reply_markup=builder.as_markup())
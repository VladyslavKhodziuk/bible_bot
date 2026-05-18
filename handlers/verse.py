from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.bible_service import BibleService
from services.bookmark_service import BookmarkService
from services.i18n import t
from keyboards.bookmarks import bookmark_toggle_button

router = Router()


def _format_verse(verse: dict, lang: str) -> str:
    """Форматирует стих с заголовком книги."""
    book_name = BibleService.get_book_name(verse["abbrev"], lang)
    reference = t(
        "verse.reference",
        lang,
        book=book_name,
        chapter=verse["chapter"],
        verse=verse["verse"],
    )
    return f"{reference}\n\n<i>{verse['text']}</i>"


def _build_verse_keyboard(
    abbrev: str,
    chapter: int,
    verse_num: int,
    lang: str,
    is_bookmarked: bool,
    return_to: str,
    show_another: bool = False,
) -> InlineKeyboardMarkup:
    """Клавиатура под стихом (дня или рандомом)."""
    builder = InlineKeyboardBuilder()

    # Кнопка закладки (тоггл)
    bm_text, bm_cb = bookmark_toggle_button(
        abbrev, chapter, verse_num, is_bookmarked, lang, return_to
    )
    builder.button(text=bm_text, callback_data=bm_cb)

    if show_another:
        builder.button(text=t("verse.another", lang), callback_data="random")

    builder.button(
        text=t("verse.open_chapter", lang),
        callback_data=f"read:ch:{abbrev}:{chapter}"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "verse_of_day")
async def show_verse_of_day(callback: CallbackQuery):
    """Стих дня — один на сутки."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    verse = BibleService.get_verse_of_day(translation)
    if not verse:
        await callback.answer("⚠️", show_alert=True)
        return

    is_bm = await BookmarkService.is_bookmarked(
        callback.from_user.id, verse["abbrev"], verse["chapter"], verse["verse"]
    )

    text = f"{t('verse.of_day_title', lang)}\n\n{_format_verse(verse, lang)}"

    await callback.message.edit_text(
        text,
        reply_markup=_build_verse_keyboard(
            verse["abbrev"], verse["chapter"], verse["verse"],
            lang, is_bm, return_to="vod", show_another=False,
        )
    )
    await callback.answer()


@router.callback_query(F.data == "random")
async def show_random_verse(callback: CallbackQuery):
    """Случайный стих — каждый клик новый."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    verse = BibleService.get_random_verse(translation)
    if not verse:
        await callback.answer("⚠️", show_alert=True)
        return

    is_bm = await BookmarkService.is_bookmarked(
        callback.from_user.id, verse["abbrev"], verse["chapter"], verse["verse"]
    )

    text = f"{t('verse.random_title', lang)}\n\n{_format_verse(verse, lang)}"

    await callback.message.edit_text(
        text,
        reply_markup=_build_verse_keyboard(
            verse["abbrev"], verse["chapter"], verse["verse"],
            lang, is_bm, return_to="rnd", show_another=True,
        )
    )
    await callback.answer()
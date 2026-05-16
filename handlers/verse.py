from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.bible_service import BibleService
from services.i18n import t
from keyboards.verse import verse_of_day_keyboard, random_verse_keyboard

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


@router.callback_query(F.data == "verse_of_day")
async def show_verse_of_day(callback: CallbackQuery):
    """Стих дня — один на сутки для всех."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    verse = BibleService.get_verse_of_day(translation)
    if not verse:
        await callback.answer("⚠️", show_alert=True)
        return

    text = f"{t('verse.of_day_title', lang)}\n\n{_format_verse(verse, lang)}"

    await callback.message.edit_text(
        text,
        reply_markup=verse_of_day_keyboard(verse["abbrev"], verse["chapter"], lang)
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

    text = f"{t('verse.random_title', lang)}\n\n{_format_verse(verse, lang)}"

    await callback.message.edit_text(
        text,
        reply_markup=random_verse_keyboard(verse["abbrev"], verse["chapter"], lang)
    )
    await callback.answer()
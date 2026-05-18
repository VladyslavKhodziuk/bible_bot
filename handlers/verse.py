from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.bible_service import BibleService
from services.bookmark_service import BookmarkService
from services.streak_service import StreakService
from services.streak_display import format_streak_indicator, get_milestone_message
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


async def _send_streak_extras(callback, streak_result, lang: str):
    """
    Отправляет дополнительные сообщения после засчитанного дня:
    - Onboarding при первой серии (с кнопкой "Понятно" — закрывает сообщение)
    - Поздравление при милстоуне
    """
    # Onboarding (первый раз серия началась)
    if streak_result.is_first_time:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=t("streak.onboarding_button", lang),
            callback_data="streak:onboarding_done"
        )
        await callback.message.answer(
            t("streak.onboarding", lang),
            reply_markup=builder.as_markup(),
        )
        await StreakService.mark_explained(callback.from_user.id)

    # Поздравление с милстоуном
    if streak_result.milestone_reached:
        msg = get_milestone_message(streak_result.milestone_reached, lang)
        if msg:
            await callback.message.answer(msg)


@router.callback_query(F.data == "verse_of_day")
async def show_verse_of_day(callback: CallbackQuery):
    """Стих дня — один на сутки. Засчитывает день серии."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    verse = BibleService.get_verse_of_day(translation)
    if not verse:
        await callback.answer("⚠️", show_alert=True)
        return

    # Засчитываем день серии
    streak_result = await StreakService.touch(callback.from_user.id)

    is_bm = await BookmarkService.is_bookmarked(
        callback.from_user.id, verse["abbrev"], verse["chapter"], verse["verse"]
    )

    # Формируем текст с индикатором серии
    streak_line = format_streak_indicator(streak_result.current_streak, lang)
    parts = [t("verse.of_day_title", lang)]
    if streak_line:
        parts.append(streak_line)
    parts.append("")
    parts.append(_format_verse(verse, lang))
    text = "\n".join(parts)

    await callback.message.edit_text(
        text,
        reply_markup=_build_verse_keyboard(
            verse["abbrev"], verse["chapter"], verse["verse"],
            lang, is_bm, return_to="vod", show_another=False,
        )
    )
    await callback.answer()

    await _send_streak_extras(callback, streak_result, lang)


@router.callback_query(F.data == "random")
async def show_random_verse(callback: CallbackQuery):
    """Случайный стих — каждый клик новый. Засчитывает день серии."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    verse = BibleService.get_random_verse(translation)
    if not verse:
        await callback.answer("⚠️", show_alert=True)
        return

    streak_result = await StreakService.touch(callback.from_user.id)

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

    await _send_streak_extras(callback, streak_result, lang)


@router.callback_query(F.data == "streak:onboarding_done")
async def close_streak_onboarding(callback: CallbackQuery):
    """Закрыть онбординг про серии — удаляем сообщение."""
    try:
        await callback.message.delete()
    except Exception:
        # Если сообщение уже удалено или слишком старое — молча игнорируем
        pass
    await callback.answer()
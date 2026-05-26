import re
import urllib.parse

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

# Username бота кэшируется после первого get_me() — нужен для ссылки в шаринге.
_bot_username: str | None = None


async def _get_bot_username(bot) -> str:
    global _bot_username
    if _bot_username is None:
        me = await bot.get_me()
        _bot_username = me.username
    return _bot_username


def _strip_html(s: str) -> str:
    """Убирает HTML-теги — для plain-text заголовка в шаринге."""
    return re.sub(r"<[^>]+>", "", s)


def _build_share_text(
    verse: dict,
    reference: str,
    lang: str,
    header: str,
    reflection: str | None = None,
) -> str:
    """Plain-text карточки для пересылки (t.me/share/url не сохраняет HTML)."""
    lines = [header, "", f"«{verse['text']}»", f"— {reference}"]
    if reflection:
        lines += ["", reflection]
    lines += ["", t("verse.share_footer", lang)]
    return "\n".join(lines)


def _build_share_url(share_text: str, bot_username: str) -> str:
    bot_url = f"https://t.me/{bot_username}"
    params = urllib.parse.urlencode({"url": bot_url, "text": share_text})
    return f"https://t.me/share/url?{params}"


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
    share_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Клавиатура под стихом (дня или рандомом)."""
    builder = InlineKeyboardBuilder()
    rows = []

    bm_text, bm_cb = bookmark_toggle_button(
        abbrev, chapter, verse_num, is_bookmarked, lang, return_to
    )
    builder.button(text=bm_text, callback_data=bm_cb)

    # «Поделиться» — в одном ряду с закладкой
    if share_url:
        builder.button(text=t("verse.share", lang), url=share_url)
        rows.append(2)
    else:
        rows.append(1)

    if show_another:
        builder.button(text=t("verse.another", lang), callback_data="random")
        rows.append(1)

    builder.button(
        text=t("verse.open_chapter", lang),
        callback_data=f"read:ch:{abbrev}:{chapter}"
    )
    rows.append(1)
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


async def _send_streak_extras(message, user_id: int, streak_result, lang: str):
    """
    Отправляет дополнительные сообщения после засчитанного дня:
    - Onboarding при первой серии (с кнопкой "Понятно" — закрывает сообщение)
    - Поздравление при милстоуне

    ``message`` — любой объект с .answer() (Message или CallbackQuery.message).
    """
    # Onboarding (первый раз серия началась)
    if streak_result.is_first_time:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=t("streak.onboarding_button", lang),
            callback_data="streak:onboarding_done"
        )
        await message.answer(
            t("streak.onboarding", lang),
            reply_markup=builder.as_markup(),
        )
        await StreakService.mark_explained(user_id)

    # Поздравление с милстоуном — с кнопкой "Понятно", которая его удаляет
    if streak_result.milestone_reached:
        msg = get_milestone_message(streak_result.milestone_reached, lang)
        if msg:
            builder = InlineKeyboardBuilder()
            builder.button(
                text=t("streak.onboarding_button", lang),
                callback_data="streak:onboarding_done"
            )
            await message.answer(msg, reply_markup=builder.as_markup())


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

    book_name = BibleService.get_book_name(verse["abbrev"], lang)
    reference = f"{book_name} {verse['chapter']}:{verse['verse']}"
    share_text = _build_share_text(
        verse, reference, lang, _strip_html(t("verse.of_day_title", lang))
    )
    share_url = _build_share_url(
        share_text, await _get_bot_username(callback.bot)
    )

    await callback.message.edit_text(
        text,
        reply_markup=_build_verse_keyboard(
            verse["abbrev"], verse["chapter"], verse["verse"],
            lang, is_bm, return_to="vod", show_another=False,
            share_url=share_url,
        )
    )
    await callback.answer()

    await _send_streak_extras(callback.message, callback.from_user.id, streak_result, lang)


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

    book_name = BibleService.get_book_name(verse["abbrev"], lang)
    reference = f"{book_name} {verse['chapter']}:{verse['verse']}"
    share_text = _build_share_text(
        verse, reference, lang, _strip_html(t("verse.random_title", lang))
    )
    share_url = _build_share_url(
        share_text, await _get_bot_username(callback.bot)
    )

    await callback.message.edit_text(
        text,
        reply_markup=_build_verse_keyboard(
            verse["abbrev"], verse["chapter"], verse["verse"],
            lang, is_bm, return_to="rnd", show_another=True,
            share_url=share_url,
        )
    )
    await callback.answer()

    await _send_streak_extras(callback.message, callback.from_user.id, streak_result, lang)


@router.callback_query(F.data == "wisdom")
async def show_wisdom_of_day(callback: CallbackQuery):
    """Мудрость дня — практический стих из книг премудрости, один на сутки.
    Засчитывает день серии."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    verse = BibleService.get_wisdom_of_day(translation, lang)
    if not verse:
        await callback.answer("⚠️", show_alert=True)
        return

    # Засчитываем день серии
    streak_result = await StreakService.touch(callback.from_user.id)

    is_bm = await BookmarkService.is_bookmarked(
        callback.from_user.id, verse["abbrev"], verse["chapter"], verse["verse"]
    )

    theme_name = t(f"wisdom.theme.{verse['theme']}", lang)
    book_name = BibleService.get_book_name(verse["abbrev"], lang)
    reference = f"{book_name} {verse['chapter']}:{verse['verse']}"

    # Заголовок + тема, затем сразу стих в цитате (как карточка стиха дня).
    parts = [
        t("wisdom.title", lang),
        t("wisdom.theme_line", lang, theme=theme_name),
        "",
        f"<blockquote>«{verse['text']}»\n<i>{reference}</i></blockquote>",
    ]
    # Отступ, чтобы размышление не сливалось со стихом
    if verse.get("reflection"):
        parts.append("")
        parts.append(verse["reflection"])
    # Серия — в самый низ, чтобы не разрывать тему и стих
    streak_line = format_streak_indicator(streak_result.current_streak, lang)
    if streak_line:
        parts.append("")
        parts.append(streak_line)
    text = "\n".join(parts)

    share_header = f"{_strip_html(t('wisdom.title', lang))} — {theme_name}"
    share_text = _build_share_text(
        verse, reference, lang, share_header, reflection=verse.get("reflection")
    )
    share_url = _build_share_url(
        share_text, await _get_bot_username(callback.bot)
    )

    await callback.message.edit_text(
        text,
        reply_markup=_build_verse_keyboard(
            verse["abbrev"], verse["chapter"], verse["verse"],
            lang, is_bm, return_to="wis", show_another=False,
            share_url=share_url,
        )
    )
    await callback.answer()

    await _send_streak_extras(callback.message, callback.from_user.id, streak_result, lang)


@router.callback_query(F.data == "streak:onboarding_done")
async def close_streak_onboarding(callback: CallbackQuery):
    """Закрыть онбординг про серии — удаляем сообщение."""
    try:
        await callback.message.delete()
    except Exception:
        # Если сообщение уже удалено или слишком старое — молча игнорируем
        pass
    await callback.answer()
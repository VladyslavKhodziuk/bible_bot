import re
import urllib.parse

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from services.user_service import UserService
from services.bible_service import BibleService
from services.bot_meta import get_bot_username
from services.bookmark_service import BookmarkService
from services.counter_service import CounterService
from services.counter_display import (
    format_counter_indicator,
    build_counter_extra,
)
from services.i18n import t
from keyboards.bookmarks import bookmark_toggle_button

router = Router()


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


def _build_share_url(share_text: str, bot_username: str | None) -> str | None:
    """Ссылка t.me/share/url. None, если username бота недоступен (сетевой сбой)
    — тогда клавиатура просто не покажет кнопку «Поделиться»."""
    if not bot_username:
        return None
    bot_url = f"https://t.me/{bot_username}"
    # quote (а не quote_plus): пробел -> %20, не "+". t.me/share/url декодирует
    # только %xx и оставляет "+" буквально — иначе в части клиентов вылезают плюсы.
    params = urllib.parse.urlencode(
        {"url": bot_url, "text": share_text}, quote_via=urllib.parse.quote
    )
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
    return f"<blockquote><i>{verse['text']}</i></blockquote>\n📖 {reference}"


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


async def _send_counter_extras(message, user_id: int, counter_result, lang: str):
    """
    Отправляет доп. сообщение после засчитанного дня (онбординг / веха /
    обычный день роста). Что именно показать решает общий билдер
    ``build_counter_extra`` — те же ветки используются и в рассылке стиха
    (services.scheduler), чтобы логика не расходилась.

    ``message`` — любой объект с .answer() (Message или CallbackQuery.message).
    """
    extra = build_counter_extra(counter_result, lang)
    if not extra:
        return
    text, keyboard, is_onboarding = extra
    await message.answer(text, reply_markup=keyboard)
    if is_onboarding:
        await CounterService.mark_explained(user_id)


async def _render_verse_of_day(tg_id: int, lang: str, translation: str, bot):
    """Готовит стих дня: засчитывает серию и собирает текст + клавиатуру.

    Возвращает ``(text, keyboard, counter_result)`` либо ``None``, если стих
    получить не удалось. Используется callback-кнопкой «стих дня» в меню.
    """
    verse = BibleService.get_verse_of_day(translation)
    if not verse:
        return None

    # Засчитываем день со Словом
    counter_result = await CounterService.touch(tg_id)

    is_bm = await BookmarkService.is_bookmarked(
        tg_id, verse["abbrev"], verse["chapter"], verse["verse"]
    )

    # Формируем текст с индикатором счётчика
    counter_line = format_counter_indicator(counter_result.count, lang)
    parts = [t("verse.of_day_title", lang)]
    if counter_line:
        parts.append(counter_line)
    parts.append("")
    parts.append(_format_verse(verse, lang))
    text = "\n".join(parts)

    book_name = BibleService.get_book_name(verse["abbrev"], lang)
    reference = f"{book_name} {verse['chapter']}:{verse['verse']}"
    share_text = _build_share_text(
        verse, reference, lang, _strip_html(t("verse.of_day_title", lang))
    )
    share_url = _build_share_url(share_text, await get_bot_username(bot))

    keyboard = _build_verse_keyboard(
        verse["abbrev"], verse["chapter"], verse["verse"],
        lang, is_bm, return_to="vod", show_another=False,
        share_url=share_url,
    )
    return text, keyboard, counter_result


@router.callback_query(F.data == "verse_of_day")
async def show_verse_of_day(callback: CallbackQuery):
    """Стих дня — один на сутки. Засчитывает день со Словом."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    rendered = await _render_verse_of_day(
        callback.from_user.id, lang, translation, callback.bot
    )
    if rendered is None:
        await callback.answer("⚠️", show_alert=True)
        return
    text, keyboard, counter_result = rendered

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

    await _send_counter_extras(callback.message, callback.from_user.id, counter_result, lang)


@router.callback_query(F.data == "random")
async def show_random_verse(callback: CallbackQuery):
    """Случайный стих — каждый клик новый. Засчитывает день со Словом."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    verse = BibleService.get_random_verse(translation)
    if not verse:
        await callback.answer("⚠️", show_alert=True)
        return

    counter_result = await CounterService.touch(callback.from_user.id)

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
        share_text, await get_bot_username(callback.bot)
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

    await _send_counter_extras(callback.message, callback.from_user.id, counter_result, lang)


@router.callback_query(F.data == "wisdom")
async def show_wisdom_of_day(callback: CallbackQuery):
    """Мудрость дня — практический стих из книг премудрости, один на сутки.
    Засчитывает день со Словом."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    verse = BibleService.get_wisdom_of_day(translation, lang)
    if not verse:
        await callback.answer("⚠️", show_alert=True)
        return

    # Засчитываем день со Словом
    counter_result = await CounterService.touch(callback.from_user.id)

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
    counter_line = format_counter_indicator(counter_result.count, lang)
    if counter_line:
        parts.append("")
        parts.append(counter_line)
    text = "\n".join(parts)

    share_header = f"{_strip_html(t('wisdom.title', lang))} — {theme_name}"
    share_text = _build_share_text(
        verse, reference, lang, share_header, reflection=verse.get("reflection")
    )
    share_url = _build_share_url(
        share_text, await get_bot_username(callback.bot)
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

    await _send_counter_extras(callback.message, callback.from_user.id, counter_result, lang)


def _build_push_text_after_read(verse: dict, lang: str, count: int) -> str:
    """Текст пуша после тапа «Прочитал»: обновлённый счётчик, без CTA-подсказки."""
    book_name = BibleService.get_book_name(verse["abbrev"], lang)
    reference = t(
        "verse.reference",
        lang,
        book=book_name,
        chapter=verse["chapter"],
        verse=verse["verse"],
    )
    parts = []
    counter_line = format_counter_indicator(count, lang)
    if counter_line:
        parts.append(counter_line)
        parts.append("")
    parts.append(t("verse.daily_push_intro", lang))
    parts.append(reference)
    parts.append("")
    parts.append(f"<i>{verse['text']}</i>")
    return "\n".join(parts)


def _push_keyboard_after_read(verse: dict, lang: str) -> InlineKeyboardMarkup:
    """Клавиатура пуша после тапа «Прочитал» — без кнопки «Прочитал»."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("verse.open_chapter", lang),
        callback_data=f"read:ch:{verse['abbrev']}:{verse['chapter']}",
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu",
    )
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "verse:read")
async def mark_verse_read(callback: CallbackQuery):
    """«Прочитал» под пушем стиха дня — засчитывает день со Словом."""
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    counter_result = await CounterService.touch(callback.from_user.id)

    # Стих дня детерминирован для даты+перевода — пересобираем тот же стих,
    # чтобы перерисовать пуш с обновлённым счётчиком и без кнопки «Прочитал».
    verse = BibleService.get_verse_of_day(user.translation)
    if verse:
        try:
            await callback.message.edit_text(
                _build_push_text_after_read(verse, user.lang, counter_result.count),
                reply_markup=_push_keyboard_after_read(verse, user.lang),
                parse_mode="HTML",
            )
        except TelegramBadRequest as e:
            # «message is not modified» — юзер тапнул повторно (same_day),
            # содержимое идентично. Не ошибка.
            if "message is not modified" not in str(e):
                raise

    await callback.answer(t("verse.read_toast", user.lang))

    # Онбординг / веха / день роста — отдельным сообщением.
    await _send_counter_extras(callback.message, callback.from_user.id, counter_result, user.lang)


@router.callback_query(F.data == "counter:onboarding_done")
async def close_counter_onboarding(callback: CallbackQuery):
    """Закрыть онбординг про счётчик — удаляем сообщение."""
    try:
        await callback.message.delete()
    except Exception:
        # Если сообщение уже удалено или слишком старое — молча игнорируем
        pass
    await callback.answer()
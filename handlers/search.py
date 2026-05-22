import logging
import asyncio

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from services.user_service import UserService
from services.bookmark_service import BookmarkService
from services.bible_service import BibleService, alphabet_matches_translation
from services.i18n import t
from keyboards.search import (
    cancel_keyboard,
    wrong_alphabet_keyboard,
    no_results_keyboard,
    scope_keyboard,
    results_keyboard,
    detail_keyboard,
    RESULTS_PER_PAGE,
)

logger = logging.getLogger(__name__)
router = Router()

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 50
MAX_RESULTS = 200


class SearchState(StatesGroup):
    waiting_for_query = State()


# ============ Шаг 1: Начало поиска ============

@router.callback_query(F.data == "search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    """Вход в поиск. Чистим состояние и просим ввести слово."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await state.clear()
    await state.set_state(SearchState.waiting_for_query)

    await callback.message.edit_text(
        t("search.prompt", lang),
        reply_markup=cancel_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "search:cancel")
async def cancel_search(callback: CallbackQuery, state: FSMContext):
    """Отмена поиска — возвращаемся в главное меню."""
    await state.clear()

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    from keyboards.menu import main_menu_keyboard
    from services.menu_text import build_menu_text
    from services.plan_service import PlanService

    active = await PlanService.get_active(callback.from_user.id) if user else None
    plan_day = active.current_day if active else None

    await callback.message.edit_text(
        build_menu_text(user, lang),
        reply_markup=main_menu_keyboard(lang, plan_day=plan_day),
    )
    await callback.answer()


# ============ Шаг 2: Юзер ввёл слово ============

@router.message(SearchState.waiting_for_query)
async def receive_query(message: Message, state: FSMContext):
    """Получаем слово, проверяем, ищем, показываем экран выбора раздела."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang
    translation = user.translation

    query = (message.text or "").strip()

    if len(query) < MIN_QUERY_LENGTH:
        await message.answer(t("search.too_short", lang))
        return
    if len(query) > MAX_QUERY_LENGTH:
        await message.answer(t("search.too_long", lang))
        return

    if not alphabet_matches_translation(query, translation):
        await state.update_data(pending_query=query)
        translation_name = t(f"settings.translation_names.{translation}", lang)
        await message.answer(
            t("search.wrong_alphabet", lang, query=query, translation=translation_name),
            reply_markup=wrong_alphabet_keyboard(lang)
        )
        return

    await _do_search_show_scope_message(message, state, query, lang, translation)


@router.callback_query(F.data == "search:force")
async def force_search(callback: CallbackQuery, state: FSMContext):
    """Юзер согласился искать несмотря на несоответствие алфавита."""
    data = await state.get_data()
    query = data.get("pending_query", "")
    if not query:
        await callback.answer("⚠️", show_alert=True)
        return

    user = await UserService.get(callback.from_user.id)
    lang = user.lang
    translation = user.translation

    await _do_search_show_scope_callback(callback, state, query, lang, translation)


# ============ Выполнение поиска и показ выбора раздела ============

async def _do_search_show_scope_message(
    message: Message, state: FSMContext,
    query: str, lang: str, translation: str,
):
    """Поиск и показ экрана выбора раздела (новым сообщением)."""
    results = BibleService.search(query, translation, max_results=MAX_RESULTS)

    if not results:
        await state.clear()
        await message.answer(
            t("search.no_results", lang, query=query),
            reply_markup=no_results_keyboard(lang)
        )
        return

    counts = _compute_counts(results)
    await state.update_data(query=query, results=results, counts=counts)
    await state.set_state(None)

    text = t("search.choose_scope", lang, query=query, total=counts["all"])
    await message.answer(text, reply_markup=scope_keyboard(counts, lang))


async def _do_search_show_scope_callback(
    callback: CallbackQuery, state: FSMContext,
    query: str, lang: str, translation: str,
):
    """То же самое, но через callback (например, после 'всё равно искать')."""
    results = await asyncio.to_thread(
        BibleService.search, query, translation, MAX_RESULTS
    )
    if not results:
        await state.clear()
        await callback.message.edit_text(
            t("search.no_results", lang, query=query),
            reply_markup=no_results_keyboard(lang)
        )
        await callback.answer()
        return

    counts = _compute_counts(results)
    await state.update_data(query=query, results=results, counts=counts)
    await state.set_state(None)

    text = t("search.choose_scope", lang, query=query, total=counts["all"])
    await callback.message.edit_text(text, reply_markup=scope_keyboard(counts, lang))
    await callback.answer()


def _compute_counts(results: list[dict]) -> dict:
    """Подсчёт результатов по заветам."""
    ot = BibleService.filter_by_testament(results, "ot")
    nt = BibleService.filter_by_testament(results, "nt")
    return {"all": len(results), "ot": len(ot), "nt": len(nt)}


# ============ Шаг 3: Юзер выбрал раздел ============

@router.callback_query(F.data.startswith("search:scope:"))
async def choose_scope(callback: CallbackQuery, state: FSMContext):
    """Юзер выбрал раздел: all / ot / nt."""
    scope = callback.data.split(":")[2]
    if scope not in ("all", "ot", "nt"):
        await callback.answer("⚠️", show_alert=True)
        return

    data = await state.get_data()
    results = data.get("results", [])
    query = data.get("query", "")

    if not results:
        await callback.answer("⚠️", show_alert=True)
        return

    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await state.update_data(scope=scope, page=0)
    await _show_results(callback, results, query, lang, scope, page=0)


# ============ Возврат к выбору раздела ============

@router.callback_query(F.data == "search:back_to_scope")
async def back_to_scope(callback: CallbackQuery, state: FSMContext):
    """Из результатов вернуться к выбору раздела."""
    data = await state.get_data()
    results = data.get("results", [])
    query = data.get("query", "")
    counts = data.get("counts", {"all": 0, "ot": 0, "nt": 0})

    if not results:
        await callback.answer("⚠️", show_alert=True)
        return

    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    text = t("search.choose_scope", lang, query=query, total=counts["all"])
    await callback.message.edit_text(text, reply_markup=scope_keyboard(counts, lang))
    await callback.answer()


# ============ Отображение результатов ============

def _apply_scope(results: list[dict], scope: str) -> list[dict]:
    """Фильтрация результатов по выбранному разделу."""
    if scope == "ot":
        return BibleService.filter_by_testament(results, "ot")
    if scope == "nt":
        return BibleService.filter_by_testament(results, "nt")
    return results


def _build_results_text(
    filtered: list[dict],
    query: str,
    lang: str,
    page: int,
    scope: str,
    total_all: int,
) -> str:
    """Текст с результатами на текущей странице."""
    title_key = {
        "all": "search.results_title_all",
        "ot": "search.results_title_ot",
        "nt": "search.results_title_nt",
    }[scope]
    parts = [t(title_key, lang, query=query)]

    if total_all >= MAX_RESULTS:
        parts.append(t("search.found_limited", lang, limit=MAX_RESULTS))

    parts.append("")

    start = page * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    page_results = filtered[start:end]

    for v in page_results:
        book_name = BibleService.get_book_name(v["abbrev"], lang)
        ref = t("search.result_header", lang, book=book_name,
                chapter=v["chapter"], verse=v["verse"])
        highlighted = BibleService.highlight(v["text"], query)
        parts.append(f"{ref}\n<i>{highlighted}</i>\n")

    return "\n".join(parts)


async def _show_results(
    callback: CallbackQuery,
    results: list[dict],
    query: str,
    lang: str,
    scope: str,
    page: int,
):
    """Показать страницу результатов."""
    filtered = _apply_scope(results, scope)
    text = _build_results_text(filtered, query, lang, page, scope, total_all=len(results))
    kb = results_keyboard(filtered, page, lang)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ============ Пагинация ============

@router.callback_query(F.data.startswith("search:page:"))
async def paginate_results(callback: CallbackQuery, state: FSMContext):
    """Переход между страницами."""
    page = int(callback.data.split(":")[2])

    data = await state.get_data()
    results = data.get("results", [])
    query = data.get("query", "")
    scope = data.get("scope", "all")

    if not results:
        await callback.answer("⚠️", show_alert=True)
        return

    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await state.update_data(page=page)
    await _show_results(callback, results, query, lang, scope, page=page)


# ============ Детальный экран стиха ============

@router.callback_query(F.data.startswith("search:open:"))
async def open_verse_detail(callback: CallbackQuery, state: FSMContext):
    """Открыть детальный экран выбранного стиха."""
    idx = int(callback.data.split(":")[2])

    data = await state.get_data()
    results = data.get("results", [])
    query = data.get("query", "")
    scope = data.get("scope", "all")

    filtered = _apply_scope(results, scope)
    if idx >= len(filtered):
        await callback.answer("⚠️", show_alert=True)
        return

    verse = filtered[idx]
    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    book_name = BibleService.get_book_name(verse["abbrev"], lang)
    ref = t("search.result_header", lang, book=book_name,
            chapter=verse["chapter"], verse=verse["verse"])
    highlighted = BibleService.highlight(verse["text"], query)

    text = (
        f"{t('search.detail_title', lang)}\n\n"
        f"{ref}\n\n"
        f"<i>{highlighted}</i>"
    )

    is_bm = await BookmarkService.is_bookmarked(
        user.tg_id, verse["abbrev"], verse["chapter"], verse["verse"]
    )

    await state.update_data(current_verse_idx=idx)
    await callback.message.edit_text(
        text,
        reply_markup=detail_keyboard(
            idx, verse["abbrev"], verse["chapter"], is_bm, lang
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("search:bm:"))
async def toggle_bookmark_from_detail(callback: CallbackQuery, state: FSMContext):
    """Тоггл закладки на детальном экране."""
    idx = int(callback.data.split(":")[2])

    data = await state.get_data()
    results = data.get("results", [])
    scope = data.get("scope", "all")
    query = data.get("query", "")
    filtered = _apply_scope(results, scope)

    if idx >= len(filtered):
        await callback.answer("⚠️", show_alert=True)
        return

    verse = filtered[idx]
    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    is_bm = await BookmarkService.is_bookmarked(
        user.tg_id, verse["abbrev"], verse["chapter"], verse["verse"]
    )
    if is_bm:
        await BookmarkService.remove(
            user.tg_id, verse["abbrev"], verse["chapter"], verse["verse"]
        )
        await callback.answer(t("bookmarks.removed", lang))
    else:
        await BookmarkService.add(
            user.tg_id, verse["abbrev"], verse["chapter"], verse["verse"]
        )
        await callback.answer(t("bookmarks.added", lang))

    new_is_bm = not is_bm
    book_name = BibleService.get_book_name(verse["abbrev"], lang)
    ref = t("search.result_header", lang, book=book_name,
            chapter=verse["chapter"], verse=verse["verse"])
    highlighted = BibleService.highlight(verse["text"], query)
    text = (
        f"{t('search.detail_title', lang)}\n\n"
        f"{ref}\n\n"
        f"<i>{highlighted}</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=detail_keyboard(
            idx, verse["abbrev"], verse["chapter"], new_is_bm, lang
        )
    )


@router.callback_query(F.data == "search:back_to_results")
async def back_to_results(callback: CallbackQuery, state: FSMContext):
    """Возврат с детального экрана к списку результатов."""
    data = await state.get_data()
    results = data.get("results", [])
    query = data.get("query", "")
    scope = data.get("scope", "all")
    page = data.get("page", 0)

    if not results:
        await callback.answer("⚠️", show_alert=True)
        return

    user = await UserService.get(callback.from_user.id)
    lang = user.lang

    await _show_results(callback, results, query, lang, scope, page)
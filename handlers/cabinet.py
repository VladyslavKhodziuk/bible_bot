import html
from datetime import date

from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.bookmark_service import BookmarkService
from services.plan_service import PlanService
from services.i18n import t
from keyboards.cabinet import cabinet_keyboard

router = Router()


def _format_day_count(days: int, lang: str) -> str:
    """«1 день» / «{N} дн.» — общий формат счётчиков дней в кабинете."""
    if days == 1:
        return t("cabinet.day_count_single", lang)
    return t("cabinet.day_count", lang, days=days)


def _format_counter_line(count: int, lang: str) -> str:
    """Одна нейтральная строка накопительного счётчика дней.

    «пока нет» при 0, иначе «N дней» через общий формат.
    """
    if count <= 0:
        return t("cabinet.counter_zero", lang)
    return t("cabinet.counter", lang, count=_format_day_count(count, lang))


async def _build_cabinet_text(user, lang: str) -> str:
    """Сформировать текст личного кабинета: приветствие + два блока статистики."""
    name = html.escape(user.first_name or "друг")

    days_in_bot = (date.today() - user.created_at.date()).days
    if days_in_bot <= 0:
        days_line = t("cabinet.days_with_bot_first", lang)
    elif days_in_bot == 1:
        days_line = t("cabinet.days_with_bot_one", lang)
    else:
        days_line = t("cabinet.days_with_bot", lang, days=days_in_bot)

    bookmarks_count = await BookmarkService.count_for_user(user.tg_id)
    history = await PlanService.get_history(user.tg_id)
    completed_plans_count = sum(1 for p in history if p.status == "completed")

    # Блок «Со Словом»: чтение Библии + закладки + завершённые планы
    word_lines = [
        t("cabinet.word_section", lang),
        _format_counter_line(user.current_streak, lang),
        t("cabinet.bookmarks", lang, count=bookmarks_count),
        t("cabinet.plans_completed", lang, count=completed_plans_count),
    ]
    word_card = "<blockquote>" + "\n".join(word_lines) + "</blockquote>"

    # Блок «В молитве»: молитвенный счётчик
    prayer_lines = [
        t("cabinet.prayer_section", lang),
        _format_counter_line(user.current_prayer_streak, lang),
    ]
    prayer_card = "<blockquote>" + "\n".join(prayer_lines) + "</blockquote>"

    parts = [
        t("cabinet.title", lang),
        "",
        t("cabinet.greeting", lang, name=name),
        days_line,
        "",
        word_card,
        "",
        prayer_card,
        "",
        t("cabinet.footer_motto", lang),
    ]
    return "\n".join(parts)


@router.callback_query(F.data == "cabinet")
async def open_cabinet(callback: CallbackQuery):
    """Открыть личный кабинет."""
    user = await UserService.get(callback.from_user.id)
    if user is None:
        await callback.answer("⚠️", show_alert=True)
        return

    lang = user.lang
    text = await _build_cabinet_text(user, lang)

    await callback.message.edit_text(
        text,
        reply_markup=cabinet_keyboard(lang)
    )
    await callback.answer()

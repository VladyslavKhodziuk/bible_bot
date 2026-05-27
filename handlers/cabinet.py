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

# Должно совпадать с MAX_FREEZES из streak_service.py
MAX_FREEZES = 2


def _format_day_count(days: int, lang: str) -> str:
    """«1 день» / «{N} дн.» — общий формат счётчиков дней в кабинете."""
    if days == 1:
        return t("cabinet.day_count_single", lang)
    return t("cabinet.day_count", lang, days=days)


def _format_streak_line(current: int, longest: int, lang: str) -> str:
    """Одна строка серии: «🔥 Серия пока не начата» либо «🔥 Серия: X · …».

    Если текущая = лучшая (и > 0), подчёркиваем «твой рекорд» — мотивация
    превзойти. Иначе показываем оба значения, чтобы было видно, к чему стремиться.
    """
    if current <= 0:
        return t("cabinet.streak_none", lang)

    current_str = _format_day_count(current, lang)
    if current >= longest:
        return t("cabinet.streak_record_match", lang, current=current_str)

    longest_str = _format_day_count(longest, lang)
    return t("cabinet.streak_with_record", lang, current=current_str, longest=longest_str)


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
        _format_streak_line(user.current_streak, user.longest_streak, lang),
        t("cabinet.freezes", lang, count=user.freezes_available, max=MAX_FREEZES),
        t("cabinet.bookmarks", lang, count=bookmarks_count),
        t("cabinet.plans_completed", lang, count=completed_plans_count),
    ]
    word_card = "<blockquote>" + "\n".join(word_lines) + "</blockquote>"

    # Блок «В молитве»: молитвенный стрик
    prayer_lines = [
        t("cabinet.prayer_section", lang),
        _format_streak_line(
            user.current_prayer_streak, user.longest_prayer_streak, lang
        ),
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

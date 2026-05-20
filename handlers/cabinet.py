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


async def _build_cabinet_text(user, lang: str) -> str:
    """Сформировать текст личного кабинета с сводкой."""
    name = user.first_name or "друг"

    # Серия — текущая
    if user.current_streak == 0:
        streak_line = t("cabinet.streak_none", lang)
    elif user.current_streak == 1:
        streak_line = t("cabinet.streak_current_single", lang)
    else:
        streak_line = t("cabinet.streak_current", lang, days=user.current_streak)

    # Серия — рекорд (только если есть)
    longest_line = None
    if user.longest_streak > 0:
        longest_line = t("cabinet.streak_longest", lang, days=user.longest_streak)

    # Заморозки
    freezes_line = t(
        "cabinet.freezes",
        lang,
        count=user.freezes_available,
        max=MAX_FREEZES,
    )

    # Дней в боте
    days_in_bot = (date.today() - user.created_at.date()).days
    if days_in_bot == 0:
        days_in_bot = 1
    days_line = t("cabinet.days_in_bot", lang, days=days_in_bot)

    # Количество закладок
    bookmarks_count = await BookmarkService.count_for_user(user.tg_id)
    bookmarks_line = t("cabinet.bookmarks_count", lang, count=bookmarks_count)

    # Количество завершённых планов
    history = await PlanService.get_history(user.tg_id)
    completed_plans_count = sum(1 for p in history if p.status == "completed")
    completed_line = t("cabinet.completed_plans_count", lang, count=completed_plans_count)

    # Собираем
    parts = [
        t("cabinet.title", lang),
        "",
        t("cabinet.greeting", lang, name=name),
        "",
        streak_line,
    ]
    if longest_line:
        parts.append(longest_line)
    parts.append(freezes_line)
    parts.append(days_line)
    parts.append(bookmarks_line)
    parts.append(completed_line)

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
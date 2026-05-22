from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.user_service import UserService
from services.plan_service import PlanService
from services.menu_text import build_menu_text
from keyboards.menu import main_menu_keyboard


# Оставлено для обратной совместимости с handlers/ai_pastor.py
def _menu_text(user, lang: str) -> str:
    return build_menu_text(user, lang)


router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Команда /menu — открыть главное меню откуда угодно."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    active = await PlanService.get_active(message.from_user.id) if user else None
    plan_day = active.current_day if active else None

    await message.answer(
        build_menu_text(user, lang),
        reply_markup=main_menu_keyboard(lang, plan_day=plan_day),
    )

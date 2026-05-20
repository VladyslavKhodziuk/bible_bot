from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from services.user_service import UserService
from services.streak_display import format_streak_indicator
from services.i18n import t
from keyboards.menu import main_menu_keyboard

def _menu_text(user, lang: str) -> str:
    """Текст главного меню с индикатором серии (если есть)."""
    base = t("menu.title", lang)
    if user is None:
        return base

    streak_line = format_streak_indicator(user.current_streak, lang)
    if streak_line:
        return f"{base}\n\n{streak_line}"
    return base

router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Команда /menu — открыть главное меню откуда угодно."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    text = _menu_text(user, lang)

    await message.answer(text, reply_markup=main_menu_keyboard(lang))

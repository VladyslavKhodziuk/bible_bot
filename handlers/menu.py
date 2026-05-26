from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.user_service import UserService
from services.menu_text import build_menu_text
from keyboards.menu import main_menu_keyboard


router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Команда /menu — открыть главное меню откуда угодно."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    await message.answer(
        await build_menu_text(user, lang, message.bot),
        reply_markup=main_menu_keyboard(lang),
    )

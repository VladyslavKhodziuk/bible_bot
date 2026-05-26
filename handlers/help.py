from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.i18n import t

router = Router()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help — экран со списком команд и обзором возможностей бота."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    builder = InlineKeyboardBuilder()
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")

    await message.answer(t("help.text", lang), reply_markup=builder.as_markup())

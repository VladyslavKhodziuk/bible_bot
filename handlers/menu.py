from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from services.user_service import UserService
from services.i18n import t
from keyboards.menu import main_menu_keyboard

router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Команда /menu — открыть главное меню откуда угодно."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    await message.answer(
        t("menu.title", lang),
        reply_markup=main_menu_keyboard(lang)
    )


# Заглушки для кнопок меню — settings УБРАН отсюда,
# т.к. теперь обрабатывается в handlers/settings.py
@router.callback_query(F.data.in_({
    "search", "topics",
    "bookmarks", "plan", "share", "donate"
}))
async def menu_stub(callback: CallbackQuery):
    """Временная заглушка для нереализованных кнопок меню."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.answer(
        t("common.in_development", lang),
        show_alert=True
    )
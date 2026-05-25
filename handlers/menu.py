from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from services.user_service import UserService
from services.menu_text import build_menu_text
from services.i18n import t
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

    await message.answer(
        build_menu_text(user, lang),
        reply_markup=main_menu_keyboard(lang),
    )


@router.callback_query(F.data == "wisdom")
async def wisdom_stub(callback: CallbackQuery):
    """Заглушка раздела «Мудрость дня» — функция в разработке."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    await callback.answer(t("wisdom.coming_soon", lang), show_alert=True)

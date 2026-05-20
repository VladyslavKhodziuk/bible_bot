"""Заглушка для будущего раздела 'AI Пастырь'."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.i18n import t

router = Router()


@router.callback_query(F.data == "ai_pastor")
async def show_stub(callback: CallbackQuery):
    """Показать заглушку 'В разработке'."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    text = (
        f"{t('ai_pastor.stub_title', lang)}\n\n"
        f"{t('ai_pastor.stub_text', lang)}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("ai_pastor.stub_back", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()
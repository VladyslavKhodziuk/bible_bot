"""Catch-all для свободного текста: мягкая эскалация-подсказка.

Если юзер пишет произвольное сообщение вне команды и вне FSM-состояния, бот
ненавязчиво подсказывает, что общается кнопками, и меняет тон с каждым повтором,
в итоге выводя в главное меню. Роутер подключается последним в main.py.
"""
import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.i18n import t
from services.menu_text import build_menu_text
from keyboards.menu import main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()

# Счётчик подряд набранных «свободных» сообщений на юзера (в памяти).
# Сбрасывается из AnalyticsMiddleware, как только юзер нажимает кнопку / вводит команду.
_strikes: dict[int, int] = {}


def reset_strikes(tg_id: int) -> None:
    """Сброс счётчика настойчивости — юзер начал пользоваться ботом правильно."""
    _strikes.pop(tg_id, None)


def _companion_menu_kb(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=t("menu.ai_pastor", lang), callback_data="ai_pastor")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


def _feedback_menu_kb(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=t("feedback.cabinet_idea", lang), callback_data="fb:start:idea")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.message()
async def handle_freetext(message: Message):
    """Любое необработанное сообщение: подсказка с эскалацией по числу повторов."""
    if message.from_user is None:
        return

    tg_id = message.from_user.id
    user = await UserService.get(tg_id)
    lang = user.lang if user else "ru"

    strike = _strikes.get(tg_id, 0) + 1
    _strikes[tg_id] = strike

    if strike == 1:
        await message.answer(t("freetext.reply_1", lang), reply_markup=_companion_menu_kb(lang))
    elif strike == 2:
        await message.answer(t("freetext.reply_2", lang), reply_markup=_companion_menu_kb(lang))
    elif strike == 3:
        await message.answer(t("freetext.reply_3", lang), reply_markup=_feedback_menu_kb(lang))
    elif strike == 4:
        await message.answer(t("freetext.reply_4", lang), reply_markup=main_menu_keyboard(lang))
    else:
        await message.answer(
            await build_menu_text(user, lang, message.bot),
            reply_markup=main_menu_keyboard(lang),
        )

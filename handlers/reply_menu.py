"""Обработчики основной reply-клавиатуры и рубрики «Частые вопросы».

Reply-кнопки приходят как обычный текст, поэтому матчим ярлык точным сравнением
во всех языках (_labels). Роутер подключается ПЕРВЫМ в main.py — постоянные
кнопки работают как глобальный «escape» даже изнутри FSM; обычный свободный ввод
(не равный ярлыку) проваливается дальше в feedback/donate как раньше.
"""
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import SUPPORTED_LANGS
from services.user_service import UserService
from services.i18n import t
from services.menu_text import build_menu_text
from keyboards.menu import main_menu_keyboard
from keyboards.reply import faq_menu_keyboard, faq_answer_keyboard
from keyboards.donate import donate_region_keyboard, donate_main_keyboard
from keyboards.settings import settings_keyboard
from keyboards.language import language_keyboard
from handlers.donate import resolve_donate_region
from handlers.freetext import reset_strikes
from handlers.settings import _build_settings_text

logger = logging.getLogger(__name__)
router = Router()


def _labels(key: str) -> set[str]:
    """Набор ярлыков кнопки по всем поддерживаемым языкам — для точного матча."""
    return {t(key, lang) for lang in SUPPORTED_LANGS}


@router.message(F.text.in_(_labels("reply.main_menu")))
async def reply_main_menu(message: Message):
    """Кнопка «Главное меню» — присылаем меню новым сообщением (reply нельзя редактировать)."""
    reset_strikes(message.from_user.id)
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"
    await message.answer(
        await build_menu_text(user, lang, message.bot),
        reply_markup=main_menu_keyboard(lang),
    )


@router.message(F.text.in_(_labels("reply.settings")))
async def reply_settings(message: Message):
    """Кнопка «Настройки» — открываем экран настроек новым сообщением (как /settings)."""
    reset_strikes(message.from_user.id)
    user = await UserService.get(message.from_user.id)
    if user is None:
        # Не делал /start — отправляем на онбординг (выбор языка)
        await message.answer(t("language.choose"), reply_markup=language_keyboard())
        return
    await message.answer(
        _build_settings_text(user, user.lang),
        reply_markup=settings_keyboard(user, user.lang),
    )


@router.message(F.text.in_(_labels("reply.faq")))
async def reply_faq(message: Message):
    """Кнопка «Частые вопросы» — открываем рубрику с inline-вопросами."""
    reset_strikes(message.from_user.id)
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"
    await message.answer(t("faq.title", lang), reply_markup=faq_menu_keyboard(lang))


@router.message(F.text.in_(_labels("reply.support")))
async def reply_support(message: Message, state: FSMContext):
    """Кнопка «Поддержать проект» — экран доната (как show_donate, но новым сообщением)."""
    reset_strikes(message.from_user.id)
    await state.clear()
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    region = resolve_donate_region(user, lang)
    if region is None:
        await message.answer(
            t("donate.region_title", lang),
            reply_markup=donate_region_keyboard(lang),
        )
    else:
        await state.update_data(donate_region=region)
        await message.answer(
            t("donate.title", lang),
            reply_markup=donate_main_keyboard(lang, region=region),
        )


@router.callback_query(F.data == "faq:menu")
async def faq_back_to_questions(callback: CallbackQuery):
    """Назад к списку вопросов FAQ."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    await callback.message.edit_text(t("faq.title", lang), reply_markup=faq_menu_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("faq:q:"))
async def faq_show_answer(callback: CallbackQuery):
    """Показать ответ на выбранный вопрос."""
    qid = callback.data.split(":", 2)[2]
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    await callback.message.edit_text(t(f"faq.a.{qid}", lang), reply_markup=faq_answer_keyboard(lang))
    await callback.answer()

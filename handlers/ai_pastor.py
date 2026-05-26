"""Хэндлер раздела 'AI Пастырь' — согласие, FSM ожидания вопроса, ответ AI."""
import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.ai_pastor_service import AIPastorService, DAILY_LIMIT
from services.i18n import t

logger = logging.getLogger(__name__)
router = Router()


# Минимальная длина осмысленного вопроса
MIN_QUESTION_LENGTH = 5
MAX_QUESTION_LENGTH = 1000


class AIPastorState(StatesGroup):
    waiting_for_question = State()


# ============ Клавиатуры ============

def _consent_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=t("ai_pastor.consent_agree", lang), callback_data="ai_pastor:consent")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


def _cancel_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=t("ai_pastor.cancel", lang), callback_data="ai_pastor:cancel")
    return builder.as_markup()


def _after_answer_keyboard(lang: str, remaining: int):
    builder = InlineKeyboardBuilder()
    if remaining > 0:
        builder.button(text=t("ai_pastor.ask_more", lang), callback_data="ai_pastor:ask_more")
    builder.button(text=t("feedback.support_button", lang), callback_data="donate")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


def _limit_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    return builder.as_markup()


# ============ Вход в раздел ============

@router.callback_query(F.data == "ai_pastor")
async def show_ai_pastor(callback: CallbackQuery, state: FSMContext):
    """Главный вход: проверяем согласие, потом лимит, потом запрашиваем вопрос."""
    await state.clear()

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    user_id = callback.from_user.id

    # 1) Согласие
    if not await AIPastorService.has_consented(user_id):
        await callback.message.edit_text(
            t("ai_pastor.consent_text", lang),
            reply_markup=_consent_keyboard(lang),
        )
        await callback.answer()
        return

    # 2) Лимит
    can, remaining = await AIPastorService.can_make_request(user_id)
    if not can:
        await callback.message.edit_text(
            t("ai_pastor.limit_reached", lang, limit=DAILY_LIMIT),
            reply_markup=_limit_keyboard(lang),
        )
        await callback.answer()
        return

    # 3) Ждём вопрос
    await state.set_state(AIPastorState.waiting_for_question)
    await callback.message.edit_text(
        t("ai_pastor.prompt", lang, remaining=remaining, limit=DAILY_LIMIT),
        reply_markup=_cancel_keyboard(lang),
    )
    await callback.answer()


# ============ Согласие с правилами ============

@router.callback_query(F.data == "ai_pastor:consent")
async def give_consent(callback: CallbackQuery, state: FSMContext):
    """Юзер принял правила — переходим к запросу вопроса."""
    user_id = callback.from_user.id
    user = await UserService.get(user_id)
    lang = user.lang if user else "ru"

    await AIPastorService.give_consent(user_id)

    can, remaining = await AIPastorService.can_make_request(user_id)
    if not can:
        await callback.message.edit_text(
            t("ai_pastor.limit_reached", lang, limit=DAILY_LIMIT),
            reply_markup=_limit_keyboard(lang),
        )
        await callback.answer()
        return

    await state.set_state(AIPastorState.waiting_for_question)
    await callback.message.edit_text(
        t("ai_pastor.prompt", lang, remaining=remaining, limit=DAILY_LIMIT),
        reply_markup=_cancel_keyboard(lang),
    )
    await callback.answer()


# ============ Отмена ввода ============

@router.callback_query(F.data == "ai_pastor:cancel")
async def cancel_input(callback: CallbackQuery, state: FSMContext):
    """Отмена ввода вопроса — возвращаемся в главное меню."""
    await state.clear()

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    from keyboards.menu import main_menu_keyboard
    from services.menu_text import build_menu_text

    await callback.message.edit_text(
        await build_menu_text(user, lang, callback.bot),
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()


# ============ Ещё один вопрос ============

@router.callback_query(F.data == "ai_pastor:ask_more")
async def ask_more(callback: CallbackQuery, state: FSMContext):
    """Юзер хочет задать ещё один вопрос — снова проверяем лимит."""
    user_id = callback.from_user.id
    user = await UserService.get(user_id)
    lang = user.lang if user else "ru"

    can, remaining = await AIPastorService.can_make_request(user_id)
    if not can:
        await callback.message.edit_text(
            t("ai_pastor.limit_reached", lang, limit=DAILY_LIMIT),
            reply_markup=_limit_keyboard(lang),
        )
        await callback.answer()
        return

    await state.set_state(AIPastorState.waiting_for_question)
    await callback.message.edit_text(
        t("ai_pastor.prompt", lang, remaining=remaining, limit=DAILY_LIMIT),
        reply_markup=_cancel_keyboard(lang),
    )
    await callback.answer()


# ============ Приём вопроса ============

@router.message(AIPastorState.waiting_for_question)
async def receive_question(message: Message, state: FSMContext, bot: Bot):
    """Юзер прислал текст вопроса — отправляем в AI, возвращаем ответ."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"
    user_id = message.from_user.id

    text = (message.text or "").strip()

    # Валидация
    if len(text) < MIN_QUESTION_LENGTH:
        await message.answer(t("ai_pastor.too_short", lang))
        return  # остаёмся в FSM

    if len(text) > MAX_QUESTION_LENGTH:
        await message.answer(t("ai_pastor.too_long", lang, max=MAX_QUESTION_LENGTH))
        return

    # Повторная проверка лимита (на случай гонок)
    can, _ = await AIPastorService.can_make_request(user_id)
    if not can:
        await state.clear()
        await message.answer(
            t("ai_pastor.limit_reached", lang, limit=DAILY_LIMIT),
            reply_markup=_limit_keyboard(lang),
        )
        return

    # Выходим из FSM — запрос пошёл
    await state.clear()

    # Промежуточное сообщение «думаю...» + индикатор печати
    thinking_msg = await message.answer(t("ai_pastor.thinking", lang))
    await bot.send_chat_action(message.chat.id, "typing")

    try:
        response_text, is_crisis = await AIPastorService.send_request(
            user_id=user_id,
            user_message=text,
            lang=lang,
        )
    except Exception:
        logger.exception("Неожиданная ошибка AI Пастыря")
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        await message.answer(t("ai_pastor.error", lang), reply_markup=_limit_keyboard(lang))
        return

    # Удаляем «думаю...»
    try:
        await thinking_msg.delete()
    except Exception:
        pass

    # Считаем сколько осталось ПОСЛЕ этого запроса
    _, remaining = await AIPastorService.can_make_request(user_id)

    # Префикс для кризисных
    if is_crisis:
        header = t("ai_pastor.crisis_header", lang)
        full = f"{header}\n\n{response_text}"
    else:
        full = response_text

    # Подпись с оставшимся лимитом
    if remaining > 0:
        full += f"\n\n<i>{t('ai_pastor.remaining', lang, remaining=remaining, limit=DAILY_LIMIT)}</i>"
    else:
        full += f"\n\n<i>{t('ai_pastor.last_used', lang, limit=DAILY_LIMIT)}</i>"

    await message.answer(
        full,
        reply_markup=_after_answer_keyboard(lang, remaining),
    )

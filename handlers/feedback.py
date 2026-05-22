import html
import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS, FEEDBACK_CHAT_IDS
from services.user_service import UserService
from services.feedback_service import FeedbackService, KIND_IDEA, KIND_BUG, KIND_REVIEW
from services.i18n import t
from keyboards.feedback import cancel_keyboard, after_idea_keyboard, after_review_keyboard

logger = logging.getLogger(__name__)
router = Router()


# FSM-состояния: бот "ждёт" разный тип сообщения от юзера
class FeedbackState(StatesGroup):
    waiting_for_idea = State()
    waiting_for_bug = State()
    waiting_for_review = State()


# Минимальная длина сообщения, чтобы считать его осмысленным
MIN_TEXT_LENGTH = 5

# Маппинг: тип фидбека → (FSM-состояние, ключ промпта, ключ благодарности)
FEEDBACK_CONFIG = {
    "idea": (FeedbackState.waiting_for_idea, "feedback.idea_prompt", "feedback.idea_thanks"),
    "bug": (FeedbackState.waiting_for_bug, "feedback.bug_prompt", "feedback.bug_thanks"),
    "review": (FeedbackState.waiting_for_review, "feedback.review_prompt", "feedback.review_thanks"),
}


# ============ Начало диалога ============

@router.callback_query(F.data.startswith("fb:start:"))
async def start_feedback(callback: CallbackQuery, state: FSMContext):
    """Юзер выбрал тип обратной связи. Переходим в FSM-состояние ожидания."""
    kind = callback.data.split(":")[2]
    if kind not in FEEDBACK_CONFIG:
        await callback.answer("⚠️", show_alert=True)
        return

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    fsm_state, prompt_key, _ = FEEDBACK_CONFIG[kind]
    await state.set_state(fsm_state)

    await callback.message.edit_text(
        t(prompt_key, lang),
        reply_markup=cancel_keyboard(lang)
    )
    await callback.answer()


# ============ Отмена ввода ============

@router.callback_query(F.data == "fb:cancel")
async def cancel_feedback(callback: CallbackQuery, state: FSMContext):
    """Отмена ввода — возвращаемся в личный кабинет."""
    logger.info(f"🔄 Отмена fb от {callback.from_user.id}")

    current_state = await state.get_state()
    logger.info(f"   текущее состояние: {current_state}")

    await state.clear()

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    # Импортируем напрямую — чтобы не было циклических зависимостей
    from handlers.cabinet import _build_cabinet_text
    from keyboards.cabinet import cabinet_keyboard

    text = await _build_cabinet_text(user, lang)

    await callback.message.edit_text(
        text,
        reply_markup=cabinet_keyboard(lang)
    )
    await callback.answer(t("feedback.cancelled", lang))


# ============ Получение текста идеи ============

@router.message(FeedbackState.waiting_for_idea)
async def receive_idea(message: Message, state: FSMContext, bot: Bot):
    await _receive_feedback(message, state, bot, KIND_IDEA)


# ============ Получение текста бага ============

@router.message(FeedbackState.waiting_for_bug)
async def receive_bug(message: Message, state: FSMContext, bot: Bot):
    await _receive_feedback(message, state, bot, KIND_BUG)


# ============ Получение текста отзыва ============

@router.message(FeedbackState.waiting_for_review)
async def receive_review(message: Message, state: FSMContext, bot: Bot):
    await _receive_feedback(message, state, bot, KIND_REVIEW)


# ============ Универсальная функция приёма ============

async def _receive_feedback(message: Message, state: FSMContext, bot: Bot, kind: str):
    """Обработка полученного текста от юзера."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    text = (message.text or "").strip()

    # Проверка минимальной длины
    if len(text) < MIN_TEXT_LENGTH:
        await message.answer(t("feedback.too_short", lang))
        return  # остаёмся в том же FSM-состоянии — ждём нормального текста

    # Сохраняем в БД
    await FeedbackService.add(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        lang=lang,
        kind=kind,
        text=text,
    )

    # Выходим из FSM
    await state.clear()

    # Благодарим юзера, и для отзыва — особая клавиатура с поддержкой проекта
    _, _, thanks_key = FEEDBACK_CONFIG[kind]
    if kind == KIND_REVIEW:
        keyboard = after_review_keyboard(lang)
    else:
        keyboard = after_idea_keyboard(lang)

    await message.answer(t(thanks_key, lang), reply_markup=keyboard)

    # Уведомление админу
    await _notify_admin(bot, message.from_user, lang, kind, text)


async def _notify_admin(bot: Bot, tg_user, lang: str, kind: str, text: str):
    """Шлём уведомление о новом фидбеке.

    Каждый тип уходит в свою Telegram-группу (если её ID задан в конфиге),
    иначе — всем админам в личку.
    """
    kind_emoji = {"idea": "💡", "bug": "🐞", "review": "😊"}
    kind_label = {"idea": "ИДЕЯ", "bug": "БАГ", "review": "ОТЗЫВ"}

    emoji = kind_emoji.get(kind, "📨")
    label = kind_label.get(kind, kind.upper())

    # Имя/юзернейм для опознания. Экранируем — first_name юзера может содержать
    # <, >, & и сломать разбор HTML (тогда фидбек не дойдёт до админа).
    user_display = html.escape(tg_user.first_name or "Юзер")
    if tg_user.username:
        user_display += f" (@{tg_user.username})"
    user_display += f" [id:{tg_user.id}]"

    # В отзывах прячем данные отправителя и язык под спойлер (раскрывается по клику)
    if kind == KIND_REVIEW:
        info_block = (
            f"От: <tg-spoiler>{user_display}</tg-spoiler>\n"
            f"Язык: <tg-spoiler>{lang}</tg-spoiler>"
        )
    else:
        info_block = (
            f"От: {user_display}\n"
            f"Язык: {lang}"
        )

    admin_text = (
        f"{emoji} <b>Новый {label}</b>\n\n"
        f"{info_block}\n\n"
        f"<i>{html.escape(text)}</i>"
    )

    # Если для типа задана группа — шлём в неё, иначе в личку админам
    group_chat_id = FEEDBACK_CHAT_IDS.get(kind)
    targets = [group_chat_id] if group_chat_id else ADMIN_IDS

    for target in targets:
        try:
            await bot.send_message(target, admin_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление ({kind}) в {target}: {e}")
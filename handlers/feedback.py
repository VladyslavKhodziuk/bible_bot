import html
import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS, FEEDBACK_CHAT_IDS
from services.user_service import UserService
from services.feedback_service import FeedbackService, KIND_IDEA, KIND_BUG, KIND_REVIEW, KIND_QUESTION
from services.i18n import t
from keyboards.feedback import cancel_keyboard, after_idea_keyboard, after_review_keyboard

logger = logging.getLogger(__name__)
router = Router()


# FSM-состояния: бот "ждёт" разный тип сообщения от юзера
class FeedbackState(StatesGroup):
    waiting_for_idea = State()
    waiting_for_bug = State()
    waiting_for_review = State()
    waiting_for_question = State()


# Минимальная длина сообщения, чтобы считать его осмысленным
MIN_TEXT_LENGTH = 5

# Маппинг: тип фидбека → (FSM-состояние, ключ промпта, ключ благодарности)
FEEDBACK_CONFIG = {
    "idea": (FeedbackState.waiting_for_idea, "feedback.idea_prompt", "feedback.idea_thanks"),
    "bug": (FeedbackState.waiting_for_bug, "feedback.bug_prompt", "feedback.bug_thanks"),
    "review": (FeedbackState.waiting_for_review, "feedback.review_prompt", "feedback.review_thanks"),
    "question": (FeedbackState.waiting_for_question, "faq.ask.prompt", "faq.ask.sent"),
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


# ============ Личный вопрос автору (из FAQ) ============

@router.callback_query(F.data == "faq:ask")
async def start_question(callback: CallbackQuery, state: FSMContext):
    """Юзер выбрал «задать вопрос автору» — переход в FSM ожидания."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await state.set_state(FeedbackState.waiting_for_question)
    await callback.message.edit_text(
        t("faq.ask.prompt", lang),
        reply_markup=cancel_keyboard(lang),
    )
    await callback.answer()


@router.message(FeedbackState.waiting_for_question)
async def receive_question(message: Message, state: FSMContext, bot: Bot):
    await _receive_feedback(message, state, bot, KIND_QUESTION)


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

    # Уведомление админу + (для вопросов и идей) сохраняем relay-маппинг,
    # чтобы reply админа в группе долетел до автора.
    await _notify_admin(bot, message.from_user, lang, kind, text)


# ============ Ответ админа пользователю через reply в группе ============

# Множество chat_id фидбэк-групп — для быстрого фильтра входящих сообщений.
_FEEDBACK_GROUP_IDS = {cid for cid in FEEDBACK_CHAT_IDS.values() if cid}


@router.message(F.reply_to_message)
async def relay_admin_reply(message: Message, bot: Bot):
    """Reply админа в фидбэк-группе → пересылка автору в ЛС.

    Срабатывает только при выполнении ВСЕХ условий:
      - сообщение из чата, числящегося в FEEDBACK_CHAT_IDS;
      - это reply на сообщение бота;
      - отправитель — администратор (ADMIN_IDS);
      - в БД есть FeedbackRelay для (chat_id, reply_to.message_id).

    Иначе пропускаем дальше — обычный чат в группе не должен ломаться.
    """
    if not _FEEDBACK_GROUP_IDS or message.chat.id not in _FEEDBACK_GROUP_IDS:
        return
    if not message.from_user or message.from_user.id not in ADMIN_IDS:
        return
    reply_to = message.reply_to_message
    if not reply_to or not reply_to.from_user or not reply_to.from_user.is_bot:
        return

    relay = await FeedbackService.find_relay(message.chat.id, reply_to.message_id)
    if relay is None:
        return  # это reply на какое-то другое сообщение бота — не наше

    reply_text = (message.text or message.caption or "").strip()
    if not reply_text:
        return

    # Локализуем префикс под язык юзера, если знаем; иначе ru как дефолт.
    target_user = await UserService.get(relay.user_tg_id)
    user_lang = target_user.lang if target_user else "ru"

    final_text = t("faq.ask.reply_prefix", user_lang) + "\n\n" + html.escape(reply_text)

    try:
        await bot.send_message(relay.user_tg_id, final_text, parse_mode="HTML")
    except Exception as e:
        # Если юзер заблокировал бота / закрыл ЛС — сообщаем в ту же группу.
        logger.warning(f"Relay-ответ не доставлен юзеру {relay.user_tg_id}: {e}")
        try:
            await message.reply(t("faq.ask.delivery_failed", "ru"))
        except Exception:
            pass
        return

    # Подтверждение в группе, что доставлено (тихая reaction-like подсказка).
    try:
        await message.reply(t("faq.ask.delivery_ok", "ru"))
    except Exception:
        pass


async def _notify_admin(bot: Bot, tg_user, lang: str, kind: str, text: str):
    """Шлём уведомление о новом фидбеке.

    Каждый тип уходит в свою Telegram-группу (если её ID задан в конфиге),
    иначе — всем админам в личку. Для каждого успешно доставленного в ГРУППУ
    сообщения сохраняется FeedbackRelay — это нужно, чтобы ответ админа
    (reply на бот-сообщение в группе) был переадресован пользователю в ЛС.
    """
    kind_emoji = {"idea": "💡", "bug": "🐞", "review": "😊", "question": "❓"}
    kind_label = {"idea": "ИДЕЯ", "bug": "БАГ", "review": "ОТЗЫВ", "question": "ВОПРОС"}

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

    # Хэштеги для быстрой фильтрации в группе.
    hashtag = {"idea": "#идея", "bug": "#баг", "review": "#отзыв", "question": "#вопрос"}.get(kind, "")
    hashtag_line = f"\n\n{hashtag}" if hashtag else ""

    # Для вопросов — короткая подсказка админу: ответить reply'ем на это сообщение.
    reply_hint = ""
    if kind == KIND_QUESTION:
        reply_hint = "\n\n<i>↩ Ответьте reply'ем на это сообщение — текст уйдёт автору в ЛС.</i>"

    admin_text = (
        f"{emoji} <b>Новый {label}</b>\n\n"
        f"{info_block}\n\n"
        f"<i>{html.escape(text)}</i>"
        f"{reply_hint}"
        f"{hashtag_line}"
    )

    # Если для типа задана группа — шлём в неё, иначе в личку админам
    group_chat_id = FEEDBACK_CHAT_IDS.get(kind)
    # Вопросы дополнительно мапим на группу «идей», если своей нет.
    if not group_chat_id and kind == KIND_QUESTION:
        group_chat_id = FEEDBACK_CHAT_IDS.get(KIND_IDEA)

    targets = [group_chat_id] if group_chat_id else ADMIN_IDS

    for target in targets:
        try:
            sent = await bot.send_message(target, admin_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление ({kind}) в {target}: {e}")
            continue

        # Сохраняем relay только для отправок в ГРУППУ (target == group_chat_id),
        # т.к. ответ в ЛС админу не имеет смысла «передавать» через бота.
        if group_chat_id and target == group_chat_id:
            try:
                await FeedbackService.save_relay(
                    group_chat_id=target,
                    group_message_id=sent.message_id,
                    user_tg_id=tg_user.id,
                    kind=kind,
                )
            except Exception as e:
                logger.warning(f"Не удалось сохранить FeedbackRelay ({kind}) {target}/{sent.message_id}: {e}")
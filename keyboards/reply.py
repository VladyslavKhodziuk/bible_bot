"""Постоянная reply-клавиатура (основные кнопки) и inline-клавиатуры рубрики FAQ.

Reply-клавиатура «прилипает» к полю ввода и держится весь сеанс — показываем её
один раз на /start (см. handlers/start.py). Кнопки шлют свой текст обычным
сообщением, поэтому их ловит handlers/reply_menu.py точным матчем ярлыка.
"""
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from services.i18n import t

# Идентификаторы вопросов FAQ. Порядок = порядок кнопок на экране.
FAQ_IDS = ["can_do", "help_me", "what_here", "progress", "free", "start"]


def main_reply_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Основные кнопки внизу: Главное меню · Настройки | Частые вопросы · Поддержать проект."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("reply.main_menu", lang))
    builder.button(text=t("reply.settings", lang))
    builder.button(text=t("reply.faq", lang))
    builder.button(text=t("reply.support", lang))
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def faq_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Список вопросов FAQ + возврат в меню.

    Кнопка «задать вопрос автору» временно скрыта — фича дорабатывается.
    Когда будет готова, расскомментировать строку faq.ask.button ниже;
    обработчик `faq:ask` в handlers/feedback.py уже на месте.
    """
    builder = InlineKeyboardBuilder()
    for qid in FAQ_IDS:
        builder.button(text=t(f"faq.q.{qid}", lang), callback_data=f"faq:q:{qid}")
    # builder.button(text=t("faq.ask.button", lang), callback_data="faq:ask")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


def faq_answer_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Под ответом на вопрос: назад к списку вопросов + в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("faq.back", lang), callback_data="faq:menu")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()

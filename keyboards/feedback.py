from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой 'Отмена' — для отмены ввода идеи/бага/отзыва."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("feedback.cancel", lang),
        callback_data="fb:cancel"
    )
    return builder.as_markup()


def after_idea_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопки после успешной отправки идеи или бага."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("cabinet.back_to_cabinet", lang),
        callback_data="cabinet"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()


def after_review_keyboard(lang: str) -> InlineKeyboardMarkup:
    """После отзыва: предложение поддержать проект + возврат."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("feedback.support_button", lang),
        callback_data="donate"
    )
    builder.button(
        text=t("feedback.later_button", lang),
        callback_data="cabinet"
    )
    builder.adjust(1)
    return builder.as_markup()
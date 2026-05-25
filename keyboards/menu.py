from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def welcome_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопки после приветствия: открыть меню + сменить часовой пояс.

    Пояс по умолчанию — Europe/Madrid; кнопка даёт юзерам из других регионов
    поправить его сразу, чтобы стих дня приходил в их локальное время.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("welcome.button", lang),
        callback_data="open_menu"
    )
    builder.button(
        text=t("welcome.change_timezone", lang),
        callback_data="onboard:tz"
    )
    builder.adjust(1)
    return builder.as_markup()


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Главное меню с основными разделами бота."""
    builder = InlineKeyboardBuilder()

    # 1: Читать Библию (главная кнопка)
    builder.button(text=t("menu.read", lang), callback_data="read")
    # 2: План чтения | Случайный стих
    builder.button(text=t("plan.menu_button", lang), callback_data="plan")
    builder.button(text=t("menu.random", lang), callback_data="random")
    # 3: Получить ответ · ИИ
    builder.button(text=t("menu.ai_pastor", lang), callback_data="ai_pastor")
    # 4: Помолиться | Мудрость дня
    builder.button(text=t("menu.pray", lang), callback_data="pray")
    builder.button(text=t("menu.wisdom", lang), callback_data="wisdom")
    # 5: Мой кабинет
    builder.button(text=t("menu.cabinet", lang), callback_data="cabinet")

    builder.adjust(1, 2, 1, 2, 1)
    return builder.as_markup()
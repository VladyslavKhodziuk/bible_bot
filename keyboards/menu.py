from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def welcome_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопка 'Открыть меню' после приветствия."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("welcome.button", lang),
        callback_data="open_menu"
    )
    return builder.as_markup()


def main_menu_keyboard(lang: str, plan_day: int | None = None) -> InlineKeyboardMarkup:
    """Главное меню с основными разделами бота.

    plan_day: текущий день активного плана (None если плана нет).
    """
    builder = InlineKeyboardBuilder()

    # 1: Поговорить с пастырем
    builder.button(text=t("menu.ai_pastor", lang), callback_data="ai_pastor")
    # 2: Читать | Поиск
    builder.button(text=t("menu.read", lang), callback_data="read")
    builder.button(text=t("menu.search", lang), callback_data="search")
    # 3: По настроению | Наугад
    builder.button(text=t("menu.topics", lang), callback_data="topics")
    builder.button(text=t("menu.random", lang), callback_data="random")
    # 4: План чтения (с днём, если есть активный план)
    if plan_day:
        plan_text = t("plan.menu_button_active", lang, day=plan_day)
    else:
        plan_text = t("plan.menu_button", lang)
    builder.button(text=plan_text, callback_data="plan")
    # 5: Кабинет | Поддержать
    builder.button(text=t("menu.cabinet", lang), callback_data="cabinet")
    builder.button(text=t("menu.donate", lang), callback_data="donate")

    builder.adjust(1, 2, 2, 1, 2)
    return builder.as_markup()
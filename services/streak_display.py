from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def format_streak_indicator(streak: int, lang: str) -> str:
    """Форматирует индикатор серии. Если 0 — пустая строка."""
    if streak <= 0:
        return ""
    if streak == 1:
        return t("streak.indicator_single", lang)
    return t("streak.indicator", lang, days=streak)


def get_milestone_message(milestone: int, lang: str) -> str | None:
    """Возвращает поздравительное сообщение для милстоуна, или None если нет."""
    msg = t(f"streak.milestones.{milestone}", lang)
    # i18n возвращает "[key]" если ключ не найден
    if msg.startswith("[") and msg.endswith("]"):
        return None
    return msg


def get_daily_progress_message(streak: int, lang: str) -> str:
    """Поздравление с ростом серии в обычный (не milestone) день."""
    return t("streak.daily_progress", lang, streak=streak)


def format_prayer_streak_indicator(streak: int, lang: str) -> str:
    """Индикатор молитвенного стрика. Если 0 — пустая строка."""
    if streak <= 0:
        return ""
    if streak == 1:
        return t("pray.streak.indicator_single", lang)
    return t("pray.streak.indicator", lang, days=streak)


def get_prayer_milestone_message(milestone: int, lang: str) -> str | None:
    """Поздравление с молитвенным милстоуном, или None если нет."""
    msg = t(f"pray.streak.milestones.{milestone}", lang)
    if msg.startswith("[") and msg.endswith("]"):
        return None
    return msg


def get_prayer_daily_progress_message(streak: int, lang: str) -> str:
    """Поздравление с ростом молитвенной серии в обычный день."""
    return t("pray.streak.daily_progress", lang, streak=streak)


def build_dismiss_keyboard(lang: str, *, dismiss_key: str) -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой «Понятно 🙌», удаляющей сообщение.

    ``dismiss_key`` — i18n-ключ для текста кнопки
    (``streak.onboarding_button`` или ``pray.streak.onboarding_button``).
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(dismiss_key, lang),
        callback_data="streak:onboarding_done",
    )
    return builder.as_markup()


def build_milestone_keyboard(lang: str, *, dismiss_key: str) -> InlineKeyboardMarkup:
    """Клавиатура для milestone-сообщения: «Поддержать проект» + «Понятно 🙌».

    «Поддержать проект» открывает донат-флоу (callback ``donate``),
    «Понятно 🙌» удаляет сообщение.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("streak.donate_button", lang),
        callback_data="donate",
    )
    builder.button(
        text=t(dismiss_key, lang),
        callback_data="streak:onboarding_done",
    )
    builder.adjust(1)
    return builder.as_markup()


def with_donate_addendum(milestone_text: str, lang: str) -> str:
    """Дописывает к milestone-сообщению блок про поддержку проекта."""
    return f"{milestone_text}\n\n{t('streak.donate_addendum', lang)}"
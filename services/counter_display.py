from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.counter_service import CounterResult
from services.prayer_counter_service import PrayerCounterResult
from services.i18n import t


def format_counter_indicator(count: int, lang: str) -> str:
    """Форматирует индикатор счётчика. Если 0 — пустая строка."""
    if count <= 0:
        return ""
    if count == 1:
        return t("counter.indicator_single", lang)
    return t("counter.indicator", lang, days=count)


def get_milestone_message(milestone: int, lang: str) -> str | None:
    """Возвращает поздравительное сообщение для вехи, или None если нет."""
    msg = t(f"counter.milestones.{milestone}", lang)
    # i18n возвращает "[key]" если ключ не найден
    if msg.startswith("[") and msg.endswith("]"):
        return None
    return msg


def get_daily_progress_message(count: int, lang: str) -> str:
    """Сообщение с ростом счётчика в обычный (не milestone) день."""
    return t("counter.daily_progress", lang, streak=count)


def format_prayer_counter_indicator(count: int, lang: str) -> str:
    """Индикатор молитвенного счётчика. Если 0 — пустая строка."""
    if count <= 0:
        return ""
    if count == 1:
        return t("pray.counter.indicator_single", lang)
    return t("pray.counter.indicator", lang, days=count)


def get_prayer_milestone_message(milestone: int, lang: str) -> str | None:
    """Поздравление с молитвенной вехой, или None если нет."""
    msg = t(f"pray.counter.milestones.{milestone}", lang)
    if msg.startswith("[") and msg.endswith("]"):
        return None
    return msg


def get_prayer_daily_progress_message(count: int, lang: str) -> str:
    """Сообщение с ростом молитвенного счётчика в обычный день."""
    return t("pray.counter.daily_progress", lang, streak=count)


def get_plan_milestone_message(percent: int, lang: str) -> str | None:
    """Поздравление с прохождением вехи плана (25/50/75 %), или None."""
    msg = t(f"plan.milestone_{percent}", lang)
    if msg.startswith("[") and msg.endswith("]"):
        return None
    return msg


def build_dismiss_keyboard(lang: str, *, dismiss_key: str) -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой «Понятно 🙌», удаляющей сообщение.

    ``dismiss_key`` — i18n-ключ для текста кнопки
    (``counter.onboarding_button`` или ``pray.counter.onboarding_button``).
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t(dismiss_key, lang),
        callback_data="counter:onboarding_done",
    )
    return builder.as_markup()


def build_milestone_keyboard(lang: str, *, dismiss_key: str) -> InlineKeyboardMarkup:
    """Клавиатура для milestone-сообщения: «Поддержать проект» + «Понятно 🙌».

    «Поддержать проект» открывает донат-флоу (callback ``donate``),
    «Понятно 🙌» удаляет сообщение.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("counter.donate_button", lang),
        callback_data="donate",
    )
    builder.button(
        text=t(dismiss_key, lang),
        callback_data="counter:onboarding_done",
    )
    builder.adjust(1)
    return builder.as_markup()


def with_donate_addendum(milestone_text: str, lang: str) -> str:
    """Дописывает к milestone-сообщению блок про поддержку проекта."""
    return f"{milestone_text}\n\n{t('counter.donate_addendum', lang)}"


# ============ Единый билдер «что показать после засчитанного дня» ============
# Возвращает (text, keyboard, is_onboarding) либо None. Чистый билдер без I/O:
# само отправление и mark_explained делает вызывающий (verse/read/scheduler),
# поэтому ветки решения не расходятся между интерактивом и рассылкой.

def build_counter_extra(
    result: CounterResult, lang: str
) -> tuple[str, InlineKeyboardMarkup, bool] | None:
    """Доп. сообщение после засчитанного дня чтения.

    Приоритет: онбординг (если ещё не показывали) → веха → обычный день роста.
    ``is_onboarding=True`` сигналит вызывающему вызвать ``mark_explained``.
    """
    if not result.already_explained:
        return (
            t("counter.onboarding", lang),
            build_dismiss_keyboard(lang, dismiss_key="counter.onboarding_button"),
            True,
        )
    if result.milestone_reached:
        msg = get_milestone_message(result.milestone_reached, lang)
        if msg:
            return (
                with_donate_addendum(msg, lang),
                build_milestone_keyboard(lang, dismiss_key="counter.onboarding_button"),
                False,
            )
        return None
    if result.streak_grew:
        return (
            get_daily_progress_message(result.count, lang),
            build_dismiss_keyboard(lang, dismiss_key="counter.onboarding_button"),
            False,
        )
    return None


def build_prayer_extra(
    result: PrayerCounterResult, lang: str
) -> tuple[str, InlineKeyboardMarkup, bool] | None:
    """Доп. сообщение после «Аминь». Зеркало build_counter_extra для молитвы.

    Онбординг гейтится на is_first_time: у молитвы единственное место touch()
    и оно всегда показывает extras. ``is_onboarding`` каллер игнорирует —
    молитвенного флага нет.
    """
    if result.is_first_time:
        return (
            t("pray.counter.onboarding", lang),
            build_dismiss_keyboard(lang, dismiss_key="pray.counter.onboarding_button"),
            True,
        )
    if result.milestone_reached:
        msg = get_prayer_milestone_message(result.milestone_reached, lang)
        if msg:
            return (
                with_donate_addendum(msg, lang),
                build_milestone_keyboard(lang, dismiss_key="pray.counter.onboarding_button"),
                False,
            )
        return None
    if result.streak_grew:
        return (
            get_prayer_daily_progress_message(result.count, lang),
            build_dismiss_keyboard(lang, dismiss_key="pray.counter.onboarding_button"),
            False,
        )
    return None

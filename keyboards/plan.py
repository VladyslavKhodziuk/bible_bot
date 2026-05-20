from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.plan_service import PlanService


def plan_list_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Список доступных планов (когда у юзера нет активного)."""
    builder = InlineKeyboardBuilder()

    for plan in PlanService.get_all_plans():
        plan_id = plan["id"]
        emoji = plan.get("emoji", "📖")
        name = PlanService.get_plan_name(plan_id, lang)
        days = plan.get("duration_days", 0)
        builder.button(
            text=f"{emoji} {name}",
            callback_data=f"plan:preview:{plan_id}"
        )

    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )

    builder.adjust(1)
    return builder.as_markup()


def plan_preview_keyboard(plan_id: str, lang: str) -> InlineKeyboardMarkup:
    """Превью плана (описание + кнопка 'Начать')."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("plan.preview_activate", lang),
        callback_data=f"plan:activate:{plan_id}"
    )
    builder.button(
        text=t("plan.preview_back", lang),
        callback_data="plan"
    )
    builder.adjust(1)
    return builder.as_markup()


def active_plan_keyboard(
    readings: list[dict],
    lang: str,
    book_names_map: dict[str, str],
    completed_today: bool = False,
) -> InlineKeyboardMarkup:
    """
    Клавиатура активного плана.

    readings: список вида [{"abbrev": "mt", "chapter": 1}, ...]
    book_names_map: {"mt": "Матфея", ...}
    completed_today: уже отмечал ли день сегодня (тогда кнопка чтения 0й главы)
    """
    builder = InlineKeyboardBuilder()
    layout = []

    # Кнопки чтения каждой главы — ведут в изолированный режим (plan:read:N)
    for idx, reading in enumerate(readings):
        abbrev = reading["abbrev"]
        chapter = reading["chapter"]
        book_name = book_names_map.get(abbrev, abbrev)
        builder.button(
            text=t("plan.active_open_chapter", lang, book=book_name, chapter=chapter),
            callback_data=f"plan:read:{idx}"
        )
        layout.append(1)

    # Действия (нет "Отметить" — это теперь только в режиме чтения)
    builder.button(
        text=t("plan.active_notification", lang),
        callback_data="plan:notif"
    )
    layout.append(1)

    builder.button(
        text=t("plan.active_change_plan", lang),
        callback_data="plan:change"
    )
    layout.append(1)

    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )
    layout.append(1)

    builder.adjust(*layout)
    return builder.as_markup()


def change_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Подтверждение смены плана."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("plan.change_confirm_yes", lang),
        callback_data="plan:change_yes"
    )
    builder.button(
        text=t("plan.change_confirm_no", lang),
        callback_data="plan"  # вернёмся к активному плану
    )
    builder.adjust(1)
    return builder.as_markup()


def completed_keyboard(lang: str) -> InlineKeyboardMarkup:
    """После завершения плана."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("plan.completed_choose_new", lang),
        callback_data="plan"  # снова открываем выбор
    )
    builder.button(
        text=t("plan.completed_to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()


def notification_settings_keyboard(
    enabled: bool,
    lang: str,
) -> InlineKeyboardMarkup:
    """Экран настройки уведомлений плана."""
    builder = InlineKeyboardBuilder()

    builder.button(
        text=t("plan.notif_set_time", lang),
        callback_data="plan:notif:set_time"
    )

    if enabled:
        builder.button(
            text=t("plan.notif_disable", lang),
            callback_data="plan:notif:disable"
        )
    else:
        builder.button(
            text=t("plan.notif_enable", lang),
            callback_data="plan:notif:enable"
        )

    builder.button(
        text="← " + t("plan.menu_button", lang),
        callback_data="plan"
    )

    builder.adjust(1)
    return builder.as_markup()


def time_picker_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Сетка времени 06:00 - 22:00 с шагом 1 час."""
    builder = InlineKeyboardBuilder()

    for hour in range(6, 23):
        time_str = f"{hour:02d}:00"
        builder.button(
            text=time_str,
            callback_data=f"plan:notif:time:{time_str}"
        )

    # Кнопка возврата
    builder.button(
        text="← " + t("plan.menu_button", lang),
        callback_data="plan:notif"
    )

    # Раскладка: 4 в ряд (всего 17 значений + кнопка возврата)
    builder.adjust(4, 4, 4, 4, 1, 1)
    return builder.as_markup()


def reading_mode_keyboard(
    reading_idx: int,
    total_readings: int,
    is_last: bool,
    lang: str,
) -> InlineKeyboardMarkup:
    """
    Клавиатура изолированного режима чтения.

    is_last: True если это последняя глава дня — тогда кнопка "Прочитал на сегодня всё"
             False — кнопка "Прочитано — следующая глава"
    """
    builder = InlineKeyboardBuilder()

    if is_last:
        builder.button(
            text=t("plan.read_complete_day", lang),
            callback_data="plan:mark_done"
        )
    else:
        builder.button(
            text=t("plan.read_next_chapter", lang),
            callback_data="plan:next_reading"
        )

    builder.button(
        text=t("plan.read_back_to_plan", lang),
        callback_data="plan"
    )
    builder.adjust(1)
    return builder.as_markup()


def day_done_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Клавиатура после завершения дня (не плана)."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("plan.back_to_plan", lang),
        callback_data="plan"
    )
    builder.button(
        text=t("plan.to_menu", lang),
        callback_data="open_menu"
    )
    builder.adjust(1)
    return builder.as_markup()
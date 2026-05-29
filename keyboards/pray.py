from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t

PRAYER_FAVORITES_PER_PAGE = 5


def prayer_fav_toggle_button(
    prayer_id: str,
    is_fav: bool,
    lang: str,
    return_to: str,
) -> tuple[str, str]:
    """(текст кнопки, callback_data) для тоггла избранной молитвы.

    return_to — куда возвращаться после действия: 'pray' (молитва дня) / 'rnd' (случайная).
    """
    if is_fav:
        text = t("pray.fav_remove_button", lang)
        action = "rm"
    else:
        text = t("pray.fav_add_button", lang)
        action = "add"
    return text, f"pf:{action}:{prayer_id}:{return_to}"


def pray_keyboard(lang: str, prayer_id: str, is_fav: bool) -> InlineKeyboardMarkup:
    """Клавиатура карточки «Молитва на сегодня».

    Раскладка:
      🙏 Аминь
      ⭐ В избранное   🎲 Случайная
      📁 По темам      📌 Мои молитвы
      🔔 Напомнить
      ← В меню
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=t("pray.amen_btn", lang), callback_data="pray:amen")
    fav_text, fav_data = prayer_fav_toggle_button(prayer_id, is_fav, lang, "pray")
    builder.button(text=fav_text, callback_data=fav_data)
    builder.button(text=t("pray.btn_random", lang), callback_data="pray:random")
    builder.button(text=t("pray.btn_topics", lang), callback_data="pray:topics")
    builder.button(text=t("pray.btn_my", lang), callback_data="pray:my")
    builder.button(text=t("pray.btn_remind", lang), callback_data="pray_notif:open")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1, 2, 2, 1, 1)
    return builder.as_markup()


def pray_after_amen_keyboard(
    lang: str, prayer_id: str, is_fav: bool
) -> InlineKeyboardMarkup:
    """Клавиатура после нажатия «Аминь» — Аминь больше не предлагается."""
    builder = InlineKeyboardBuilder()
    fav_text, fav_data = prayer_fav_toggle_button(prayer_id, is_fav, lang, "pray")
    builder.button(text=fav_text, callback_data=fav_data)
    builder.button(text=t("pray.btn_random", lang), callback_data="pray:random")
    builder.button(text=t("pray.btn_topics", lang), callback_data="pray:topics")
    builder.button(text=t("pray.btn_my", lang), callback_data="pray:my")
    builder.button(text=t("pray.btn_remind", lang), callback_data="pray_notif:open")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def pray_random_keyboard(
    lang: str, prayer_id: str, is_fav: bool
) -> InlineKeyboardMarkup:
    """Клавиатура экрана случайной молитвы.

    Раскладка:
      ⭐ В избранное
      🎲 Ещё одна
      ← К молитве дня   ← В меню
    """
    builder = InlineKeyboardBuilder()
    fav_text, fav_data = prayer_fav_toggle_button(prayer_id, is_fav, lang, "rnd")
    builder.button(text=fav_text, callback_data=fav_data)
    builder.button(text=t("pray.btn_another_random", lang), callback_data="pray:random")
    builder.button(text=t("pray.back_to_card", lang), callback_data="pray")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1, 1, 2)
    return builder.as_markup()


def pray_topics_menu_keyboard(sections: list[dict], lang: str) -> InlineKeyboardMarkup:
    """Меню «По темам»: кнопки тем, сгруппированные по секциям (layout из YAML).

    Подзаголовки секций печатаются в тексте сообщения, здесь — только кнопки.
    """
    builder = InlineKeyboardBuilder()
    rows: list[int] = []

    for section in sections:
        topics = section.get("topics", [])
        for topic in topics:
            name = (topic.get("names") or {}).get(lang) or (topic.get("names") or {}).get("en", "")
            emoji = topic.get("emoji", "")
            label = f"{emoji} {name}".strip()
            builder.button(text=label, callback_data=f"pray:tp:{topic['id']}")
        layout = section.get("layout") or [1] * len(topics)
        rows.extend(layout)

    builder.button(text=t("pray.back_to_card", lang), callback_data="pray")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    rows.extend([1, 1])

    builder.adjust(*rows)
    return builder.as_markup()


def pray_topic_card_keyboard(
    lang: str, topic_id: str, prayer_id: str, is_fav: bool, *, is_pool: bool
) -> InlineKeyboardMarkup:
    """Карточка молитвы темы: избранное, (для пула) «Другая», назад к темам / в меню."""
    builder = InlineKeyboardBuilder()
    fav_text, fav_data = prayer_fav_toggle_button(prayer_id, is_fav, lang, f"tp_{topic_id}")
    builder.button(text=fav_text, callback_data=fav_data)

    rows = [1]
    if is_pool:
        builder.button(
            text=t("pray.btn_another_in_topic", lang),
            callback_data=f"pray:tp:{topic_id}:r:{prayer_id}",
        )
        rows.append(1)

    builder.button(text=t("pray.back_to_topics", lang), callback_data="pray:topics")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    rows.append(2)

    builder.adjust(*rows)
    return builder.as_markup()


def prayer_favorites_list_keyboard(
    items: list[tuple[str, str]],
    page: int,
    total: int,
    lang: str,
) -> InlineKeyboardMarkup:
    """Список избранных молитв с пагинацией.

    items — список (prayer_id, title). Работает и для пустого списка.
    """
    builder = InlineKeyboardBuilder()
    rows = []

    for prayer_id, title in items:
        builder.button(text=f"📌 {title}", callback_data=f"pf:view:{prayer_id}")
        rows.append(1)

    if total > 0:
        total_pages = (total + PRAYER_FAVORITES_PER_PAGE - 1) // PRAYER_FAVORITES_PER_PAGE
        nav_count = 0
        if page > 0:
            builder.button(text="◀️", callback_data=f"pf:list:{page - 1}")
            nav_count += 1
        if total_pages > 1:
            builder.button(text=f"{page + 1}/{total_pages}", callback_data="noop")
            nav_count += 1
        if page < total_pages - 1:
            builder.button(text="▶️", callback_data=f"pf:list:{page + 1}")
            nav_count += 1
        if nav_count > 0:
            rows.append(nav_count)

    builder.button(text=t("pray.back_to_card", lang), callback_data="pray")
    rows.append(1)
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    rows.append(1)

    builder.adjust(*rows)
    return builder.as_markup()


def prayer_favorite_view_keyboard(prayer_id: str, lang: str) -> InlineKeyboardMarkup:
    """Просмотр одной избранной молитвы: удалить, назад к списку, в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("pray.my_delete", lang), callback_data=f"pf:del:{prayer_id}")
    builder.button(text=t("pray.back_to_list", lang), callback_data="pf:list:0")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


def pray_stub_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Фолбэк, когда молитва не подобрана: возврат к карточке / в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("pray.back_to_card", lang), callback_data="pray")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()

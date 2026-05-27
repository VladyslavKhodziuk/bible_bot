from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t


def pray_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Клавиатура карточки «Молитва на сегодня».

    Раскладка:
      🙏 Аминь
      📁 По темам      📌 Мои молитвы
      🔔 Напомнить
      ← В меню
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=t("pray.amen_btn", lang), callback_data="pray:amen")
    builder.button(text=t("pray.btn_topics", lang), callback_data="pray:topics")
    builder.button(text=t("pray.btn_my", lang), callback_data="pray:my")
    builder.button(text=t("pray.btn_remind", lang), callback_data="pray_notif:open")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1, 2, 1, 1)
    return builder.as_markup()


def pray_after_amen_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Клавиатура после нажатия «Аминь» — Аминь больше не предлагается."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("pray.btn_topics", lang), callback_data="pray:topics")
    builder.button(text=t("pray.btn_my", lang), callback_data="pray:my")
    builder.button(text=t("pray.btn_remind", lang), callback_data="pray_notif:open")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def pray_stub_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Заглушка для «По темам» / «Мои молитвы» — пока возврат к карточке."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("pray.back_to_card", lang), callback_data="pray")
    builder.button(text=t("common.back_to_menu", lang), callback_data="open_menu")
    builder.adjust(1)
    return builder.as_markup()


# Алиас на случай, если где-то ещё ссылаются по старому имени
pray_topics_soon_keyboard = pray_stub_keyboard

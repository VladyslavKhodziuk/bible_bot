from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    DONATE_BUYMEACOFFEE_URL,
    DONATE_PAYPAL_URL,
    DONATE_CRYPTO_URL,
    DONATE_STAR_PRESETS,
)
from services.i18n import t


def donate_main_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Главный экран доната: Stars + внешние ссылки + инфо."""
    builder = InlineKeyboardBuilder()

    # Основная кнопка — Telegram Stars
    builder.button(
        text=t("donate.stars_button", lang),
        callback_data="donate:stars"
    )

    # Внешние ссылки — показываем только если URL задан
    if DONATE_BUYMEACOFFEE_URL:
        builder.button(
            text=t("donate.buymeacoffee_button", lang),
            url=DONATE_BUYMEACOFFEE_URL
        )

    if DONATE_CRYPTO_URL:
        builder.button(
            text=t("donate.crypto_button", lang),
            url=DONATE_CRYPTO_URL
        )

    if DONATE_PAYPAL_URL:
        builder.button(
            text=t("donate.paypal_button", lang),
            url=DONATE_PAYPAL_URL
        )

    # Информационная кнопка
    builder.button(
        text=t("donate.where_button", lang),
        callback_data="donate:where"
    )

    # Навигация
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )

    # Раскладка: все кнопки по одной в ряд
    builder.adjust(1)
    return builder.as_markup()


def donate_stars_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Выбор суммы звёзд: пресеты + произвольная + назад."""
    builder = InlineKeyboardBuilder()

    # Пресеты из конфига
    for stars, usd in DONATE_STAR_PRESETS:
        builder.button(
            text=t("donate.preset_label", lang, amount=stars, usd=usd),
            callback_data=f"donate:pay:{stars}"
        )

    # Произвольная сумма
    builder.button(
        text=t("donate.custom_amount", lang),
        callback_data="donate:custom"
    )

    # Назад
    builder.button(
        text=t("donate.back", lang),
        callback_data="donate"
    )

    # Раскладка: все по одной
    builder.adjust(1)
    return builder.as_markup()


def donate_where_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопка 'Назад' с экрана «Куда идут средства»."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("donate.back", lang),
        callback_data="donate"
    )
    return builder.as_markup()


def donate_cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопка отмены при вводе произвольной суммы."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("donate.cancel", lang),
        callback_data="donate:cancel_custom"
    )
    return builder.as_markup()

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    DONATE_MONOBANK_URL,
    DONATE_REVOLUT_URL,
    DONATE_PAYPAL_URL,
    DONATE_CRYPTO_URL,
    DONATE_STAR_PRESETS,
)
from services.i18n import t


def donate_region_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Выбор региона перед показом способов оплаты (только uk/ru)."""
    builder = InlineKeyboardBuilder()

    builder.button(
        text=t("donate.region_ua", lang),
        callback_data="donate:region:ua"
    )
    builder.button(
        text=t("donate.region_other", lang),
        callback_data="donate:region:other"
    )

    # Навигация
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )

    builder.adjust(1)
    return builder.as_markup()


def donate_main_keyboard(lang: str, region: str = "other") -> InlineKeyboardMarkup:
    """Главный экран доната: Stars + региональные ссылки + инфо."""
    builder = InlineKeyboardBuilder()

    # Основная кнопка — Telegram Stars
    builder.button(
        text=t("donate.stars_button", lang),
        callback_data="donate:stars"
    )

    # Monobank — только для региона "ua"
    if region == "ua" and DONATE_MONOBANK_URL:
        builder.button(
            text=t("donate.monobank_button", lang),
            callback_data="donate:monobank"
        )

    # Revolut — для всех (как "Поддержка любой картой")
    if DONATE_REVOLUT_URL:
        builder.button(
            text=t("donate.revolut_button", lang),
            url=DONATE_REVOLUT_URL
        )

    # PayPal — только для региона "other"
    if region == "other" and DONATE_PAYPAL_URL:
        builder.button(
            text=t("donate.paypal_button", lang),
            url=DONATE_PAYPAL_URL
        )

    # Крипто — для всех (если URL задан)
    if DONATE_CRYPTO_URL:
        builder.button(
            text=t("donate.crypto_button", lang),
            url=DONATE_CRYPTO_URL
        )

    # Информационная кнопка
    builder.button(
        text=t("donate.where_button", lang),
        callback_data="donate:where"
    )

    # Навигация — назад к выбору региона (для uk/ru) или в меню (для en/es)
    if lang in ("uk", "ru"):
        builder.button(
            text=t("donate.back", lang),
            callback_data="donate"
        )
    else:
        builder.button(
            text=t("common.back_to_menu", lang),
            callback_data="open_menu"
        )

    # Раскладка: все кнопки по одной в ряд
    builder.adjust(1)
    return builder.as_markup()


def donate_monobank_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопки под текстом банки Monobank."""
    builder = InlineKeyboardBuilder()

    builder.button(
        text=t("donate.monobank_open", lang),
        url=DONATE_MONOBANK_URL
    )
    builder.button(
        text=t("donate.back", lang),
        callback_data="donate:region:ua"
    )
    builder.button(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu"
    )

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

    # Назад — к главному экрану доната (через region callback)
    builder.button(
        text=t("donate.back", lang),
        callback_data="donate:back_to_main"
    )

    # Раскладка: все по одной
    builder.adjust(1)
    return builder.as_markup()


def donate_where_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопка 'Назад' с экрана «Куда идут средства»."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("donate.back", lang),
        callback_data="donate:back_to_main"
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

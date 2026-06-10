from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    DONATE_MONOBANK_URL,
    DONATE_REVOLUT_URL,
    DONATE_PAYPAL_URL,
    DONATE_CRYPTO_URL,
    DONATE_BIZUM_PHONE,
    DONATE_STAR_PRESETS,
)
from services.i18n import t


def donate_main_keyboard(lang: str, in_spain: bool = False) -> InlineKeyboardMarkup:
    """Главный экран доната: Stars + способы оплаты по языку/таймзоне + инфо."""
    builder = InlineKeyboardBuilder()

    # Основная кнопка — Telegram Stars
    builder.row(InlineKeyboardButton(
        text=t("donate.stars_button", lang),
        callback_data="donate:stars",
    ))

    # Monobank — для украино/русскоязычной аудитории
    if lang in ("uk", "ru") and DONATE_MONOBANK_URL:
        builder.row(InlineKeyboardButton(
            text=t("donate.monobank_button", lang),
            callback_data="donate:monobank",
        ))

    # Bizum (испанская таймзона) + Revolut — в одном ряду
    pay_row = []
    if in_spain and DONATE_BIZUM_PHONE:
        pay_row.append(InlineKeyboardButton(
            text=t("donate.bizum_button", lang),
            callback_data="donate:bizum",
        ))
    if DONATE_REVOLUT_URL:
        pay_row.append(InlineKeyboardButton(
            text=t("donate.revolut_button", lang),
            url=DONATE_REVOLUT_URL,
        ))
    if pay_row:
        builder.row(*pay_row)

    # PayPal — для всех (если URL задан)
    if DONATE_PAYPAL_URL:
        builder.row(InlineKeyboardButton(
            text=t("donate.paypal_button", lang),
            url=DONATE_PAYPAL_URL,
        ))

    # Крипто — для всех (если URL задан)
    if DONATE_CRYPTO_URL:
        builder.row(InlineKeyboardButton(
            text=t("donate.crypto_button", lang),
            url=DONATE_CRYPTO_URL,
        ))

    # Информационная кнопка
    builder.row(InlineKeyboardButton(
        text=t("donate.where_button", lang),
        callback_data="donate:where",
    ))

    # Проблема с оплатой — ведёт в поток репорта о проблеме
    builder.row(InlineKeyboardButton(
        text=t("donate.problem_button", lang),
        callback_data="fb:start:bug",
    ))

    builder.row(InlineKeyboardButton(
        text=t("common.back_to_menu", lang),
        callback_data="open_menu",
    ))

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
        callback_data="donate:back_to_main"
    )

    builder.adjust(1)
    return builder.as_markup()


def donate_bizum_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Кнопки под реквизитами Bizum: копировать номер (нативный copy_text) + назад."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("donate.bizum_copy", lang),
        copy_text=CopyTextButton(text=DONATE_BIZUM_PHONE),
    )
    builder.button(
        text=t("donate.back", lang),
        callback_data="donate:back_to_main"
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

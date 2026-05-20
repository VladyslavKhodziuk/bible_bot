import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, LabeledPrice

from config import ADMIN_IDS, DONATE_STARS_MIN, DONATE_STARS_MAX
from services.user_service import UserService
from services.donate_service import DonateService
from services.i18n import t
from keyboards.donate import (
    donate_main_keyboard,
    donate_stars_keyboard,
    donate_where_keyboard,
    donate_cancel_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()


# ============ FSM-состояния ============

class DonateState(StatesGroup):
    waiting_for_amount = State()


# ============ Главный экран доната ============

@router.callback_query(F.data == "donate")
async def show_donate(callback: CallbackQuery, state: FSMContext):
    """Показать главный экран доната."""
    # Сбрасываем FSM если юзер вернулся назад из ввода суммы
    await state.clear()

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("donate.title", lang),
        reply_markup=donate_main_keyboard(lang)
    )
    await callback.answer()


# ============ Экран выбора суммы Stars ============

@router.callback_query(F.data == "donate:stars")
async def show_stars_presets(callback: CallbackQuery):
    """Показать пресеты для Telegram Stars."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("donate.choose_amount", lang),
        reply_markup=donate_stars_keyboard(lang)
    )
    await callback.answer()


# ============ Оплата по пресету ============

@router.callback_query(F.data.startswith("donate:pay:"))
async def send_stars_invoice(callback: CallbackQuery, bot: Bot):
    """Создать Invoice на выбранное количество звёзд."""
    amount = int(callback.data.split(":")[2])
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await _send_invoice(bot, callback.from_user.id, amount, lang)
    await callback.answer()


# ============ Произвольная сумма — начало FSM ============

@router.callback_query(F.data == "donate:custom")
async def start_custom_amount(callback: CallbackQuery, state: FSMContext):
    """Запросить произвольную сумму звёзд."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await state.set_state(DonateState.waiting_for_amount)

    await callback.message.edit_text(
        t("donate.enter_amount", lang, min=DONATE_STARS_MIN, max=DONATE_STARS_MAX),
        reply_markup=donate_cancel_keyboard(lang)
    )
    await callback.answer()


# ============ Произвольная сумма — отмена ============

@router.callback_query(F.data == "donate:cancel_custom")
async def cancel_custom_amount(callback: CallbackQuery, state: FSMContext):
    """Отменить ввод произвольной суммы, вернуться к выбору."""
    await state.clear()

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("donate.choose_amount", lang),
        reply_markup=donate_stars_keyboard(lang)
    )
    await callback.answer()


# ============ Произвольная сумма — получение числа ============

@router.message(DonateState.waiting_for_amount)
async def receive_custom_amount(message: Message, state: FSMContext, bot: Bot):
    """Получить число от юзера и создать Invoice."""
    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    text = (message.text or "").strip()

    # Проверяем, что это целое число в допустимом диапазоне
    try:
        amount = int(text)
        if amount < DONATE_STARS_MIN or amount > DONATE_STARS_MAX:
            raise ValueError
    except ValueError:
        await message.answer(
            t("donate.invalid_amount", lang, min=DONATE_STARS_MIN, max=DONATE_STARS_MAX)
        )
        return  # Остаёмся в FSM — ждём корректного ввода

    # Выходим из FSM и отправляем Invoice
    await state.clear()
    await _send_invoice(bot, message.from_user.id, amount, lang)


# ============ Экран «Куда идут средства» ============

@router.callback_query(F.data == "donate:where")
async def show_where_funds_go(callback: CallbackQuery):
    """Показать информацию о том, куда идут средства."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("donate.where_title", lang),
        reply_markup=donate_where_keyboard(lang)
    )
    await callback.answer()


# ============ Telegram Payments — pre_checkout ============

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Подтверждение pre-checkout. Для Stars всегда OK."""
    await pre_checkout_query.answer(ok=True)


# ============ Telegram Payments — successful_payment ============

@router.message(F.successful_payment)
async def process_successful_payment(message: Message, bot: Bot):
    """Обработка успешного платежа — сохранение + благодарность + уведомление."""
    payment = message.successful_payment
    amount = payment.total_amount  # для XTR это количество звёзд
    charge_id = payment.telegram_payment_charge_id
    provider_charge_id = payment.provider_payment_charge_id

    user = await UserService.get(message.from_user.id)
    lang = user.lang if user else "ru"

    # Сохраняем в БД
    await DonateService.add(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        amount=amount,
        telegram_payment_charge_id=charge_id,
        provider_payment_charge_id=provider_charge_id,
    )

    # Благодарим юзера
    await message.answer(
        t("donate.thanks", lang, amount=amount)
    )

    # Уведомляем админа
    await _notify_admin_donation(bot, message.from_user, amount)


# ============ Вспомогательные функции ============

async def _send_invoice(bot: Bot, chat_id: int, amount: int, lang: str):
    """Отправить Invoice на оплату через Telegram Stars."""
    await bot.send_invoice(
        chat_id=chat_id,
        title=t("donate.invoice_title", lang),
        description=t("donate.invoice_description", lang, amount=amount),
        payload=f"donate_{chat_id}_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label="Stars", amount=amount)],
        provider_token="",
    )


async def _notify_admin_donation(bot: Bot, tg_user, amount: int):
    """Уведомить всех админов о новом донате."""
    user_display = tg_user.first_name or "Юзер"
    if tg_user.username:
        user_display += f" (@{tg_user.username})"
    user_display += f" [id:{tg_user.id}]"

    admin_text = (
        f"⭐ <b>Новый донат!</b>\n\n"
        f"От: {user_display}\n"
        f"Сумма: <b>{amount} ⭐</b>\n"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")

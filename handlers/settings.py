from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.user_service import UserService
from services.i18n import t
from keyboards.language import language_keyboard
from keyboards.settings import (
    settings_keyboard,
    language_settings_keyboard,
)

router = Router()
def _build_settings_text(user, lang: str) -> str:
    """Текст главного экрана настроек."""
    language_name = t(f"settings.language_names.{lang}", lang)

    lines = [
        t("settings.title", lang),
        "",
        t("settings.current_language", lang, language=language_name),
    ]

    # Уведомления
    if user.notifications_enabled:
        notif_status = t("settings.notifications_on", lang, time=user.notification_time)
    else:
        notif_status = t("settings.notifications_off", lang)
    lines.append(t("settings.notifications", lang, status=notif_status))

    # Разделитель + подсказка о фидбеке
    lines.append("")
    lines.append(t("settings.feedback_section", lang))

    return "\n".join(lines)


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Команда /settings — открыть настройки откуда угодно."""
    user = await UserService.get(message.from_user.id)
    if user is None:
        # Не делал /start — отправляем на онбординг (выбор языка)
        await message.answer(t("language.choose"), reply_markup=language_keyboard())
        return

    await message.answer(
        _build_settings_text(user, user.lang),
        reply_markup=settings_keyboard(user, user.lang),
    )


@router.callback_query(F.data == "settings")
async def open_settings_from_menu(callback: CallbackQuery):
    """Открытие настроек из главного меню."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        _build_settings_text(user, lang),
        reply_markup=settings_keyboard(user, lang)
    )
    await callback.answer()


@router.callback_query(F.data == "settings:open")
async def open_settings(callback: CallbackQuery):
    """Возврат на экран настроек."""
    await open_settings_from_menu(callback)


# ============ Смена языка интерфейса ============

@router.callback_query(F.data == "settings:change_lang")
async def change_language_screen(callback: CallbackQuery):
    """Экран выбора нового языка."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("language.choose", lang),
        reply_markup=language_settings_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("changelang:"))
async def apply_new_language(callback: CallbackQuery):
    """Применение нового языка. Перевод Библии автоматически меняется на язык."""
    new_lang = callback.data.split(":")[1]
    await UserService.set_language(callback.from_user.id, new_lang)

    # Удаляем предыдущий экран (выбор языка), чтобы внимание было только на
    # новом сообщении о смене языка.
    try:
        await callback.message.delete()
    except Exception:
        pass  # уже удалено / слишком старое — не критично

    # Подтверждение смены языка с inline-кнопкой «В меню».
    # (Одно сообщение не может нести и inline-кнопку, и нижнюю reply-клавиатуру;
    # подписи нижней клавиатуры сменят язык при следующем /start.)
    builder = InlineKeyboardBuilder()
    builder.button(text=t("common.back_to_menu", new_lang), callback_data="open_menu")
    await callback.message.answer(
        t("language.changed", new_lang),
        reply_markup=builder.as_markup(),
    )
    await callback.answer()
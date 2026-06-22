from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from services.user_service import UserService
from services.i18n import t
from services.timezones import is_valid, label as tz_label
from keyboards.notifications import timezone_picker_keyboard
from keyboards.reply import main_reply_keyboard
from keyboards.settings import (
    settings_keyboard,
    language_settings_keyboard,
)

router = Router()
def _build_settings_text(user, lang: str) -> str:
    """Текст главного экрана настроек."""
    language_name = t(f"settings.language_names.{lang}", lang)

    if user.notifications_enabled:
        notif_status = t("settings.notifications_on", lang, time=user.notification_time)
    else:
        notif_status = t("settings.notifications_off", lang)

    lines = [
        t("settings.title", lang),
        t("settings.subtitle", lang),
        "",
        t("settings.current_language", lang, language=language_name),
        t("settings.notifications", lang, status=notif_status),
        t("settings.timezone", lang, timezone=tz_label(user.timezone, lang)),
        "",
        t("settings.feedback_section", lang),
    ]

    return "\n".join(lines)


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Команда /settings — открыть настройки откуда угодно.

    Если юзер ещё не зарегистрирован (зашёл сразу в /settings, минуя /start) —
    создаём запись с языком из Telegram language_code и сразу показываем настройки.
    """
    user, _ = await UserService.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        language_code=message.from_user.language_code,
    )
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

    # Подтверждение + сразу обновляем нижнюю reply-клавиатуру на новый язык.
    # Возврат в меню — через постоянную «🏠 Главное меню» внизу.
    await callback.message.answer(
        t("language.changed", new_lang),
        reply_markup=main_reply_keyboard(new_lang),
    )
    await callback.answer()


# ============ Смена часового пояса ============

@router.callback_query(F.data == "settings:tz")
async def choose_timezone(callback: CallbackQuery):
    """Экран выбора часового пояса (из настроек)."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("notifications.choose_timezone", lang),
        reply_markup=timezone_picker_keyboard(lang, current_tz=user.timezone if user else None),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:settz:"))
async def set_timezone(callback: CallbackQuery):
    """Сохранить пояс и вернуть на экран настроек."""
    tz_name = callback.data.split(":", 2)[2]  # IANA-имя (может содержать '/')

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    if not is_valid(tz_name):
        await callback.answer("⚠️", show_alert=True)
        return

    await UserService.set_timezone(callback.from_user.id, tz_name)
    user = await UserService.get(callback.from_user.id)

    await callback.answer(
        t("notifications.timezone_changed", lang, timezone=tz_label(tz_name, lang)),
        show_alert=False,
    )
    await callback.message.edit_text(
        _build_settings_text(user, lang),
        reply_markup=settings_keyboard(user, lang),
    )
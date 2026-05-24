from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.i18n import t
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

    await callback.answer(
        t("language.changed", new_lang),
        show_alert=True
    )

    user = await UserService.get(callback.from_user.id)
    await callback.message.edit_text(
        _build_settings_text(user, new_lang),
        reply_markup=settings_keyboard(user, new_lang)
    )
from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.i18n import t
from keyboards.settings import settings_keyboard, language_settings_keyboard

router = Router()


@router.callback_query(F.data == "settings")
async def open_settings_from_menu(callback: CallbackQuery):
    """Открытие настроек из главного меню."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    language_name = t(f"settings.language_names.{lang}", lang)

    text = (
        f"{t('settings.title', lang)}\n\n"
        f"{t('settings.current_language', lang, language=language_name)}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=settings_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "settings:open")
async def open_settings(callback: CallbackQuery):
    """Возврат на экран настроек (например, кнопка 'Назад' из выбора языка)."""
    await open_settings_from_menu(callback)


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
    """Применение нового языка из настроек."""
    new_lang = callback.data.split(":")[1]

    await UserService.set_language(callback.from_user.id, new_lang)

    # Подтверждение всплывашкой на новом языке
    await callback.answer(
        t("language.changed", new_lang),
        show_alert=True
    )

    # Возвращаемся в настройки уже на новом языке
    language_name = t(f"settings.language_names.{new_lang}", new_lang)
    text = (
        f"{t('settings.title', new_lang)}\n\n"
        f"{t('settings.current_language', new_lang, language=language_name)}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=settings_keyboard(new_lang)
    )
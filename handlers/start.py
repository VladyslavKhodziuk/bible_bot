from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from services.user_service import UserService
from services.streak_display import format_streak_indicator
from services.i18n import t
from keyboards.language import language_keyboard
from keyboards.menu import welcome_keyboard, main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработка /start: новому юзеру — выбор языка, старому — приветствие."""
    user = await UserService.get(message.from_user.id)

    if user is None:
        # Новый пользователь — показываем выбор языка
        # Юзера создадим ТОЛЬКО после выбора языка
        await message.answer(
            t("language.choose"),
            reply_markup=language_keyboard()
        )
    else:
        # Вернувшийся пользователь — короткое приветствие и сразу меню
        name = user.first_name or "друг"
        await message.answer(
            t("welcome_back", user.lang, name=name)
        )
        await message.answer(
            t("menu.title", user.lang),
            reply_markup=main_menu_keyboard(user.lang)
        )


@router.callback_query(F.data.startswith("setlang:"))
async def set_language(callback: CallbackQuery):
    """Обработка выбора языка."""
    lang = callback.data.split(":")[1]

    user = await UserService.get(callback.from_user.id)

    if user is None:
        # Первый раз — создаём юзера с выбранным языком
        await UserService.create(
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            lang=lang
        )
    else:
        # Юзер уже есть — просто меняем язык
        await UserService.set_language(callback.from_user.id, lang)

    # Удаляем сообщение с выбором языка
    await callback.message.delete()

    # Шлём приветствие на выбранном языке
    name = callback.from_user.first_name or "друг"
    await callback.message.answer(
        t("welcome.text", lang, name=name),
        reply_markup=welcome_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "open_menu")
async def open_menu(callback: CallbackQuery):
    """Переход из приветствия или другого экрана в главное меню."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    base = t("menu.title", lang)
    if user and user.current_streak > 0:
        streak_line = format_streak_indicator(user.current_streak, lang)
        if streak_line:
            base = f"{base}\n\n{streak_line}"

    await callback.message.edit_text(
        base,
        reply_markup=main_menu_keyboard(lang)
    )
    await callback.answer()
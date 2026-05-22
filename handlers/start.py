import html

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from services.user_service import UserService
from services.plan_service import PlanService
from services.menu_text import build_menu_text
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
        name = html.escape(user.first_name or "друг")
        await message.answer(
            t("welcome_back", user.lang, name=name)
        )
        active = await PlanService.get_active(user.tg_id)
        plan_day = active.current_day if active else None
        await message.answer(
            build_menu_text(user, user.lang),
            reply_markup=main_menu_keyboard(user.lang, plan_day=plan_day),
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
    name = html.escape(callback.from_user.first_name or "друг")
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

    active = await PlanService.get_active(callback.from_user.id) if user else None
    plan_day = active.current_day if active else None

    await callback.message.edit_text(
        build_menu_text(user, lang),
        reply_markup=main_menu_keyboard(lang, plan_day=plan_day),
    )
    await callback.answer()
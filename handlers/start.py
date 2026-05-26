import html

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

from services.user_service import UserService
from services.menu_text import build_menu_text
from services.i18n import t
from keyboards.language import language_keyboard
from keyboards.menu import welcome_keyboard, main_menu_keyboard
from keyboards.notifications import onboarding_timezone_keyboard
from services.timezones import is_valid, label as tz_label

router = Router()


def _verse_line(user, lang: str) -> str:
    """Строка-плашка о стихе дня для приветствия.

    Если уведомления включены (по умолчанию они вкл) — показываем время и
    часовой пояс, чтобы юзер сразу знал, когда придёт стих и в каком поясе.
    """
    if user.notifications_enabled:
        return t(
            "welcome.verse_time",
            lang,
            time=user.notification_time,
            timezone=tz_label(user.timezone, lang),
        )
    return t("welcome.verse_off", lang)


def _welcome_text(user, lang: str) -> str:
    """Текст приветствия с плашкой про стих дня."""
    name = html.escape(user.first_name or "друг")
    return t("welcome.text", lang, name=name, verse_line=_verse_line(user, lang))


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    """Обработка /start: новому юзеру — выбор языка, старому — приветствие.

    Поддерживает deep-link payload: /start verse → сразу карточка стиха дня
    (ссылка из текста меню), без показа самого меню.
    """
    user = await UserService.get(message.from_user.id)

    if user is None:
        # Новый пользователь — показываем выбор языка
        # Юзера создадим ТОЛЬКО после выбора языка
        await message.answer(
            t("language.choose"),
            reply_markup=language_keyboard()
        )
        return

    # Deep-link «стих дня» — отдаём карточку вместо меню
    if command.args == "verse":
        from handlers.verse import deliver_verse_of_day
        await deliver_verse_of_day(message, message.from_user.id)
        return

    # Вернувшийся пользователь — короткое приветствие и сразу меню
    name = html.escape(user.first_name or "друг")
    await message.answer(
        t("welcome_back", user.lang, name=name)
    )
    await message.answer(
        await build_menu_text(user, user.lang, message.bot),
        reply_markup=main_menu_keyboard(user.lang),
    )


@router.callback_query(F.data.startswith("setlang:"))
async def set_language(callback: CallbackQuery):
    """Обработка выбора языка → сразу приветствие.

    Часовой пояс при онбординге не спрашиваем: новый юзер получает дефолтный
    (Europe/Madrid). Поправить его можно кнопкой прямо на экране приветствия.
    """
    lang = callback.data.split(":")[1]

    user = await UserService.get(callback.from_user.id)

    # Удаляем сообщение с выбором языка
    await callback.message.delete()

    if user is None:
        await UserService.create(
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            lang=lang
        )
    else:
        await UserService.set_language(callback.from_user.id, lang)

    user = await UserService.get(callback.from_user.id)
    await callback.message.answer(
        _welcome_text(user, lang),
        reply_markup=welcome_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "onboard:tz")
async def onboarding_open_timezone(callback: CallbackQuery):
    """С экрана приветствия открыть выбор часового пояса."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("onboarding.choose_timezone", lang),
        reply_markup=onboarding_timezone_keyboard(lang, current_tz=user.timezone if user else None),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("onboard:settz:"))
async def onboarding_set_timezone(callback: CallbackQuery):
    """Сохранить выбранный пояс и вернуть на приветствие с обновлённым временем."""
    tz_name = callback.data.split(":", 2)[2]  # IANA-имя (может содержать '/')

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    if not is_valid(tz_name):
        await callback.answer("⚠️", show_alert=True)
        return

    await UserService.set_timezone(callback.from_user.id, tz_name)
    await callback.answer(
        t("notifications.timezone_changed", lang, timezone=tz_label(tz_name, lang)),
        show_alert=False
    )

    user = await UserService.get(callback.from_user.id)
    await callback.message.edit_text(
        _welcome_text(user, lang),
        reply_markup=welcome_keyboard(lang),
    )


@router.callback_query(F.data == "onboard:welcome")
async def onboarding_back_to_welcome(callback: CallbackQuery):
    """Вернуться из выбора пояса на приветствие без изменений."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        _welcome_text(user, lang),
        reply_markup=welcome_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "open_menu")
async def open_menu(callback: CallbackQuery):
    """Переход из приветствия или другого экрана в главное меню."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        await build_menu_text(user, lang, callback.bot),
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()

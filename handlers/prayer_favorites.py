"""«Мои молитвы»: список избранных молитв + тоггл сохранения с карточек."""
from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.bot_meta import get_bot_username
from services.prayer_service import PrayerService
from services.prayer_favorite_service import PrayerFavoriteService
from services.i18n import t
from keyboards.pray import (
    prayer_favorites_list_keyboard,
    prayer_favorite_view_keyboard,
    PRAYER_FAVORITES_PER_PAGE,
)

router = Router()


# ============ Список избранных молитв ============

@router.callback_query(F.data == "pray:my")
async def show_favorites(callback: CallbackQuery):
    """Открыть список избранных молитв (первая страница)."""
    await _show_favorites_page(callback, page=0)


@router.callback_query(F.data.startswith("pf:list:"))
async def show_favorites_page(callback: CallbackQuery):
    """Конкретная страница списка."""
    page = int(callback.data.split(":")[2])
    await _show_favorites_page(callback, page=page)


async def _show_favorites_page(callback: CallbackQuery, page: int):
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    total = await PrayerFavoriteService.count_for_user(callback.from_user.id)

    if total == 0:
        await callback.message.edit_text(
            t("pray.my_empty", lang),
            reply_markup=prayer_favorites_list_keyboard([], 0, 0, lang),
        )
        await callback.answer()
        return

    favorites = await PrayerFavoriteService.list_for_user(
        callback.from_user.id,
        limit=PRAYER_FAVORITES_PER_PAGE,
        offset=page * PRAYER_FAVORITES_PER_PAGE,
    )

    items = []
    for fav in favorites:
        prayer = PrayerService.get_prayer_by_id(fav.prayer_id, lang, translation)
        # Молитва могла исчезнуть из пула (например, после обновления подборки) —
        # показываем нейтральный заголовок-заглушку вместо сырого id.
        title = prayer["title"] if prayer else t("pray.fav_unavailable", lang)
        items.append((fav.prayer_id, title))

    await callback.message.edit_text(
        t("pray.my_title", lang, count=total),
        reply_markup=prayer_favorites_list_keyboard(items, page, total, lang),
    )
    await callback.answer()


# ============ Просмотр одной сохранённой молитвы ============

@router.callback_query(F.data.startswith("pf:view:"))
async def view_favorite(callback: CallbackQuery):
    """Карточка одной сохранённой молитвы."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    prayer_id = callback.data.split(":", 2)[2]
    prayer = PrayerService.get_prayer_by_id(prayer_id, lang, translation)
    if not prayer:
        await callback.answer("⚠️", show_alert=True)
        return

    bot_username = await get_bot_username(callback.bot)
    await callback.message.edit_text(
        _build_favorite_text(prayer, lang, bot_username),
        reply_markup=prayer_favorite_view_keyboard(prayer_id, lang),
        disable_web_page_preview=True,
    )
    await callback.answer()


def _build_favorite_text(prayer: dict, lang: str, bot_username: str) -> str:
    """Карточка сохранённой молитвы (заголовок «Сохранённая молитва» + share)."""
    from handlers.pray import _prayer_card_block, _share_link_html

    parts = [t("pray.title", lang), ""]
    parts.extend(_prayer_card_block(prayer, lang, t("pray.fav_card_title", lang)))
    share = _share_link_html(
        prayer, lang, bot_username, t("pray.share_header_generic", lang)
    )
    if share:
        parts.append("")
        parts.append(share)
    return "\n".join(parts)


# ============ Удаление из избранного ============

@router.callback_query(F.data.startswith("pf:del:"))
async def delete_favorite(callback: CallbackQuery):
    """Убрать молитву из избранного и вернуться к списку."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    prayer_id = callback.data.split(":", 2)[2]
    await PrayerFavoriteService.remove(callback.from_user.id, prayer_id)

    await callback.answer(t("pray.fav_removed", lang), show_alert=False)
    await _show_favorites_page(callback, page=0)


# ============ Тоггл сохранения с карточек молитвы ============

@router.callback_query(F.data.startswith("pf:add:"))
async def toggle_add_favorite(callback: CallbackQuery):
    """Сохранить молитву в избранное (с карточки молитвы дня / случайной)."""
    parts = callback.data.split(":")
    prayer_id = parts[2]
    return_to = parts[3] if len(parts) > 3 else "pray"

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    result = await PrayerFavoriteService.add(callback.from_user.id, prayer_id)
    if result is None:
        await callback.answer(t("pray.fav_limit_reached", lang), show_alert=True)
    else:
        await callback.answer(t("pray.fav_added", lang), show_alert=False)

    await _refresh_source_screen(callback, return_to, prayer_id)


@router.callback_query(F.data.startswith("pf:rm:"))
async def toggle_remove_favorite(callback: CallbackQuery):
    """Убрать молитву из избранного через тоггл-кнопку на карточке."""
    parts = callback.data.split(":")
    prayer_id = parts[2]
    return_to = parts[3] if len(parts) > 3 else "pray"

    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await PrayerFavoriteService.remove(callback.from_user.id, prayer_id)
    await callback.answer(t("pray.fav_removed", lang), show_alert=False)

    await _refresh_source_screen(callback, return_to, prayer_id)


async def _refresh_source_screen(callback: CallbackQuery, return_to: str, prayer_id: str):
    """Перерисовать исходный экран с обновлённой кнопкой избранного.

    return_to: 'pray' — карточка молитвы дня, 'rnd' — та же случайная молитва,
    'tp_<topic_id>' — карточка темы (детерминированная молитва дня темы).
    """
    if return_to.startswith("tp_"):
        # Карточка темы: повторно отрисовываем тему (детерминированная молитва дня)
        from handlers.pray import render_topic_prayer

        topic_id = return_to[len("tp_"):]
        await render_topic_prayer(callback, topic_id)
    elif return_to == "rnd":
        # Перерисуем ту же случайную молитву по id (повторный pray:random дал бы новую)
        from handlers.pray import _build_random_text
        from keyboards.pray import pray_random_keyboard

        user = await UserService.get(callback.from_user.id)
        lang = user.lang if user else "ru"
        translation = user.translation if user else "ru_synodal"

        prayer = PrayerService.get_prayer_by_id(prayer_id, lang, translation)
        if not prayer:
            return

        bot_username = await get_bot_username(callback.bot)
        is_fav = await PrayerFavoriteService.is_favorite(callback.from_user.id, prayer_id)
        await callback.message.edit_text(
            _build_random_text(prayer, lang, bot_username),
            reply_markup=pray_random_keyboard(lang, prayer_id, is_fav),
            disable_web_page_preview=True,
        )
    else:
        # Молитва дня: повторный вход показывает ту же молитву (детерминирована по дате)
        from handlers.pray import show_pray

        await show_pray(callback)

from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.bible_service import BibleService
from services.topic_service import TopicService
from services.i18n import t
from keyboards.topics import topics_keyboard, topic_view_keyboard
from keyboards.pray import pray_keyboard

router = Router()


@router.callback_query(F.data == "pray")
async def show_pray(callback: CallbackQuery):
    """Раздел «Помолиться» — обёртка над подбором стихов по настроению."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("pray.title", lang),
        reply_markup=pray_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "topics")
async def show_topics(callback: CallbackQuery):
    """Показать сетку тем."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"

    await callback.message.edit_text(
        t("topics.title", lang),
        reply_markup=topics_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topic:"))
async def show_topic(callback: CallbackQuery):
    """Показать подборку стихов по выбранной теме."""
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    topic_id = callback.data.split(":", 1)[1]
    topic = TopicService.get_topic(topic_id, lang, translation)

    if not topic:
        await callback.answer("⚠️", show_alert=True)
        return

    # Формируем сообщение: эмодзи + название темы + вступление + стихи
    parts = [
        f"{topic['emoji']} <b>{topic['name']}</b>",
        "",
        f"<i>{topic['intro']}</i>",
        "",
    ]

    for v in topic["verses"]:
        book_name = BibleService.get_book_name(v["abbrev"], lang)
        reference = t(
            "topics.reference",
            lang,
            book=book_name,
            chapter=v["chapter"],
            verse=v["verse"]
        )
        parts.append(f"{reference}\n{v['text']}\n")

    text = "\n".join(parts)

    await callback.message.edit_text(
        text,
        reply_markup=topic_view_keyboard(lang)
    )
    await callback.answer()
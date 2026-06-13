import random

from aiogram import Router, F
from aiogram.types import CallbackQuery

from services.user_service import UserService
from services.bible_service import BibleService
from services.topic_service import TopicService
from services.i18n import t
from keyboards.topics import topics_keyboard, topic_view_keyboard

router = Router()


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
    """Показать один случайный стих темы.

    Callback может быть:
      topic:<id>            — первый вход (любой случайный стих).
      topic:<id>:r:<idx>    — «другой стих» (random.choice с исключением idx).
    """
    user = await UserService.get(callback.from_user.id)
    lang = user.lang if user else "ru"
    translation = user.translation if user else "ru_synodal"

    parts = callback.data.split(":")
    topic_id = parts[1]
    exclude_idx: int | None = None
    if len(parts) >= 4 and parts[2] == "r":
        try:
            exclude_idx = int(parts[3])
        except ValueError:
            exclude_idx = None

    topic = TopicService.get_topic(topic_id, lang, translation)
    if not topic or not topic["verses"]:
        await callback.answer("⚠️", show_alert=True)
        return

    indices = list(range(len(topic["verses"])))
    if exclude_idx is not None and len(indices) > 1:
        indices = [i for i in indices if i != exclude_idx]

    chosen_idx = random.choice(indices)
    v = topic["verses"][chosen_idx]

    book_name = BibleService.get_book_name(v["abbrev"], lang)
    reference = t(
        "topics.reference",
        lang,
        book=book_name,
        chapter=v["chapter"],
        verse=v["verse"],
    )

    text = "\n".join([
        f"{topic['emoji']} <b>{topic['name']}</b>",
        "",
        f"<i>{topic['intro']}</i>",
        "",
        reference,
        v["text"],
    ])

    await callback.message.edit_text(
        text,
        reply_markup=topic_view_keyboard(lang, topic_id, chosen_idx, v["abbrev"], v["chapter"]),
    )
    await callback.answer()
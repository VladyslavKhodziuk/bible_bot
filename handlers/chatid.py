"""Утилита для получения ID чата/канала.

- /chatid (или /id) в любом чате — возвращает ID текущего чата.
- Пересланное в личку боту сообщение из канала/группы — возвращает ID источника
  (так удобно узнать ID канала: бот не получает команды в каналах напрямую).

Роутер подключается последним, чтобы не перехватывать обычные сообщения.
"""
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    MessageOriginChannel,
    MessageOriginChat,
    MessageOriginUser,
    MessageOriginHiddenUser,
)

logger = logging.getLogger(__name__)
router = Router()

_HINT = "Чтобы узнать ID канала — перешли мне сюда любой пост из самого канала."


def _format_chat(chat) -> str:
    title = chat.title or getattr(chat, "full_name", None) or chat.username or "—"
    return (
        f"📋 <b>{title}</b>\n"
        f"chat_id: <code>{chat.id}</code>\n"
        f"тип: {chat.type}"
    )


@router.message(Command("chatid", "id"))
async def cmd_chatid(message: Message):
    """ID текущего чата (личка/группа/супергруппа)."""
    await message.answer(_format_chat(message.chat), parse_mode="HTML")


@router.message(F.forward_origin)
async def forwarded(message: Message):
    """Любая пересылка: отдаём ID источника в зависимости от его типа."""
    origin = message.forward_origin

    if isinstance(origin, MessageOriginChannel):
        await message.answer(
            "Канал-источник:\n\n" + _format_chat(origin.chat), parse_mode="HTML"
        )
    elif isinstance(origin, MessageOriginChat):
        await message.answer(
            "Чат-источник:\n\n" + _format_chat(origin.sender_chat), parse_mode="HTML"
        )
    elif isinstance(origin, MessageOriginUser):
        u = origin.sender_user
        await message.answer(
            f"Это переслано от пользователя <b>{u.full_name}</b> "
            f"(id <code>{u.id}</code>), а не из канала.\n\n{_HINT}",
            parse_mode="HTML",
        )
    else:  # MessageOriginHiddenUser
        await message.answer(
            f"Переслано от пользователя со скрытым профилем — ID недоступен.\n\n{_HINT}",
            parse_mode="HTML",
        )

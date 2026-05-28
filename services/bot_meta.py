"""Устойчивое получение метаданных бота (username), общее для хендлеров.

Username нужен только для декоративной t.me/share/url-ссылки «Поделиться».
Сетевой сбой при ``bot.get_me()`` (плохой Wi-Fi, кратковременный обрыв до
api.telegram.org) НЕ должен ронять хендлер. Поэтому ``get_bot_username()``
никогда не бросает: при ошибке возвращает последнее закэшированное значение
или ``None``, а вызывающий просто не рисует ссылку/кнопку «Поделиться».
"""
import logging

logger = logging.getLogger(__name__)

_bot_username: str | None = None


async def get_bot_username(bot) -> str | None:
    """Username бота (кэш на процесс). Никогда не бросает исключение.

    Возвращает ``None``, если username ещё не получен и сеть сейчас недоступна.
    В этом случае декоративная ссылка «Поделиться» просто не отображается,
    а основной контент (меню/стих/молитва) остаётся.
    """
    global _bot_username
    if _bot_username is not None:
        return _bot_username
    try:
        me = await bot.get_me()
        _bot_username = me.username
    except Exception as e:
        logger.warning(
            f"Не удалось получить username бота (get_me): {type(e).__name__}: {e}"
        )
        return None
    return _bot_username


async def prewarm(bot) -> None:
    """Best-effort прогрев кэша на старте — чтобы первый рендер уже имел username."""
    await get_bot_username(bot)

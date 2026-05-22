"""Срочные алерты администратору о сбоях (мониторинг).

В отличие от суточного отчёта аналитики, эти сообщения уходят в ЛС ADMIN_IDS
немедленно в момент проблемы. Чтобы при краш-цикле не завалить админа сотнями
сообщений, одинаковые алерты (по ключу) троттлятся: один и тот же key шлётся
не чаще, чем раз в ALERT_COOLDOWN_SEC.

Бот сохраняется один раз при старте (init), чтобы notify можно было звать из
любого места — middleware, сервисов, планировщика — без передачи bot.
"""
import time
import html
import logging

from aiogram import Bot

from config import ADMIN_IDS, ALERT_COOLDOWN_SEC

logger = logging.getLogger(__name__)


class AlertService:
    """Стейтлес-сервис рассылки срочных алертов с дедупликацией в памяти."""

    _bot: Bot | None = None
    _last_sent: dict[str, float] = {}

    @classmethod
    def init(cls, bot: Bot) -> None:
        """Сохранить bot при старте приложения."""
        cls._bot = bot

    @classmethod
    async def notify(cls, key: str, text: str) -> None:
        """Отправить алерт в ЛС всем ADMIN_IDS, если не сработал троттлинг.

        key — стабильный идентификатор класса проблемы (напр. "handler_error:plan").
        Одинаковый key не шлётся чаще раза в ALERT_COOLDOWN_SEC.
        """
        if cls._bot is None or not ADMIN_IDS:
            return

        now = time.monotonic()
        last = cls._last_sent.get(key)
        if last is not None and now - last < ALERT_COOLDOWN_SEC:
            return
        cls._last_sent[key] = now

        for admin_id in ADMIN_IDS:
            try:
                await cls._bot.send_message(
                    chat_id=admin_id, text=text, parse_mode="HTML"
                )
            except Exception as e:
                # Алерт не должен ронять вызывающий код и маскировать исходную ошибку.
                logger.error(f"Не удалось отправить алерт админу {admin_id}: {e}")

    @classmethod
    async def alert_error(cls, key: str, title: str, detail: str) -> None:
        """Удобная обёртка: формирует HTML-текст алерта об ошибке."""
        text = (
            f"🚨 <b>{html.escape(title)}</b>\n"
            f"<code>{html.escape(detail)}</code>"
        )
        await cls.notify(key, text)

"""Outer-middleware: throttling + сбор активности + перехват ошибок.

Регистрируется на dp.update, поэтому видит каждое входящее обновление
(сообщения и нажатия кнопок) в одной точке.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update

from services.analytics_service import AnalyticsService
from services.alert_service import AlertService

logger = logging.getLogger(__name__)


class AnalyticsMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        message = event.message
        callback = event.callback_query

        # Определяем юзера и категорию события.
        if callback is not None:
            tg_id = callback.from_user.id if callback.from_user else None
            kind = "callback"
            event_type = AnalyticsService.classify_callback(callback.data)
        elif message is not None:
            tg_id = message.from_user.id if message.from_user else None
            kind = "message"
            event_type = AnalyticsService.classify_message(message.text)
        else:
            # Прочие апдейты (pre_checkout, edited и т.п.) не трекаем.
            return await handler(event, data)

        if tg_id is None or event_type is None:
            return await handler(event, data)

        # Throttling: режем спам до обработки и до записи нормального события.
        if not AnalyticsService.allow(tg_id):
            AnalyticsService.record(tg_id, event_type, "throttled")
            if callback is not None:
                try:
                    await callback.answer("⏳", show_alert=False)
                except Exception:
                    pass
            return None  # обработчик не вызываем

        AnalyticsService.record(tg_id, event_type, kind)

        try:
            return await handler(event, data)
        except Exception as e:
            AnalyticsService.record(tg_id, event_type, "error")
            # Срочный алерт админу. Ключ по категории — троттлит шквал
            # одинаковых ошибок до одного сообщения в ALERT_COOLDOWN_SEC.
            await AlertService.alert_error(
                key=f"handler_error:{event_type}",
                title=f"Ошибка в обработчике ({event_type})",
                detail=f"{type(e).__name__}: {e} | tg_id={tg_id}, kind={kind}",
            )
            raise  # пробрасываем, чтобы стандартное логирование сработало

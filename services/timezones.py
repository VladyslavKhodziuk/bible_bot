"""Работа с часовыми поясами пользователей.

Используем стандартный zoneinfo (база IANA из пакета tzdata) — это даёт
корректный перевод часов (DST) круглый год, в отличие от фиксированного
UTC-смещения. Все вычисления «локального времени/даты пользователя» идут
через эти хелперы.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import DEFAULT_TZ

# Курируемый короткий список зон для выбора в UI. Покрывает основные регионы
# языков бота (ru/uk/en/es). Подписи строятся как «Город (UTC±HH:MM)».
SUPPORTED_TIMEZONES: list[str] = [
    "Europe/London",
    "Europe/Madrid",
    "Europe/Kyiv",
    "Europe/Moscow",
    "Asia/Yekaterinburg",
    "Asia/Almaty",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Mexico_City",
    "America/Bogota",
    "America/Argentina/Buenos_Aires",
    "UTC",
]

# Человекочитаемое название города/зоны (латиницей — универсально читаемо).
_CITY_LABEL: dict[str, str] = {
    "Europe/London": "London",
    "Europe/Madrid": "Madrid",
    "Europe/Kyiv": "Kyiv",
    "Europe/Moscow": "Moscow",
    "Asia/Yekaterinburg": "Yekaterinburg",
    "Asia/Almaty": "Almaty",
    "America/New_York": "New York",
    "America/Chicago": "Chicago",
    "America/Denver": "Denver",
    "America/Los_Angeles": "Los Angeles",
    "America/Mexico_City": "Mexico City",
    "America/Bogota": "Bogota",
    "America/Argentina/Buenos_Aires": "Buenos Aires",
    "UTC": "UTC",
}


def _zone(tz_name: str) -> ZoneInfo:
    """ZoneInfo по имени; при неизвестном/битом — DEFAULT_TZ."""
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo(DEFAULT_TZ)


def is_valid(tz_name: str) -> bool:
    """Проверка, что имя зоны существует в базе IANA."""
    try:
        ZoneInfo(tz_name)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False


def local_now(tz_name: str) -> datetime:
    """Текущее tz-aware время в зоне пользователя."""
    return datetime.now(_zone(tz_name))


def local_hhmm(tz_name: str) -> str:
    """Текущее локальное время пользователя в формате 'HH:MM'."""
    return local_now(tz_name).strftime("%H:%M")


def local_today(tz_name: str) -> date:
    """Сегодняшняя дата в зоне пользователя (для стриков)."""
    return local_now(tz_name).date()


def offset_label(tz_name: str) -> str:
    """Текущее смещение зоны в виде 'UTC+03:00' (учитывает DST на сейчас)."""
    off = local_now(tz_name).utcoffset()
    if off is None:
        return "UTC+00:00"
    total_min = int(off.total_seconds()) // 60
    sign = "+" if total_min >= 0 else "-"
    hh, mm = divmod(abs(total_min), 60)
    return f"UTC{sign}{hh:02d}:{mm:02d}"


def label(tz_name: str) -> str:
    """Подпись для кнопки/статуса: 'Kyiv (UTC+03:00)'."""
    city = _CITY_LABEL.get(tz_name, tz_name)
    return f"{city} ({offset_label(tz_name)})"

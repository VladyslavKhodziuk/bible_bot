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
    "Asia/Tbilisi",
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

# Название города по UI-языку (en — fallback для неизвестного языка).
_CITY_LABEL: dict[str, dict[str, str]] = {
    "Europe/London": {"en": "London", "ru": "Лондон", "uk": "Лондон", "es": "Londres"},
    "Europe/Madrid": {"en": "Madrid", "ru": "Мадрид", "uk": "Мадрид", "es": "Madrid"},
    "Europe/Kyiv": {"en": "Kyiv", "ru": "Киев", "uk": "Київ", "es": "Kiev"},
    "Asia/Tbilisi": {"en": "Tbilisi", "ru": "Тбилиси", "uk": "Тбілісі", "es": "Tiflis"},
    "Asia/Almaty": {"en": "Almaty", "ru": "Алматы", "uk": "Алмати", "es": "Almaty"},
    "America/New_York": {"en": "New York", "ru": "Нью-Йорк", "uk": "Нью-Йорк", "es": "Nueva York"},
    "America/Chicago": {"en": "Chicago", "ru": "Чикаго", "uk": "Чикаго", "es": "Chicago"},
    "America/Denver": {"en": "Denver", "ru": "Денвер", "uk": "Денвер", "es": "Denver"},
    "America/Los_Angeles": {"en": "Los Angeles", "ru": "Лос-Анджелес", "uk": "Лос-Анджелес", "es": "Los Ángeles"},
    "America/Mexico_City": {"en": "Mexico City", "ru": "Мехико", "uk": "Мехіко", "es": "Ciudad de México"},
    "America/Bogota": {"en": "Bogota", "ru": "Богота", "uk": "Богота", "es": "Bogotá"},
    "America/Argentina/Buenos_Aires": {"en": "Buenos Aires", "ru": "Буэнос-Айрес", "uk": "Буенос-Айрес", "es": "Buenos Aires"},
    "UTC": {"en": "UTC", "ru": "UTC", "uk": "UTC", "es": "UTC"},
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


def label(tz_name: str, lang: str = "en") -> str:
    """Подпись для кнопки/статуса на языке UI: 'Киев (UTC+03:00)'.

    Город берётся из локализованного словаря (fallback: en → само имя зоны),
    смещение всегда числовое и языконезависимое.
    """
    cities = _CITY_LABEL.get(tz_name, {})
    city = cities.get(lang) or cities.get("en") or tz_name
    return f"{city} ({offset_label(tz_name)})"


# Эмодзи-циферблаты, индекс = час % 12. Две шкалы: ровный час и «половина».
_CLOCK_HOUR = ["🕛", "🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚"]
_CLOCK_HALF = ["🕧", "🕜", "🕝", "🕞", "🕟", "🕠", "🕡", "🕢", "🕣", "🕤", "🕥", "🕦"]


def clock_emoji(tz_name: str) -> str:
    """Циферблат, показывающий текущий локальный час зоны.

    Минуты округляются до ближайшего получаса: …:00 — ровный час,
    …:30 — «половина», иначе тикаем на следующий час.
    """
    now = local_now(tz_name)
    hour = now.hour % 12
    half = round(now.minute / 30)  # 0, 1 или 2
    if half == 0:
        return _CLOCK_HOUR[hour]
    if half == 1:
        return _CLOCK_HALF[hour]
    return _CLOCK_HOUR[(hour + 1) % 12]

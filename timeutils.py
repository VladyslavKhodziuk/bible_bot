"""Утилиты времени.

`datetime.utcnow()` устарел в Python 3.12 (даёт DeprecationWarning). Заменяем
его на `utcnow()` с той же семантикой: возвращаем naive (без tzinfo) UTC-время.

Важно сохранить именно naive UTC: вся БД (created_at, started_at и т.п.) и
вычисления в analytics_service полагаются на naive-значения. Возврат tz-aware
datetime сломал бы сравнения «naive vs aware».
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Текущее время UTC без tzinfo — прямая замена datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

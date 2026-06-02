"""Генератор «лёгких» планов чтения: Новый Завет и Псалмы.

Пересоздаёт data/plans/nt_30.yaml и data/plans/psalms_30.yaml в темпе
1 глава/псалом в день, чтобы планы были реально выполнимы.

    Новый Завет : Матфея -> Откровение, по 1 главе в день -> 260 дней.
    Псалмы      : Пс 1..150, по 1 псалму в день           -> 150 дней.

ID планов и имена файлов НЕ меняются (это сломало бы прогресс активных
пользователей и порядок в UI). «Библия за год», Притчи и «Жизнь Иисуса»
не трогаются.

Запуск:
    python scripts/build_reading_plans.py
"""

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PLANS_DIR = Path(__file__).parent.parent / "data" / "plans"

# Книги Нового Завета: (abbrev, число глав) в порядке data/books.yaml.
# Канонические (Protestant) числа глав — совпадают с допущениями текущих
# планов и не зависят от версификации конкретного перевода.
NT_BOOKS: list[tuple[str, int]] = [
    ("mt", 28), ("mk", 16), ("lk", 24), ("jo", 21), ("act", 28),
    ("rm", 16), ("1co", 16), ("2co", 13), ("gl", 6), ("eph", 6),
    ("ph", 4), ("cl", 4), ("1ts", 5), ("2ts", 3), ("1tm", 6),
    ("2tm", 4), ("tt", 3), ("phm", 1), ("hb", 13), ("jm", 5),
    ("1pe", 5), ("2pe", 3), ("1jo", 5), ("2jo", 1), ("3jo", 1),
    ("jd", 1), ("re", 22),
]

# ---- Метаданные планов (имена/описания на 4 языках) ----

NT_META = {
    "id": "nt_30",
    "emoji": "📖",
    "names": {
        "ru": "Новый Завет",
        "en": "New Testament",
        "es": "Nuevo Testamento",
        "uk": "Новий Заповіт",
    },
    "descriptions": {
        "ru": "Весь Новый Завет по одной главе в день — 260 дней спокойного, вдумчивого чтения.",
        "en": "The entire New Testament, one chapter a day — 260 days of calm, thoughtful reading.",
        "es": "Todo el Nuevo Testamento, un capítulo al día — 260 días de lectura tranquila y reflexiva.",
        "uk": "Весь Новий Заповіт по одному розділу на день — 260 днів спокійного, вдумливого читання.",
    },
}

PSALMS_META = {
    "id": "psalms_30",
    "emoji": "🙏",
    "names": {
        "ru": "Псалтирь за 150 дней",
        "en": "Psalms in 150 days",
        "es": "Salmos en 150 días",
        "uk": "Псалтир за 150 днів",
    },
    "descriptions": {
        "ru": "По одному псалму в день — 150 дней молитвенного чтения, что настраивает сердце.",
        "en": "One psalm a day — 150 days of prayerful reading that tunes the heart.",
        "es": "Un salmo al día — 150 días de lectura orante que sintoniza el corazón.",
        "uk": "По одному псалму на день — 150 днів молитовного читання, що налаштовує серце.",
    },
}


def build_one_per_day(books: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Разворачивает книги в плоский список (abbrev, chapter) — по главам."""
    flat: list[tuple[str, int]] = []
    for abbrev, count in books:
        for ch in range(1, count + 1):
            flat.append((abbrev, ch))
    return flat


def render_plan(meta: dict, readings: list[tuple[str, int]]) -> str:
    """Собирает YAML-текст плана в компактном inline-формате (как в репозитории)."""
    lines: list[str] = []
    lines.append(f"id: {meta['id']}")
    lines.append(f'emoji: "{meta["emoji"]}"')
    lines.append(f"duration_days: {len(readings)}")
    lines.append("names:")
    for lang in ("ru", "en", "es", "uk"):
        lines.append(f'  {lang}: "{meta["names"][lang]}"')
    lines.append("descriptions:")
    for lang in ("ru", "en", "es", "uk"):
        lines.append(f'  {lang}: "{meta["descriptions"][lang]}"')
    lines.append("schedule:")
    for day, (abbrev, chapter) in enumerate(readings, start=1):
        lines.append(f"  - day: {day}")
        lines.append("    readings:")
        lines.append(f'      - {{ abbrev: "{abbrev}", chapter: {chapter} }}')
    return "\n".join(lines) + "\n"


def write_plan(meta: dict, readings: list[tuple[str, int]]) -> None:
    # Защита: каждый день ровно одна глава, главы в пределах книг.
    assert all(ch >= 1 for _, ch in readings), "Найдена глава < 1"
    path = PLANS_DIR / f"{meta['id']}.yaml"
    path.write_text(render_plan(meta, readings), encoding="utf-8")
    logger.info("Записан %s: %d дней (1 глава/день)", path.name, len(readings))


def main() -> None:
    if not PLANS_DIR.exists():
        raise SystemExit(f"Папка планов не найдена: {PLANS_DIR}")

    nt_readings = build_one_per_day(NT_BOOKS)
    assert len(nt_readings) == 260, f"Ожидалось 260 глав НЗ, получено {len(nt_readings)}"
    write_plan(NT_META, nt_readings)

    psalms_readings = build_one_per_day([("ps", 150)])
    assert len(psalms_readings) == 150
    write_plan(PSALMS_META, psalms_readings)

    logger.info("Готово. Перезаписаны nt_30.yaml и psalms_30.yaml.")


if __name__ == "__main__":
    main()

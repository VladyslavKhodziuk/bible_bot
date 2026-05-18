from services.i18n import t


def format_streak_indicator(streak: int, lang: str) -> str:
    """Форматирует индикатор серии. Если 0 — пустая строка."""
    if streak <= 0:
        return ""
    if streak == 1:
        return t("streak.indicator_single", lang)
    return t("streak.indicator", lang, days=streak)


def get_milestone_message(milestone: int, lang: str) -> str | None:
    """Возвращает поздравительное сообщение для милстоуна, или None если нет."""
    msg = t(f"streak.milestones.{milestone}", lang)
    # i18n возвращает "[key]" если ключ не найден
    if msg.startswith("[") and msg.endswith("]"):
        return None
    return msg
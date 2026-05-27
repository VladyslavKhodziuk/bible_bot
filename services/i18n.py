from pathlib import Path
import yaml

from config import SUPPORTED_LANGS, DEFAULT_LANG

LOCALES_DIR = Path(__file__).parent.parent / "locales"

# Кэш загруженных переводов
_translations: dict[str, dict] = {}


def _load_lang(lang: str) -> dict:
    """Загружает YAML-файл языка, кэширует результат."""
    if lang not in _translations:
        path = LOCALES_DIR / f"{lang}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Файл локализации не найден: {path}")
        with open(path, "r", encoding="utf-8") as f:
            _translations[lang] = yaml.safe_load(f)
    return _translations[lang]


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """
    Получить переведённый текст по ключу с точечной нотацией.

    Примеры:
        t("menu.read", "ru")
        t("welcome.text", "ru", name="Vladyslav")
    """
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    data = _load_lang(lang)

    # Идём по ключу через точки: "menu.read" → data["menu"]["read"]
    for part in key.split("."):
        if isinstance(data, dict) and part in data:
            data = data[part]
        else:
            return f"[{key}]"  # ключ не найден — вернём сам ключ для отладки

    if not isinstance(data, str):
        return f"[{key}]"

    # Подставляем переменные {name}, {count} и т.п.
    if kwargs:
        try:
            return data.format(**kwargs)
        except KeyError:
            return data

    return data


def t_list(key: str, lang: str = DEFAULT_LANG) -> list:
    """Получить локализованный список по ключу с точечной нотацией.

    Возвращает [] если ключ не найден или указывает не на список.
    Нужно для таблиц типа месяцев, где элементы индексируются по позиции.
    """
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    data = _load_lang(lang)

    for part in key.split("."):
        if isinstance(data, dict) and part in data:
            data = data[part]
        else:
            return []

    return data if isinstance(data, list) else []
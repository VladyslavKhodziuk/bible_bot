"""Утилиты для кнопок/ссылок «Поделиться» через Telegram t.me/share/url."""
import urllib.parse


def build_share_url(text: str, link_url: str) -> str:
    """Ссылка t.me/share/url с заданным текстом и вложенным url.

    quote (а не quote_plus): пробел -> %20, не "+". t.me/share/url декодирует
    только %xx и оставляет "+" буквально — иначе в части клиентов вылезают плюсы.
    """
    params = urllib.parse.urlencode(
        {"url": link_url, "text": text}, quote_via=urllib.parse.quote
    )
    return f"https://t.me/share/url?{params}"

"""
One-off scraper: downloads the "Новый русский перевод" (НРТ / NRT) Bible from
bible.by and writes data/bibles/ru_nrt.json in the project format.

bible.by numbers books 1..66. The OT (1-39), Gospels+Acts (40-44) and
Revelation (66) follow the same order as data/books.yaml, but the NT epistles
use the Slavonic/Synodal order (General Epistles James..Jude come BEFORE the
Pauline Epistles Romans..Hebrews). BIBLE_BY_ID maps each books.yaml abbrev to
its real bible.by book id, so the output JSON stays in books.yaml order.
Chapters are discovered dynamically: an out-of-range chapter returns a 200 page
with zero verse <div>s, which signals the end of the book.

Run:  python tools/scrape_nrt.py
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

BASE = "https://bible.by/nrt/{book}/{chapter}/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bible-bot-importer/1.0)"}
DELAY = 0.25          # polite pause between requests (seconds)
MAX_CHAPTERS = 160    # safety cap (Psalms = 150)
RETRIES = 3

# books.yaml abbrev -> bible.by book id (NT epistles use Slavonic order)
BIBLE_BY_ID = {
    # Old Testament (1-39, same order as books.yaml)
    "gn": 1, "ex": 2, "lv": 3, "nm": 4, "dt": 5, "js": 6, "jud": 7, "rt": 8,
    "1sm": 9, "2sm": 10, "1kgs": 11, "2kgs": 12, "1ch": 13, "2ch": 14,
    "ezr": 15, "ne": 16, "et": 17, "job": 18, "ps": 19, "prv": 20, "ec": 21,
    "so": 22, "is": 23, "jr": 24, "lm": 25, "ez": 26, "dn": 27, "ho": 28,
    "jl": 29, "am": 30, "ob": 31, "jn": 32, "mi": 33, "na": 34, "hk": 35,
    "zp": 36, "hg": 37, "zc": 38, "ml": 39,
    # Gospels + Acts (40-44)
    "mt": 40, "mk": 41, "lk": 42, "jo": 43, "act": 44,
    # General (Catholic) Epistles come first on bible.by (45-51)
    "jm": 45, "1pe": 46, "2pe": 47, "1jo": 48, "2jo": 49, "3jo": 50, "jd": 51,
    # Pauline Epistles (52-65)
    "rm": 52, "1co": 53, "2co": 54, "gl": 55, "eph": 56, "ph": 57, "cl": 58,
    "1ts": 59, "2ts": 60, "1tm": 61, "2tm": 62, "tt": 63, "phm": 64, "hb": 65,
    # Revelation (66)
    "re": 66,
}

ROOT = Path(__file__).resolve().parent.parent
BOOKS_FILE = ROOT / "data" / "books.yaml"
OUT_FILE = ROOT / "data" / "bibles" / "ru_nrt.json"

VERSE_DIV_RE = re.compile(r'<div id="(\d+)"[^>]*>(.*?)</div>', re.DOTALL)
SUP_RE = re.compile(r"<sup>.*?</sup>", re.DOTALL)
SUB_SPAN_RE = re.compile(r'<span class="sub">.*?</span>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def fetch(url: str) -> str:
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def clean_verse(raw: str) -> str:
    raw = SUP_RE.sub("", raw)        # drop verse number
    raw = SUB_SPAN_RE.sub("", raw)   # drop footnote markers [1] [2]
    raw = raw.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    raw = TAG_RE.sub("", raw)        # strip remaining inline tags (em, a, ...)
    raw = html.unescape(raw)
    raw = WS_RE.sub(" ", raw).strip()
    return raw


def parse_chapter(body: str) -> list[str]:
    verses: list[tuple[int, str]] = []
    for m in VERSE_DIV_RE.finditer(body):
        num = int(m.group(1))
        text = clean_verse(m.group(2))
        verses.append((num, text))
    verses.sort(key=lambda x: x[0])
    return [t for _, t in verses]


def main() -> int:
    book_order = list(yaml.safe_load(BOOKS_FILE.read_text(encoding="utf-8")).keys())
    if len(book_order) != 66:
        print(f"WARNING: expected 66 books in books.yaml, got {len(book_order)}")

    result = []
    for abbrev in book_order:
        book_id = BIBLE_BY_ID[abbrev]
        chapters: list[list[str]] = []
        ch = 1
        while ch <= MAX_CHAPTERS:
            body = fetch(BASE.format(book=book_id, chapter=ch))
            verses = parse_chapter(body)
            if not verses:
                break
            chapters.append(verses)
            ch += 1
            time.sleep(DELAY)
        result.append({"abbrev": abbrev, "chapters": chapters})
        total_v = sum(len(c) for c in chapters)
        print(f"{abbrev:5} (id {book_id:2}) -> {len(chapters):3} chapters, {total_v:5} verses", flush=True)

    OUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nWrote {OUT_FILE} ({OUT_FILE.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

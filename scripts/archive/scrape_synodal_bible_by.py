"""Scrape the Russian Synodal Bible from bible.by and build data/bibles/ru_synodal.json.

Source: https://bible.by/syn/{book}/{chapter}/  (book 1..66 = Genesis..Revelation,
matching the first 66 abbrevs of data/books.yaml in order).

Faithful reproduction of bible.by:
  - native Synodal psalm numbering (Ps 50 = "Помилуй меня, Боже"; superscription is a verse),
  - modern Russian text (no Church Slavonic),
  - added words are <em> italics on the site -> kept as plain text (no [brackets] anywhere).

Verse markup: inside <div class="text" data-book data-chapter>, each verse is
    <div id="N"><sup>N</sup> TEXT</div>
Section headings are separate <div class="top-paragraph"> / <div class="paragraph"> with no
numeric id and are ignored.

Pages are cached under scripts/_cache/bibleby/ so re-runs don't re-hit the site.

Run:  python scripts/scrape_synodal_bible_by.py            # build the JSON
      python scripts/scrape_synodal_bible_by.py --refresh  # ignore cache, re-fetch
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BOOKS_FILE = ROOT / "data" / "books.yaml"
OUT = ROOT / "data" / "bibles" / "ru_synodal.json"
CACHE = ROOT / "scripts" / "_cache" / "bibleby"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html",
           "Accept-Language": "ru,en;q=0.9", "Referer": "https://bible.by/"}
DELAY = 0.3          # polite delay between live fetches (seconds)
RETRIES = 4

REFRESH = "--refresh" in sys.argv

# bible.by /syn/ book numbers 1..66 -> our abbrev. The OT (1..39) matches books.yaml,
# but the NT uses the Eastern-Orthodox order: Gospels, Acts, the General/Catholic epistles
# (James, Peter, John, Jude), THEN the Pauline epistles, Hebrews, Revelation.
BIBLEBY_ABBREVS = [
    # OT 1..39
    "gn", "ex", "lv", "nm", "dt", "js", "jud", "rt", "1sm", "2sm", "1kgs", "2kgs",
    "1ch", "2ch", "ezr", "ne", "et", "job", "ps", "prv", "ec", "so", "is", "jr",
    "lm", "ez", "dn", "ho", "jl", "am", "ob", "jn", "mi", "na", "hk", "zp", "hg", "zc", "ml",
    # NT 40..66 (Orthodox order)
    "mt", "mk", "lk", "jo", "act",
    "jm", "1pe", "2pe", "1jo", "2jo", "3jo", "jd",
    "rm", "1co", "2co", "gl", "eph", "ph", "cl", "1ts", "2ts", "1tm", "2tm", "tt", "phm",
    "hb", "re",
]


def fetch(url: str) -> str:
    """Fetch a URL with browser headers, retry-with-backoff, and disk caching."""
    key = re.sub(r"[^0-9a-z]+", "_", url.replace("https://bible.by/", "")).strip("_")
    cached = CACHE / f"{key}.html"
    if cached.exists() and not REFRESH:
        return cached.read_text("utf-8")
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_text(html, "utf-8")
            time.sleep(DELAY)
            return html
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            last = e
        except Exception as e:  # noqa: BLE001 - transient network
            last = e
        time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def slice_container(html: str) -> str:
    """Return the balanced inner HTML of the <div ... data-chapter=...> verse container."""
    start = html.find("data-chapter=")
    if start < 0:
        return ""
    # back up to the start of that <div tag, then walk forward balancing <div>/</div>
    open_tag = html.rfind("<div", 0, start)
    i = open_tag
    depth = 0
    token = re.compile(r"<div\b|</div>")
    out_start = html.find(">", open_tag) + 1
    for m in token.finditer(html, open_tag):
        if m.group() == "</div>":
            depth -= 1
            if depth == 0:
                return html[out_start:m.start()]
        else:
            depth += 1
    return html[out_start:]


class VerseParser(HTMLParser):
    """Collect text of every <div id="<digits>">, dropping the leading <sup> verse number."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.verses: dict[int, str] = {}
        self.cur_id: str | None = None
        self.depth = 0
        self.in_sup = 0
        self.buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "div":
            vid = d.get("id")
            if self.cur_id is None and vid and vid.isdigit():
                self.cur_id, self.depth, self.buf, self.in_sup = vid, 1, [], 0
            elif self.cur_id is not None:
                self.depth += 1
        elif tag == "sup" and self.cur_id is not None:
            self.in_sup += 1

    def handle_endtag(self, tag):
        if self.cur_id is None:
            return
        if tag == "sup" and self.in_sup > 0:
            self.in_sup -= 1
        elif tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.verses[int(self.cur_id)] = "".join(self.buf)
                self.cur_id = None

    def handle_data(self, data):
        if self.cur_id is not None and self.in_sup == 0:
            self.buf.append(data)


def clean(text: str) -> str:
    """Normalise a verse: drop stray bracket/cross-numbering artifacts, collapse whitespace."""
    text = re.sub(r"\(\d+[:\-]\d+\)", " ", text)   # defensive; bible.by has none
    text = re.sub(r"\[[^\]]*\]", " ", text)         # defensive; bible.by has none
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?»])", r"\1", text)   # tidy space before punctuation
    return text


def parse_chapter(html: str) -> list[str]:
    inner = slice_container(html)
    if not inner:
        return []
    p = VerseParser()
    p.feed(inner)
    if not p.verses:
        return []
    n = max(p.verses)
    return [clean(p.verses.get(i, "")) for i in range(1, n + 1)]


def chapter_count(html: str, book: int) -> int:
    nums = [int(m) for m in re.findall(rf"/syn/{book}/(\d+)/", html)]
    return max(nums) if nums else 1


def main() -> None:
    books_meta = yaml.safe_load(BOOKS_FILE.read_text("utf-8"))
    canonical_order = list(books_meta.keys())

    by_ab: dict[str, dict] = {}
    for bnum, abbrev in enumerate(BIBLEBY_ABBREVS, start=1):
        ru_name = books_meta[abbrev]["ru"]
        first = fetch(f"https://bible.by/syn/{bnum}/1/")
        title = re.search(r"<title>(.*?)</title>", first)
        title_book = title.group(1).split(",")[0] if title else "?"
        nchap = chapter_count(first, bnum)
        print(f"[{bnum:>2}] {abbrev:<5} {ru_name:<22} chapters={nchap}  ({title_book.strip()})")
        # fail-fast sanity gate: page title's book name must look like the expected name
        norm = lambda s: re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip().lower()
        a, b = norm(ru_name)[:4], norm(title_book)[:4]
        if a != b and "песн" not in norm(title_book):
            raise RuntimeError(f"book {bnum}: title '{title_book.strip()}' != expected '{ru_name}' ({abbrev})")
        chapters = []
        for ch in range(1, nchap + 1):
            html = first if ch == 1 else fetch(f"https://bible.by/syn/{bnum}/{ch}/")
            verses = parse_chapter(html)
            if not verses:
                raise RuntimeError(f"no verses parsed for {abbrev} ch {ch} (book {bnum})")
            chapters.append(verses)
        by_ab[abbrev] = {"abbrev": abbrev, "name": ru_name, "chapters": chapters}

    # write in canonical books.yaml order (only the 66 we scraped)
    result = [by_ab[ab] for ab in canonical_order if ab in by_ab]
    OUT.write_text(json.dumps(result, ensure_ascii=False), "utf-8")
    total = sum(len(c) for b in result for c in b["chapters"])
    print(f"\nWrote {OUT}\n  books={len(result)}  verses={total}")


if __name__ == "__main__":
    main()

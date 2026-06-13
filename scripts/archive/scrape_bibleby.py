"""Scrape a Russian Bible translation from bible.by into data/bibles/<out>.json.

Generalised from scrape_synodal_bible_by.py. bible.by serves every translation
under /{code}/{book}/{chapter}/ with ONE site-wide book numbering (1..66 =
Genesis..Revelation, Eastern-Orthodox NT order — same BIBLEBY_ABBREVS as the
Synodal scraper; verified e.g. /desp/45/1/ == James).

Faithful reproduction of bible.by:
  - native psalm numbering (matches Synodal), superscription is a verse,
  - added/italic words kept as plain text (no [brackets]),
  - verse markup: <div id="N"><sup>N</sup> TEXT</div> inside the
    <div class="text" data-book data-chapter> container; <sup> (verse number and
    footnote markers) is dropped, section-heading divs without numeric id ignored.

Pages are cached under scripts/_cache/<code>/ so re-runs don't re-hit the site.

Run:
  python scripts/scrape_bibleby.py --code erv  --out ru_erv.json
  python scripts/scrape_bibleby.py --code bti  --out ru_bti.json
  python scripts/scrape_bibleby.py --code desp --out ru_desp.json --nt-only
  python scripts/scrape_bibleby.py --code erv  --out ru_erv.json --refresh
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BOOKS_FILE = ROOT / "data" / "books.yaml"
BIBLES_DIR = ROOT / "data" / "bibles"
CACHE_ROOT = ROOT / "scripts" / "_cache"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html",
           "Accept-Language": "ru,en;q=0.9", "Referer": "https://bible.by/"}
DELAY = 0.35         # polite delay between live fetches (seconds)
RETRIES = 7          # bible.by occasionally throws transient 503s under load

# bible.by book numbers 1..66 -> our abbrev. OT (1..39) matches books.yaml; NT
# (40..66) uses Eastern-Orthodox order: Gospels, Acts, the General/Catholic
# epistles (James, Peter, John, Jude), THEN the Pauline epistles, Hebrews, Rev.
# This numbering is site-wide (same for every translation on bible.by).
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
NT_START = 40  # first NT book number on bible.by


def fetch(url: str, cache_dir: Path, refresh: bool) -> str:
    """Fetch a URL with browser headers, retry-with-backoff, and disk caching."""
    key = re.sub(r"[^0-9a-z]+", "_", url.replace("https://bible.by/", "")).strip("_")
    cached = cache_dir / f"{key}.html"
    if cached.exists() and not refresh:
        return cached.read_text("utf-8")
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_text(html, "utf-8")
            time.sleep(DELAY)
            return html
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            last = e
        except Exception as e:  # noqa: BLE001 - transient network
            last = e
        time.sleep(min(0.5 * (2 ** attempt), 20))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def slice_container(html: str) -> str:
    """Return the balanced inner HTML of the <div ... data-chapter=...> verse container."""
    start = html.find("data-chapter=")
    if start < 0:
        return ""
    # back up to the start of that <div tag, then walk forward balancing <div>/</div>
    open_tag = html.rfind("<div", 0, start)
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
    """Collect text of every <div id="<digits>">, dropping the leading <sup> verse
    number and footnote widgets.

    Footnote markers on bible.by are <span class="tooltips">…<span class="sup gray">*
    </span></span> with the note text living in the data-original-title attribute
    (never as element text). We skip the entire subtree of any span whose class
    contains "tooltip" or "sup" so the literal "*" marker doesn't leak into verses.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.verses: dict[int, str] = {}
        self.cur_id: str | None = None
        self.depth = 0
        self.in_sup = 0
        self.skip_depth = 0   # >0 == inside a footnote-marker span subtree
        self.buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self.cur_id is not None and self.skip_depth > 0:
            self.skip_depth += 1
            return
        d = dict(attrs)
        if tag == "div":
            vid = d.get("id")
            if self.cur_id is None and vid and vid.isdigit():
                self.cur_id, self.depth, self.buf = vid, 1, []
                self.in_sup = self.skip_depth = 0
            elif self.cur_id is not None:
                self.depth += 1
        elif tag == "sup" and self.cur_id is not None:
            self.in_sup += 1
        elif tag == "span" and self.cur_id is not None:
            cls = d.get("class", "")
            # tooltip/sup: footnote markers; note: BTI merge-range labels like
            # "[20-21]" (verses 20-21 merged into v20, v21 left empty). All carry
            # no real verse text — drop the whole subtree. <em>/<span class="jesus">
            # etc. are NOT skipped: they hold genuine verse text.
            if "tooltip" in cls or "sup" in cls or "note" in cls:
                self.skip_depth = 1

    def handle_endtag(self, tag):
        if self.cur_id is None:
            return
        if self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if tag == "sup" and self.in_sup > 0:
            self.in_sup -= 1
        elif tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.verses[int(self.cur_id)] = "".join(self.buf)
                self.cur_id = None

    def handle_data(self, data):
        if self.cur_id is not None and self.in_sup == 0 and self.skip_depth == 0:
            self.buf.append(data)


def clean(text: str) -> str:
    """Normalise a verse: drop markers/dividers/cross-numbering, collapse whitespace.

    ERV/BTI conventions handled here:
      - "[...]" textual-variant brackets: keep the inner text, drop the brackets
        (they often span verse boundaries, leaving lone "[" / "]"); the bot has no
        footnote apparatus, so plain text is consistent with the other translations.
      - "*" footnote-reference markers and "* * *" Psalter-book dividers: an
        asterisk is never legitimate verse content -> strip all of them.
    """
    text = re.sub(r"\(\d+[:\-]\d+\)", " ", text)   # cross-reference artifacts
    text = text.replace("[", " ").replace("]", " ")  # textual-variant brackets -> keep text
    text = text.replace("*", " ")                    # footnote markers & "* * *" dividers
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


def chapter_count(html: str, code: str, book: int) -> int:
    nums = [int(m) for m in re.findall(rf"/{code}/{book}/(\d+)/", html)]
    return max(nums) if nums else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape a bible.by translation into JSON.")
    ap.add_argument("--code", required=True, help="bible.by translation code, e.g. erv/bti/desp")
    ap.add_argument("--out", required=True, help="output filename under data/bibles/, e.g. ru_erv.json")
    ap.add_argument("--nt-only", action="store_true", help="scrape only the 27 NT books (40..66)")
    ap.add_argument("--refresh", action="store_true", help="ignore cache, re-fetch live")
    args = ap.parse_args()

    code = args.code
    out_path = BIBLES_DIR / args.out
    cache_dir = CACHE_ROOT / code

    books_meta = yaml.safe_load(BOOKS_FILE.read_text("utf-8"))
    canonical_order = list(books_meta.keys())

    # Which bible.by book numbers to scrape.
    if args.nt_only:
        book_numbers = range(NT_START, len(BIBLEBY_ABBREVS) + 1)
    else:
        book_numbers = range(1, len(BIBLEBY_ABBREVS) + 1)

    by_ab: dict[str, dict] = {}
    for bnum in book_numbers:
        abbrev = BIBLEBY_ABBREVS[bnum - 1]
        ru_name = books_meta[abbrev]["ru"]
        first = fetch(f"https://bible.by/{code}/{bnum}/1/", cache_dir, args.refresh)
        title = re.search(r"<title>(.*?)</title>", first)
        title_book = title.group(1).split(",")[0] if title else "?"
        nchap = chapter_count(first, code, bnum)
        print(f"[{bnum:>2}] {abbrev:<5} {ru_name:<22} chapters={nchap}  ({title_book.strip()})")
        # sanity check: page title's book name vs expected. bible.by numbering is
        # site-wide and verified, but translations use different book names
        # (e.g. ERV "1 Летопись" vs Synodal "1 Паралипоменон") — so a mismatch is
        # a WARNING (eyeball it), not a hard failure. A truly missing/empty book
        # is still caught downstream ("no verses parsed").
        norm = lambda s: re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip().lower()
        a, b = norm(ru_name)[:4], norm(title_book)[:4]
        if a != b and "песн" not in norm(title_book):
            print(f"     WARN: title '{title_book.strip()}' != expected '{ru_name}' ({abbrev})")
        chapters = []
        for ch in range(1, nchap + 1):
            html = first if ch == 1 else fetch(f"https://bible.by/{code}/{bnum}/{ch}/", cache_dir, args.refresh)
            verses = parse_chapter(html)
            if not verses:
                raise RuntimeError(f"no verses parsed for {abbrev} ch {ch} (book {bnum})")
            chapters.append(verses)
        by_ab[abbrev] = {"abbrev": abbrev, "name": ru_name, "chapters": chapters}

    # write in canonical books.yaml order (only the books we scraped)
    result = [by_ab[ab] for ab in canonical_order if ab in by_ab]
    out_path.write_text(json.dumps(result, ensure_ascii=False), "utf-8")
    total = sum(len(c) for b in result for c in b["chapters"])
    print(f"\nWrote {out_path}\n  books={len(result)}  verses={total}")


if __name__ == "__main__":
    main()

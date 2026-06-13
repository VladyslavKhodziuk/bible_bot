"""
One-off scraper: downloads the public-domain "Biblia Torres Amat" (1825, Catholic
translation from the Vulgate) from bibliatodo.com and writes
data/bibles/es_torres.json in the project format.

bibliatodo serves one chapter per URL:
    https://www.bibliatodo.com/la-biblia/Torres-amat/<slug>-<chapter>
Each verse is a <p class="bt-verse" ... d-v="N">...<span class="bt-verse-text">
TEXT</span></p>. An out-of-range chapter returns a 200 page with zero verse
paragraphs, which signals the end of the book.

Only the 66 books in data/books.yaml are scraped (the Catholic deuterocanonical
books served by the site are skipped); output stays in books.yaml order so it
aligns with the other translations by list index.

Run:  python tools/scrape_torres.py            # full scrape
      python tools/scrape_torres.py gn re      # only the given abbrevs (test)
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

BASE = "https://www.bibliatodo.com/la-biblia/Torres-amat/{slug}-{chapter}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bible-bot-importer/1.0)"}
DELAY = 0.25          # polite pause between requests (seconds)
MAX_CHAPTERS = 160    # safety cap (Psalms = 150)
RETRIES = 3

# books.yaml abbrev -> bibliatodo slug (66-book Protestant canon)
SLUG = {
    "gn": "genesis", "ex": "exodo", "lv": "levitico", "nm": "numeros",
    "dt": "deuteronomio", "js": "josue", "jud": "jueces", "rt": "rut",
    "1sm": "1samuel", "2sm": "2samuel", "1kgs": "1reyes", "2kgs": "2reyes",
    "1ch": "1cronicas", "2ch": "2cronicas", "ezr": "esdras", "ne": "nehemias",
    "et": "ester", "job": "job", "ps": "salmos", "prv": "proverbios",
    "ec": "eclesiastes", "so": "cantares", "is": "isaias", "jr": "jeremias",
    "lm": "lamentaciones", "ez": "ezequiel", "dn": "daniel", "ho": "oseas",
    "jl": "joel", "am": "amos", "ob": "abdias", "jn": "jonas", "mi": "miqueas",
    "na": "nahum", "hk": "habacuc", "zp": "sofonias", "hg": "hageo",
    "zc": "zacarias", "ml": "malaquias",
    "mt": "mateo", "mk": "marcos", "lk": "lucas", "jo": "juan", "act": "hechos",
    "rm": "romanos", "1co": "1corintios", "2co": "2corintios", "gl": "galatas",
    "eph": "efesios", "ph": "filipenses", "cl": "colosenses",
    "1ts": "1tesalonicenses", "2ts": "2tesalonicenses", "1tm": "1timoteo",
    "2tm": "2timoteo", "tt": "tito", "phm": "filemon", "hb": "hebreos",
    "jm": "santiago", "1pe": "1pedro", "2pe": "2pedro", "1jo": "1juan",
    "2jo": "2juan", "3jo": "3juan", "jd": "judas", "re": "apocalipsis",
}

ROOT = Path(__file__).resolve().parent.parent
BOOKS_FILE = ROOT / "data" / "books.yaml"
OUT_FILE = ROOT / "data" / "bibles" / "es_torres.json"

VERSE_RE = re.compile(
    r'<p class="bt-verse"[^>]*d-v="(\d+)"[^>]*>.*?'
    r'<span class="bt-verse-text">(.*?)</span>',
    re.DOTALL,
)
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
    raw = TAG_RE.sub("", raw)         # strip inline tags (footnote links, em, ...)
    raw = html.unescape(raw)
    raw = WS_RE.sub(" ", raw).strip()
    return raw


def parse_chapter(body: str) -> list[str]:
    """Return verse texts ordered by verse number. Warns on non-contiguous numbering."""
    pairs: list[tuple[int, str]] = []
    for m in VERSE_RE.finditer(body):
        pairs.append((int(m.group(1)), clean_verse(m.group(2))))
    pairs.sort(key=lambda x: x[0])
    nums = [n for n, _ in pairs]
    if nums and nums != list(range(1, len(nums) + 1)):
        print(f"    WARNING: non-contiguous verses {nums[:3]}...{nums[-3:]}", flush=True)
    return [t for _, t in pairs]


def main() -> int:
    book_order = list(yaml.safe_load(BOOKS_FILE.read_text(encoding="utf-8")).keys())
    if len(book_order) != 66:
        print(f"WARNING: expected 66 books in books.yaml, got {len(book_order)}")

    only = set(sys.argv[1:])  # optional abbrev filter for testing
    result = []
    for abbrev in book_order:
        slug = SLUG[abbrev]
        if only and abbrev not in only:
            continue
        chapters: list[list[str]] = []
        ch = 1
        while ch <= MAX_CHAPTERS:
            body = fetch(BASE.format(slug=slug, chapter=ch))
            verses = parse_chapter(body)
            if not verses:
                break
            chapters.append(verses)
            ch += 1
            time.sleep(DELAY)
        result.append({"abbrev": abbrev, "chapters": chapters})
        total_v = sum(len(c) for c in chapters)
        print(f"{abbrev:5} ({slug:16}) -> {len(chapters):3} chapters, {total_v:5} verses", flush=True)

    if only:
        print("\n(test run — not writing file)")
        return 0

    OUT_FILE.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_FILE} ({OUT_FILE.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

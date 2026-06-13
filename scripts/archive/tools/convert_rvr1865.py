"""
One-off converter: downloads the public-domain "Reina-Valera 1865" (SpaRV1865)
from the scrollmapper/bible_databases repo and writes data/bibles/es_rvr1865.json
in the project format.

Source format:
    {"translation": "...", "books": [
        {"name": "Genesis", "chapters": [
            {"chapter": 1, "verses": [{"verse": 1, "text": "..."}, ...]}, ...]}, ...]}

The source uses the same 66-book canonical order as data/books.yaml (verified;
only the display names differ, e.g. "I Samuel" vs "1 Samuel"), so books are
mapped by list index. Output: [{"abbrev": ..., "chapters": [[verse_str, ...]]}].

Run:  python tools/convert_rvr1865.py
"""
import json
import re
import urllib.request
from pathlib import Path

import yaml

SRC = "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/SpaRV1865.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bible-bot-importer/1.0)"}

ROOT = Path(__file__).resolve().parent.parent
BOOKS_FILE = ROOT / "data" / "books.yaml"
OUT_FILE = ROOT / "data" / "bibles" / "es_rvr1865.json"

WS_RE = re.compile(r"\s+")


def main() -> int:
    req = urllib.request.Request(SRC, headers=HEADERS)
    src = json.load(urllib.request.urlopen(req, timeout=120))
    sm_books = src["books"]

    book_order = list(yaml.safe_load(BOOKS_FILE.read_text(encoding="utf-8")).keys())
    if len(book_order) != len(sm_books):
        raise SystemExit(f"book count mismatch: books.yaml={len(book_order)} source={len(sm_books)}")

    result = []
    for abbrev, sm in zip(book_order, sm_books):
        chapters = []
        for ch in sm["chapters"]:
            verses = sorted(ch["verses"], key=lambda v: v["verse"])
            nums = [v["verse"] for v in verses]
            if nums and nums != list(range(1, len(nums) + 1)):
                print(f"    WARN {abbrev} ch{ch['chapter']}: non-contiguous {nums[:3]}...{nums[-3:]}")
            chapters.append([WS_RE.sub(" ", v["text"]).strip() for v in verses])
        result.append({"abbrev": abbrev, "chapters": chapters})
        total_v = sum(len(c) for c in chapters)
        print(f"{abbrev:5} <- {sm['name']:20} -> {len(chapters):3} chapters, {total_v:5} verses", flush=True)

    OUT_FILE.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_FILE} ({OUT_FILE.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
One-off cleaner: strips editorial markup from data/bibles/es_sagradas.json so
the Sagradas Escrituras 1569 text renders as plain text like the other
translations.

Removes:
  - paragraph markers (¶)
  - italic tags for translator-supplied words (<I>...</I> and any stray tags)
  - collapses runs of whitespace left behind

Rewrites the file in place (preserving its list/{abbrev,name,chapters} shape).

Run:  python tools/clean_sagradas.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "bibles" / "es_sagradas.json"

TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
WS_RE = re.compile(r"\s+")


def clean(text: str) -> str:
    text = TAG_RE.sub("", text)
    text = text.replace("¶", "")
    return WS_RE.sub(" ", text).strip()


def main() -> int:
    data = json.loads(FILE.read_text(encoding="utf-8-sig"))
    changed = 0
    for book in data:
        for chapter in book["chapters"]:
            for i, verse in enumerate(chapter):
                cleaned = clean(verse)
                if cleaned != verse:
                    chapter[i] = cleaned
                    changed += 1
    FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"cleaned {changed} verses; wrote {FILE} ({FILE.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

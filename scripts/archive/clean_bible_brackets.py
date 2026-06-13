"""One-time cleanup of editorial markup in English Bible JSONs.

Some public-domain English translations ship with translator markup embedded
right in the verse text, which looks broken to end users:

  * KJV (en_kjv) — curly-brace marginal notes like ``{firmament: Heb. expansion}``
    (alternate readings, contain a colon), curly-brace italicized additions like
    ``{was}`` / ``{and}`` (no colon), square-bracket Psalm superscriptions like
    ``[A Psalm of David.]``, and guillemet-wrapped epistle subscriptions like
    ``«Written to the Romans from Corinthus…}»`` (editorial post-scripts, not
    scripture) — plus a couple of orphan ``}`` left by corrupted source notes.
  * WEB (en_web) / ASV (en_asv) — square-bracket added words like ``[namely]``.

This script rewrites the affected JSON files in place (after backing each up to
``<file>.bak``) with these rules, applied to every verse string:

  1. Remove guillemet subscriptions ``«…»`` -> ""                      (editorial post-script)
  2. Remove brace notes that contain a colon  ``{x: y}``  -> ""        (marginal note)
  3. Unwrap remaining braces                   ``{word}`` -> ``word``    (inserted word)
  4. Unwrap square brackets                    ``[text]`` -> ``text``    (keep the text)
  5. Remove an orphan trailing ``word}`` left by a corrupted opening brace
  6. Strip any residual stray brace/bracket/guillemet chars
  7. Tidy whitespace: collapse runs of spaces, drop spaces before , . ; : ! ?

JSON structure: a file is a list of books; each book has ``chapters`` (a list of
chapters); each chapter is a list of verse strings.

Run once:  python scripts/clean_bible_brackets.py
"""
import json
import re
import shutil
from pathlib import Path

BIBLES_DIR = Path(__file__).resolve().parent.parent / "data" / "bibles"

# Files that carry editorial markup.
TARGET_FILES = ("en_kjv.json", "en_web.json", "en_asv.json")

_SUBSCRIPTION = re.compile(r"\s*«[^»]*»")  # «Written to the Romans…}»
_NOTE_BRACE = re.compile(r"\{[^}]*:[^}]*\}")   # {firmament: Heb. expansion}
_WORD_BRACE = re.compile(r"\{([^}:]*)\}")      # {was} -> was
_BRACKET = re.compile(r"\[([^\]]*)\]")         # [A Psalm of David.] -> A Psalm of David.
_ORPHAN_CLOSE = re.compile(r"\s*\S+\}")        # "… substance. yourselves}" -> "… substance."
_STRAY = re.compile(r"[{}\[\]«»]")   # any residual brace/bracket/guillemet
_SPACE_RUN = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")


def clean_text(text: str) -> str:
    """Strip editorial brackets/braces/subscriptions from a single verse string."""
    text = _SUBSCRIPTION.sub("", text)
    text = _NOTE_BRACE.sub("", text)
    text = _WORD_BRACE.sub(r"\1", text)
    text = _BRACKET.sub(r"\1", text)
    text = _ORPHAN_CLOSE.sub("", text)
    text = _STRAY.sub("", text)
    text = _SPACE_RUN.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    return text.strip()


def clean_file(path: Path) -> None:
    if not path.exists():
        print(f"  SKIP (not found): {path.name}")
        return

    with open(path, "r", encoding="utf-8-sig") as f:
        books = json.load(f)

    changed = 0
    total = 0
    sample_before = sample_after = None
    for book in books:
        for chapter in book.get("chapters", []):
            for i, verse in enumerate(chapter):
                total += 1
                cleaned = clean_text(verse)
                if cleaned != verse:
                    changed += 1
                    if sample_before is None:
                        sample_before, sample_after = verse, cleaned
                    chapter[i] = cleaned

    if changed == 0:
        print(f"  {path.name}: nothing to clean ({total} verses)")
        return

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"  backup -> {backup.name}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False)

    print(f"  {path.name}: cleaned {changed}/{total} verses")
    print(f"    before: {sample_before[:120]}")
    print(f"    after:  {sample_after[:120]}")


def main() -> None:
    print(f"Cleaning bibles in {BIBLES_DIR}")
    for name in TARGET_FILES:
        clean_file(BIBLES_DIR / name)
    print("Done.")


if __name__ == "__main__":
    main()

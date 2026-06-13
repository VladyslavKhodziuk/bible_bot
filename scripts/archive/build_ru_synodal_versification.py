"""Generate the `ru_synodal` block of data/versification_map.json after the bible.by rebuild.

Why: the new ru_synodal.json reproduces bible.by's authentic Synodal (Septuagint) psalm
numbering (Ps 50 = "Помилуй меня"), whereas the curated pools (verse/wisdom/topic) store
Masoretic references. ru_synodal therefore no longer resolves by identity and needs map
entries — exactly like ru_nrt already has. (ru_nrt, en_*, es_*, uk_* entries are unaffected
and are left intact.)

Key fact (verified): the new ru_synodal and ru_nrt share IDENTICAL versification across the
whole Bible except Romans 14 & 16 (doxology placement), and no curated reference falls there.
ru_synodal's curated divergences therefore equal ru_nrt's. So we copy ru_nrt's effective
(auto + manual) entries for every curated reference, validating that each target coordinate
exists in the new ru_synodal and that the chapter's verse count matches ru_nrt's (a guard that
would catch any Romans-like divergence touching a curated ref). A content-similarity check
(ru_nrt vs ru_synodal at the mapped verse) is printed for eyeball review.

Run:  python scripts/build_ru_synodal_versification.py            # report only
      python scripts/build_ru_synodal_versification.py --write    # merge into the map
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NEW = ROOT / "data" / "bibles" / "ru_synodal.json"
NRT = ROOT / "data" / "bibles" / "ru_nrt.json"
MAP = ROOT / "data" / "versification_map.json"
MANUAL = ROOT / "data" / "versification_map_manual.json"
DATA = ROOT / "data"

_spec = importlib.util.spec_from_file_location("bvm", ROOT / "scripts" / "build_versification_map.py")
bvm = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bvm)


def load(path: Path) -> dict[str, dict]:
    return {b["abbrev"]: b for b in json.loads(path.read_text("utf-8-sig"))}


def collect_refs() -> list[tuple[str, int, int]]:
    refs: set[tuple[str, int, int]] = set()
    for r in yaml.safe_load((DATA / "verses_of_day.yaml").read_text("utf-8")).get("verses", []):
        ab, cv = r.rsplit(" ", 1); c, v = cv.split(":"); refs.add((ab, int(c), int(v)))
    for items in (yaml.safe_load((DATA / "wisdom_of_day.yaml").read_text("utf-8")).get("themes") or {}).values():
        for it in items or []:
            ab, cv = it["ref"].rsplit(" ", 1); c, v = cv.split(":"); refs.add((ab, int(c), int(v)))
    for t in yaml.safe_load((DATA / "topics.yaml").read_text("utf-8")).values():
        for r in t.get("verses", []):
            ab, c, v = r.split(":"); refs.add((ab, int(c), int(v)))
    return sorted(refs)


def chap_len(books: dict, ab: str, ch: int) -> int | None:
    b = books.get(ab)
    if not b or not (0 <= ch - 1 < len(b["chapters"])):
        return None
    return len(b["chapters"][ch - 1])


def verse(books: dict, ab: str, ch: int, v: int) -> str | None:
    n = chap_len(books, ab, ch)
    return books[ab]["chapters"][ch - 1][v - 1] if n and 0 <= v - 1 < n else None


def main() -> None:
    write = "--write" in sys.argv
    syn, nrt = load(NEW), load(NRT)
    auto = json.loads(MAP.read_text("utf-8"))
    manual = json.loads(MANUAL.read_text("utf-8"))
    nrt_map = dict(auto.get("ru_nrt", {}))
    nrt_map.update(manual.get("ru_nrt", {}))   # hand corrections win

    refs = collect_refs()
    entries: dict[str, list[int]] = {}
    review: list[str] = []
    problems: list[str] = []
    for ab, ch, v in refs:
        key = f"{ab} {ch}:{v}"
        # Only Psalms diverge between Masoretic (curated pool) and the Synodal tradition.
        # Non-psalm books follow Masoretic numbering in the Synodal (identity); any ru_nrt
        # entries there are NRT-specific translation quirks that do NOT apply to ru_synodal
        # (verified by hand: ec 4:9/4:12, js 24:15, dn 3:17, mt 22:37/39 all hold at identity).
        if ab != "ps":
            continue
        coord = nrt_map.get(key)
        # guard: if syn and nrt disagree on this chapter's length, copying nrt is unsafe
        if chap_len(syn, ab, ch) != chap_len(nrt, ab, ch):
            problems.append(f"{key}: syn/nrt chapter length differ — review")
            continue
        if coord is None:
            continue                                  # numbering coincides -> identity
        sc, sv = coord
        if verse(syn, ab, sc, sv) is None:
            problems.append(f"{key} -> {sc}:{sv} OUT OF RANGE in ru_synodal")
            continue
        entries[key] = [sc, sv]
        sim = bvm.sim(bvm.norm(verse(nrt, ab, sc, sv)), bvm.norm(verse(syn, ab, sc, sv)))
        review.append(f"  {key} -> {sc}:{sv}  (nrt~syn sim={sim:.2f})\n"
                      f"      syn: {(verse(syn, ab, sc, sv) or '')[:70]}")

    print(f"Curated refs: {len(refs)}  |  ru_synodal overrides: {len(entries)}\n")
    print("=== OVERRIDES (copied from ru_nrt, validated against ru_synodal) ===")
    print("\n".join(review))
    if problems:
        print(f"\n=== PROBLEMS ({len(problems)}) ===")
        print("\n".join("  " + p for p in problems))

    if write:
        auto["ru_synodal"] = dict(sorted(entries.items()))
        MAP.write_text(json.dumps(auto, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
        print(f"\nMerged ru_synodal block ({len(entries)} entries) into {MAP}")
    else:
        print("\n(report only; pass --write to merge)")


if __name__ == "__main__":
    main()

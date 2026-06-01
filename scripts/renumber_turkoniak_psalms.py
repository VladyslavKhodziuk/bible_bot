"""Renumber uk_turkoniak Psalms from Masoretic to authentic Septuagint numbering.

Turkoniak is translated from the Septuagint and uses Septuagint psalm numbering (Ps 22 = the
goodness/mercy psalm, Ps 50 = "Помилуй мене"). Our data/bibles/uk_turkoniak.json had the psalms
in Masoretic order (matching the uk_ogienko anchor), so the bot showed e.g. "Псалми 23:6" where
the printed Turkoniak says 22:6. This regroups/relabels the 150 psalms to Septuagint numbering,
copying every verse string VERBATIM (no text change), and regenerates uk_turkoniak's psalm
entries in data/versification_map.json so curated (Masoretic) references still resolve.

Note: our data merges 2-line historical superscriptions into verse 1 (Masoretic style), so for a
few historically-titled psalms the VERSE number stays 1-2 lower than a printed Septuagint
Turkoniak; the CHAPTER numbering and the reported Ps 23->22 case are fully corrected.

Run:  python scripts/renumber_turkoniak_psalms.py            # report only
      python scripts/renumber_turkoniak_psalms.py --write    # apply data + map changes
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIBLE = ROOT / "data" / "bibles" / "uk_turkoniak.json"
MAP = ROOT / "data" / "versification_map.json"

_spec = importlib.util.spec_from_file_location("brsv", ROOT / "scripts" / "build_ru_synodal_versification.py")
brsv = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(brsv)
collect_refs = brsv.collect_refs


def build_lxx_psalms(mt: list[list[str]]) -> tuple[list[list[str]], "callable"]:
    """Return (lxx_chapters, mt_to_lxx) for the standard Masoretic->Septuagint psalm transform.

    mt is a list of 150 Masoretic chapters (each a list of verse strings). Verses are copied
    verbatim. Also returns a closure mt_to_lxx(ch, v) -> (lxx_ch, lxx_v) consistent with the
    rebuilt data (used to regenerate the versification map).
    """
    assert len(mt) == 150, f"expected 150 MT psalms, got {len(mt)}"
    g = lambda n: mt[n - 1]                       # MT chapter n (1-based) -> verse list
    n9 = len(g(9))                                # merge offset for MT 10 -> LXX 9
    n114 = len(g(114))                            # merge offset for MT 115 -> LXX 113

    lxx: list[list[str]] = []
    lxx += [list(g(n)) for n in range(1, 9)]      # LXX 1-8 = MT 1-8
    lxx.append(list(g(9)) + list(g(10)))          # LXX 9   = MT 9 + MT 10
    lxx += [list(g(n)) for n in range(11, 114)]   # LXX 10-112 = MT 11-113
    lxx.append(list(g(114)) + list(g(115)))       # LXX 113 = MT 114 + MT 115
    lxx.append(list(g(116)[:9]))                  # LXX 114 = MT 116:1-9
    lxx.append(list(g(116)[9:]))                  # LXX 115 = MT 116:10-19
    lxx += [list(g(n)) for n in range(117, 147)]  # LXX 116-145 = MT 117-146
    lxx.append(list(g(147)[:11]))                 # LXX 146 = MT 147:1-11
    lxx.append(list(g(147)[11:]))                 # LXX 147 = MT 147:12-20
    lxx += [list(g(n)) for n in range(148, 151)]  # LXX 148-150 = MT 148-150
    assert len(lxx) == 150, f"produced {len(lxx)} LXX psalms"

    def mt_to_lxx(ch: int, v: int) -> tuple[int, int]:
        if 1 <= ch <= 8 or 148 <= ch <= 150:
            return ch, v
        if ch == 9:
            return 9, v
        if ch == 10:
            return 9, v + n9
        if 11 <= ch <= 113:
            return ch - 1, v
        if ch == 114:
            return 113, v
        if ch == 115:
            return 113, v + n114
        if ch == 116:
            return (114, v) if v <= 9 else (115, v - 9)
        if 117 <= ch <= 146:
            return ch - 1, v
        if ch == 147:
            return (146, v) if v <= 11 else (147, v - 11)
        raise ValueError(f"psalm chapter out of range: {ch}")

    return lxx, mt_to_lxx


def main() -> None:
    write = "--write" in sys.argv
    books = json.loads(BIBLE.read_text("utf-8-sig"))
    ps_book = next(b for b in books if b["abbrev"] == "ps")
    mt = ps_book["chapters"]

    before_flat = [t for ch in mt for t in ch]
    lxx, mt_to_lxx = build_lxx_psalms(mt)
    after_flat = [t for ch in lxx for t in ch]

    # invariant: every verse string preserved, same order (only regrouped)
    assert before_flat == after_flat, "verse text changed — transform is not text-preserving!"
    print(f"psalms: {len(mt)} -> {len(lxx)} | verses preserved: {len(after_flat)} "
          f"(was {len(before_flat)})")
    print("  spot:")
    print(f"    LXX 22 verses={len(lxx[21])}  22:6 = {lxx[21][5][:60]}")
    print(f"    LXX 50:1 = {lxx[49][0][:55]}")
    print(f"    LXX 9 verses={len(lxx[8])} | LXX113 verses={len(lxx[112])}")
    print(f"    LXX114:1 = {lxx[113][0][:45]} | LXX115:1 = {lxx[114][0][:45]}")
    print(f"    LXX147:1 = {lxx[146][0][:50]}")

    # versification map: regenerate ONLY uk_turkoniak's psalm entries from the same transform
    full = json.loads(MAP.read_text("utf-8"))
    tk_block = dict(full.get("uk_turkoniak", {}))
    nonps = {k: v for k, v in tk_block.items() if not k.startswith("ps ")}
    ps_entries: dict[str, list[int]] = {}
    for ab, ch, v in collect_refs():
        if ab != "ps":
            continue
        lc, lv = mt_to_lxx(ch, v)
        if (lc, lv) != (ch, v):
            ps_entries[f"ps {ch}:{v}"] = [lc, lv]
    merged = dict(sorted({**nonps, **ps_entries}.items()))
    print(f"\nuk_turkoniak map: {len(nonps)} non-psalm kept, {len(ps_entries)} psalm entries")
    for k in ("ps 23:6", "ps 51:10", "ps 32:8", "ps 9:9", "ps 116:1", "ps 147:3"):
        if k in ps_entries:
            print(f"    {k} -> {ps_entries[k]}")

    if write:
        ps_book["chapters"] = lxx
        BIBLE.write_text(json.dumps(books, ensure_ascii=False), "utf-8")
        full["uk_turkoniak"] = merged
        MAP.write_text(json.dumps(full, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
        print(f"\nWrote {BIBLE.name} and uk_turkoniak block of {MAP.name}")
    else:
        print("\n(report only; pass --write to apply)")


if __name__ == "__main__":
    main()

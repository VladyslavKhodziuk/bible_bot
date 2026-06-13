"""Validate the rebuilt data/bibles/ru_synodal.json (structure, cleanliness, key verses)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NEW = ROOT / "data" / "bibles" / "ru_synodal.json"
KJV = ROOT / "data" / "bibles" / "en_kjv.json"
BOOKS = ROOT / "data" / "books.yaml"


def load(p: Path):
    return {b["abbrev"]: b for b in json.loads(p.read_text("utf-8-sig"))}


def main() -> None:
    data = json.loads(NEW.read_text("utf-8-sig"))
    by_ab = {b["abbrev"]: b for b in data}
    meta = yaml.safe_load(BOOKS.read_text("utf-8"))
    expected = list(meta.keys())[:66]
    kjv = load(KJV)

    fail = []

    # 1. book set & order
    got = [b["abbrev"] for b in data]
    if got != expected:
        fail.append(f"book order/set mismatch: {got}")

    # 2. cleanliness + no empty verses
    total = 0
    bad_artifacts = []
    empties = []
    for b in data:
        for ci, ch in enumerate(b["chapters"], 1):
            for vi, v in enumerate(ch, 1):
                total += 1
                if not v.strip():
                    empties.append(f"{b['abbrev']} {ci}:{vi}")
                if re.search(r"[<>\[\]]|\(\d+[:\-]\d+\)|<sup>", v):
                    bad_artifacts.append(f"{b['abbrev']} {ci}:{vi}: {v[:50]}")
    if empties:
        fail.append(f"{len(empties)} empty verses, e.g. {empties[:5]}")
    if bad_artifacts:
        fail.append(f"{len(bad_artifacts)} artifact verses, e.g. {bad_artifacts[:5]}")

    # 3. psalms structure (native Synodal numbering)
    ps = by_ab["ps"]["chapters"]
    if len(ps) != 150:
        fail.append(f"Psalms has {len(ps)} chapters, expected 150")
    if len(ps[49]) != 21:
        fail.append(f"Ps 50 has {len(ps[49])} verses, expected 21 (superscription counted)")
    if "Помилуй меня" not in ps[49][2]:
        fail.append(f"Ps 50:3 not the Miserere: {ps[49][2][:50]}")
    if "мя" in ps[49][2].split():
        fail.append("Ps 50:3 contains Church-Slavonic 'мя'")

    # 4. spot-check famous verses
    checks = [
        ("gn", 1, 1, "В начале сотворил Бог"),
        ("jo", 3, 16, "так возлюбил Бог мир"),
        ("ps", 22, 1, "Пастырь мой"),          # LXX numbering: Masoretic 23 == Synodal 22
        ("ps", 50, 12, "Сердце чистое сотвори"),
    ]
    for ab, ch, v, needle in checks:
        try:
            txt = by_ab[ab]["chapters"][ch - 1][v - 1]
        except (KeyError, IndexError):
            txt = ""
        if needle not in txt:
            fail.append(f"{ab} {ch}:{v} missing '{needle}': {txt[:50]}")

    # 5. NT verse counts should match KJV (Masoretic == Synodal for NT)
    nt = list(meta.keys())[39:66]
    mismatch = []
    for ab in nt:
        if ab not in kjv:
            continue
        a, k = by_ab[ab]["chapters"], kjv[ab]["chapters"]
        if len(a) != len(k):
            mismatch.append(f"{ab}: {len(a)} ch vs KJV {len(k)}")
            continue
        for i in range(len(k)):
            if len(a[i]) != len(k[i]):
                mismatch.append(f"{ab} ch{i+1}: {len(a[i])} vs KJV {len(k[i])}")
    if mismatch:
        # informational — minor NT versification diffs exist; print but don't hard-fail
        print(f"NT verse-count diffs vs KJV ({len(mismatch)}): {mismatch[:15]}")

    print(f"\nbooks={len(data)}  verses={total}  psalms={len(ps)}")
    if fail:
        print("\nFAILURES:")
        for f in fail:
            print("  -", f)
        raise SystemExit(1)
    print("ALL STRUCTURAL CHECKS PASSED")


if __name__ == "__main__":
    main()

"""Build a versification alignment map for shared (cross-translation) references.

Problem: curated content (verse of the day, wisdom of the day, topics) stores a
single canonical reference (abbrev chapter:verse) in *Masoretic / Protestant*
versification and resolves the text in each user's translation by that number.
That breaks for translations that use a different versification tradition:
  - ru_nrt        -> Greek/Septuagint psalm numbering (Ps 23 == Masoretic Ps 24)
  - uk_khomenko   -> Catholic: psalm superscription counted as a verse (shift)
  - uk_turkoniak  -> Septuagint (Jeremiah re-ordered, scattered verse merges)
  - uk_kulish, en_asv/web -> a few scattered chapters
The anchors (ru_synodal, en_kjv, es_rvr, uk_ogienko) match the curated pool.

Method: for each translation, only books whose chapter verse-counts differ from
the anchor (the "structural gate") are processed — this eliminates false
positives from paraphrase translations whose numbering is identical. For a
gated book we align the anchor's flattened verse sequence to the translation's
by *banded monotonic sequence alignment* (Needleman-Wunsch in a diagonal band)
on token similarity; this resolves chapter/verse shifts by context rather than
fragile per-verse thresholds. Books that are RE-ORDERED across versifications
(Jeremiah) are aligned by per-reference best match across the whole book.

Writes data/versification_map.json:
    { "<translation>": { "<abbrev> <ch>:<v>": [mapped_ch, mapped_v], ... }, ... }
Only divergent references are stored (an absent entry == identity).

Run:  python scripts/build_versification_map.py            # report (verify by eye)
      python scripts/build_versification_map.py --write    # write the map
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BIBLES = ROOT / "data" / "bibles"
OUT = ROOT / "data" / "versification_map.json"

TRANSLATIONS = {
    "ru_synodal": "ru", "ru_nrt": "ru",
    "en_kjv": "en", "en_asv": "en", "en_web": "en",
    "es_rvr": "es", "es_rvr1865": "es", "es_torres": "es", "es_sagradas": "es",
    "uk_ogienko": "uk", "uk_kulish": "uk", "uk_turkoniak": "uk", "uk_khomenko": "uk",
}
ANCHOR = {"ru": "ru_synodal", "en": "en_kjv", "es": "es_rvr", "uk": "uk_ogienko"}

REORDERED = {"jr"}   # non-monotonic across versifications -> per-ref whole-book match
BAND = 80            # half-width of the alignment band (verses)
GAP = 0.04           # gap penalty in the alignment DP
MIN_KEEP = 0.12      # mapped pair below this is dropped (avoid confident-wrong overrides)
LOW_SIM = 0.18       # kept but printed with a <<low tag for manual review


def load_bibles() -> dict[str, dict[str, dict]]:
    return {
        code: {b["abbrev"]: b for b in json.loads((BIBLES / f"{code}.json").read_text("utf-8-sig"))}
        for code in TRANSLATIONS
    }


def verse(books: dict, ab: str, ch: int, v: int) -> str | None:
    b = books.get(ab)
    if not b:
        return None
    chs = b["chapters"]
    if not (0 <= ch - 1 < len(chs)):
        return None
    vs = chs[ch - 1]
    return vs[v - 1] if 0 <= v - 1 < len(vs) else None


def norm(text: str | None) -> frozenset[str]:
    if not text:
        return frozenset()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("’", "'").replace("ʼ", "'")
    # strip leading "(50:12)" / "(50-12)" cross-numbering annotations
    text = re.sub(r"\(\d+[:\-]\d+\)", " ", text)
    return frozenset(re.findall(r"\w+", text, flags=re.UNICODE))


def sim(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def flatten(book: dict) -> list[tuple[int, int, frozenset[str]]]:
    out = []
    for ci, verses in enumerate(book["chapters"], start=1):
        for vi, text in enumerate(verses, start=1):
            out.append((ci, vi, norm(text)))
    return out


def align(a_seq: list, b_seq: list) -> dict[tuple[int, int], tuple[int, int, float]]:
    """Banded Needleman-Wunsch. Returns anchor (ch,v) -> (tch, tv, sim) for matches."""
    n, m = len(a_seq), len(b_seq)
    NEG = float("-inf")
    # dp[i][j] over band; store as dict of dicts keyed by absolute j
    prev = {0: 0.0}
    back = [dict() for _ in range(n + 1)]  # back[i][j] = 'd'/'u'/'l'
    # initialise row 0
    for j in range(1, min(m, BAND) + 1):
        prev[j] = prev[j - 1] - GAP
        back[0][j] = "l"
    rows = [prev]
    for i in range(1, n + 1):
        center = int(i * m / n) if n else 0
        lo, hi = max(0, center - BAND), min(m, center + BAND)
        cur: dict[int, float] = {}
        ai = a_seq[i - 1][2]
        for j in range(lo, hi + 1):
            best, bk = NEG, None
            up = rows[i - 1].get(j)
            if up is not None:  # deletion (anchor verse unmatched)
                val = up - GAP
                if val > best:
                    best, bk = val, "u"
            if j > lo or j == 0:
                left = cur.get(j - 1)
                if left is not None:  # insertion
                    val = left - GAP
                    if val > best:
                        best, bk = val, "l"
            if j >= 1:
                diag = rows[i - 1].get(j - 1)
                if diag is not None:
                    val = diag + sim(ai, b_seq[j - 1][2])
                    if val > best:
                        best, bk = val, "d"
            if bk is not None:
                cur[j] = best
                back[i][j] = bk
        if not cur:  # safety: keep a path
            j = min(m, center)
            cur[j] = rows[i - 1].get(j, 0.0) - GAP
            back[i][j] = "u"
        rows.append(cur)
    # traceback from (n, best j in last row)
    last = rows[n]
    j = max(last, key=last.get)
    i = n
    mapping: dict[tuple[int, int], tuple[int, int, float]] = {}
    while i > 0:
        bk = back[i].get(j)
        if bk == "d":
            ac, av, ai = a_seq[i - 1]
            bc, bv, bj = b_seq[j - 1]
            mapping[(ac, av)] = (bc, bv, sim(ai, bj))
            i, j = i - 1, j - 1
        elif bk == "u":
            i -= 1
        elif bk == "l":
            j -= 1
        else:
            i -= 1
    return mapping


def best_match(books: dict, ab: str, atok: frozenset) -> tuple[int, int, float, float]:
    b = books[ab]
    best_pos, best, second = (1, 1), -1.0, -1.0
    for ci, verses in enumerate(b["chapters"], start=1):
        for vi, text in enumerate(verses, start=1):
            s = sim(atok, norm(text))
            if s > best:
                second, best, best_pos = best, s, (ci, vi)
            elif s > second:
                second = s
    return best_pos[0], best_pos[1], best, max(second, 0.0)


def book_differs(tb: dict, ab_books: dict, ab: str) -> bool:
    t, a = tb.get(ab), ab_books.get(ab)
    if not t or not a:
        return False
    tc, ac = t["chapters"], a["chapters"]
    return len(tc) != len(ac) or any(len(tc[i]) != len(ac[i]) for i in range(len(ac)))


def collect_refs() -> list[tuple[str, int, int]]:
    refs: set[tuple[str, int, int]] = set()
    d = ROOT / "data"
    for r in yaml.safe_load((d / "verses_of_day.yaml").read_text("utf-8")).get("verses", []):
        ab, cv = r.rsplit(" ", 1); c, v = cv.split(":"); refs.add((ab, int(c), int(v)))
    for items in (yaml.safe_load((d / "wisdom_of_day.yaml").read_text("utf-8")).get("themes") or {}).values():
        for it in items or []:
            ab, cv = it["ref"].rsplit(" ", 1); c, v = cv.split(":"); refs.add((ab, int(c), int(v)))
    for t in yaml.safe_load((d / "topics.yaml").read_text("utf-8")).values():
        for r in t.get("verses", []):
            ab, c, v = r.split(":"); refs.add((ab, int(c), int(v)))
    # Prayer pools render their verse via BibleService.resolve_shared too, so their
    # references need the same alignment coverage (esp. the Psalm refs).
    def add_colon(ref: str) -> None:
        ab, c, v = ref.split(":"); refs.add((ab, int(c), int(v)))
    for p in yaml.safe_load((d / "prayers_of_day.yaml").read_text("utf-8")) or []:
        if p.get("ref"):
            add_colon(p["ref"])
    for sec in (yaml.safe_load((d / "prayer_topics.yaml").read_text("utf-8")) or {}).get("sections", []):
        for topic in sec.get("topics", []):
            if (topic.get("prayer") or {}).get("ref"):
                add_colon(topic["prayer"]["ref"])
            for pr in topic.get("prayers") or []:
                if pr.get("ref"):
                    add_colon(pr["ref"])
    return sorted(refs)


def main() -> None:
    write = "--write" in sys.argv
    bibles = load_bibles()
    refs = collect_refs()
    refs_by_book: dict[str, list] = {}
    for ab, ch, v in refs:
        refs_by_book.setdefault(ab, []).append((ch, v))
    print(f"Collected {len(refs)} unique shared references\n")

    result: dict[str, dict[str, list[int]]] = {}
    review: list[str] = []

    for code, lang in TRANSLATIONS.items():
        anchor = ANCHOR[lang]
        if code == anchor:
            continue
        # Russian is handled by scripts/build_ru_synodal_versification.py: ru_synodal now
        # uses authentic Synodal (Septuagint) psalm numbering, so it is NOT a Masoretic
        # anchor and this token-aligner would mis-map it (and wipe ru_nrt's psalm entries,
        # since both Russian translations share that numbering). Skip and preserve on write.
        if lang == "ru":
            continue
        tb, ab_books = bibles[code], bibles[anchor]
        per: dict[str, list[int]] = {}
        for ab, refpairs in refs_by_book.items():
            if not book_differs(tb, ab_books, ab):
                continue
            if ab in REORDERED:
                for ch, v in refpairs:
                    atext = verse(ab_books, ab, ch, v)
                    if not atext:
                        continue
                    bc, bv, bs, ss = best_match(tb, ab, norm(atext))
                    if (bc, bv) != (ch, v) and bs - ss >= 0.05 and bs >= MIN_KEEP:
                        per[f"{ab} {ch}:{v}"] = [bc, bv]
                        tag = "  <<low" if bs < LOW_SIM else ""
                        review.append(
                            f"  [{code}] {ab} {ch}:{v} -> {bc}:{bv} (sim={bs:.2f} 2nd={ss:.2f}){tag}\n"
                            f"      A: {atext[:72]}\n      B: {verse(tb, ab, bc, bv)[:72]}"
                        )
                continue
            mapping = align(flatten(ab_books[ab]), flatten(tb[ab]))
            for ch, v in refpairs:
                m = mapping.get((ch, v))
                if not m:
                    continue
                bc, bv, s = m
                if (bc, bv) != (ch, v) and s >= MIN_KEEP:
                    per[f"{ab} {ch}:{v}"] = [bc, bv]
                    tag = "  <<low" if s < LOW_SIM else ""
                    review.append(
                        f"  [{code}] {ab} {ch}:{v} -> {bc}:{bv} (sim={s:.2f}){tag}\n"
                        f"      A: {(verse(ab_books, ab, ch, v) or '')[:72]}\n"
                        f"      B: {(verse(tb, ab, bc, bv) or '')[:72]}"
                    )
        if per:
            result[code] = dict(sorted(per.items()))

    print("=== OVERRIDES ===")
    for code in TRANSLATIONS:
        if code in result:
            print(f"  {code}: {len(result[code])}")
    print(f"\n=== REVIEW EACH OVERRIDE ({sum(len(v) for v in result.values())}) ===")
    print("\n".join(review))

    if write:
        # preserve the Russian blocks (maintained by build_ru_synodal_versification.py)
        if OUT.exists():
            existing = json.loads(OUT.read_text("utf-8"))
            for code in ("ru_synodal", "ru_nrt"):
                if code in existing:
                    result[code] = existing[code]
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
        print(f"\nWrote {OUT} (Russian blocks preserved)")
    else:
        print("\n(report only; pass --write to save)")


if __name__ == "__main__":
    main()

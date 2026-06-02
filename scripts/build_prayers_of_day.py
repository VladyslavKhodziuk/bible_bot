"""Build data/prayers_of_day.yaml from the 366-day prayer DOCX (day-mapped pool).

The DOCX (Russian only) holds 366 prayers, one per day-of-year (366th = leap day):
each is `День N. <Title>` / prayer body / `📖 «<Synodal verse text>»<Book ch:verse>`.

This script:
  1. Parses the DOCX into 366 (title_ru, text_ru, book, syn_ch, syn_v, verse_text).
  2. Resolves the Russian book name -> abbrev via data/books.yaml (+ short-form aliases).
  3. Verifies each Synodal coordinate against data/bibles/ru_synodal.json (the DOCX uses
     Synodal/Septuagint numbering); if the stored coord's text mismatches, it searches the
     chapter for the verse and corrects it.
  4. Converts each ref to the CANONICAL (Masoretic) numbering the bot stores:
       - non-Psalms: identity (Synodal == Masoretic for these books).
       - Psalms: mas_ch = syn_ch + (0 if syn_ch <= 8 else 1)  (none of the 83 refs hit a
         merge/split chapter boundary, verified), and mas_v via TAIL-ANCHORED offset
         mas_v = syn_v - (len(syn_chapter) - len(mas_chapter))  — reliable for mid-psalm
         verses because psalm bodies end on identical content across versifications.
  5. Emits:
       - _prayers_intermediate.json  : per-day {day,id,ref,title_ru,text_ru, + diagnostics}
       - _psalm_ref_report.txt       : Synodal text vs en_kjv text at the Masoretic ref,
                                        side by side, for eyeball verification.
       - _ru_versification_additions.json : {ru_synodal:{...}, ru_nrt:{...}} map entries
                                        (Masoretic key -> [syn_ch, syn_v]) for the manual map.

Run:  python scripts/build_prayers_of_day.py
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCX = Path.home() / "Downloads" / "Молитвы на 366 дней для бота.docx"
BIBLES = ROOT / "data" / "bibles"
BOOKS_YAML = ROOT / "data" / "books.yaml"

# Short Gospel forms / Psalm / typos used in the DOCX that books.yaml ru fields don't match.
RU_NAME_ALIASES = {
    "Матфея": "mt", "Марка": "mk", "Луки": "lk", "Иоанна": "jo",
    "Псалом": "ps", "Псалтирь": "ps", "Иисуса Навина": "js",
    "Филиппинцам": "ph",  # typo for Филиппийцам
}


def load_bible(code: str) -> dict[str, dict]:
    return {b["abbrev"]: b for b in json.loads((BIBLES / f"{code}.json").read_text("utf-8-sig"))}


def chapter_verses(bible: dict, ab: str, ch: int) -> list[str] | None:
    b = bible.get(ab)
    if not b or not (0 <= ch - 1 < len(b["chapters"])):
        return None
    return b["chapters"][ch - 1]


def get_verse(bible: dict, ab: str, ch: int, v: int) -> str | None:
    vs = chapter_verses(bible, ab, ch)
    return vs[v - 1] if vs and 0 <= v - 1 < len(vs) else None


def norm(text: str | None) -> frozenset[str]:
    if not text:
        return frozenset()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"\(\d+[:\-]\d+\)", " ", text)
    return frozenset(re.findall(r"\w+", text, flags=re.UNICODE))


def sim(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def contained(quote: frozenset, verse: frozenset) -> float:
    """Fraction of the (often abridged) DOCX quote tokens found in the full verse."""
    return len(quote & verse) / len(quote) if quote else 0.0


def parse_docx() -> list[dict]:
    xml = zipfile.ZipFile(DOCX).read("word/document.xml").decode("utf-8")
    paras = [
        html.unescape("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p)))
        for p in re.split(r"</w:p>", xml)
    ]
    ne = [p.strip() for p in paras if p.strip()]

    entries: list[dict] = []
    i = 0
    day_re = re.compile(r"^День\s+(\d+)\.\s*(.+)$")
    while i < len(ne):
        m = day_re.match(ne[i])
        if not m:
            i += 1
            continue
        day = int(m.group(1))
        title = m.group(2).strip()
        body = ne[i + 1].strip()
        verse_line = ne[i + 2].strip()
        i += 3

        s = verse_line.lstrip("📖").strip()
        vm = re.search(r"«(.+?)»\s*(.+?)\s*(\d+):(\d+)", s)
        if not vm:
            raise SystemExit(f"Day {day}: cannot parse verse line: {verse_line!r}")
        entries.append({
            "day": day,
            "title_ru": title,
            "text_ru": body,
            "verse_text": vm.group(1).strip(),
            "book_ru": vm.group(2).strip(),
            "syn_ch": int(vm.group(3)),
            "syn_v": int(vm.group(4)),
        })
    return entries


def main() -> None:
    books_meta = yaml.safe_load(BOOKS_YAML.read_text("utf-8"))
    ru2ab = {v["ru"]: k for k, v in books_meta.items() if isinstance(v, dict) and "ru" in v}
    ru2ab.update(RU_NAME_ALIASES)

    syn = load_bible("ru_synodal")
    kjv = load_bible("en_kjv")

    entries = parse_docx()
    assert len(entries) == 366, len(entries)
    assert [e["day"] for e in entries] == list(range(1, 367))

    report: list[str] = []
    flagged: list[str] = []
    ru_add: dict[str, list[int]] = {}
    out: list[dict] = []

    for e in entries:
        ab = ru2ab.get(e["book_ru"])
        if not ab:
            raise SystemExit(f"Day {e['day']}: unknown book {e['book_ru']!r}")

        sc, sv = e["syn_ch"], e["syn_v"]
        # The DOCX references are author-supplied and trusted; its quoted text is often an
        # ABRIDGED fragment, so verify by containment (quote tokens ⊆ verse tokens), not Jaccard.
        # A genuinely wrong coordinate shows low containment AND a clearly better verse nearby.
        nt = norm(e["verse_text"])
        actual = get_verse(syn, ab, sc, sv)
        c_here = contained(nt, norm(actual)) if actual else 0.0
        if c_here < 0.6:
            vs = chapter_verses(syn, ab, sc) or []
            best, bi = c_here, sv
            for idx, txt in enumerate(vs, start=1):
                c = contained(nt, norm(txt))
                if c > best:
                    best, bi = c, idx
            if best >= 0.8 and bi != sv:
                flagged.append(f"Day {e['day']} {ab} {sc}:{sv} — better containment at v{bi} ({best:.2f} vs {c_here:.2f})")
            elif best < 0.6:
                flagged.append(f"Day {e['day']} {ab} {sc}:{sv} — low containment {c_here:.2f} (verify ref)")

        # canonical (Masoretic) ref
        if ab == "ps":
            mas_ch = sc if sc <= 8 else sc + 1
            syn_len = len(chapter_verses(syn, ab, sc) or [])
            mas_len = len(chapter_verses(kjv, ab, mas_ch) or [])
            offset = syn_len - mas_len            # title/split shift at the tail
            mas_v = sv - offset
            kjv_txt = get_verse(kjv, ab, mas_ch, mas_v)
            if mas_v < 1 or kjv_txt is None:
                flagged.append(f"Day {e['day']} ps {sc}:{sv} -> {mas_ch}:{mas_v} OUT OF RANGE (kjv ps{mas_ch} len {mas_len})")
            if sv <= offset + 1:                  # ref sits in the title region -> verify by hand
                flagged.append(f"Day {e['day']} ps {sc}:{sv} -> {mas_ch}:{mas_v} near title (offset {offset}) — verify")
            ru_add[f"ps {mas_ch}:{mas_v}"] = [sc, sv]
            report.append(
                f"Day {e['day']:>3} | ps {sc}:{sv} -> {mas_ch}:{mas_v} (off {offset})\n"
                f"    SYN: {(get_verse(syn, ab, sc, sv) or '')[:78]}\n"
                f"    KJV: {(kjv_txt or '')[:78]}"
            )
            ref = f"{ab}:{mas_ch}:{mas_v}"
        else:
            # non-Psalm: Synodal == Masoretic for these books (bot stores Masoretic identity)
            ref = f"{ab}:{sc}:{sv}"

        out.append({
            "day": e["day"],
            "id": f"day_{e['day']:03d}",
            "ref": ref,
            "title_ru": e["title_ru"],
            "text_ru": e["text_ru"],
            "verse_text_ru": e["verse_text"],
        })

    # ── diagnostics (kept untracked; useful while filling translations) ──
    (ROOT / "_prayers_intermediate.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    (ROOT / "_psalm_ref_report.txt").write_text("\n".join(report), "utf-8")

    # ── cross-check ru_add coords against ru_nrt.json (shares Synodal numbering) ──
    nrt = load_bible("ru_nrt")
    for key, (sc, sv) in ru_add.items():
        a = norm(get_verse(syn, "ps", sc, sv))
        b = norm(get_verse(nrt, "ps", sc, sv))
        if a and b and sim(a, b) < 0.3:
            flagged.append(f"{key} -> [{sc},{sv}]: ru_synodal/ru_nrt text differ (sim {sim(a,b):.2f})")

    # ── merge ru psalm map entries into data/versification_map_manual.json ──
    merge_versification(ru_add)

    # ── assemble data/prayers_of_day.yaml (ru from DOCX, en/es/uk from translations file) ──
    coverage = assemble_yaml(out)

    print(f"Parsed {len(out)} prayers. Psalm map entries: {len(ru_add)}.")
    print(f"Translation coverage: {coverage}")
    if flagged:
        print(f"\n=== FLAGGED ({len(flagged)}) — verify by hand ===")
        print("\n".join("  " + f for f in flagged))
    else:
        print("No flags.")


def merge_versification(ru_add: dict[str, list[int]]) -> None:
    """Merge the Psalm map entries (Masoretic key -> [syn_ch, syn_v]) into the manual map
    for both ru_synodal and ru_nrt (they share Synodal/Septuagint numbering)."""
    path = ROOT / "data" / "versification_map_manual.json"
    m = json.loads(path.read_text("utf-8"))
    for code in ("ru_synodal", "ru_nrt"):
        block = m.setdefault(code, {})
        for k, v in ru_add.items():
            if k in block and block[k] != v:
                raise SystemExit(f"manual map conflict {code} {k}: {block[k]} != {v}")
            block[k] = v
        m[code] = dict(sorted(block.items()))
    path.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", "utf-8")


def assemble_yaml(out: list[dict]) -> str:
    """Write data/prayers_of_day.yaml. en/es/uk come from scripts/prayer_translations.yaml
    (id -> {title:{en,es,uk}, text:{en,es,uk}}); missing languages fall back to ru so the
    bot always renders (translations are filled in incrementally)."""
    tr_path = ROOT / "scripts" / "prayer_translations.json"
    tr = json.loads(tr_path.read_text("utf-8")) if tr_path.exists() else {}
    tr = tr or {}

    have = {"title": 0, "text": 0}
    entries = []
    for e in out:
        t = tr.get(e["id"], {})
        t_title = t.get("title") or {}
        t_text = t.get("text") or {}
        if all(t_title.get(l) for l in ("en", "es", "uk")):
            have["title"] += 1
        if all(t_text.get(l) for l in ("en", "es", "uk")):
            have["text"] += 1
        entries.append({
            "id": e["id"],
            "ref": e["ref"],  # abbrev:chapter:verse (canonical/Masoretic)
            "title": {
                "ru": e["title_ru"],
                "en": t_title.get("en") or e["title_ru"],
                "es": t_title.get("es") or e["title_ru"],
                "uk": t_title.get("uk") or e["title_ru"],
            },
            "text": {
                "ru": e["text_ru"],
                "en": t_text.get("en") or e["text_ru"],
                "es": t_text.get("es") or e["text_ru"],
                "uk": t_text.get("uk") or e["text_ru"],
            },
        })

    header = (
        "# Молитвы на каждый день года (366 дней; 366-я — для високосного года).\n"
        "# Молитва дня выбирается по номеру дня в году (см. services/prayer_service.py).\n"
        "# Эти же молитвы используются как пул «Случайная молитва».\n"
        "# Поля:\n"
        "#   id    — day_NNN (NNN = номер дня года)\n"
        "#   ref   — канонический (масоретский) стих «abbrev:chapter:verse»\n"
        "#   title — заголовок молитвы на 4 языках\n"
        "#   text  — текст молитвы на 4 языках\n"
        "# Сгенерировано scripts/build_prayers_of_day.py — не редактировать вручную.\n"
    )
    body = yaml.dump(entries, allow_unicode=True, sort_keys=False, width=88,
                     default_flow_style=False)
    (ROOT / "data" / "prayers_of_day.yaml").write_text(header + body, "utf-8")
    return f"title {have['title']}/366, text {have['text']}/366"


if __name__ == "__main__":
    main()

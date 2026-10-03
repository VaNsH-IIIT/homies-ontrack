"""Repair French accents lost as U+FFFD ('�') in agent notes (owner: P2). Data-quality fix for text features.

4,636 notes in the raw release arrive with accented letters replaced by '�' ("client a appel�", "ao�t",
"�quipe difficult�s"). The notes are templated, so every broken word has a correctly spelled twin in the clean
notes: a broken word is replaced only when exactly one known word fits it (same length, same letters, '�' = one
accented letter). Anything ambiguous stays as it is, so the repair never invents text.
"""
from __future__ import annotations

import re
from functools import lru_cache

BAD = "�"
ACCENTED = "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ"
WORD = re.compile(r"[^\W\d_]+|�", re.UNICODE)
BROKEN = re.compile(r"[\w�]*�[\w�]*", re.UNICODE)


@lru_cache(maxsize=1)
def lexicon() -> dict[tuple[int, str], list[str]]:
    """Accented words from clean notes, indexed by (length, accent-free skeleton) for fast lookup."""
    from ontrack.db import connect
    con = connect(read_only=True)
    rows = con.execute(
        "SELECT DISTINCT unnest(regexp_extract_all(lower(note_text), '[[:alpha:]]*[" + ACCENTED + "][[:alpha:]]*')) "
        "FROM bronze.agent_notes WHERE note_text IS NOT NULL AND note_text NOT LIKE '%' || chr(65533) || '%'"
    ).fetchall()
    con.close()
    index: dict[tuple[int, str], list[str]] = {}
    # Template words that only ever appear broken in the release (ordinary French dictionary words).
    extra = ["échéance", "fâché", "fâchée", "élevé", "élevée", "déposé", "été", "évacué", "évacuée"]
    for (w,) in rows + [(x,) for x in extra]:
        if not w:
            continue
        skeleton = "".join(BAD if ch in ACCENTED.lower() else ch for ch in w)
        bucket = index.setdefault((len(w), skeleton), [])
        if w not in bucket:
            bucket.append(w)
    return index


def _fix_word(broken: str) -> str:
    if broken == BAD:                      # the one-letter French word: "payer 198$ à la prochaine paie"
        return "à"
    skeleton = "".join(BAD if ch in ACCENTED.lower() else ch for ch in broken.lower())
    cands = [c for c in lexicon().get((len(broken), skeleton), [])
             if all(b == BAD or b == c_ for b, c_ in zip(broken.lower(), c))]
    if len(cands) != 1:
        return broken
    fixed = cands[0]
    return fixed.upper() if broken.isupper() else (fixed.capitalize() if broken[:1].isupper() else fixed)


def repair(text: str | None) -> str | None:
    if not text or BAD not in text:
        return text
    return BROKEN.sub(lambda m: _fix_word(m.group(0)), text)

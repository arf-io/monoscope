"""monoscope.banners — TheDraw-font titles, sized to the terminal.

Vendored fonts (``fonts/*.tdf``, the scene's own TheDraw fonts as shipped
with tdfiglet — the same files every BBS menu of the era was lettered with):

    hero    1911.tdf       the Razor 1911 font (10 rows)  — splash only
    big     blcktrnc.tdf   Blocktronics (7 rows, full 94-glyph set)
    mid     cfh-snwx.tdf   Cfh 3 (5 rows)
    small   silverx.tdf    Silver (4 rows, bevelled)
    tiny    nirvana.tdf    Nirvana (4 rows, compact)

``banner_rows(kind, text)`` → list of rows of ``(char, level)`` where level is
0..1 (the font's baked shading by luminance rank), ready to be recolored
into any palette family. Results are cached; missing glyphs are skipped.
"""

from __future__ import annotations

import os

from . import tdf

__all__ = ["banner_rows", "banner_height", "banner_width", "BANNER_LADDER", "font_for"]

_HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(_HERE, "fonts")

BANNER_LADDER = {
    "hero": "1911.tdf",
    "big": "blcktrnc.tdf",
    "mid": "cfh-snwx.tdf",
    "small": "silverx.tdf",
    "tiny": "nirvana.tdf",
}
_HEIGHTS = {"hero": 10, "big": 7, "mid": 5, "small": 4, "tiny": 4}
_FONTS = {}
_CACHE = {}


def font_for(kind):
    f = _FONTS.get(kind)
    if f is None:
        name = BANNER_LADDER.get(kind)
        if not name:
            return None
        path = os.path.join(FONT_DIR, name)
        try:
            f = tdf.load_font(path)
        except (OSError, ValueError):
            f = False
        _FONTS[kind] = f
    return f or None


def banner_height(kind, text="MONOSCOPE"):
    """Rows the rendered (trimmed) banner for `text` occupies."""
    rows = banner_rows(kind, text)
    if rows:
        return len(rows)
    f = font_for(kind)
    return f.height if f else _HEIGHTS.get(kind, 0)


def banner_rows(kind, text):
    key = (kind, text)
    rows = _CACHE.get(key)
    if rows is not None:
        return rows
    f = font_for(kind)
    if f is None:
        _CACHE[key] = []
        return []
    b = f.render(text).trim()
    if not b.rows:
        _CACHE[key] = []
        return []
    used = sorted({tdf.CGA_LUMA_RANK[c[1]] for r in b.rows for c in r if c[0] != " "})
    pos = {rk: (i / max(1, len(used) - 1)) for i, rk in enumerate(used)} if used else {}
    out = []
    for r in b.rows:
        line = []
        for ch, fgi, bgi in r:
            if ch == " " and bgi == 0:
                line.append((" ", 0.0))
            else:
                # a cell with only a background colour reads as a solid block
                if ch == " " and bgi:
                    line.append(("█", tdf.CGA_LUMA_RANK[bgi] / 15.0))
                else:
                    line.append((ch, pos.get(tdf.CGA_LUMA_RANK[fgi], 0.5)))
        out.append(line)
    _CACHE[key] = out
    return out


def banner_width(kind, text):
    rows = banner_rows(kind, text)
    return max((len(r) for r in rows), default=0)

"""monoscope.tdf — TheDraw (.TDF) color font loader and renderer.

TheDraw fonts are *the* BBS-era title lettering (every "WELCOME", "SYSOP",
"FILE DIRS" header in the Roy/ACiD/iCE packs). tdfiglet renders them as
CP437+CGA ANSI; we load the same files natively so titles can be set in any
string at runtime and colored live from the panel's palette family.

Format (verified against tdfiglet.c, ~/Augments/tdfiglet):
    0..19   magic  "\\x13TheDraw FONTS file\\x1a"
    24      name length, 25.. name
    41      font type: 0 outline, 1 block, 2 color
    42      spacing (columns between glyphs)
    43..44  block size (u16 LE)
    45..232 char offsets: 94 × u16 LE for '!'..'~' (0xFFFF = missing)
    233..   glyph data: width, height, then (char, attr) pairs; 0x0D = new
            row (no attr byte follows); 0x00 terminates the glyph.
            attr: low nibble fg (CGA 0-15), high nibble bg (0-7).
A .TDF file may bundle several fonts back to back (each with its own header
at a 24-byte alignment); we take the first, like tdfiglet does — the fonts
we vendor are single-font files.

Rendering returns a :class:`Banner` — a rectangular grid of cells
``(char, fg_idx, bg_idx)`` where fg/bg are CGA indices — plus helpers to
recolor by *luminance rank* into a palette ramp, which is how the shading a
font author baked into 16 colors becomes a bevel in any hue.
"""

from __future__ import annotations

import os
import struct

__all__ = ["Font", "Banner", "load_font", "CGA_LUMA_RANK", "CGA_RGB"]

MAGIC = b"\x13TheDraw FONTS file\x1a"
NUM_CHARS = 94

CGA_RGB = [
    (0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
    (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
    (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
    (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255),
]


def _luma(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


#: CGA index → luminance rank 0..15 (0 darkest). Used to map a font's baked
#: shading onto a monochrome/family ramp.
CGA_LUMA_RANK = {}
for _i, _c in sorted(enumerate(CGA_RGB), key=lambda p: _luma(p[1])):
    CGA_LUMA_RANK[_i] = len(CGA_LUMA_RANK)


class Font:
    __slots__ = ("name", "type", "spacing", "glyphs", "height", "path")

    def __init__(self, name, ftype, spacing, glyphs, height, path=""):
        self.name = name
        self.type = ftype
        self.spacing = spacing
        self.glyphs = glyphs      # dict char -> (width, height, rows[list of list of (ch, fg, bg)])
        self.height = height
        self.path = path

    def has(self, ch):
        return ch in self.glyphs

    def render(self, text, spacing=None, fallback_upper=True):
        """Render text to a Banner. Missing glyphs try the other case, then
        are skipped (a space advances by a fixed gap)."""
        sp = self.spacing if spacing is None else spacing
        cols = []   # list of columns; each column is a list of height cells
        H = self.height
        first = True
        for ch in text:
            if ch == " ":
                gap = max(2, sp * 2 if sp else 3)
                for _ in range(gap):
                    cols.append([(" ", 0, 0)] * H)
                first = True
                continue
            g = self.glyphs.get(ch)
            if g is None and fallback_upper:
                g = self.glyphs.get(ch.upper()) or self.glyphs.get(ch.lower())
            if g is None:
                continue
            gw, gh, rows = g
            if not first:
                for _ in range(sp):
                    cols.append([(" ", 0, 0)] * H)
            first = False
            for x in range(gw):
                col = []
                for y in range(H):
                    if y < len(rows) and x < len(rows[y]):
                        col.append(rows[y][x])
                    else:
                        col.append((" ", 0, 0))
                cols.append(col)
        # transpose to rows
        W = len(cols)
        grid = [[cols[x][y] for x in range(W)] for y in range(H)]
        return Banner(grid)


class Banner:
    """A rendered title: rows of (char, fg_idx, bg_idx)."""

    __slots__ = ("rows",)

    def __init__(self, rows):
        self.rows = rows

    @property
    def width(self):
        return len(self.rows[0]) if self.rows else 0

    @property
    def height(self):
        return len(self.rows)

    def trim(self):
        """Drop fully blank leading/trailing columns and blank rows."""
        rows = self.rows
        # blank rows top/bottom
        def row_blank(r):
            return all(c[0] == " " and c[2] == 0 for c in r)
        while rows and row_blank(rows[0]):
            rows = rows[1:]
        while rows and row_blank(rows[-1]):
            rows = rows[:-1]
        if not rows:
            self.rows = []
            return self
        W = len(rows[0])
        def col_blank(x):
            return all(r[x][0] == " " and r[x][2] == 0 for r in rows)
        x0 = 0
        while x0 < W and col_blank(x0):
            x0 += 1
        x1 = W
        while x1 > x0 and col_blank(x1 - 1):
            x1 -= 1
        self.rows = [r[x0:x1] for r in rows]
        return self

    def levels(self):
        """Per-cell fg luminance rank grid (0..15), for recoloring."""
        return [[CGA_LUMA_RANK[c[1]] for c in r] for r in self.rows]

    def recolored(self, ramp, bg=None, bg_ramp=None):
        """Yield (row_index, list of (char, fg_rgb, bg_rgb|None)) with the
        font's 16-color shading mapped onto `ramp` (list of RGB dark→bright)
        by luminance rank. Cells with a CGA background get bg from bg_ramp
        (or `bg` when None)."""
        n = len(ramp)
        # ranks actually used by this banner, so a font that uses only 4
        # colours still spans the whole ramp
        used = sorted({CGA_LUMA_RANK[c[1]] for r in self.rows for c in r if c[0] != " "})
        if not used:
            used = [0]
        pos = {rk: (i / max(1, len(used) - 1)) for i, rk in enumerate(used)}
        out = []
        for y, r in enumerate(self.rows):
            cells = []
            for (ch, fgi, bgi) in r:
                if ch == " " and bgi == 0:
                    cells.append((" ", None, bg))
                    continue
                t = pos.get(CGA_LUMA_RANK[fgi], 0.0)
                fg = ramp[min(n - 1, int(round(t * (n - 1))))]
                if bgi:
                    tb = CGA_LUMA_RANK[bgi] / 15.0
                    b = (bg_ramp or ramp)[min(n - 1, int(tb * (n - 1)))]
                else:
                    b = bg
                cells.append((ch, fg, b))
            out.append(cells)
        return out


def load_font(path):
    """Load the first font from a .TDF file."""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(MAGIC):
        raise ValueError("not a TheDraw font: %s" % path)
    return _parse_font(data, 0, path)


def _parse_font(data, base, path=""):
    namelen = data[base + 24]
    name = data[base + 25: base + 25 + namelen].decode("cp437", "replace")
    ftype = data[base + 41]
    spacing = data[base + 42]
    offsets = struct.unpack_from("<94H", data, base + 45)
    dstart = base + 233
    glyphs = {}
    height = 0
    for i, off in enumerate(offsets):
        if off == 0xFFFF:
            continue
        p = dstart + off
        if p + 2 > len(data):
            continue
        gw, gh = data[p], data[p + 1]
        p += 2
        rows = [[]]
        while p < len(data):
            b = data[p]
            p += 1
            if b == 0:
                break
            if b == 0x0D:
                rows.append([])
                continue
            if ftype == 2:
                if p >= len(data):
                    break
                attr = data[p]
                p += 1
                fg, bg = attr & 0x0F, (attr >> 4) & 0x0F
            else:
                fg, bg = 7, 0
            ch = bytes([b]).decode("cp437", "replace")
            rows[-1].append((ch, fg, bg))
        if rows and not rows[-1]:
            rows.pop()
        gh = max(gh, len(rows))
        height = max(height, gh)
        glyphs[chr(0x21 + i)] = (gw, gh, rows)
    return Font(name, ftype, spacing, glyphs, height, path)


def scan_fonts(directory):
    """Yield (path, name, type, spacing, height, nglyphs) for every .tdf."""
    for fn in sorted(os.listdir(directory)):
        if not fn.lower().endswith(".tdf"):
            continue
        p = os.path.join(directory, fn)
        try:
            f = load_font(p)
        except Exception:
            continue
        yield (p, f.name, f.type, f.spacing, f.height, len(f.glyphs))

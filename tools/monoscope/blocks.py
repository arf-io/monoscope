"""monoscope.blocks — the block-shading vocabulary.

Everything the ANSI scene did with ░▒▓█ ▀▄ ▌▐ and sixteen colors, done in
truecolor on a :class:`~monoscope.canvas.Canvas`:

* ``dither_gradient``  — a horizontal band whose color steps through K hard
  bands with ░▒▓ transition cells at each boundary (the classic "█▓▒░" fade,
  never an airbrush).
* ``fade_run``         — ``█▓▒░`` run of one color dissolving into the ground.
* ``PixelGrid``        — a 2× vertical raster (one cell = 1×2 pixels) drawn
  with ▀ (fg=top, bg=bottom): the half-block technique behind every chunky
  logo, meter and signature glyph.
* ``bevel_frame``      — a Roy-style enclosure: bright ▀ top lip, ▐/▌
  half-block rails, dark ▄ foot, dithered corner caps.
* ``rail``             — a vertical shaded rail with a lit segment.
* ``sparkles``         — deterministic twinkling star field around a logo.

Rules of the medium (from the MONOSCOPE spec §2.1): full- and half-cell
solids survive the CRT chain; ░▒▓ are used for *ornament at fixed
positions* (caps, rails, frames), never for data.
"""

from __future__ import annotations

import math

from .canvas import Canvas
from . import color as C

__all__ = ["SHADES", "dither_gradient", "fade_run", "PixelGrid", "bevel_frame",
           "rail", "sparkles", "shade_row", "vbar_glyph", "VBLOCKS", "HBLOCKS"]

SHADES = "░▒▓"
VBLOCKS = " ▁▂▃▄▅▆▇█"      # 9 levels, bottom-anchored
HBLOCKS = " ▏▎▍▌▋▊▉█"      # 9 levels, left-anchored


def vbar_glyph(t):
    """Vertical block for t∈[0,1] (8 sub-cell levels)."""
    if t <= 0:
        return " "
    return VBLOCKS[min(8, max(1, int(round(t * 8))))]


def _band_colors(stops, k):
    return C.gradient(stops, max(2, k))


def dither_gradient(cv, x, y, w, stops, bands=6, y2=None, ground=None, reverse=False):
    """Paint a horizontal dithered gradient across w columns of row y (and
    rows y..y2 if given): `bands` hard color bands, ░▒▓ at each boundary
    (fg = next band, bg = current band). `stops` are RGB stops."""
    if w <= 0:
        return
    cols = _band_colors(stops, bands)
    if reverse:
        cols = cols[::-1]
    nb = len(cols)
    seg = w / nb
    rows = range(y, (y2 if y2 is not None else y) + 1)
    for i in range(w):
        b = min(nb - 1, int(i / seg))
        # position within band 0..1
        pos = (i - b * seg) / seg if seg > 0 else 0.0
        cur = cols[b]
        nxt = cols[min(nb - 1, b + 1)]
        ch, fg, bg = " ", None, cur
        if b < nb - 1 and pos > 0.55:
            # transition zone: three shade steps
            z = (pos - 0.55) / 0.45
            idx = min(2, int(z * 3))
            ch, fg, bg = SHADES[idx], nxt, cur
        for yy in rows:
            cv.put(x + i, yy, ch, fg=fg, bg=bg)


def fade_run(cv, x, y, w, color, ground, direction=1, solid=0):
    """A run that dissolves: `solid` cells of █ then ▓▒░ into `ground`.
    direction=1 fades to the right, -1 to the left."""
    if w <= 0:
        return
    seq = ["█"] * solid + list("▓▒░")
    if direction < 0:
        seq = seq[::-1]
    for i in range(w):
        idx = i if direction > 0 else w - 1 - i
        ch = seq[idx] if idx < len(seq) else " "
        cv.put(x + i, y, ch, fg=color, bg=None)


def shade_row(cv, x, y, w, color, ground, pattern="▓▒░"):
    for i in range(min(w, len(pattern))):
        cv.put(x + i, y, pattern[i], fg=color, bg=None)


class PixelGrid:
    """A w × (2h) pixel raster rendered onto h cell rows with half-blocks.
    Pixels are RGB or None (transparent → keeps the canvas background)."""

    __slots__ = ("w", "h", "px")

    def __init__(self, w, h2):
        self.w, self.h = w, h2       # h is pixel rows (2 per cell row)
        self.px = [[None] * w for _ in range(h2)]

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = c

    def rect(self, x, y, w, h, c):
        for yy in range(max(0, y), min(self.h, y + h)):
            row = self.px[yy]
            for xx in range(max(0, x), min(self.w, x + w)):
                row[xx] = c

    def blit(self, cv, x0, y0, ground=None):
        """Draw onto canvas at cell (x0, y0). Transparent halves take the
        canvas' existing bg (or `ground` when given)."""
        for cy in range(0, (self.h + 1) // 2):
            top = self.px[cy * 2]
            bot = self.px[cy * 2 + 1] if cy * 2 + 1 < self.h else [None] * self.w
            yy = y0 + cy
            if yy < 0 or yy >= cv.h:
                continue
            for cx in range(self.w):
                xx = x0 + cx
                if xx < 0 or xx >= cv.w:
                    continue
                t, b = top[cx], bot[cx]
                if t is None and b is None:
                    if ground is not None:
                        cv.put(xx, yy, " ", bg=ground)
                    continue
                cur_bg = ground if ground is not None else cv.bg[yy * cv.w + xx]
                if t is not None and b is not None:
                    if t == b:
                        cv.put(xx, yy, "█", fg=t, bg=t)
                    else:
                        cv.put(xx, yy, "▀", fg=t, bg=b)
                elif t is not None:
                    cv.put(xx, yy, "▀", fg=t, bg=cur_bg)
                else:
                    cv.put(xx, yy, "▄", fg=b, bg=cur_bg)


def bevel_frame(cv, x, y, w, h, fam, hue_t=None, title=None, lit=1.0, ground=None):
    """Roy-style enclosure. Top lip: bright ▀ run with a dithered fade at
    both ends; rails: ▐ (left) ▌ (right) in mid tone; foot: dark ▄ run.
    `fam` is a color Family; hue_t (0..1) picks a sweep color for the lip
    when the family has hues, else the ramp is used."""
    if w < 4 or h < 2:
        return
    ground = ground if ground is not None else fam.ground
    base = fam.sweep(hue_t) if (hue_t is not None and fam.hues) else fam.hot
    base = C.crt_safe(base)
    top = C.lighten(base, 0.35 * lit)
    mid = C.darken(base, 0.25)
    low = C.darken(base, 0.62)
    # top lip
    cv.put(x, y, "▄", fg=low, bg=None)
    for i in range(1, w - 1):
        cv.put(x + i, y, "▄", fg=top, bg=None)
    cv.put(x + w - 1, y, "▄", fg=low, bg=None)
    # under-lip glow row: fades ▓▒░ at the ends
    if h >= 3:
        cv.put(x, y + 1, "▐", fg=mid, bg=None)
        cv.put(x + w - 1, y + 1, "▌", fg=mid, bg=None)
    for yy in range(y + 1, y + h - 1):
        cv.put(x, yy, "▐", fg=mid, bg=None)
        cv.put(x + w - 1, yy, "▌", fg=mid, bg=None)
    # foot
    for i in range(w):
        cv.put(x + i, y + h - 1, "▀", fg=low, bg=None)
    # corner dither caps on the foot
    if w >= 8:
        cv.put(x + 1, y + h - 1, "▓", fg=low, bg=None)
        cv.put(x + w - 2, y + h - 1, "▓", fg=low, bg=None)
    if title:
        t = " %s " % title
        tx = x + 3
        cv.put(tx, y, t, fg=fam.glow, bg=mid, maxw=w - 6)


def rail(cv, x, y, h, fam, lit_from=None, lit_to=None, hue_t=None, ground=None, glyph="▐"):
    """Vertical rail: dim `glyph` column, with rows lit_from..lit_to lit
    (the selection). Under the durability rule the rail is a half-block."""
    ground = ground if ground is not None else fam.ground
    dimc = fam.dim
    lit = C.crt_safe(fam.sweep(hue_t) if (hue_t is not None and fam.hues) else fam.hot)
    for i in range(h):
        yy = y + i
        on = lit_from is not None and lit_to is not None and lit_from <= yy <= lit_to
        cv.put(x, yy, glyph, fg=lit if on else dimc, bg=None)


def sparkles(cv, x, y, w, h, tick, fam, density=0.02, seed=7, ground=None):
    """Deterministic twinkling star field in a rect: a hashed set of cells
    shows · ˙ ✦ cycling with tick, in the family's glow/dim colours."""
    if w <= 0 or h <= 0:
        return
    n = max(1, int(w * h * density))
    glyphs = "·˙•✦·"
    for k in range(n):
        hx = (k * 7919 + seed * 104729) % 65521
        hy = (k * 15485863 + seed * 31) % 65521
        sx = x + hx % w
        sy = y + hy % h
        phase = (tick // 3 + k * 5) % 24
        if phase > 9:
            continue
        g = glyphs[phase % len(glyphs)]
        col = fam.glow if phase in (3, 4, 5) else fam.dim
        cv.put(sx, sy, g, fg=col, bg=None)

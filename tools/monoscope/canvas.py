"""monoscope.canvas — cell grid, painter, and the frame-diff renderer.

The panel is drawn as a *complete* frame every tick into a :class:`Canvas`
(width × height cells, every cell with an explicit fg/bg), then handed to
:class:`Renderer` which emits only the cells that differ from the previous
frame, as a single byte string the terminal driver writes inside a DEC 2026
synchronized-output bracket.

Why every cell has an explicit background: "terminal default" is unknowable
(the user's theme, the CRT shader's glass tint...) and it means the frame is
not deterministic. A canvas cell is a known color, so a diff can never
"forget" a region and the flat-field diagnostic mode is a valid test.

Colors are ``(r, g, b)`` tuples. Attributes are bit flags. Emission is SGR
38;2 / 48;2 (truecolor) or an xterm-256 quantization when the terminal did
not declare truecolor.
"""

from __future__ import annotations

import unicodedata

__all__ = ["Canvas", "Renderer", "BOLD", "DIM", "ITALIC", "UNDERLINE", "REVERSE",
           "cwidth", "swidth", "xterm256_index"]

BOLD, DIM, ITALIC, UNDERLINE, REVERSE = 1, 2, 4, 8, 16

_ZW = {"​", "‌", "‍", "⁠", "﻿"}
_WIDTH_CACHE = {}


def cwidth(ch):
    """Display width of one character (0, 1 or 2)."""
    if ch < "\u0300":          # fast path: everything below the combining block is width 1
        return 1
    w = _WIDTH_CACHE.get(ch)
    if w is not None:
        return w
    if ch in _ZW or unicodedata.combining(ch):
        w = 0
    elif unicodedata.east_asian_width(ch) in ("W", "F"):
        w = 2
    else:
        w = 1
    _WIDTH_CACHE[ch] = w
    return w


def swidth(s):
    return sum(cwidth(c) for c in s)


def xterm256_index(rgb):
    """Nearest xterm-256 index for an RGB tuple (cube + greys)."""
    r, g, b = rgb
    if abs(r - g) < 6 and abs(g - b) < 6:
        v = (r + g + b) // 3
        if v < 8:
            return 16
        if v > 238:
            return 231
        idx = int(round((v - 8) / 10.0))
        return 232 + max(0, min(23, idx))

    def q(v):
        if v < 48:
            return 0
        if v < 115:
            return 1
        return int((v - 35) / 40)
    return 16 + 36 * q(r) + 6 * q(g) + q(b)


class Canvas:
    """A width×height grid. Cells: parallel flat lists for speed."""

    __slots__ = ("w", "h", "ch", "fg", "bg", "at", "default_bg", "default_fg", "cursor")

    def __init__(self, w, h, bg=(0, 0, 0), fg=(200, 200, 200)):
        self.w, self.h = max(0, w), max(0, h)
        n = self.w * self.h
        self.default_bg, self.default_fg = bg, fg
        self.ch = [" "] * n
        self.fg = [fg] * n
        self.bg = [bg] * n
        self.at = [0] * n
        self.cursor = None  # (x, y) to show a real cursor, or None

    def clear(self, bg=None, fg=None):
        n = self.w * self.h
        bg = self.default_bg if bg is None else bg
        fg = self.default_fg if fg is None else fg
        self.ch[:] = [" "] * n
        self.fg[:] = [fg] * n
        self.bg[:] = [bg] * n
        self.at[:] = [0] * n
        self.cursor = None

    # -- primitives ----------------------------------------------------------

    def put(self, x, y, text, fg=None, bg=None, at=0, maxw=None):
        """Write text at (x,y) with clipping. bg=None keeps the existing bg
        of each cell (lets text sit on a gradient); fg=None keeps existing fg.
        Returns the x position after the last written cell."""
        if y < 0 or y >= self.h or x >= self.w:
            return x
        w = self.w
        base = y * w
        limit = w if maxw is None else min(w, x + maxw)
        chs, fgs, bgs, ats = self.ch, self.fg, self.bg, self.at
        for c in text:
            cw = cwidth(c)
            if cw == 0:
                # attach combining mark to previous cell
                if x - 1 >= 0 and x - 1 < w:
                    chs[base + x - 1] += c
                continue
            if x + cw > limit:
                break
            if x >= 0:
                i = base + x
                chs[i] = c
                if fg is not None:
                    fgs[i] = fg
                if bg is not None:
                    bgs[i] = bg
                ats[i] = at
                if cw == 2 and x + 1 < w:
                    chs[i + 1] = ""      # continuation marker
                    if fg is not None:
                        fgs[i + 1] = fg
                    if bg is not None:
                        bgs[i + 1] = bg
                    ats[i + 1] = at
            x += cw
        return x

    def fill(self, x, y, w, h, ch=" ", fg=None, bg=None, at=0):
        """Fill a rect (clipped). ch may be '' to keep glyphs and only paint."""
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        W = self.w
        chs, fgs, bgs, ats = self.ch, self.fg, self.bg, self.at
        for yy in range(y0, y1):
            b = yy * W
            for xx in range(b + x0, b + x1):
                if ch:
                    chs[xx] = ch
                if fg is not None:
                    fgs[xx] = fg
                if bg is not None:
                    bgs[xx] = bg
                ats[xx] = at

    def paint_bg(self, x, y, w, bg):
        """Set background of a horizontal run without touching glyphs."""
        if y < 0 or y >= self.h:
            return
        x0, x1 = max(0, x), min(self.w, x + w)
        if x1 <= x0:
            return
        b = y * self.w
        bgs = self.bg
        for i in range(b + x0, b + x1):
            bgs[i] = bg

    def paint_row_bg(self, y, colors):
        """Per-column background for a whole row: colors is a list of len w."""
        if y < 0 or y >= self.h:
            return
        b = y * self.w
        self.bg[b:b + self.w] = colors[: self.w]

    def hline(self, x, y, w, ch, fg=None, bg=None, at=0):
        self.fill(x, y, w, 1, ch, fg, bg, at)

    def vline(self, x, y, h, ch, fg=None, bg=None, at=0):
        self.fill(x, y, 1, h, ch, fg, bg, at)

    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            return self.ch[i], self.fg[i], self.bg[i], self.at[i]
        return None

    def dim_rect(self, x, y, w, h, amount=0.5, tint=None):
        """Darken a rect (backdrop for sheets): scales fg and bg toward tint."""
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        k = 1.0 - amount
        tr, tg, tb = tint if tint else (0, 0, 0)
        cache = {}

        def dimc(c):
            v = cache.get(c)
            if v is None:
                v = (int(c[0] * k + tr * amount), int(c[1] * k + tg * amount), int(c[2] * k + tb * amount))
                cache[c] = v
            return v
        W = self.w
        fgs, bgs = self.fg, self.bg
        for yy in range(y0, y1):
            b = yy * W
            for i in range(b + x0, b + x1):
                fgs[i] = dimc(fgs[i])
                bgs[i] = dimc(bgs[i])

    def blit_spans(self, x, y, spans, maxw=None):
        """spans: iterable of (text, fg, bg, at) tuples; None fg/bg = keep."""
        for sp in spans:
            text, fg, bg, at = (sp + (0,))[:4] if len(sp) < 4 else sp
            x = self.put(x, y, text, fg, bg, at, maxw=None if maxw is None else maxw - 0)
        return x

    def snapshot_text(self):
        """Plain-text rows (for tests / debugging)."""
        out = []
        for y in range(self.h):
            b = y * self.w
            out.append("".join(c if c else "" for c in self.ch[b:b + self.w]))
        return out


class Renderer:
    """Frame differ + SGR emitter.

    Three properties keep the picture stable under a heavy update rate — they
    are why the panel does not tear or trail a cursor across itself:

    * **The hardware cursor is hidden for the whole payload.** It is re-shown,
      if the frame wants it, only as the very last thing written. Leaving it
      shown while dirty runs are painted is what makes a cursor appear to
      skate across the screen.
    * **The payload is as small as we can make it.** Only changed cells are
      emitted; runs of the same cell collapse to ECMA-48 REP (``CSI Pn b``)
      where the terminal supports it; and the cursor is moved with whichever
      of absolute (``CSI y;xH``) or relative (``CSI Pn C``) motion is fewer
      bytes. A frame the terminal can swallow in one read is a frame it
      cannot tear.
    * **Repaints are never whole-screen in one frame.** :meth:`heal_band`
      re-emits one horizontal band at a time, so the periodic self-heal costs
      a fraction of a frame instead of a full-screen spike.
    """

    def __init__(self, truecolor=True, rep=False):
        self.truecolor = truecolor
        self.rep = bool(rep)      # terminal implements ECMA-48 REP (CSI Pn b)
        self.prev = None          # (w, h, ch, fg, bg, at) of last emitted frame
        self._sgr_cache = {}
        self._fg_cache = {}
        self._bg_cache = {}
        self._cursor_shown = False
        self._cursor_at = None
        self.frames = 0
        self.bytes_out = 0
        self.cells_out = 0
        self.max_bytes = 0        # worst-case payload seen (tearing headroom)

    def invalidate(self):
        """Force the next render to be a full repaint (resize, mode change).

        Cheap: it just drops the previous-frame memory. Prefer
        :meth:`heal_band` for the *periodic* self-heal — a full repaint of a
        200x50 panel is ~100 kB in one write, which is exactly the payload
        size that makes a terminal tear.
        """
        self.prev = None

    def heal_band(self, y0, y1):
        """Mark rows ``[y0, y1)`` as unknown so the next render re-emits them.

        This is the incremental form of :meth:`invalidate`: the self-heal
        walks the screen a band at a time instead of repainting all of it in
        a single frame. Poisoning the remembered characters (rather than
        clearing ``prev``) is what forces the differ to treat the band as
        dirty while leaving every other row on the fast path.
        """
        if self.prev is None:
            return
        w, h = self.prev[0], self.prev[1]
        pch = self.prev[2]
        y0 = max(0, y0)
        y1 = min(h, y1)
        for y in range(y0, y1):
            b = y * w
            for i in range(b, b + w):
                pch[i] = "\x00"   # a character no canvas can ever hold

    _ATTR_CODES = ((BOLD, "1"), (DIM, "2"), (ITALIC, "3"),
                   (UNDERLINE, "4"), (REVERSE, "7"))

    def _fgs(self, fg):
        s = self._fg_cache.get(fg)
        if s is None:
            s = ("38;2;%d;%d;%d" % fg) if self.truecolor else ("38;5;%d" % xterm256_index(fg))
            self._fg_cache[fg] = s
        return s

    def _bgs(self, bg):
        s = self._bg_cache.get(bg)
        if s is None:
            s = ("48;2;%d;%d;%d" % bg) if self.truecolor else ("48;5;%d" % xterm256_index(bg))
            self._bg_cache[bg] = s
        return s

    def _sgr(self, fg, bg, at):
        """The full, self-contained SGR for a cell — reset, then everything."""
        key = (fg, bg, at)
        s = self._sgr_cache.get(key)
        if s is not None:
            return s
        parts = ["0"]
        for bit, code in self._ATTR_CODES:
            if at & bit:
                parts.append(code)
        if fg is not None:
            parts.append(self._fgs(fg))
        if bg is not None:
            parts.append(self._bgs(bg))
        s = "\x1b[" + ";".join(parts) + "m"
        if len(self._sgr_cache) > 20000:
            self._sgr_cache.clear()
        self._sgr_cache[key] = s
        return s

    def _sgr_delta(self, fg, bg, at, cur):
        """The *shortest* SGR that gets from state ``cur`` to (fg, bg, at).

        This is where the frame's byte budget actually goes. A panel cell is
        a foreground, a background and some attributes; re-stating all three
        for every cell costs ~30 bytes each, and at 200x60 that is the
        difference between a frame the terminal swallows whole and one it
        paints in visible instalments.

        Almost every neighbouring cell shares its background with the one
        before it (the panel ground) and usually its attributes too, so the
        delta is typically just the 16-byte foreground — or nothing at all.

        Falls back to the full reset form whenever an attribute has to be
        turned *off*, since SGR has no cheap "clear just this one" for the
        set we use.
        """
        if cur is None:
            return self._sgr(fg, bg, at)
        cfg, cbg, cat = cur
        if cat & ~at:                       # an attribute must be cleared
            return self._sgr(fg, bg, at)
        # A colour going from set back to None is "use the terminal default",
        # which no additive delta can say. This has to be checked BEFORE the
        # empty-delta early return below, or a cell whose only change is
        # fg -> None emits nothing at all and keeps the previous colour.
        if (fg is None and cfg is not None) or (bg is None and cbg is not None):
            return self._sgr(fg, bg, at)
        parts = []
        added = at & ~cat
        if added:
            for bit, code in self._ATTR_CODES:
                if added & bit:
                    parts.append(code)
        if fg != cfg and fg is not None:
            parts.append(self._fgs(fg))
        if bg != cbg and bg is not None:
            parts.append(self._bgs(bg))
        if not parts:
            return ""
        return "\x1b[" + ";".join(parts) + "m"

    def render(self, cv, full=False):
        """Return the byte string that turns the terminal from the previous
        frame into `cv`. Empty bytes when nothing changed."""
        w, h = cv.w, cv.h
        chs, fgs, bgs, ats = cv.ch, cv.fg, cv.bg, cv.at
        prev = self.prev
        if full or prev is None or prev[0] != w or prev[1] != h:
            prev = None
        out = []
        ap = out.append
        if prev is None:
            ap("\x1b[H")
        pch = prev[2] if prev else None
        pfg = prev[3] if prev else None
        pbg = prev[4] if prev else None
        pat = prev[5] if prev else None
        cur_sgr = None
        cells = 0
        cur_y = -1
        cur_x = -1
        use_rep = self.rep
        for y in range(h):
            b = y * w
            if prev is not None:
                e = b + w
                # row-level fast skip: slice compares run in C
                if pch[b:e] == chs[b:e] and pbg[b:e] == bgs[b:e] and pfg[b:e] == fgs[b:e] and pat[b:e] == ats[b:e]:
                    continue
            x = 0
            while x < w:
                i = b + x
                c = chs[i]
                if c == "":
                    x += 1
                    continue
                if prev is not None and pch[i] == c and pfg[i] == fgs[i] and pbg[i] == bgs[i] and pat[i] == ats[i]:
                    x += cwidth(c[0]) or 1
                    continue
                # start of a dirty run: position the cursor unless we are
                # already there. Absolute vs relative is chosen by byte count —
                # a short hop along the same row is cheaper as CUF.
                if not (cur_y == y and cur_x == x):
                    absolute = "\x1b[%d;%dH" % (y + 1, x + 1)
                    if cur_y == y and cur_x < x:
                        gap = x - cur_x
                        relative = "\x1b[C" if gap == 1 else "\x1b[%dC" % gap
                        ap(relative if len(relative) < len(absolute) else absolute)
                    else:
                        ap(absolute)
                    cur_y, cur_x = y, x
                cell = (fgs[i], bgs[i], ats[i])
                if cell != cur_sgr:
                    d = self._sgr_delta(cell[0], cell[1], cell[2], cur_sgr)
                    if d:
                        ap(d)
                    cur_sgr = cell
                ap(c)
                cells += 1
                cw = cwidth(c[0]) if c else 1
                x += cw
                cur_x += cw
                # Collapse an identical run with ECMA-48 REP. Dither ramps,
                # rails and noise fields are long stretches of one 3-byte
                # block glyph in one colour; repeating them costs 4 bytes
                # instead of 3 per cell. Width-1 only — REP repeats the last
                # graphic character, which is ill-defined for wide cells.
                if use_rep and cw == 1 and len(c) == 1:
                    n = 0
                    j = b + x
                    xx = x
                    while (xx < w and chs[j] == c and fgs[j] == fgs[i]
                           and bgs[j] == bgs[i] and ats[j] == ats[i]):
                        n += 1
                        xx += 1
                        j += 1
                    if n:
                        seq = "\x1b[b" if n == 1 else "\x1b[%db" % n
                        if len(seq) < n * len(c.encode("utf-8")):
                            ap(seq)
                            cells += n
                            x += n
                            cur_x += n
        # Cursor discipline. `out` at this point holds cell writes only.
        #
        # If this frame paints anything while the hardware cursor is showing,
        # the cursor is dragged over every dirty run on its way — the "cursor
        # redrawing across the screen" artifact. So: hide it *before* the
        # cells (prepended, still inside the DEC 2026 bracket), and put it
        # back at its home square as the last thing in the payload.
        #
        # When nothing changed we emit nothing at all, so a parked cursor is
        # left alone instead of being blinked off and on every ambient frame.
        painted = bool(out)
        if painted and self._cursor_shown:
            out.insert(0, "\x1b[?25l")
            self._cursor_shown = False
        if cv.cursor is not None:
            cx, cy = cv.cursor
            if painted or not self._cursor_shown or self._cursor_at != (cx, cy):
                ap("\x1b[%d;%dH" % (cy + 1, cx + 1))
                self._cursor_at = (cx, cy)
            if not self._cursor_shown:
                ap("\x1b[?25h")
                self._cursor_shown = True
        elif self._cursor_shown:
            ap("\x1b[?25l")
            self._cursor_shown = False
        # remember this frame
        self.prev = (w, h, list(chs), list(fgs), list(bgs), list(ats))
        if not out:
            return b""
        data = "".join(out).encode("utf-8", "replace")
        self.frames += 1
        self.bytes_out += len(data)
        self.cells_out += cells
        if len(data) > self.max_bytes:
            self.max_bytes = len(data)
        return data

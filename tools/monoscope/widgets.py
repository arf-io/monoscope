"""monoscope.widgets — the panel's component vocabulary.

Every widget is a function ``draw_x(cv, x, y, w, ..., fam, tick, motion)`` that
paints into a rect of the :class:`~monoscope.canvas.Canvas` and returns
nothing (or the number of rows used). Widgets are pure functions of their
arguments — no clock, no I/O — so a frame is reproducible from
``(model, tick, w, h)``.

Vocabulary (names follow the MONOSCOPE spec §3):

    band            top band: ░▒▓█ TITLE ███…███ context █▓▒░, hue-swept
    section_band    ▀▀ GROUP · description ▀▀▀▀ in the group hue
    group_bar       the SMPTE chips: nine contiguous bg runs + labels
    strip           the channel strip: cursor│label│meter│value│unit│delta
    meter           bg-fill meter with peg-over-range ▶ and inherited tick
    switch          ▐██ ON ██▌ / ▐▒▒ OFF ▒▒▌
    chips           enum selector: ▐P22▌ p1 p31 …
    button          ▐ FIRE ▌ block button (flashes on activation)
    ruler           min ▐████▒▒▒▌ max with markers (default/inherited/now)
    status_band     powerline-style segments with ▌ separators
    hint_band       key/label pairs
    signature       ▁▂▃▄▅▆▇█ tube fingerprint
    text_block      word-wrapped prose
"""

from __future__ import annotations

import math

from .canvas import BOLD, DIM, swidth
from . import color as C
from .blocks import SHADES, vbar_glyph

__all__ = ["band", "section_band", "group_bar", "strip", "meter", "switch", "chips",
           "button", "ruler", "status_band", "hint_band", "signature", "text_block",
           "wrap_text", "STRIP_LABEL_W", "STRIP_VALUE_W", "STRIP_UNIT_W", "meter_width",
           "sweep_colors", "put_shaded_text", "paint_banner", "noise_field", "banner_block"]

STRIP_LABEL_W = 13
STRIP_VALUE_W = 7
STRIP_UNIT_W = 5
METER_MIN, METER_MAX = 16, 34
_METER_CACHE = {}
_SWEEP_ROW_CACHE = {}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def wrap_text(text, width):
    """Greedy word wrap; never returns an empty list for non-empty text."""
    if width <= 0:
        return []
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        while len(w) > width:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:width])
            w = w[width:]
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def sweep_colors(fam, w, tick, motion, speed=0.5, span=1.0, offset=0.0, sat_scale=1.0):
    """Per-column sweep colors across w cells: hue (or ramp) position drifts
    `speed` degrees per tick when motion is on. Returns a list of RGB."""
    if w <= 0:
        return []
    key = (id(fam), w, tick if motion else 0, speed, span, offset, sat_scale)
    out = _SWEEP_ROW_CACHE.get(key)
    if out is not None:
        return out
    drift = (tick * speed / 360.0) if motion else 0.0
    out = []
    for i in range(w):
        t = (offset + drift + (i / max(1, w)) * span) % 1.0
        c = fam.sweep(t)
        if sat_scale != 1.0:
            h, s, v = C.rgb_to_hsv(c)
            c = C.hsv_to_rgb(h, s * sat_scale, v)
        out.append(c)
    if len(_SWEEP_ROW_CACHE) > 64:
        _SWEEP_ROW_CACHE.clear()
    _SWEEP_ROW_CACHE[key] = out
    return out


def put_shaded_text(cv, x, y, text, colors, bg=None, at=0):
    """Text where each character takes the color at its column."""
    for i, ch in enumerate(text):
        col = colors[min(len(colors) - 1, i)] if colors else None
        cv.put(x + i, y, ch, fg=col, bg=bg, at=at)


def meter_width(avail):
    return max(METER_MIN, min(METER_MAX, avail))


def noise_field(cv, x, y, w, h, tick, fam, density=0.06, seed=3, motion=True):
    """Roy's negative-space texture: dark ░ scattered in the rect, denser
    toward the vertical middle, thinning outward; a slow drift when motion
    is on (never more than ~12% of the field lit)."""
    if w <= 0 or h <= 0:
        return
    n = int(w * h * density)
    col = fam.noise
    ph = (tick // 6) if motion else 0
    for k in range(n):
        hx = (k * 7919 + seed * 104729 + ph * 31) % 65521
        hy = (k * 15485863 + seed * 7 + ph * 17) % 65521
        sx = x + hx % w
        sy = y + hy % h
        # denser near the middle rows
        mid = abs((sy - y) - h / 2.0) / max(1.0, h / 2.0)
        if (hx % 7) / 7.0 < mid * 0.8:
            continue
        cur = cv.get(sx, sy)
        if cur and cur[0] != " ":
            continue
        cv.put(sx, sy, "░", fg=col, bg=None)


def paint_banner(cv, x, y, rows, fam, tick, motion=True, hue_span=0.8, speed=0.6):
    """Draw pre-rendered TDF banner rows (list of rows of (char, level))
    at (x, y): the font's baked shading (level 1 = brightest) is mapped onto
    the family FACE ramp (Roy's vertical ramp idiom: bright top → body → dark
    → cool foot) and, for colour families, tinted by the hue sweep so the
    logo lives. Returns the banner width."""
    if not rows:
        return 0
    bw = max(len(r) for r in rows)
    sweep = sweep_colors(fam, max(1, bw), tick, motion, speed=speed, span=hue_span)
    for ry, row in enumerate(rows):
        for cx, cell in enumerate(row):
            ch, level = cell
            if ch == " ":
                continue
            face = fam.face_at(1.0 - level)
            if fam.hues:
                base = sweep[min(bw - 1, cx)]
                col = C.lerp_rgb(face, base, 0.5)
            else:
                col = face
            cv.put(x + cx, y + ry, ch, fg=col, bg=None)
    return bw


# ---------------------------------------------------------------------------
# bands
# ---------------------------------------------------------------------------

def band(cv, x, y, w, title, right, fam, tick, motion=True, ground=None, hue_span=1.0, dark=0.35):
    """The demoscene band: a hue-swept solid run with the title woven in at
    the left and a context string at the right, capped by ░▒▓ / ▓▒░.
    Two rows tall when h allows? No — one row; callers stack bands."""
    if w < 8:
        return
    ground = ground if ground is not None else fam.ground
    cols = sweep_colors(fam, w, tick, motion, span=hue_span)
    # caps
    left_cap, right_cap = "░▒▓", "▓▒░"
    for i in range(3):
        cv.put(x + i, y, left_cap[i], fg=cols[i], bg=None)
        cv.put(x + w - 3 + i, y, right_cap[i], fg=cols[w - 3 + i], bg=None)
    # solid run
    for i in range(3, w - 3):
        cv.put(x + i, y, " ", bg=cols[i])
    # title text: dark on the lit band for legibility, bold
    t = " %s " % title
    tx = x + 4
    for i, ch in enumerate(t):
        if tx + i >= x + w - 4:
            break
        bgc = cols[tx + i - x]
        cv.put(tx + i, y, ch, fg=C.darken(bgc, 0.75), bg=bgc, at=BOLD)
    if right:
        r = " %s " % right
        rx = x + w - 4 - len(r)
        if rx > tx + len(t) + 1:
            for i, ch in enumerate(r):
                bgc = cols[rx + i - x]
                cv.put(rx + i, y, ch, fg=C.darken(bgc, 0.75), bg=bgc)


def section_band(cv, x, y, w, title, desc, hue_rgb, fam, tick=0, motion=True, badges=""):
    """▀▀ TITLE · desc ▀▀▀▀▀▀ — Roy's glow rail on a half-height run: fades
    in over three cells, is bright under the title, decays along the row and
    fades out at the far end; a slow specular hot spot breathes along the
    run when motion is on (colour only — the glyphs never move)."""
    if w < 6:
        return
    lit = C.crt_safe(hue_rgb)
    text = " %s " % title
    if desc:
        text += "· %s " % desc
    if badges:
        text += "· %s " % badges
    text = text[: max(0, w - 4)]
    tend = 2 + len(text)
    bright = C.darken(lit, 0.30)
    dimc = C.darken(lit, 0.74)
    spot = None
    if motion and w - tend > 12:
        # hot spot position oscillates along the free run
        import math as _m
        f = 0.5 + 0.5 * _m.sin(tick * 0.045 + (x * 0.7 + y * 1.3))
        spot = tend + 4 + int(f * (w - tend - 8))
    for i in range(w):
        if i < 3:
            c = C.lerp_rgb(dimc, bright, (i + 1) / 3.0)
        elif i < tend + 2:
            c = bright
        else:
            f = min(1.0, (i - tend - 2) / max(1.0, (w - tend) * 0.55))
            c = C.lerp_rgb(bright, dimc, f)
        if i >= w - 3:
            c = C.lerp_rgb(c, fam.ground2, (i - (w - 4)) / 3.0)
        if spot is not None and abs(i - spot) <= 3:
            k = 1.0 - abs(i - spot) / 4.0
            c = C.lerp_rgb(c, C.lighten(lit, 0.35), 0.75 * k)
        cv.put(x + i, y, "▀", fg=c, bg=None)
    cv.put(x + 2, y, text, fg=C.lighten(lit, 0.15), bg=None, at=BOLD)


GROUP_SHORT = {"video": "VIDEO", "geometry": "GEOM", "scan": "SCAN", "vector": "VECTOR", "mask": "MASK",
               "phosphor": "PHOS", "artifacts": "ARTIFACT", "burnin": "BURN", "system": "SYS"}


def group_bar(cv, x, y, w, groups, active, hues, fam, tick, motion=True, counts=None, modified=None):
    """Two rows: labels row (dim, active bright) and the chip row — nine
    contiguous background runs, active at full luminance, others ~35%.
    (The SMPTE card.)"""
    n = len(groups)
    if n == 0 or w < n * 4:
        return
    ground = fam.ground
    seg = w / n
    for i, g in enumerate(groups):
        x0 = x + int(i * seg)
        x1 = x + int((i + 1) * seg)
        hue = hues.get(g, 0.0)
        base = C.crt_safe(C.hue_to_rgb(hue)) if fam.hues else fam.shade(0.35 + 0.6 * i / max(1, n - 1))
        if i == active:
            chip = base
            glyph = "█"
        else:
            chip = C.darken(base, 0.6)
            glyph = "▄"
        for xx in range(x0, x1 - (1 if i < n - 1 else 0)):
            cv.put(xx, y + 1, glyph, fg=chip, bg=None)
        label = (GROUP_SHORT.get(g, g.upper()) if seg < 11 else g.upper())
        badge = ""
        if modified and modified.get(g):
            badge = "✱%d" % modified[g]
        text = (label + (" " + badge if badge else ""))[: max(1, x1 - x0 - 1)]
        lx = x0 + max(0, (x1 - x0 - 1 - len(text)) // 2)
        cv.put(lx, y, text, fg=(C.lighten(base, 0.45) if i == active else C.lerp_rgb(fam.dim, base, 0.5)),
               bg=None, at=BOLD if i == active else 0)


# ---------------------------------------------------------------------------
# strip parts
# ---------------------------------------------------------------------------

def meter(cv, x, y, w, t, fam, hue_rgb, lit=1.0, peg=False, marker=None, empty=None):
    """Background-fill meter: t∈[0,1] of `w` cells lit in hue_rgb, rest in
    the unlit tone. The lit run is a copper-bar gradient (dark hue at the
    left rising to the full hue at the value end, one bright cap cell) so a
    row of meters reads like a lit VU bank instead of a slab of colour.
    `lit` scales overall brightness (breathing on selection); `peg` paints
    ▶ at the last cell (over range); `marker` (0..1) draws a ▏ tick for
    the inherited value."""
    if w <= 0:
        return
    on = C.crt_safe(hue_rgb)
    lit = max(0.0, min(1.0, lit))
    off = empty if empty is not None else C.lerp_rgb(fam.ground, fam.ground2, 0.9)
    off = C.lerp_rgb(off, C.darken(on, 0.85), 0.35)
    if peg:
        n = w
    else:
        n = int(round(max(0.0, min(1.0, t)) * w))
    litq = int(lit * 16)
    key = (on, off, w, n, litq)
    cols = _METER_CACHE.get(key)
    if cols is None:
        dark = C.darken(on, 0.55)
        k = 0.6 + 0.4 * (litq / 16.0)
        cols = []
        for i in range(w):
            if i < n:
                c = C.lerp_rgb(dark, on, (i + 1) / max(1, n))
                c = C.scale(c, k)
                if i == n - 1 and n < w:
                    c = C.lighten(c, 0.25)
                cols.append(c)
            else:
                cols.append(off)
        if len(_METER_CACHE) > 4096:
            _METER_CACHE.clear()
        _METER_CACHE[key] = cols
    b = y * cv.w
    if 0 <= y < cv.h:
        chs, fgs, bgs = cv.ch, cv.fg, cv.bg
        x0, x1 = max(0, x), min(cv.w, x + w)
        for i in range(x0, x1):
            chs[b + i] = " "
            bgs[b + i] = cols[i - x]
        # the bloom past the needle: two cells of ▒ ░ in the lit colour over
        # the unlit run (Roy's meter tip / glow-bar fade-out). Ghostty draws
        # ░▒ as flat 25/50 % blends, so this reads as phosphor bloom.
        if 0 < n < w - 1 and not peg:
            tip = cols[n - 1]
            for j, g in ((0, "▒"), (1, "░")):
                i = x + n + j
                if x0 <= i < x1:
                    chs[b + i] = g
                    fgs[b + i] = tip
                    bgs[b + i] = off
    if peg:
        cv.put(x + w - 1, y, "▶", fg=fam.glow, bg=on)
    if marker is not None and not peg:
        mx = x + max(0, min(w - 1, int(round(marker * (w - 1)))))
        cur = cv.get(mx, y)
        cv.put(mx, y, "▏", fg=fam.glow, bg=cur[2] if cur else None)


def switch(cv, x, y, on, fam, hue_rgb, lit=1.0):
    """▐██ ON ██▌ (lit) / ▐▒▒ OFF ▒▒▌ (unlit). Returns width (10)."""
    ground = fam.ground
    if on:
        c = C.scale(C.crt_safe(hue_rgb), 0.6 + 0.4 * lit)
        cv.put(x, y, "▐", fg=c, bg=None)
        cv.put(x + 1, y, "   ON   ", fg=C.darken(c, 0.75), bg=c, at=BOLD)
        cv.put(x + 9, y, "▌", fg=c, bg=None)
    else:
        c = fam.dim
        cv.put(x, y, "▐", fg=c, bg=None)
        cv.put(x + 1, y, "░░ OFF ░░", fg=c, bg=fam.ground2)
        cv.put(x + 10, y, "▌", fg=c, bg=None)
    return 10 if on else 11


def chips(cv, x, y, w, members, current, fam, hue_rgb, lit=1.0):
    """Enum selector as chips: the current member is a lit block ▐NAME▌,
    the others plain dim text. Truncates to w with a … tail. Returns width."""
    ground = fam.ground
    on = C.scale(C.crt_safe(hue_rgb), 0.6 + 0.4 * lit)
    cx = x
    for m in members:
        name = str(m)
        if m == current:
            need = len(name) + 2
            if cx + need > x + w:
                break
            cv.put(cx, y, "▐", fg=on, bg=None)
            cv.put(cx + 1, y, name, fg=C.darken(on, 0.75), bg=on, at=BOLD)
            cv.put(cx + 1 + len(name), y, "▌", fg=on, bg=None)
            cx += need + 1
        else:
            need = len(name)
            if cx + need > x + w:
                if cx + 1 <= x + w:
                    cv.put(cx, y, "…", fg=fam.dim, bg=None)
                break
            cv.put(cx, y, name, fg=fam.dim, bg=None)
            cx += need + 2
    return cx - x


def button(cv, x, y, label, fam, hue_rgb, lit=1.0, fired=0.0):
    """▐ LABEL ▌ block button. `fired` in [0,1] flashes the face toward glow."""
    ground = fam.ground
    c = C.scale(C.crt_safe(hue_rgb), 0.55 + 0.45 * lit)
    if fired > 0:
        c = C.lerp_rgb(c, fam.glow, fired)
    text = " %s " % label
    cv.put(x, y, "▐", fg=c, bg=None)
    cv.put(x + 1, y, text, fg=C.darken(c, 0.78), bg=c, at=BOLD)
    cv.put(x + 1 + len(text), y, "▌", fg=c, bg=None)
    return len(text) + 2


def ruler(cv, x, y, w, lo, hi, marks, fam, hue_rgb):
    """A range strip: `lo` ▐████▒▒▒▒▌ `hi`, with named markers.
    marks: list of (t, glyph, color) with t in [0,1] (may exceed for peg)."""
    lo_s, hi_s = str(lo), str(hi)
    inner = w - len(lo_s) - len(hi_s) - 4
    if inner < 6:
        return
    cv.put(x, y, lo_s, fg=fam.dim, bg=None)
    bx = x + len(lo_s) + 1
    cv.put(bx, y, "▐", fg=fam.dim, bg=None)
    on = C.crt_safe(hue_rgb)
    off = C.lerp_rgb(fam.ground2, fam.dim, 0.35)
    now_t = None
    for t, g, col in marks:
        if g == "now":
            now_t = t
    n = int(round(max(0.0, min(1.0, now_t if now_t is not None else 0.0)) * inner))
    for i in range(inner):
        cv.put(bx + 1 + i, y, " ", bg=on if i < n else off)
    for t, g, col in marks:
        if g == "now":
            continue
        pos = bx + 1 + max(0, min(inner - 1, int(round(t * (inner - 1)))))
        cur = cv.get(pos, y)
        cv.put(pos, y, g, fg=col, bg=cur[2] if cur else None)
    cv.put(bx + 1 + inner, y, "▌", fg=fam.dim, bg=None)
    cv.put(bx + 2 + inner, y, hi_s, fg=fam.dim, bg=None)


# ---------------------------------------------------------------------------
# status / hints
# ---------------------------------------------------------------------------

def status_band(cv, x, y, w, segments, fam, tick, motion=True):
    """Segments: list of (text, kind) where kind in {'title','info','ok','warn','bad','armed'}.
    Painted as ▌-separated blocks whose bg steps down the family ramp."""
    if w < 4:
        return
    ground = fam.ground
    cv.fill(x, y, w, 1, " ", bg=fam.ground2)
    cx = x
    n = max(1, len(segments))
    for i, (text, kind) in enumerate(segments):
        text = " %s " % text
        if kind == "title":
            bg = C.crt_safe(fam.sweep((tick * 0.002) % 1.0 if motion else 0.0)) if fam.hues else fam.shade(0.8)
            fg = C.darken(bg, 0.78)
            at = BOLD
        elif kind == "ok":
            bg = C.darken(fam.ok, 0.6)
            fg = fam.ok
            at = 0
        elif kind == "warn":
            bg = C.darken(fam.warn, 0.6)
            fg = fam.warn
            at = BOLD
        elif kind == "bad":
            bg = C.darken(fam.bad, 0.55)
            fg = fam.bad
            at = BOLD
        elif kind == "armed":
            pulse = C.breathing(tick, 0.25) if motion else 1.0
            bg = C.scale(C.crt_safe(fam.hot), 0.35 + 0.35 * pulse)
            fg = fam.glow
            at = BOLD
        else:
            bg = C.lerp_rgb(fam.ground2, fam.dim, 0.35 - 0.05 * min(i, 4))
            fg = fam.ink
            at = 0
        if cx + len(text) > x + w:
            text = text[: max(0, x + w - cx)]
        cv.put(cx, y, text, fg=fg, bg=bg, at=at)
        cx += len(text)
        if cx < x + w:
            nxt = segments[i + 1] if i + 1 < len(segments) else None
            cv.put(cx, y, "▌", fg=bg, bg=fam.ground2)
            cx += 1
        if cx >= x + w:
            break


def hint_band(cv, x, y, w, pairs, fam, tick, motion=True):
    """Roy's hotkey rail: ▌░▒▓│ key label │ key label … █▓▒░▐ — keys bright
    on a dark hue-tinted rail, labels dim, │ separators, faded end caps.
    Truncates whole pairs that do not fit."""
    if w < 8:
        return
    hot = C.crt_safe(fam.hot)
    rail = C.lerp_rgb(fam.ground2, C.darken(hot, 0.7), 0.5)
    sep = C.darken(hot, 0.5)
    cv.fill(x, y, w, 1, " ", bg=rail)
    # end caps
    cv.put(x, y, "░", fg=rail, bg=None)
    cv.put(x + 1, y, "▒", fg=rail, bg=None)
    cv.put(x + 2, y, "▓", fg=rail, bg=None)
    cv.put(x + w - 3, y, "▓", fg=rail, bg=None)
    cv.put(x + w - 2, y, "▒", fg=rail, bg=None)
    cv.put(x + w - 1, y, "░", fg=rail, bg=None)
    cx = x + 4
    limit = x + w - 4
    for i, (k, label) in enumerate(pairs):
        need = len(k) + 1 + len(label) + 3
        if cx + need > limit:
            break
        cv.put(cx, y, k, fg=fam.glow, bg=rail, at=BOLD)
        cv.put(cx + len(k), y, " " + label, fg=C.lerp_rgb(fam.dim, fam.ink, 0.35), bg=rail)
        cx += len(k) + 1 + len(label) + 1
        if i < len(pairs) - 1 and cx + 2 <= limit:
            cv.put(cx, y, "│", fg=sep, bg=rail)
        cx += 2


def signature(cv, x, y, values, fam, hue_rgb=None, framed=True):
    """Eight ▁▂▃▄▅▆▇█ verticals encoding [0,1] values — the tube fingerprint.
    Returns width used."""
    ground = fam.ground
    col = C.crt_safe(hue_rgb) if hue_rgb else fam.hot
    cx = x
    if framed:
        cv.put(cx, y, "▐", fg=fam.dim, bg=None)
        cx += 1
    for v in values:
        cv.put(cx, y, vbar_glyph(v), fg=col, bg=fam.ground2)
        cx += 1
    if framed:
        cv.put(cx, y, "▌", fg=fam.dim, bg=None)
        cx += 1
    return cx - x


def text_block(cv, x, y, w, h, text, fam, fg=None, at=0):
    """Word-wrapped prose in a rect; returns rows used."""
    lines = wrap_text(text, w)[:h]
    for i, ln in enumerate(lines):
        cv.put(x, y + i, ln, fg=fg or fam.ink, bg=None, at=at)
    return len(lines)


# ---------------------------------------------------------------------------
# the channel strip
# ---------------------------------------------------------------------------

def strip(cv, x, y, w, row, fam, hue_rgb, tick, motion=True, selected=False,
          entry=None, meter_w=None, delta_text="", badge=""):
    """One parameter row.

    row: dict with keys
        kind: 'rotary'|'switch'|'selector'|'button'|'action'|'text'
        label, value_text, unit, t (0..1 or None), peg (bool), on (bool),
        members (list), current, over (bool), fired (0..1), modified (bool)
    Layout: [cursor 2][label 13][gap 1][meter mw][gap 2][value 7][unit 5][gap 1][delta …]
    Everything is placed at fixed offsets; leftover width goes to delta.
    """
    ground = fam.ground
    lit = 1.0
    if selected:
        # row lift: paint the row background one step up, and breathe the meter
        cv.fill(x, y, w, 1, " ", bg=fam.ground2)
        lit = C.breathing(tick, 0.18) if motion else 1.0
        cv.put(x, y, "▐", fg=C.crt_safe(hue_rgb), bg=None)
        cv.put(x + 1, y, "▶", fg=fam.glow, bg=fam.ground2, at=BOLD)
    else:
        cv.put(x, y, "  ", bg=None)
    bg_row = fam.ground2 if selected else ground
    lx = x + 2
    label = row.get("label", "")[:STRIP_LABEL_W]
    lab_fg = fam.ink if not row.get("hidden_kind") else fam.dim
    if row.get("modified"):
        lab_fg = C.lighten(C.crt_safe(hue_rgb), 0.35)
    cv.put(lx, y, label.ljust(STRIP_LABEL_W), fg=lab_fg, bg=bg_row, at=BOLD if selected else 0)
    mx = lx + STRIP_LABEL_W + 1
    avail = w - (mx - x) - (2 + STRIP_VALUE_W + STRIP_UNIT_W + 1)
    mw = meter_w if meter_w is not None else meter_width(avail)
    if mw < 4:
        mw = max(0, avail)
    kind = row.get("kind")
    vx = mx + mw + 2
    ux = vx + STRIP_VALUE_W
    dx = ux + STRIP_UNIT_W + 1
    if kind == "rotary":
        if entry is not None:
            # in-place entry field over the meter
            field = entry.get("text", "")
            cv.put(mx, y, "▐", fg=fam.glow, bg=bg_row)
            cv.fill(mx + 1, y, mw - 2, 1, " ", bg=C.darken(fam.hot, 0.65))
            shown = field[-(mw - 3):] if len(field) > mw - 3 else field
            cv.put(mx + 1, y, shown, fg=fam.glow, bg=C.darken(fam.hot, 0.65), at=BOLD)
            cv.cursor = (mx + 1 + len(shown), y)
            cv.put(mx + mw - 1, y, "▌", fg=fam.glow, bg=bg_row)
            if entry.get("over"):
                cv.put(vx, y, "⚠ OVER".ljust(STRIP_VALUE_W + STRIP_UNIT_W), fg=fam.warn, bg=bg_row, at=BOLD)
            else:
                cv.put(vx, y, str(entry.get("preview", "")).rjust(STRIP_VALUE_W), fg=fam.ink, bg=bg_row)
        else:
            t = row.get("t")
            meter(cv, mx, y, mw, t if t is not None else 0.0, fam, hue_rgb, lit=lit,
                  peg=bool(row.get("peg")), marker=row.get("inherited_t"))
            val = str(row.get("value_text", ""))
            vfg = fam.warn if row.get("over") else (fam.glow if selected else fam.ink)
            cv.put(vx, y, val.rjust(STRIP_VALUE_W)[-STRIP_VALUE_W:], fg=vfg, bg=bg_row, at=BOLD if selected else 0)
            unit = str(row.get("unit", ""))[:STRIP_UNIT_W]
            cv.put(ux, y, " " + unit, fg=fam.dim, bg=bg_row)
    elif kind == "switch":
        switch(cv, mx, y, bool(row.get("on")), fam, hue_rgb, lit=lit)
        val = "ON" if row.get("on") else "OFF"
        cv.put(vx, y, val.rjust(STRIP_VALUE_W), fg=(fam.glow if selected else fam.ink), bg=bg_row)
    elif kind == "selector":
        used = chips(cv, mx, y, mw + 2 + STRIP_VALUE_W + STRIP_UNIT_W - 4, row.get("members", []), row.get("current"), fam, hue_rgb, lit=lit)
        idx = row.get("index_text", "")
        if idx:
            cv.put(ux + 1, y, idx.rjust(STRIP_UNIT_W - 1), fg=fam.dim, bg=bg_row)
    elif kind in ("button", "action"):
        button(cv, mx, y, row.get("button_label", row.get("label", "")), fam, hue_rgb, lit=lit, fired=row.get("fired", 0.0))
        st = row.get("value_text", "")
        if st:
            cv.put(vx, y, str(st).rjust(STRIP_VALUE_W), fg=fam.ink, bg=bg_row)
    elif kind == "text":
        # free text value (terminal overrides): show as a lit field
        val = str(row.get("value_text", ""))
        cv.put(mx, y, "▐", fg=fam.dim, bg=bg_row)
        cv.put(mx + 1, y, val[: mw - 2].ljust(mw - 2), fg=fam.ink, bg=fam.ground2 if not selected else C.darken(fam.hot, 0.7))
        cv.put(mx + mw - 1, y, "▌", fg=fam.dim, bg=bg_row)
    # delta / badge column
    if dx < x + w:
        if badge:
            cv.put(dx, y, badge, fg=fam.warn, bg=bg_row, at=BOLD, maxw=x + w - dx)
        elif delta_text:
            cv.put(dx, y, delta_text, fg=fam.dim, bg=bg_row, maxw=x + w - dx)
    return dx


def banner_block(cv, w, y, kind, text, fam, tick, motion=True, margin_top=1, full=None):
    """A complete banner block: top margin, noise field + sparkles around,
    the TDF title centred. Returns rows used (0 when the font is missing).
    `full` (defaults to `motion`) gates the expensive ambient life: noise
    drift, twinkling sparkles, the hue sweep across the letters."""
    from .banners import banner_rows
    from .blocks import sparkles
    rows = banner_rows(kind, text)
    if not rows:
        return 0
    if full is None:
        full = motion
    bh = len(rows)
    bw = max(len(r) for r in rows)
    bx = max(0, (w - bw) // 2)
    total = bh + margin_top
    noise_field(cv, 0, y, w, total, tick, fam, density=0.03, motion=full)
    sparkles(cv, 0, y, w, total, tick if full else 0, fam, density=0.010)
    paint_banner(cv, bx, y + margin_top, rows, fam, tick, full)
    return total

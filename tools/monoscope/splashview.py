"""monoscope.splashview — the logon matrix.

A short boot splash: the MONOSCOPE hero banner (Razor 1911 TheDraw font when
the terminal is wide enough) revealed the way an ANSI loaded at 2400 baud —
cells appear left-to-right, row by row — over a noise field, with a
CONNECT line naming the tube and the bus.

It waits for the operator: the splash holds until a key is pressed (any key
enters the panel, ``q`` quits). ``SPLASH_TICKS`` is the *reveal* budget — how
long the banner takes to load in — not a dismissal timer. Motion "off" shows
the finished frame at once, and the splash is skipped entirely when stdin is
not a tty, so a non-interactive run can never block on a key that will never
come.
"""

from __future__ import annotations

from .canvas import BOLD
from . import color as C
from . import widgets as W
from .banners import banner_rows

__all__ = ["render_splash", "SPLASH_TICKS"]

SPLASH_TICKS = 40          # at the 20-tick/s response clock ≈ 2 s


def render_splash(m, cv, tick):
    fam = m.fam
    motion = m.motion != "off"
    w, h = cv.w, cv.h
    t = tick - m.splash_t0
    kind = "hero" if (w >= 124 and h >= 24) else "big" if (w >= 70 and h >= 16) else "small"
    rows = banner_rows(kind, "MONOSCOPE")
    bh = len(rows)
    bw = max((len(r) for r in rows), default=0)
    total_h = bh + 6
    y0 = max(1, (h - total_h) // 2)
    bx = max(0, (w - bw) // 2)
    W.noise_field(cv, 0, 0, w, h, tick, fam, density=0.03, motion=motion)
    from .blocks import sparkles
    sparkles(cv, 0, 0, w, h, tick if motion else 0, fam, density=0.006)
    # reveal budget: cells per tick, so the whole banner lands in ~60% of the splash
    total_cells = bh * bw
    if motion:
        budget = int(total_cells * min(1.0, (t + 1) / (SPLASH_TICKS * 0.6)))
    else:
        budget = total_cells
    sweep = W.sweep_colors(fam, max(1, bw), tick, motion, speed=0.6, span=0.8)
    shown = 0
    for ry, row in enumerate(rows):
        for cx, (ch, level) in enumerate(row):
            if shown >= budget:
                break
            shown += 1
            if ch == " ":
                continue
            face = fam.face_at(1.0 - level)
            col = C.lerp_rgb(face, sweep[min(bw - 1, cx)], 0.5) if fam.hues else face
            cv.put(bx + cx, y0 + ry, ch, fg=col, bg=None)
        else:
            continue
        break
    # the cursor of the "download": a bright cell right after the last revealed one
    if motion and shown < total_cells and shown > 0:
        ry, cx = divmod(shown, bw)
        if ry < bh:
            cv.put(bx + cx, y0 + ry, "▌", fg=fam.glow, bg=None)
    yy = y0 + bh + 1
    if budget >= total_cells or not motion:
        line1 = "the crtctl control surface"
        cv.put(max(0, (w - len(line1)) // 2), yy, line1, fg=fam.dim, bg=None)
        tube = m.ctl.active_preset or "schema defaults"
        n = len(m.preset_docs()) if hasattr(m, "preset_docs") else 0
        line2 = "CONNECT 14400 · %s · %s · %d tubes in the bank" % (m.dest, tube.upper(), n)
        hot = C.crt_safe(fam.hot)
        cv.put(max(0, (w - len(line2)) // 2), yy + 2, line2[: w - 2], fg=hot, bg=None, at=BOLD)
        blink = (tick // 6) % 2 == 0 if motion else True
        if blink:
            line3 = "press any key"
            cv.put(max(0, (w - len(line3)) // 2), yy + 4, line3, fg=fam.ink, bg=None)
    W.band(cv, 0, h - 1, w, "MONOSCOPE", "SysOp %s" % (m.user or "?"), fam, tick, motion)

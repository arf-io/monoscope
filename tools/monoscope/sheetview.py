"""monoscope.sheetview — the SAVE TUBE sheet, rising over a dimmed bench."""

from __future__ import annotations

from .canvas import BOLD
from . import color as C
from . import widgets as W
from . import blocks as B

__all__ = ["render_sheet"]


def render_sheet(m, cv, tick, L):
    fam = m.fam
    motion = m.motion != "off"
    s = m.sheet
    w, h = cv.w, cv.h
    diff = s.diff() if s.kind == "preset" else []
    desc_lines = W.wrap_text(s.description, max(20, min(w - 8, 90))) if s.kind == "preset" else []
    # sheet height: header(1) name(2) file(1) desc band(1) desc(n) diff band(1) diff rows + hint
    want = 1 + 2 + 1 + 1 + max(1, len(desc_lines)) + 1 + min(len(diff), 8) + 2 + 1
    if s.kind != "preset":
        want = 1 + 2 + 1 + 2
    sh = min(h - 5, max(8, want))
    y0 = h - 3 - sh
    x0 = 0
    sw = w
    # dim the bench (25% per spec; a touch more for legibility)
    cv.dim_rect(0, 0, w, y0, 0.35)
    cv.fill(x0, y0, sw, sh, " ", bg=fam.ground)
    title = "SAVE TUBE" if s.kind == "preset" else "SAVE PROFILE"
    W.band(cv, x0, y0, sw, title, "sheet · %d rows" % sh, fam, tick, motion)
    y = y0 + 1
    hot = C.crt_safe(fam.hot)
    # NAME field
    cv.put(x0 + 2, y, "NAME", fg=fam.dim, bg=None, at=BOLD)
    fx = x0 + 15
    fw = min(sw - fx - 2, 60)
    focused = s.focus == "name"
    field_bg = C.darken(hot, 0.65) if focused else fam.ground2
    cv.put(fx, y, "▐", fg=hot if focused else fam.dim, bg=None)
    cv.fill(fx + 1, y, fw - 2, 1, " ", bg=field_bg)
    txt = s.name
    cv.put(fx + 1, y, txt[: fw - 2], fg=fam.glow if focused else fam.ink, bg=field_bg, at=BOLD)
    cv.put(fx + fw - 1, y, "▌", fg=hot if focused else fam.dim, bg=None)
    if focused:
        cv.cursor = (fx + 1 + min(s.cursor, fw - 3), y)
    y += 1
    cv.put(fx, y, "auto-named from the inherited tube + $USER · ^U clears" if s.kind == "preset" else "profile = full-state snapshot · restores with L", fg=fam.dim, bg=None)
    y += 1
    cv.put(x0 + 2, y, "FILE", fg=fam.dim, bg=None, at=BOLD)
    sub = "presets" if s.kind == "preset" else "profiles"
    cv.put(fx, y, "%s/%s.json" % (sub, s.slug), fg=fam.ink, bg=None)
    y += 1
    if s.kind == "preset":
        W.section_band(cv, x0, y, sw, "DESCRIPTION", "auto-written from the diff · editable · ^R rewrites", hot, fam, tick, motion)
        y += 1
        dfocus = s.focus == "description"
        shown = desc_lines or [""]
        # cursor position within wrapped text
        cur_line, cur_col = 0, 0
        if dfocus:
            acc = 0
            for i, ln in enumerate(shown):
                if s.desc_cursor <= acc + len(ln):
                    cur_line, cur_col = i, s.desc_cursor - acc
                    break
                acc += len(ln) + 1
            else:
                cur_line, cur_col = len(shown) - 1, len(shown[-1])
        max_desc = max(1, min(len(shown), sh - 9))
        for i, ln in enumerate(shown[:max_desc]):
            cv.put(x0 + 2, y, ln, fg=fam.glow if dfocus else fam.ink, bg=C.darken(hot, 0.8) if dfocus else None)
            if dfocus and i == cur_line:
                cv.cursor = (x0 + 2 + min(cur_col, len(ln)), y)
            y += 1
        # DIFF
        inh = m.ctl.active_preset or "defaults"
        W.section_band(cv, x0, y, sw, "DIFF vs %s" % inh, "%d changed · ↵/^D drops a line · ^Z restores" % len(diff), hot, fam, tick, motion)
        y += 1
        rows_avail = max(0, (y0 + sh) - y - 2)
        dfocus2 = s.focus == "diff"
        top = 0
        if len(diff) > rows_avail:
            top = max(0, min(s.diff_sel - rows_avail // 2, len(diff) - rows_avail))
        for i in range(rows_avail):
            idx = top + i
            if idx >= len(diff):
                break
            key, lab, old, new, spec = diff[idx]
            sel = dfocus2 and idx == s.diff_sel
            if sel:
                cv.fill(x0, y, sw, 1, " ", bg=fam.ground2)
                cv.put(x0, y, "▐", fg=hot, bg=None)
                cv.put(x0 + 1, y, "▶", fg=fam.glow, bg=fam.ground2)
            cv.put(x0 + 2, y, lab[:14].ljust(14), fg=fam.ink, bg=None, at=BOLD if sel else 0)
            lo, hi = spec.get("min"), spec.get("max")
            mx = x0 + 17
            if lo is not None and hi is not None and hi != lo and spec.get("type") in ("float", "int"):
                try:
                    t = (float(new) - float(lo)) / (float(hi) - float(lo))
                except (TypeError, ValueError):
                    t = 0.0
                W.meter(cv, mx, y, 20, max(0.0, min(1.0, t)), fam, m.group_rgb(spec.get("group", "video")), peg=t > 1.0)
            newv = m.cm.display_value(spec, new)
            oldv = m.cm.display_value(spec, old)
            cv.put(mx + 22, y, newv.rjust(8), fg=fam.glow if sel else fam.ink, bg=None, at=BOLD)
            cv.put(mx + 32, y, "◂ %s" % oldv, fg=fam.dim, bg=None)
            y += 1
        if len(diff) > rows_avail and rows_avail > 0:
            cv.put(x0 + 2, y, "+ %d more changed · ↑↓ scrolls the diff" % (len(diff) - rows_avail), fg=fam.dim, bg=None)
            y += 1
        if not diff:
            cv.put(x0 + 2, y, "no settings differ from %s — saving writes an empty override set" % inh, fg=fam.dim, bg=None)
            y += 1
    # footer line inside the sheet
    fy = y0 + sh - 1
    cv.put(x0 + 2, fy, "saving writes only these overrides — defaults are never stored" if s.kind == "preset" else "a profile stores every non-default value + the active preset + terminal overrides", fg=fam.dim, bg=None)
    # hints override for the sheet
    hints = [("Tab", "field"), ("↵", "save" if s.focus != "diff" else "drop line"), ("Esc", "cancel")]
    if s.kind == "preset":
        hints += [("^R", "rewrite"), ("^D", "drop line"), ("^Z", "restore lines")]
    W.hint_band(cv, 0, h - 1, w, hints, fam, tick, motion)
    B.bevel_frame(cv, x0, y0 - 1, sw, sh + 2, fam, hue_t=(tick * 0.002) % 1.0 if motion else 0.3)
    # the frame's top lip overwrote the band's row-1? no: bevel at y0-1; redraw band on top
    W.band(cv, x0, y0, sw, title, "sheet · %d rows" % sh, fam, tick, motion)

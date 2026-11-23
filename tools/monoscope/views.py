"""monoscope.views — render(model, canvas, tick): the whole frame, every tick.

One pure function per mode; every cell of the canvas is written (the canvas
is cleared to the family ground first, so a blank is a known colour).
Layout ladder (MONOSCOPE §3.2):

    w < 100          group bar on top, single bench column, detail band below
    100 <= w < 150   RAIL(20) ▐ BENCH ▐ (detail band below the bench)
    w >= 150         RAIL(20) ▐ BENCH ▐ SCOPE(56)

Header ladder (rows): >= 40 rows → TDF banner (7 rows) above the band;
>= 30 rows → 5-row banner; else band only.
"""

from __future__ import annotations

import math
import os

from .canvas import BOLD, DIM
from . import color as C
from . import widgets as W
from . import blocks as B
from .banners import banner_rows, banner_height, BANNER_LADDER

__all__ = ["render", "layout_for", "Layout"]

RAIL_W = 20
SCOPE_W = 56


class Layout:
    __slots__ = ("w", "h", "header_h", "banner", "rail", "bench", "scope", "detail", "status_y", "hint_y", "group_bar_y", "bench_top")

    def __init__(self):
        pass


def layout_for(w, h, motion="full"):
    L = Layout()
    L.w, L.h = w, h
    # bottom: status + hint
    L.hint_y = h - 1
    L.status_y = h - 2
    # header
    L.banner = None
    y = 0
    if h >= 44 and w >= 100:
        L.banner = "big"
    elif h >= 34 and w >= 80:
        L.banner = "mid"
    elif h >= 28:
        L.banner = "small"
    L.header_h = (banner_height(L.banner) + 1) if L.banner else 0
    y += L.header_h
    # band row
    band_y = y
    y += 1
    L.group_bar_y = None
    if w < 100:
        L.group_bar_y = y
        y += 2
    L.bench_top = y
    body_h = L.status_y - y
    if w >= 150:
        L.rail = (0, y, RAIL_W, body_h)
        L.scope = (w - SCOPE_W, y, SCOPE_W, body_h)
        L.bench = (RAIL_W + 1, y, w - RAIL_W - 1 - SCOPE_W - 1, body_h)
        L.detail = None
    elif w >= 100:
        L.rail = (0, y, RAIL_W, body_h)
        L.scope = None
        dh = max(5, min(9, body_h // 3))
        L.bench = (RAIL_W + 1, y, w - RAIL_W - 1, body_h - dh)
        L.detail = (RAIL_W + 1, y + body_h - dh, w - RAIL_W - 1, dh)
    else:
        L.rail = None
        L.scope = None
        dh = max(4, min(7, body_h // 3))
        L.bench = (0, y, w, body_h - dh)
        L.detail = (0, y + body_h - dh, w, dh)
    L.header_h = band_y
    return L


# ---------------------------------------------------------------------------
# frame
# ---------------------------------------------------------------------------

def apply_ground_wave(m, cv, tick):
    """Breathe the panel ground — the last thing that touches the frame.

    Run as a post-pass rather than by tinting `cv.clear`, because everything
    drawn after the clear (bands, rails, chips, meters) sets its own explicit
    background and would paint the wave straight back out again.

    Only the two family grounds are moved. Every deliberate colour on the
    panel — a lit meter, a group chip, a selected row, a warning — is left
    exactly as the widget set it. The ground breathes; the instruments do
    not.
    """
    if m.motion == "off" or not getattr(m, "ground_wave", True):
        return
    fam = m.fam
    g, g2 = fam.ground, fam.ground2
    bg = cv.bg
    w, h = cv.w, cv.h
    hues = bool(fam.hues)
    for y in range(h):
        b = y * w
        row = bg[b:b + w]
        # Cheap gate: most rows of a busy panel are still mostly ground, but
        # a row with none of it costs one membership test instead of a walk.
        if g not in row and g2 not in row:
            continue
        sub = {g: C.bg_wave(g, y, h, tick, m.motion, hues),
               g2: C.bg_wave(g2, y, h, tick, m.motion, hues)}
        bg[b:b + w] = [sub.get(c, c) for c in row]


def render(m, cv, tick):
    fam = m.fam
    motion = m.motion != "off"
    cv.clear(bg=None, fg=fam.ink)
    if m.mode == "flatfield":
        _render_flatfield(m, cv, tick)
        return                      # the flat field is a diagnostic: no wave
    if m.mode == "splash":
        from .splashview import render_splash
        render_splash(m, cv, tick)
        apply_ground_wave(m, cv, tick)
        return
    if m.mode == "help":
        _render_help(m, cv, tick)
        apply_ground_wave(m, cv, tick)
        return
    if m.mode == "bank":
        from .bankview import render_bank
        render_bank(m, cv, tick)
        apply_ground_wave(m, cv, tick)
        return
    L = layout_for(cv.w, cv.h, m.motion)
    _render_header(m, cv, tick, L)
    _render_bench(m, cv, tick, L)
    if L.rail:
        _render_rail(m, cv, tick, L)
    if L.scope:
        _render_scope(m, cv, tick, L)
    elif L.detail:
        _render_detail(m, cv, tick, L)
    _render_status(m, cv, tick, L)
    _render_hints(m, cv, tick, L)
    if m.mode == "sheet" and m.sheet is not None:
        from .sheetview import render_sheet
        render_sheet(m, cv, tick, L)
    if m.mode == "confirm" and m.confirm is not None:
        _render_confirm(m, cv, tick, L)
    _render_toasts(m, cv, tick, L)
    apply_ground_wave(m, cv, tick)


def _tube_title(m):
    name = m.ctl.active_preset or "(defaults)"
    return name


def _render_header(m, cv, tick, L):
    fam = m.fam
    motion = m.motion != "off"
    w = cv.w
    y = 0
    if L.banner:
        y += W.banner_block(cv, w, 0, L.banner, "MONOSCOPE", fam, tick, motion, full=(m.motion == "full"))
    # the band
    right = "%s · %s" % (m.dest, "MONOSCOPE") if w >= 120 else ""
    tube = _tube_title(m)
    modn = sum(m.modified_counts().values())
    title = "MONOSCOPE" if L.banner is None else tube.upper()
    if L.banner is None:
        right = tube.upper() + (" ✱%d" % modn if modn else "")
    else:
        right = ("✱%d modified" % modn) if modn else "aligned to tube"
    W.band(cv, 0, L.header_h, w, title, right, fam, tick, motion)
    if L.group_bar_y is not None:
        cur = m.selected_row()
        gid = cur.gid if cur else m.group_ids[0]
        active = m.group_ids.index(gid) if gid in m.group_ids else 0
        W.group_bar(cv, 0, L.group_bar_y, w, m.group_ids, active, C.GROUP_HUES, fam, tick, motion,
                    modified=m.modified_counts())
        seg = w / max(1, len(m.group_ids))
        for i, gid in enumerate(m.group_ids):
            m.hit_add(int(i * seg), int((i + 1) * seg), L.group_bar_y, "group", gid)
            m.hit_add(int(i * seg), int((i + 1) * seg), L.group_bar_y + 1, "group", gid)


def _row_dict(m, r):
    """Build the strip data dict for a bench row."""
    ctl = m.ctl
    spec = r.spec
    d = {"kind": r.kind, "label": r.label, "unit": spec.get("unit", "") or ""}
    if r.kind == "rotary":
        v = ctl.values.get(r.key)
        t = m.value_t(r.key)
        d["t"] = min(1.0, t) if t is not None else 0.0
        d["peg"] = t is not None and t > 1.0 + 1e-9
        d["over"] = t is not None and (t > 1.0 + 1e-9 or t < -1e-9)
        d["value_text"] = m.cm.display_value(spec, v)
        d["modified"] = m.row_modified(r)
    elif r.kind == "switch":
        d["on"] = bool(ctl.values.get(r.key))
        d["modified"] = m.row_modified(r)
    elif r.kind == "selector":
        members = list((spec.get("values") or {}).keys())
        cur = ctl.values.get(r.key)
        d["members"] = members
        d["current"] = cur
        d["index_text"] = "%d/%d" % ((members.index(cur) + 1) if cur in members else 0, len(members))
        d["modified"] = m.row_modified(r)
    elif r.kind == "button":
        on = bool(ctl.values.get("power_on"))
        d["button_label"] = "POWER"
        d["value_text"] = "ON" if on else "OFF"
        d["fired"] = _fired(m, r.key)
    elif r.kind == "action":
        d["button_label"] = r.label
        d["fired"] = _fired(m, r.key)
    elif r.kind == "swapstyle":
        d["kind"] = "selector"
        d["members"] = list(m.cm.SWAP_STYLES) if hasattr(m.cm, "SWAP_STYLES") else ["carry", "degauss", "fresh"]
        d["current"] = getattr(ctl, "swap_style", "carry")
        d["index_text"] = ""
    elif r.kind == "terminal":
        val = ctl.terminal.get(r.key)
        if r.key == "font-size":
            d["kind"] = "rotary"
            lo, hi = 6.0, 40.0
            if val is None:
                d["t"] = 0.0
                d["value_text"] = "default"
            else:
                d["t"] = (float(val) - lo) / (hi - lo)
                d["value_text"] = "%g" % float(val)
            d["unit"] = "pt" if val is not None else ""
        else:
            d["kind"] = "text"
            d["value_text"] = val or "default"
    return d


def _fired(m, key):
    t = m.fired.get(key)
    if t is None:
        return 0.0
    dt = m.now() - t
    if dt > 0.35:
        return 0.0
    return 1.0 - dt / 0.35


def _render_bench(m, cv, tick, L):
    fam = m.fam
    motion = m.motion == "full"      # section-band hot spots + breathing are full-motion life
    x, y, w, h = L.bench
    vis = m.visible_rows()
    if not vis:
        cv.put(x + 2, y + 1, "no rows match /%s" % m.filter, fg=fam.dim, bg=None)
        return
    # ensure selection visible: compute position of sel in vis
    pos = 0
    for i, (k, r) in enumerate(vis):
        if k == m.sel:
            pos = i
            break
    if pos < m.scroll + 1:
        m.scroll = max(0, pos - 1)
    if pos >= m.scroll + h - 1:
        m.scroll = pos - h + 2
    m.scroll = max(0, min(m.scroll, max(0, len(vis) - h)))
    base = m.baseline()
    inherit_names = m.ctl.active_preset or "defaults"
    counts = {}
    for k, r in vis:
        if r.kind != "header":
            counts[r.gid] = counts.get(r.gid, 0) + 1
    modc = m.modified_counts()
    yy = y
    # sticky header: if first visible row is not a header, paint the group's band on the first row
    first_k, first_r = vis[m.scroll]
    if first_r.kind != "header":
        gid = first_r.gid
        W.section_band(cv, x, yy, w, gid.upper(), m.ctl.groups.get(gid, ""), m.group_rgb(gid), fam, tick, motion,
                       badges="%d knobs%s" % (counts.get(gid, 0), " · ✱%d" % modc[gid] if modc.get(gid) else ""))
        yy += 1
        start = m.scroll
    else:
        start = m.scroll
    for i in range(start, len(vis)):
        if yy >= y + h:
            break
        k, r = vis[i]
        r.y = yy
        if r.kind == "header":
            gid = r.gid
            W.section_band(cv, x, yy, w, gid.upper(), m.ctl.groups.get(gid, ""), m.group_rgb(gid), fam, tick, motion,
                           badges="%d knobs%s" % (counts.get(gid, 0), " · ✱%d" % modc[gid] if modc.get(gid) else ""))
        else:
            d = _row_dict(m, r)
            hue = m.group_rgb(r.gid)
            selected = (k == m.sel)
            entry = m.entry if (selected and m.mode == "entry") else None
            delta = ""
            badge = ""
            if r.kind == "rotary" and r.key in base:
                bv = base.get(r.key)
                if m.ctl.values.get(r.key) != bv:
                    delta = "◂ %s" % m.cm.display_value(r.spec, bv)
                    t = m.value_t(r.key)
                    if t is not None:
                        lo, hi = r.spec.get("min"), r.spec.get("max")
                        if lo is not None and hi is not None and hi != lo:
                            d["inherited_t"] = max(0.0, min(1.0, (float(bv) - float(lo)) / (float(hi) - float(lo))))
                if d.get("over"):
                    lo, hi = r.spec.get("min"), r.spec.get("max")
                    badge = "⚠ %s %s" % ("cap" if d.get("peg") else "floor", m.cm.display_value(r.spec, hi if d.get("peg") else lo))
            elif r.kind in ("switch", "selector") and r.key in base:
                bv = base.get(r.key)
                if m.ctl.values.get(r.key) != bv:
                    delta = "◂ %s" % m.cm.display_value(r.spec, bv)
            W.strip(cv, x, yy, w, d, fam, hue, tick, motion, selected=selected, entry=entry,
                    delta_text=delta, badge=badge)
            m.hit_add(x, x + w, yy, "row", k)
            m.meter_geo[k] = (x + 2 + W.STRIP_LABEL_W + 1, W.meter_width(w - (2 + W.STRIP_LABEL_W + 1) - (2 + W.STRIP_VALUE_W + W.STRIP_UNIT_W + 1)))
            if entry is not None and yy + 1 < y + h:
                _render_entry_ruler(m, cv, x, yy + 1, w, r, hue)
                yy += 1
        yy += 1
    # scroll thumb on the right edge of the bench when the list overflows
    if len(vis) > h:
        _thumb(cv, x + w - 1, y, h, m.scroll, len(vis), fam)


def _render_entry_ruler(m, cv, x, y, w, r, hue):
    fam = m.fam
    spec = r.spec
    lo, hi = spec.get("min"), spec.get("max")
    if lo is None or hi is None:
        return
    e = m.entry or {}
    marks = []
    dflt = m.ctl.defaults.get(r.key)
    base = m.baseline().get(r.key)
    span = float(hi) - float(lo)
    def tt(v):
        try:
            return (float(v) - float(lo)) / span
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
    if dflt is not None:
        marks.append((tt(dflt), "◇", fam.dim))
    if base is not None and base != dflt:
        marks.append((tt(base), "◂", fam.ink))
    pv = e.get("value")
    if pv is not None:
        marks.append((max(0.0, min(1.0, tt(pv))), "▲", fam.glow))
        marks.append((tt(pv), "now", None))
    W.ruler(cv, x + 2 + W.STRIP_LABEL_W + 1, y, min(w - 20, 60), m.cm.display_value(spec, lo), m.cm.display_value(spec, hi), marks, fam, hue)
    note = e.get("note", "")
    if note:
        cv.put(x + 2, y, note[: W.STRIP_LABEL_W], fg=fam.warn if e.get("over") else fam.dim, bg=None)


def _thumb(cv, x, y, h, scroll, total, fam):
    if total <= 0 or h <= 0:
        return
    th = max(1, int(h * h / total))
    ty = y + int((h - th) * scroll / max(1, total - h))
    for i in range(h):
        yy = y + i
        on = ty <= yy < ty + th
        cv.put(x, yy, "▐", fg=fam.hot if on else fam.dim, bg=None)


def _render_rail(m, cv, tick, L):
    fam = m.fam
    motion = m.motion != "off"
    x, y, w, h = L.rail
    cur = m.selected_row()
    cur_gid = cur.gid if cur else None
    modc = m.modified_counts()
    counts = {}
    for r in m.rows:
        if r.kind != "header":
            counts[r.gid] = counts.get(r.gid, 0) + 1
    # rail title
    cv.put(x + 2, y, "GROUPS", fg=fam.dim, bg=None, at=BOLD)
    yy = y + 2
    for i, gid in enumerate(m.group_ids):
        if yy >= y + h - 3:
            break
        hue = m.group_rgb(gid)
        active = (gid == cur_gid)
        focused = (m.focus == "rail" and i == m.rail_sel)
        if active:
            cv.put(x, yy, "▐", fg=hue, bg=None)
            cv.put(x + 1, yy, "▶", fg=fam.glow, bg=None)
        else:
            cv.put(x, yy, "  ", bg=None)
        name = gid.upper()[:9]
        cnt = "%2d" % counts.get(gid, 0)
        badge = ("✱%d" % modc[gid]) if modc.get(gid) else ""
        col = C.lighten(hue, 0.35) if active else (fam.ink if focused else C.lerp_rgb(fam.dim, hue, 0.5))
        cv.put(x + 2, yy, name.ljust(9), fg=col, bg=fam.ground2 if focused else fam.ground, at=BOLD if active else 0)
        cv.put(x + 11, yy, cnt, fg=fam.dim, bg=fam.ground2 if focused else fam.ground)
        if badge:
            cv.put(x + 14, yy, badge, fg=fam.warn, bg=fam.ground2 if focused else fam.ground)
        # a short chip in the group hue under the name? keep it minimal: a 1-cell chip
        cv.put(x + w - 3, yy, ("██" if active else "▄▄"), fg=hue if active else C.darken(hue, 0.5), bg=None)
        m.hit_add(x, x + w, yy, "group", gid)
        yy += 1
    # legend
    ly = y + h - 2
    if ly > yy:
        cv.put(x + 2, ly, "✱ = differs", fg=fam.dim, bg=None)
        cv.put(x + 4, ly + 1, "from tube", fg=fam.dim, bg=None)
    # rail separator: half-block column
    for i in range(h):
        cv.put(x + w, y + i, "▐", fg=C.darken(fam.hot, 0.6), bg=None)


def _detail_lines(m, r, width):
    """Identity + prose lines for the focused row (pure)."""
    ctl = m.ctl
    spec = r.spec
    lines = []
    if r.kind in ("rotary", "switch", "selector"):
        head = "%s · %s · %s · %s" % (r.label, r.key, spec.get("define", ""), spec.get("type", ""))
    elif r.kind == "button":
        head = "%s · %s · %s" % (r.label, r.key, spec.get("define", ""))
    else:
        head = "%s · %s" % (r.label, r.key)
    lines.append(("head", head))
    body = spec.get("help") or spec.get("desc") or ""
    for ln in W.wrap_text(body, width):
        lines.append(("body", ln))
    return lines


def _render_detail(m, cv, tick, L):
    """Narrow layouts: the detail band under the bench."""
    fam = m.fam
    motion = m.motion != "off"
    x, y, w, h = L.detail
    r = m.selected_row()
    if r is None:
        return
    hue = m.group_rgb(r.gid)
    W.section_band(cv, x, y, w, r.label, "%s · %s · %s" % (r.key, r.spec.get("define", ""), r.spec.get("type", "")) if r.spec.get("define") else r.key, hue, fam, tick, motion)
    body = r.spec.get("help") or r.spec.get("desc") or ""
    lines = W.wrap_text(body, w - 4)
    avail = h - 1
    # reserve one row for the range strip + one for default/inherited/now when a rotary
    reserve = 2 if r.kind == "rotary" else 0
    for i, ln in enumerate(lines[: max(0, avail - reserve)]):
        cv.put(x + 2, y + 1 + i, ln, fg=fam.ink, bg=None)
    if r.kind == "rotary" and avail >= 2:
        yy = y + h - 2
        _range_and_values(m, cv, x + 2, yy, w - 4, r, hue)


def _range_and_values(m, cv, x, y, w, r, hue):
    fam = m.fam
    spec = r.spec
    lo, hi = spec.get("min"), spec.get("max")
    dflt = m.ctl.defaults.get(r.key)
    base = m.baseline().get(r.key)
    now = m.ctl.values.get(r.key)
    if lo is not None and hi is not None and hi != lo:
        span = float(hi) - float(lo)
        def tt(v):
            try:
                return (float(v) - float(lo)) / span
            except (TypeError, ValueError):
                return 0.0
        marks = [(max(0.0, min(1.0, tt(now))), "now", None)]
        if dflt is not None:
            marks.append((max(0.0, min(1.0, tt(dflt))), "◇", fam.dim))
        if base is not None and base != dflt:
            marks.append((max(0.0, min(1.0, tt(base))), "◂", fam.ink))
        marks.append((max(0.0, min(1.0, tt(now))), "▲", fam.glow))
        W.ruler(cv, x, y, min(w, 64), m.cm.display_value(spec, lo), m.cm.display_value(spec, hi), marks, fam, hue)
        step = spec.get("step")
        if step is not None and w > 70:
            cv.put(x + min(w, 64) + 2, y, "step %s" % m.cm.display_value(spec, step), fg=fam.dim, bg=None)
    dv = m.cm.display_value
    parts = [("default", dv(spec, dflt))]
    if base is not None:
        parts.append(("inherited", dv(spec, base)))
    parts.append(("now", dv(spec, now)))
    cx = x
    for i, (k, v) in enumerate(parts):
        cv.put(cx, y + 1, k, fg=fam.dim, bg=None)
        cx += len(k) + 1
        cv.put(cx, y + 1, v, fg=fam.ink, bg=None, at=BOLD if k == "now" else 0)
        cx += len(v) + 3
    if base is not None:
        if now == base:
            cv.put(cx, y + 1, "═ matches tube", fg=fam.ok, bg=None)
        else:
            cv.put(cx, y + 1, "✱ differs from tube", fg=fam.warn, bg=None)


def _render_scope(m, cv, tick, L):
    """Wide layout: SCOPE pane — identity, prose, range strip, default/
    inherited/now, SAME KNOB OTHER TUBES, TUBE block, PENDING block."""
    fam = m.fam
    motion = m.motion != "off"
    x, y, w, h = L.scope
    # separator
    for i in range(h):
        cv.put(x - 1, y + i, "▐", fg=C.darken(fam.hot, 0.6), bg=None)
    r = m.selected_row()
    if r is None:
        return
    hue = m.group_rgb(r.gid)
    yy = y
    W.section_band(cv, x, yy, w, "SCOPE", "", hue, fam, tick, motion)
    yy += 1
    cv.put(x + 1, yy, r.label, fg=C.lighten(hue, 0.3), bg=None, at=BOLD)
    yy += 1
    ident = "%s → %s · %s" % (r.key, r.spec.get("define", "—"), r.spec.get("type", ""))
    if r.spec.get("step") is not None:
        ident += " · step %s" % m.cm.display_value(r.spec, r.spec.get("step"))
    cv.put(x + 1, yy, ident[: w - 2], fg=fam.dim, bg=None)
    yy += 2
    body = r.spec.get("help") or r.spec.get("desc") or ""
    lines = W.wrap_text(body, w - 2)
    max_prose = max(3, min(len(lines), h - 18))
    for ln in lines[:max_prose]:
        cv.put(x + 1, yy, ln, fg=fam.ink, bg=None)
        yy += 1
    if len(lines) > max_prose:
        cv.put(x + 1, yy - 1, lines[max_prose - 1][: w - 4] + " …", fg=fam.ink, bg=None)
    yy += 1
    if r.kind == "rotary" and yy + 2 < y + h:
        _range_and_values(m, cv, x + 1, yy, w - 2, r, hue)
        yy += 3
    # SAME KNOB, OTHER TUBES
    if r.kind in ("rotary",) and yy + 4 < y + h:
        W.section_band(cv, x, yy, w, "SAME KNOB, OTHER TUBES", "", hue, fam, tick, motion)
        yy += 1
        idx = m.preset_index if m.preset_index is not None else m.build_preset_index()
        entries = idx.get(r.key, [])
        spec = r.spec
        lo, hi = spec.get("min"), spec.get("max")
        now = m.ctl.values.get(r.key)
        active = m.ctl.active_preset
        if entries and lo is not None and hi is not None:
            # pick up to N entries around the current value: sorted by value
            n = max(0, min(7, y + h - yy - 8))
            vals = entries
            # find position nearest to now
            try:
                nowf = float(now)
                pos = min(range(len(vals)), key=lambda i: abs(float(vals[i][0]) - nowf))
            except (TypeError, ValueError):
                pos = 0
            lo_i = max(0, pos - n // 2)
            hi_i = min(len(vals), lo_i + n)
            lo_i = max(0, hi_i - n)
            for v, name in vals[lo_i:hi_i]:
                try:
                    t = (float(v) - float(lo)) / (float(hi) - float(lo))
                except (TypeError, ValueError, ZeroDivisionError):
                    t = 0.0
                vs = m.cm.display_value(spec, v).rjust(6)
                here = (name == active)
                cv.put(x + 1, yy, vs, fg=fam.glow if here else fam.ink, bg=None, at=BOLD if here else 0)
                cv.put(x + 8, yy, name[: w - 26].ljust(w - 26), fg=fam.ink if here else fam.dim, bg=None)
                mx = x + w - 17
                W.meter(cv, mx, yy, 13, max(0.0, min(1.0, t)), fam, hue, lit=1.0 if here else 0.55, peg=t > 1.0)
                if here:
                    cv.put(mx + 14, yy, "◂", fg=fam.glow, bg=None)
                yy += 1
        else:
            cv.put(x + 1, yy, "no preset in the bank sets this knob", fg=fam.dim, bg=None)
            yy += 1
        yy += 1
    # TUBE block
    if yy + 4 < y + h:
        W.section_band(cv, x, yy, w, "TUBE", m.ctl.active_preset or "defaults", hue, fam, tick, motion)
        yy += 1
        v = m.ctl.values
        dv = lambda k: m.cm.display_value(m.ctl.params[k], v.get(k)) if k in m.ctl.params else "—"
        pairs = [("PHOSPHOR", dv("phosphor")), ("MASK", "%s @ %s" % (dv("mask_type"), dv("mask_triads"))),
                 ("RASTER", "%s lines" % dv("scan_lines")), ("GEOMETRY", dv("geom_mode")),
                 ("ERA", dv("era")), ("PERSIST", dv("persistence")),
                 ("SWAP STYLE", getattr(m.ctl, "swap_style", "carry")), ("POWER", "ON" if v.get("power_on") else "OFF")]
        col_w = (w - 2) // 2
        for i in range(0, len(pairs), 2):
            if yy >= y + h - 3:
                break
            for j in range(2):
                if i + j < len(pairs):
                    k, val = pairs[i + j]
                    cx = x + 1 + j * col_w
                    cv.put(cx, yy, k.ljust(11), fg=fam.dim, bg=None)
                    cv.put(cx + 11, yy, str(val)[: col_w - 12], fg=fam.ink, bg=None)
            yy += 1
        yy += 1
    # PENDING block
    if yy + 2 < y + h:
        W.section_band(cv, x, yy, w, "RELOAD", "", hue, fam, tick, motion)
        yy += 1
        if m.reload_pending():
            left = max(0.0, m.reload_deadline - m.now())
            cv.put(x + 1, yy, "shaders regenerated · reload in %.2f s" % left, fg=fam.warn, bg=None)
        elif m.last_reload:
            ok, detail, ts = m.last_reload
            txt = ("OK %s" % ts) if ok else ("NO CARRIER %s — %s" % (ts, detail))
            cv.put(x + 1, yy, txt[: w - 2], fg=fam.ok if ok else fam.bad, bg=None)
        else:
            cv.put(x + 1, yy, ("no reload sent yet · %s" % m.dest)[: w - 2], fg=fam.dim, bg=None)
        yy += 1


def _render_status(m, cv, tick, L):
    fam = m.fam
    motion = m.motion != "off"
    segs = [("MONOSCOPE", "title")]
    tube = m.ctl.active_preset or "(defaults)"
    modn = sum(m.modified_counts().values())
    segs.append(("%s%s" % (tube.upper(), " ✱%d" % modn if modn else ""), "info"))
    if m.reload_pending():
        segs.append(("◉ ARMED", "armed"))
    elif m.last_reload:
        ok, detail, ts = m.last_reload
        segs.append((("RELOAD OK %s" % ts) if ok else ("NO CARRIER %s" % ts), "ok" if ok else "bad"))
    else:
        segs.append(("RELOAD —", "info"))
    if not m.mouse_on:
        segs.append(("MOUSE OFF", "info"))
    if cv.w >= 100:
        segs.append((m.dest, "info"))
    r = m.selected_row()
    if r is not None and cv.w >= 120:
        segs.append(("%s" % r.gid.upper(), "info"))
    if m.filter:
        segs.append(("/%s" % m.filter, "warn"))
    if m.modified_only:
        segs.append(("✱ ONLY", "warn"))
    if m.motion != "full":
        segs.append(("MOTION %s" % m.motion.upper(), "info"))
    W.status_band(cv, 0, L.status_y, cv.w, segs, fam, tick, motion)


def hints_for(m):
    r = m.selected_row()
    if m.mode == "entry":
        return [("0-9.-", "digits"), ("↵", "commit"), ("Esc", "cancel"), ("⌫", "delete"), ("^U", "clear")]
    if m.mode == "confirm":
        return [("↵", m.confirm.get("yes", "yes") if m.confirm else "yes"), ("Esc", m.confirm.get("no", "no") if m.confirm else "no")]
    if m.filter_active:
        return [("type", "to filter"), ("↵", "keep"), ("Esc", "clear")]
    if m.focus == "rail":
        return [("↑↓", "group"), ("↵ →", "into bench"), ("Tab", "focus"), ("1-9", "group"), ("q", "quit")]
    base = [("←→", "level"), ("<>", "×5")]
    if r is not None:
        if r.kind == "rotary" or (r.kind == "terminal" and r.key == "font-size"):
            base.append(("↵", "type value"))
        elif r.kind in ("switch",):
            base.append(("↵", "toggle"))
        elif r.kind in ("selector", "swapstyle"):
            base.append(("↵", "cycle"))
        elif r.kind in ("button", "action"):
            base.append(("↵", "fire"))
        elif r.kind == "terminal":
            base.append(("↵", "type"))
    base += [("0", "default"), ("⌫", "revert to tube"), ("/", "find"), ("*", "modified"),
             ("1-9", "group"), ("p", "tubes"), ("P", "save tube"), ("S/L", "profiles"),
             ("u", "undo"), ("E", "erase"), ("m", "motion"), ("?", "help"), ("q", "quit")]
    return base


def _render_hints(m, cv, tick, L):
    fam = m.fam
    W.hint_band(cv, 0, L.hint_y, cv.w, hints_for(m), fam, tick, m.motion != "off")


def _render_toasts(m, cv, tick, L):
    fam = m.fam
    msgs = m.live_messages()
    if not msgs:
        return
    # stack above the status band, right-aligned
    y = L.status_y - 1
    for text, kind, _exp in reversed(msgs[-3:]):
        col = {"ok": fam.ok, "warn": fam.warn, "bad": fam.bad}.get(kind, fam.ink)
        t = " %s " % text
        x = max(0, cv.w - len(t) - 1)
        cv.put(x, y, t, fg=C.darken(col, 0.8), bg=col, at=BOLD)
        cv.put(x - 1, y, "▐", fg=col, bg=None)
        y -= 1
        if y < 0:
            break


def _render_confirm(m, cv, tick, L):
    """A sheet-style confirm centred on the bench: dim backdrop, band, lines."""
    fam = m.fam
    c = m.confirm
    lines = c.get("lines", [])
    w = min(cv.w - 4, max(44, max((len(l) for l in lines), default=0) + 6))
    h = len(lines) + 4
    x = (cv.w - w) // 2
    y = max(1, (cv.h - h) // 2)
    cv.dim_rect(0, 0, cv.w, cv.h, 0.45)
    cv.fill(x, y, w, h, " ", bg=fam.ground)
    W.band(cv, x, y, w, c.get("title", "CONFIRM"), "", fam, tick, m.motion != "off")
    for i, ln in enumerate(lines):
        cv.put(x + 3, y + 2 + i, ln[: w - 6], fg=fam.warn if i == 0 else fam.ink, bg=None)
    yes, no = c.get("yes", "yes"), c.get("no", "no")
    hint = "↵ %s   Esc %s" % (yes, no)
    cv.put(x + 3, y + h - 1, hint, fg=fam.hot, bg=None, at=BOLD)
    B.bevel_frame(cv, x - 1, y - 1, w + 2, h + 2, fam, hue_t=(tick * 0.002) % 1.0)


def _render_flatfield(m, cv, tick):
    """§8.4 diagnostic: one flat colour across every cell, cycling slowly."""
    levels = [(20, 20, 20), (110, 110, 110), (220, 220, 220)]
    lv = levels[(tick // 40) % 3]
    cv.clear(bg=lv, fg=lv)
    cv.put(2, cv.h - 1, "FLAT FIELD %d/3 · q quit · space next" % ((tick // 40) % 3 + 1), fg=(255, 255, 255) if lv[0] < 128 else (0, 0, 0), bg=lv)


def _render_help(m, cv, tick):
    from .helpview import render_help
    render_help(m, cv, tick)

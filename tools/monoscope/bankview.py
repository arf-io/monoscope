"""monoscope.bankview — the TUBE BANK / PROFILE BANK screen.

Full-screen takeover (no floating box over an animated ground). Band with
count + sort, column header, the list with name / year / family / signature,
a detail band at the bottom (or a detail card at the right when wide).
"""

from __future__ import annotations

from .canvas import BOLD
from . import color as C
from . import widgets as W
from . import blocks as B
from .banners import banner_rows
from .bankstate import signature_values

__all__ = ["render_bank"]


def render_bank(m, cv, tick):
    fam = m.fam
    motion = m.motion != "off"
    b = m.bank
    w, h = cv.w, cv.h
    is_presets = b.source == "presets"
    title = "TUBE BANK" if is_presets else "PROFILE BANK"
    y = 0
    # banner ladder (smaller than the bench: keep rows for the list)
    kind = None
    if h >= 40 and w >= 90:
        kind = "mid"
    elif h >= 30:
        kind = "small"
    if kind:
        y += W.banner_block(cv, w, 0, kind, title, fam, tick, motion)
    n = len(b.entries)
    right = "%d %s · SORT %s" % (n, "TUBES" if is_presets else "PROFILES", b.sort.upper()) if is_presets else "%d PROFILES" % n
    if b.filter:
        right = "/%s · " % b.filter + right
    W.band(cv, 0, y, w, title if not kind else (m.ctl.active_preset or "defaults").upper(), right, fam, tick, motion)
    y += 1
    # column header
    wide = w >= 150
    list_w = (w - 62) if wide else w
    name_w = max(18, min(30, list_w - 34))
    hdr = "  %-*s %4s  %-14s  %s" % (name_w, "name", "YEAR" if b.sort == "year" else "year", "family", "signature")
    cv.put(0, y, hdr[:list_w], fg=fam.dim, bg=None)
    if is_presets:
        cv.put(min(list_w - 20, len(hdr) + 4), y, "s cycles the sort", fg=fam.dim, bg=None)
        m.hit_add(0, list_w, y, "banksort", None)
    y += 1
    cv.hline(0, y, list_w, "▀", fg=C.darken(fam.hot, 0.6), bg=None)
    y += 1
    # detail area
    if wide:
        list_h = h - y - 2
        det_x, det_y, det_w, det_h = list_w + 2, y - 2, w - list_w - 2, h - y
    else:
        det_h = max(5, min(9, (h - y) // 3))
        list_h = h - y - 2 - det_h
        det_x, det_y, det_w = 0, y + list_h, w
    list_h = max(1, list_h)
    # scroll: centered cursor (vim scrolloff-to-center)
    if n:
        top = m.cm.center_scroll(n, b.sel, list_h) if hasattr(m.cm, "center_scroll") else max(0, min(b.sel - list_h // 2, n - list_h))
    else:
        top = 0
    b.scroll = top
    params = m.ctl.params
    defaults = m.ctl.defaults
    hue = C.crt_safe(fam.hot)
    for i in range(list_h):
        idx = top + i
        yy = y + i
        if idx >= n:
            break
        e = b.entries[idx]
        selected = (idx == b.sel)
        active = (e["name"] == m.ctl.active_preset)
        if selected:
            cv.fill(0, yy, list_w, 1, " ", bg=fam.ground2)
            cv.put(0, yy, "▐", fg=hue, bg=None)
            cv.put(1, yy, "▶", fg=fam.glow, bg=fam.ground2, at=BOLD)
        meta = e.get("meta") or {}
        year = str(meta.get("year") or "")
        fam_s = str(meta.get("type") or ("profile" if not is_presets else ""))[:14]
        name = e["name"][:name_w]
        col = fam.glow if selected else (C.lighten(hue, 0.3) if active else fam.ink)
        cv.put(2, yy, name.ljust(name_w), fg=col, bg=None, at=BOLD if (selected or active) else 0)
        cv.put(3 + name_w, yy, year.rjust(4), fg=fam.dim if not selected else fam.ink, bg=None)
        cv.put(9 + name_w, yy, fam_s.ljust(14), fg=fam.dim if not selected else fam.ink, bg=None)
        # signature
        vals = dict(defaults)
        vals.update(e.get("params") or {})
        sig = signature_values(vals, params)
        sx = 25 + name_w
        W.signature(cv, sx, yy, sig, fam, hue_rgb=fam.hot)
        if active:
            cv.put(sx + 11, yy, "◂ loaded", fg=fam.dim, bg=None)
        m.hit_add(0, list_w, yy, "bankrow", idx)
    if n > list_h:
        _thumb(cv, list_w - 1, y, list_h, top, n, fam)
    if n == 0:
        cv.put(2, y + 1, "nothing matches /%s" % b.filter if b.filter else "the bank is empty", fg=fam.dim, bg=None)
    # detail
    e = b.current()
    if wide:
        for i in range(det_h):
            cv.put(det_x - 1, det_y + i, "▐", fg=C.darken(fam.hot, 0.6), bg=None)
    if e is not None:
        _detail(m, cv, det_x, det_y, det_w, det_h, e, tick, wide)
    # status + hints
    segs = [("MONOSCOPE", "title"), (title, "info")]
    if m.ctl.active_preset:
        segs.append(("LOADED %s" % m.ctl.active_preset.upper(), "info"))
    segs.append(("SWAP %s" % getattr(m.ctl, "swap_style", "carry").upper(), "info"))
    if m.reload_pending():
        segs.append(("◉ ARMED", "armed"))
    W.status_band(cv, 0, h - 2, w, segs, fam, tick, motion)
    if b.filter_active:
        hints = [("type", "to filter"), ("↵", "keep"), ("Esc", "clear")]
    else:
        hints = [("↑↓", "browse"), ("PgUp/Dn", "page"), ("↵", "apply" if is_presets else "load")]
        if is_presets:
            hints += [("s", "sort"), ("w", "swap style"), ("L", "profiles")]
        else:
            hints += [("p", "tubes")]
        hints += [("/", "find"), ("x", "delete"), ("Esc", "back")]
    W.hint_band(cv, 0, h - 1, w, hints, fam, tick, motion)


def _thumb(cv, x, y, h, scroll, total, fam):
    th = max(1, int(h * h / total))
    ty = y + int((h - th) * scroll / max(1, total - h))
    for i in range(h):
        yy = y + i
        on = ty <= yy < ty + th
        cv.put(x, yy, "▐", fg=fam.hot if on else fam.dim, bg=None)


def _detail(m, cv, x, y, w, h, e, tick, wide):
    fam = m.fam
    motion = m.motion != "off"
    hue = C.crt_safe(fam.hot)
    meta = e.get("meta") or {}
    bits = [str(meta.get("year") or ""), str(meta.get("manufacturer") or ""), str(meta.get("type") or "")]
    if meta.get("price_usd"):
        bits.append("$%s" % meta["price_usd"])
    bits = [b for b in bits if b]
    W.section_band(cv, x, y, w, e["name"], " · ".join(bits), hue, fam, tick, motion)
    yy = y + 1
    lines = []
    try:
        lines = m.cm.preset_detail_lines(e, m.ctl.params, m.ctl.defaults, w - 2, utf=True)
    except Exception:
        lines = [e["name"], e.get("description", "")]
    # preset_detail_lines returns: [name, meta line(s), "", description..., "", headline pairs..., "─ character ─", extras...]
    # the band already shows name + meta, so start after the first blank line
    body = lines[1:]
    if "" in body:
        body = body[body.index("") + 1:]
    for ln in body[: h - 1]:
        if ln.startswith("─") or ln.startswith("- "):
            W.section_band(cv, x, yy, w, "CHARACTER", "", hue, fam, tick, motion)
        else:
            cv.put(x + 1, yy, ln[: w - 2], fg=fam.ink, bg=None)
        yy += 1
        if yy >= y + h:
            break
    if wide and yy + 3 < y + h:
        # signature broken out
        vals = dict(m.ctl.defaults)
        vals.update(e.get("params") or {})
        sig = signature_values(vals, m.ctl.params)
        names = ["persist", "bandwidth", "pitch", "curve", "bloom", "halo", "snow", "wear"]
        yy += 1
        W.section_band(cv, x, yy, w, "SIGNATURE", "", hue, fam, tick, motion)
        yy += 1
        for i, (nm, v) in enumerate(zip(names, sig)):
            if yy >= y + h:
                break
            cv.put(x + 1, yy, nm.ljust(10), fg=fam.dim, bg=None)
            W.meter(cv, x + 12, yy, min(24, w - 14), v, fam, hue)
            yy += 1

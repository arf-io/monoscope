"""monoscope.model — the panel's state and its pure derivations.

The Model owns everything the renderer needs: the CrtCtl core (params,
values, presets), the flat list of bench rows, selection/scroll, the mode
(bench/entry/bank/profiles/sheet/help/confirm), the filter, undo history,
reload state, and the motion/palette settings. ``update()`` mutates it in
response to events; ``render()`` (in views.py) reads it.

Nothing here touches the terminal.
"""

from __future__ import annotations

import os
import time

from . import color as C

__all__ = ["Row", "Model", "SORT_MODES", "SWAP_STYLES", "MOTION_MODES"]

SORT_MODES = ("name", "year", "type", "manufacturer", "price", "resolution")
SWAP_STYLES = ("carry", "degauss", "fresh")
MOTION_MODES = ("full", "reduced", "off")

DEBOUNCE_S = 0.15
ACCEL_WINDOW_S = 0.15
ACCEL_AFTER = 10
ACCEL_MULT = 3
RESPONSE_S = 0.4          # response clock window after input
FIRE_FLASH_S = 0.35


class Row:
    """A bench row: a section header or a control."""

    __slots__ = ("kind", "key", "gid", "label", "spec", "y")

    def __init__(self, kind, key=None, gid=None, label="", spec=None):
        self.kind = kind      # 'header' | 'rotary' | 'switch' | 'selector' | 'button' | 'action' | 'swapstyle' | 'terminal'
        self.key = key
        self.gid = gid
        self.label = label
        self.spec = spec or {}
        self.y = -1

    @property
    def selectable(self):
        return self.kind != "header"


class Model:
    def __init__(self, ctl, dest, crtctl_mod, motion="full", now=None):
        self.ctl = ctl
        self.dest = dest
        self.cm = crtctl_mod              # the crtctl module (helpers, constants)
        self.motion = motion if motion in MOTION_MODES else "full"
        # The travelling ground wave (see views.apply_ground_wave). Follows
        # the motion mode; MONOSCOPE_GRADIENT=off turns it off on its own for
        # anyone who wants the panel's colour motion without the breath.
        self.ground_wave = os.environ.get("MONOSCOPE_GRADIENT", "1").lower() not in ("0", "off", "no")
        self.now = now or time.monotonic
        self.mode = "bench"               # bench|entry|bank|sheet|help|confirm|flatfield
        self.focus = "bench"              # bench|rail|scope
        self.rows = []
        self.sel = 0
        self.scroll = 0
        self.filter = ""
        self.filter_active = False        # typing into the filter
        self.modified_only = False
        self.messages = []                # toasts: (text, kind, expires)
        self.reload_deadline = None
        self.last_reload = None           # (ok, detail, hh:mm:ss)
        self.reload_count = 0
        self.last_input_t = 0.0
        self.tick = 0
        self.fired = {}                   # key -> time fired (button flash)
        self.undo = []                    # (key, old, new)
        self.redo = []
        self.accel_last = 0.0
        self.accel_n = 0
        self.entry = None                 # {'key','text','over','preview'}
        self.confirm = None               # {'text','yes','no','on_yes','on_no', 'lines'}
        self.bank = None                  # BankState
        self.sheet = None                 # SheetState
        self.help_scroll = 0
        self.rail_sel = 0
        self.warnings = []
        self.preset_index = None          # {key: [(value, preset_name)]} built lazily
        self.flat_level = 0
        self.splash_t0 = 0
        self.mouse_on = True
        self.user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        self.fam = C.P22
        self.group_ids = [g for g in ctl.groups.keys()]
        self.hits = {}                    # y -> [(x0, x1, kind, payload)] rebuilt every render
        self.meter_geo = {}               # row index -> (mx, mw)
        self._baseline = None             # cached baseline_values() (invalidate on preset/profile change)
        self._baseline_key = None
        self.rebuild_rows()
        self.refresh_family()

    # -- baseline (inherited tube values), cached ---------------------------------

    def baseline(self):
        """ctl.baseline_values() cached per active preset — render must never
        read a file. Call invalidate_baseline() after apply/save/load."""
        key = self.ctl.active_preset
        if self._baseline is None or self._baseline_key != key:
            self._baseline = self.ctl.baseline_values()
            self._baseline_key = key
        return self._baseline

    def invalidate_baseline(self):
        self._baseline = None

    # -- hit testing (mouse) ------------------------------------------------------

    def hits_reset(self):
        self.hits = {}
        self.meter_geo = {}

    def hit_add(self, x0, x1, y, kind, payload):
        self.hits.setdefault(y, []).append((x0, x1, kind, payload))

    def hit_at(self, x, y):
        for x0, x1, kind, payload in self.hits.get(y, []):
            if x0 <= x < x1:
                return (kind, payload)
        return None

    # -- rows ----------------------------------------------------------------

    def rebuild_rows(self, keep_key=None):
        ctl = self.ctl
        rows = []
        gids = list(ctl.groups.keys())
        for gid in gids:
            desc = ctl.groups.get(gid, "")
            rows.append(Row("header", gid=gid, label=gid.upper(), spec={"desc": desc}))
            for key, spec in ctl.params.items():
                if spec.get("group") != gid:
                    continue
                knob = spec.get("knob", "rotary")
                if knob == "hidden":
                    continue
                if knob == "button" and key == "power_on":
                    rows.append(Row("button", key=key, gid=gid, label=spec.get("label", key), spec=spec))
                    continue
                if knob in ("rotary", "selector", "switch"):
                    rows.append(Row(knob, key=key, gid=gid, label=spec.get("label", key), spec=spec))
            if gid == "system":
                if "degauss_nonce" in ctl.params:
                    rows.append(Row("action", key="degauss", gid=gid, label="DEGAUSS", spec=ctl.params["degauss_nonce"]))
                if "erase_nonce" in ctl.params:
                    rows.append(Row("action", key="erase", gid=gid, label="ERASE / TUBE-SWAP", spec=ctl.params["erase_nonce"]))
                rows.append(Row("swapstyle", key="swap_style", gid=gid, label="SWAP STYLE",
                                spec={"desc": "What a preset switch does with the previous tube's glow.",
                                      "help": "carry = the old phosphor's persistence carries over and is reinterpreted by the new tube (organic cross-preset ghosting — official behavior, not a bug). degauss = same, plus the coil thunk. fresh = new tube: instant clear via the erase nonce."}))
                rows.append(Row("terminal", key="font-size", gid=gid, label="FONT SIZE",
                                spec={"desc": "Terminal font-size override for this tube (crt-overrides.conf).",
                                      "help": "Written to crt-overrides.conf and passed to the fork via --config-file; low-res tubes carry a font-size so the raster has room to breathe. 'default' clears the override. Range 6..40.",
                                      "min": 6, "max": 40, "step": 1, "type": "float", "unit": "pt"}))
                rows.append(Row("terminal", key="font-family", gid=gid, label="FONT FAMILY",
                                spec={"desc": "Terminal font-family override for this tube.",
                                      "help": "Any family name Ghostty can resolve. Written to crt-overrides.conf; 'default' clears it.", "type": "text"}))
        self.rows = rows
        if keep_key is not None:
            for i, r in enumerate(rows):
                if r.key == keep_key:
                    self.sel = i
                    break
        self.sel = self._clamp_sel(self.sel)

    def visible_rows(self):
        """Rows after filter / modified-only; headers kept only when they
        have at least one visible child. Returns list of (index, Row)."""
        if not self.filter and not self.modified_only:
            return list(enumerate(self.rows))
        base = self.baseline() if self.modified_only else None
        f = self.filter.lower()
        out = []
        pending_header = None
        for i, r in enumerate(self.rows):
            if r.kind == "header":
                pending_header = (i, r)
                continue
            if f and not self._row_matches(r, f):
                continue
            if self.modified_only and not self.row_modified(r, base):
                continue
            if pending_header is not None:
                out.append(pending_header)
                pending_header = None
            out.append((i, r))
        return out

    def _row_matches(self, r, f):
        spec = r.spec
        hay = " ".join([r.label or "", r.key or "", spec.get("desc", "") or "", spec.get("help", "") or "",
                        spec.get("define", "") or "", r.gid or ""]).lower()
        return f in hay

    def row_modified(self, r, base=None):
        if r.kind in ("header", "action", "swapstyle", "terminal", "button"):
            return False
        base = base if base is not None else self.baseline()
        return self.ctl.values.get(r.key) != base.get(r.key)

    def modified_counts(self):
        base = self.baseline()
        out = {}
        for r in self.rows:
            if r.kind in ("rotary", "switch", "selector"):
                if self.ctl.values.get(r.key) != base.get(r.key):
                    out[r.gid] = out.get(r.gid, 0) + 1
        return out

    def _clamp_sel(self, i):
        vis = self.visible_rows()
        if not vis:
            return 0
        idxs = [k for k, r in vis if r.selectable]
        if not idxs:
            return vis[0][0]
        if i in idxs:
            return i
        # nearest selectable
        return min(idxs, key=lambda k: abs(k - i))

    def selected_row(self):
        if 0 <= self.sel < len(self.rows):
            return self.rows[self.sel]
        return None

    def move(self, delta):
        vis = self.visible_rows()
        idxs = [k for k, r in vis if r.selectable]
        if not idxs:
            return
        if self.sel not in idxs:
            self.sel = idxs[0]
            return
        pos = idxs.index(self.sel)
        pos = max(0, min(len(idxs) - 1, pos + delta))
        self.sel = idxs[pos]

    def jump_group(self, gid):
        for i, r in enumerate(self.rows):
            if r.gid == gid and r.selectable:
                self.sel = i
                self.rail_sel = self.group_ids.index(gid) if gid in self.group_ids else self.rail_sel
                return

    def section_jump(self, direction):
        r = self.selected_row()
        if r is None:
            return
        gids = self.group_ids
        gi = gids.index(r.gid) if r.gid in gids else 0
        gi = (gi + direction) % len(gids)
        self.jump_group(gids[gi])

    # -- values ----------------------------------------------------------------

    def value_t(self, key):
        """Position of the value within nominal range, 0..1 (may exceed)."""
        spec = self.ctl.params.get(key) or {}
        lo, hi = spec.get("min"), spec.get("max")
        if lo is None or hi is None or hi == lo:
            return None
        v = self.ctl.values.get(key)
        try:
            return (float(v) - float(lo)) / (float(hi) - float(lo))
        except (TypeError, ValueError):
            return None

    def refresh_family(self):
        ph = self.ctl.values.get("phosphor")
        self.fam = C.family_for_phosphor(ph)
        C.set_sat_ceiling(self.ctl.values.get("mask_type"), self.ctl.values.get("mask_strength"))
        try:
            from . import widgets as _W
            _W._METER_CACHE.clear()
            _W._SWEEP_ROW_CACHE.clear()
        except Exception:
            pass

    def hue_for_group(self, gid):
        return C.GROUP_HUES.get(gid, 0.0)

    def group_rgb(self, gid):
        if self.fam.hues:
            return C.crt_safe(C.hue_to_rgb(self.hue_for_group(gid)))
        gids = self.group_ids
        i = gids.index(gid) if gid in gids else 0
        return self.fam.shade(0.35 + 0.6 * i / max(1, len(gids) - 1))

    # -- toasts ------------------------------------------------------------------

    def toast(self, text, kind="info", ttl=3.0):
        self.messages.append((text, kind, self.now() + ttl))
        self.messages = self.messages[-5:]

    def live_messages(self):
        t = self.now()
        self.messages = [m for m in self.messages if m[2] > t]
        return self.messages

    # -- reload -------------------------------------------------------------------

    def arm_reload(self):
        self.reload_deadline = self.now() + DEBOUNCE_S

    def reload_pending(self):
        return self.reload_deadline is not None

    # -- preset index -------------------------------------------------------------

    def build_preset_index(self):
        """{key: sorted [(value, name)]} over the bank, for SAME KNOB, OTHER TUBES."""
        idx = {}
        docs = self.ctl.list_preset_docs()
        for d in docs:
            params = d.get("params") or {}
            for k, v in params.items():
                if k in self.ctl.params:
                    idx.setdefault(k, []).append((v, d["name"]))
        for k in idx:
            try:
                idx[k].sort(key=lambda p: (float(p[0]) if not isinstance(p[0], str) else 0.0, p[1]))
            except Exception:
                pass
        self.preset_index = idx
        self._docs_cache = docs
        return idx

    def preset_docs(self):
        if self.preset_index is None:
            self.build_preset_index()
        return self._docs_cache

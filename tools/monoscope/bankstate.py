"""monoscope.bankstate — the tube bank / profile bank state (pure)."""

from __future__ import annotations

__all__ = ["BankState", "signature_values"]

SIG_KEYS = ("persistence", "h_bandwidth", "mask_triads", "curve_radius", "scan_bloom", "halation", "noise", "burnin_rate")


def signature_values(values, params):
    """Eight [0,1] values fingerprinting a tube: persist, bandwidth, pitch,
    curvature, bloom, halation, snow, wear (from the value dict + specs)."""
    out = []
    for k in SIG_KEYS:
        spec = params.get(k)
        if not spec:
            out.append(0.0)
            continue
        lo, hi = spec.get("min"), spec.get("max")
        v = values.get(k, spec.get("default"))
        try:
            t = (float(v) - float(lo)) / (float(hi) - float(lo))
        except (TypeError, ValueError, ZeroDivisionError):
            t = 0.0
        out.append(max(0.0, min(1.0, t)))
    return out


class BankState:
    """A browsable list of presets or profiles."""

    def __init__(self, m, source="presets"):
        self.m = m
        self.source = source            # 'presets' | 'profiles'
        self.sort = "name"
        self.filter = ""
        self.filter_active = False
        self.sel = 0
        self.scroll = 0
        self.entries = []               # sorted, filtered list of dicts
        self.all_entries = []
        self.load()

    def load(self):
        m = self.m
        if self.source == "presets":
            docs = m.ctl.list_preset_docs()
            self.all_entries = docs
        else:
            out = []
            for name, saved, path in m.ctl.list_profiles():
                try:
                    doc = m.ctl.read_profile(name)
                except Exception:
                    doc = {}
                out.append({"name": name, "description": "profile · saved %s" % (saved or "?"),
                            "meta": None, "params": doc.get("params") or {}, "terminal": doc.get("terminal") or {},
                            "path": path, "saved": saved, "active_preset": doc.get("active_preset")})
            self.all_entries = out
        self.apply_sort_filter(keep=None)
        # start on the active preset
        active = m.ctl.active_preset
        for i, e in enumerate(self.entries):
            if e["name"] == active:
                self.sel = i
                break

    def apply_sort_filter(self, keep=None):
        m = self.m
        cur = keep if keep is not None else (self.entries[self.sel]["name"] if self.entries and 0 <= self.sel < len(self.entries) else None)
        ents = list(self.all_entries)
        f = self.filter.lower().strip()
        if f:
            def hay(e):
                meta = e.get("meta") or {}
                return " ".join([e.get("name", ""), e.get("description", ""), str(meta.get("manufacturer", "")),
                                 str(meta.get("type", "")), str(meta.get("year", ""))]).lower()
            ents = [e for e in ents if f in hay(e)]
        if self.source == "presets":
            try:
                ents = m.cm.sort_preset_entries(ents, self.sort)
            except Exception:
                ents.sort(key=lambda e: e["name"])
        else:
            ents.sort(key=lambda e: e.get("saved") or "", reverse=True)
        self.entries = ents
        self.sel = 0
        if cur is not None:
            for i, e in enumerate(ents):
                if e["name"] == cur:
                    self.sel = i
                    break
        self.sel = max(0, min(self.sel, max(0, len(ents) - 1)))

    def cycle_sort(self):
        modes = self.m.cm.SORT_MODES if hasattr(self.m.cm, "SORT_MODES") else ("name", "year", "type", "manufacturer", "price", "resolution")
        i = modes.index(self.sort) if self.sort in modes else 0
        self.sort = modes[(i + 1) % len(modes)]
        self.apply_sort_filter()

    def move(self, d):
        if not self.entries:
            return
        n = len(self.entries)
        self.sel = (self.sel + d) % n if abs(d) == 1 else max(0, min(n - 1, self.sel + d))

    def current(self):
        if self.entries and 0 <= self.sel < len(self.entries):
            return self.entries[self.sel]
        return None

"""monoscope.sheetstate — the SAVE TUBE sheet (and the small profile-name
sheet): auto-name, auto-description from the diff, live diff with drop.

Pure state; the view draws it, the app mutates it.
"""

from __future__ import annotations

import os
import re

__all__ = ["SheetState", "slugify", "auto_name", "auto_description", "diff_lines"]


def slugify(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.")
    s = re.sub(r"-{2,}", "-", s).lower()
    return s or "tube"


def auto_name(inherited, user=None):
    base = (inherited or "custom").replace("-", " ").strip()
    words = [w.capitalize() if not w.isdigit() else w for w in base.split()]
    disp = " ".join(words)
    if user:
        return "%s %s Custom" % (disp, user)
    return "%s Custom" % disp


def _fmt(cm, spec, v):
    try:
        return cm.display_value(spec, v)
    except Exception:
        return str(v)


def diff_lines(m):
    """[(key, label, old, new, spec)] for every non-system param that differs
    from the inherited tube, ranked most-characterful first."""
    ctl = m.ctl
    base = m.baseline()
    out = []
    for key, spec in ctl.params.items():
        if spec.get("group") == "system":
            continue
        old, new = base.get(key), ctl.values.get(key)
        if old == new:
            continue
        # distance relative to range for ranking
        lo, hi = spec.get("min"), spec.get("max")
        try:
            dist = abs(float(new) - float(old)) / (float(hi) - float(lo))
        except (TypeError, ValueError, ZeroDivisionError):
            dist = 1.0
        out.append((dist, key, spec.get("label", key), old, new, spec))
    out.sort(key=lambda t: (-t[0], t[1]))
    return [(k, lab, o, n, sp) for _d, k, lab, o, n, sp in out]


def auto_description(m, dropped=()):
    """Inherited tube's own description + a prose rendering of the diff."""
    ctl = m.ctl
    cm = m.cm
    inh = ctl.active_preset
    desc = ""
    meta_line = ""
    if inh:
        try:
            doc = ctl.read_preset(inh)
            desc = (doc.get("description") or "").strip()
            meta = doc.get("meta") or {}
            bits = []
            if meta.get("year"):
                bits.append(str(meta["year"]))
            if meta.get("price_usd"):
                bits.append("$%s" % meta["price_usd"])
            meta_line = (" (%s)" % ", ".join(bits)) if bits else ""
        except Exception:
            pass
    lines = diff_lines(m)
    lines = [d for d in lines if d[0] not in dropped]
    disp = inh.replace("-", " ").title() if inh else "the schema defaults"
    head = "Based on %s" % disp
    if desc:
        first = desc.split(". ")[0].rstrip(".")
        head += " — " + first + "."
    else:
        head += "."
    if not lines:
        return head + " No settings differ from that tube."
    parts = []
    for key, lab, old, new, spec in lines[:6]:
        parts.append("%s %s → %s" % (lab, _fmt(cm, spec, old), _fmt(cm, spec, new)))
    more = len(lines) - 6
    body = " Differs from that tube in %d setting%s: %s%s." % (
        len(lines), "" if len(lines) == 1 else "s", ", ".join(parts), (" and %d more" % more) if more > 0 else "")
    return head + body


class SheetState:
    """Fields: name (text), description (text), diff (list). ``focus`` is one
    of 'name' | 'description' | 'diff'."""

    def __init__(self, m, kind="preset"):
        self.m = m
        self.kind = kind                    # 'preset' | 'profile'
        self.focus = "name"
        user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        inherited = m.ctl.active_preset or ""
        if kind == "preset":
            self.name = auto_name(inherited, user or None)
            self.dropped = set()
            self.description = auto_description(m)
        else:
            self.name = "profile-%s" % __import__("time").strftime("%Y%m%d-%H%M")
            self.dropped = set()
            self.description = ""
        self.cursor = len(self.name)
        self.diff_sel = 0
        self.diff_scroll = 0
        self.desc_cursor = len(self.description)
        self.error = ""

    @property
    def slug(self):
        return slugify(self.name)

    def diff(self):
        return [d for d in diff_lines(self.m) if d[0] not in self.dropped]

    def rewrite_description(self):
        self.description = auto_description(self.m, self.dropped)
        self.desc_cursor = len(self.description)

    def drop_current(self):
        d = self.diff()
        if not d:
            return None
        key = d[max(0, min(self.diff_sel, len(d) - 1))][0]
        self.dropped.add(key)
        self.diff_sel = max(0, min(self.diff_sel, len(d) - 2))
        return key

    def undrop_all(self):
        self.dropped.clear()

    # -- text editing ---------------------------------------------------------

    def _field(self):
        return "name" if self.focus == "name" else "description"

    def insert(self, text):
        if self.focus == "name":
            self.name = self.name[: self.cursor] + text + self.name[self.cursor:]
            self.cursor += len(text)
        elif self.focus == "description":
            self.description = self.description[: self.desc_cursor] + text + self.description[self.desc_cursor:]
            self.desc_cursor += len(text)

    def backspace(self):
        if self.focus == "name" and self.cursor > 0:
            self.name = self.name[: self.cursor - 1] + self.name[self.cursor:]
            self.cursor -= 1
        elif self.focus == "description" and self.desc_cursor > 0:
            self.description = self.description[: self.desc_cursor - 1] + self.description[self.desc_cursor:]
            self.desc_cursor -= 1

    def delete(self):
        if self.focus == "name" and self.cursor < len(self.name):
            self.name = self.name[: self.cursor] + self.name[self.cursor + 1:]
        elif self.focus == "description" and self.desc_cursor < len(self.description):
            self.description = self.description[: self.desc_cursor] + self.description[self.desc_cursor + 1:]

    def move_cursor(self, d):
        if self.focus == "name":
            self.cursor = max(0, min(len(self.name), self.cursor + d))
        elif self.focus == "description":
            self.desc_cursor = max(0, min(len(self.description), self.desc_cursor + d))

    def home_end(self, end):
        if self.focus == "name":
            self.cursor = len(self.name) if end else 0
        elif self.focus == "description":
            self.desc_cursor = len(self.description) if end else 0

    def clear_field(self):
        if self.focus == "name":
            self.name, self.cursor = "", 0
        elif self.focus == "description":
            self.description, self.desc_cursor = "", 0

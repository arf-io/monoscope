"""monoscope.helpview — the key reference, generated from one table so the
docs and the panel can never disagree."""

from __future__ import annotations

from .canvas import BOLD
from . import color as C
from . import widgets as W
from .banners import banner_rows

__all__ = ["render_help", "KEYMAP"]

# (section, [(keys, action)])
KEYMAP = [
    ("BENCH", [
        ("↑ ↓ / j k", "select knob"),
        ("PgUp PgDn", "move five knobs"),
        ("Home End / g G", "first / last knob"),
        ("← → / h l", "adjust one step (held: repeats accelerate ×3 after 10)"),
        ("< > / Shift-←→ / Ctrl-←→", "adjust five steps"),
        ("↵", "rotary: type a value · switch: toggle · selector: cycle · button: fire"),
        ("0", "reset this knob to the schema default"),
        ("⌫ / Del", "revert this knob to the inherited tube's value"),
        ("Tab", "focus the group rail (↑↓ jumps groups, ↵ back) · Shift-Tab: previous group"),
        ("1-9", "jump to group N"),
        ("/", "filter knobs by label, key, define or help text (Esc clears)"),
        ("*", "show only knobs that differ from the tube"),
        ("u / U", "undo / redo a knob change"),
        ("p / P", "tube bank / save this tube as a preset"),
        ("L / S", "profile bank / save a full-state profile"),
        ("E", "erase (DVST page flash / tube-swap clear) — from anywhere"),
        ("r", "reload the terminal now"),
        ("m", "cycle motion: full → reduced → off"),
        ("M", "toggle mouse capture (off = the terminal can select text again)"),
        ("[ ]", "ambient frame rate −/+ 2 fps"),
        ("^F", "flat-field diagnostic (§8.4: ghosts over a flat field are the shader's)"),
        ("mouse", "click a row · click/drag inside a meter · wheel scrolls · click a group"),
        ("? / q", "this help / quit (flushes a pending reload first)"),
    ]),
    ("TYPING A VALUE", [
        ("0-9 . - e", "digits (int knobs round) — outside the nominal range is allowed"),
        ("↑ ↓", "nudge the typed value by one step"),
        ("↵", "commit — outside nominal asks once, shows the consequence"),
        ("Esc", "cancel · ^U clears · d = 'default'"),
    ]),
    ("TUBE BANK", [
        ("↑ ↓ PgUp PgDn", "browse (cursor stays centred)"),
        ("s", "cycle sort: name → year → type → manufacturer → price → resolution"),
        ("/", "filter by name / maker / family / description"),
        ("w", "cycle swap style (carry / degauss / fresh) — what the switch does with the old glow"),
        ("↵", "apply the tube"),
        ("x / Del", "delete the file (asks first)"),
        ("Esc", "back to the bench"),
    ]),
    ("SAVE SHEET", [
        ("Tab", "name → description → diff"),
        ("↵", "save (in the diff: drop the line from the save and revert it)"),
        ("^R", "rewrite the description from the current diff"),
        ("^D / ^Z", "drop the selected diff line / restore all dropped lines"),
        ("Esc", "cancel"),
    ]),
    ("CLI", [
        ("crtctl get|set|list|apply", "unchanged — the panel is crtctl's interactive form"),
        ("crtctl preset NAME · presets", "apply / list tubes; preset --save NAME --description D"),
        ("crtctl save|load|profiles", "full-state snapshots"),
        ("crtctl power|degauss|erase|swap-style", "buttons"),
        ("crtctl terminal [key [value]]", "font-size / font-family overrides"),
        ("crtctl targets · status", "instances · paths & state"),
        ("crtctl panel [--motion M] [--flat-field]", "this panel"),
    ]),
]


def render_help(m, cv, tick):
    fam = m.fam
    motion = m.motion != "off"
    w, h = cv.w, cv.h
    y = 0
    if h >= 34:
        y += W.banner_block(cv, w, 0, "small", "HELP", fam, tick, motion)
    W.band(cv, 0, y, w, "HELP", "MONOSCOPE · every key", fam, tick, motion)
    y += 1
    lines = []
    for section, items in KEYMAP:
        lines.append(("section", section, ""))
        for k, a in items:
            lines.append(("item", k, a))
        lines.append(("blank", "", ""))
    avail = h - y - 2
    top = max(0, min(m.help_scroll, max(0, len(lines) - avail)))
    m.help_scroll = top
    hot = C.crt_safe(fam.hot)
    kw = 26
    for i in range(avail):
        idx = top + i
        if idx >= len(lines):
            break
        kind, k, a = lines[idx]
        yy = y + i
        if kind == "section":
            W.section_band(cv, 0, yy, w, k, "", hot, fam, tick, motion)
        elif kind == "item":
            cv.put(2, yy, k[:kw].ljust(kw), fg=hot, bg=None, at=BOLD)
            for j, ln in enumerate(W.wrap_text(a, w - kw - 4)[:1]):
                cv.put(2 + kw + 1, yy, ln, fg=fam.ink, bg=None)
    W.status_band(cv, 0, h - 2, w, [("MONOSCOPE", "title"), ("HELP", "info"), ("%d/%d" % (top + 1, len(lines)), "info")], fam, tick, motion)
    W.hint_band(cv, 0, h - 1, w, [("↑↓ PgUp PgDn", "scroll"), ("Esc / q / ?", "back")], fam, tick, motion)

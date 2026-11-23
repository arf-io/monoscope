"""monoscope.keys — terminal input decoder.

Turns the raw byte stream from the tty into :class:`Event` objects:
keys (with shift/ctrl/alt modifiers), mouse (SGR 1006), bracketed paste,
focus in/out. Understands the legacy xterm/VT sequences *and* the kitty
keyboard protocol's CSI-u form (which Ghostty, kitty, wezterm and foot emit
once we push flag 1), so Esc / Shift-arrows / Ctrl-letters are unambiguous
where the terminal can make them so and still work everywhere else.

Every event has a stable ``id`` string for keymaps::

    "a"  "A"  "1"        printable characters (shift is implied by case)
    "enter" "esc" "tab" "backtab" "backspace" "space" "del" "ins"
    "up" "down" "left" "right" "home" "end" "pgup" "pgdn"
    "f1" … "f12"
    "S-up"  "C-left"  "A-x"  "C-S-right"   modifiers prefix: S- C- A- (in that order)
    "mouse"  "paste"  "focus_in"  "focus_out"

Escape disambiguation: a lone ESC is emitted only after ``ESC_TIMEOUT``
seconds elapse without a continuation byte — call :meth:`Decoder.flush`
on idle ticks so it can fire.
"""

from __future__ import annotations

import time

__all__ = ["Event", "Decoder", "ESC_TIMEOUT"]

ESC_TIMEOUT = 0.05  # seconds; tmux escape-time is 10 ms, ghostty pushes CSI-u so a lone ESC is explicit there

SHIFT, ALT, CTRL = 1, 2, 4


class Event:
    __slots__ = ("kind", "name", "char", "mods", "x", "y", "button", "pressed", "text", "id", "t")

    def __init__(self, kind, name="", char="", mods=0, x=0, y=0, button=0, pressed=False, text=""):
        self.kind = kind          # 'key' | 'mouse' | 'paste' | 'focus'
        self.name = name          # 'up', 'enter', 'char', 'wheel_up', ...
        self.char = char          # for printable keys
        self.mods = mods
        self.x, self.y = x, y     # mouse, 0-based
        self.button = button      # 0 left 1 middle 2 right 64 wheel-up 65 wheel-down
        self.pressed = pressed
        self.text = text
        self.t = time.monotonic()
        self.id = self._make_id()

    def _make_id(self):
        if self.kind == "key":
            if self.name == "char":
                # letters carry their own case; modifiers other than shift prefix
                base = self.char
                m = self.mods & ~SHIFT if len(base) == 1 and base.isalpha() else self.mods
                if base == " ":
                    base = "space"
                return _prefix(m) + base
            return _prefix(self.mods) + self.name
        if self.kind == "mouse":
            return "mouse"
        return self.kind if self.kind != "focus" else ("focus_in" if self.pressed else "focus_out")

    @property
    def shift(self):
        return bool(self.mods & SHIFT)

    @property
    def ctrl(self):
        return bool(self.mods & CTRL)

    @property
    def alt(self):
        return bool(self.mods & ALT)

    def __repr__(self):
        if self.kind == "mouse":
            return "Event(mouse %s btn=%d at %d,%d %s)" % (self.name, self.button, self.x, self.y, "press" if self.pressed else "release")
        return "Event(%s)" % self.id


def _prefix(mods):
    s = ""
    if mods & CTRL:
        s += "C-"
    if mods & SHIFT:
        s += "S-"
    if mods & ALT:
        s += "A-"
    return s


def _xterm_mods(n):
    """xterm modifier parameter (1-based bitfield+1) → our flags."""
    n = max(0, int(n) - 1)
    m = 0
    if n & 1:
        m |= SHIFT
    if n & 2:
        m |= ALT
    if n & 4:
        m |= CTRL
    return m


_CSI_FINAL = {
    "A": "up", "B": "down", "C": "right", "D": "left",
    "H": "home", "F": "end", "Z": "backtab",
    "P": "f1", "Q": "f2", "R": "f3", "S": "f4",
}
_CSI_TILDE = {
    1: "home", 2: "ins", 3: "del", 4: "end", 5: "pgup", 6: "pgdn", 7: "home", 8: "end",
    11: "f1", 12: "f2", 13: "f3", 14: "f4", 15: "f5", 17: "f6", 18: "f7", 19: "f8",
    20: "f9", 21: "f10", 23: "f11", 24: "f12",
}
_SS3 = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end",
        "P": "f1", "Q": "f2", "R": "f3", "S": "f4", "M": "enter"}
# kitty CSI-u functional key codepoints (private use area) → names
_KITTY_FUNC = {
    57358: "capslock", 57359: "scrolllock", 57360: "numlock",
    57361: "printscreen", 57362: "pause", 57363: "menu",
    57364: "f13", 57376: "f25",
    57399: "0", 57400: "1", 57401: "2", 57402: "3", 57403: "4", 57404: "5",
    57405: "6", 57406: "7", 57407: "8", 57408: "9", 57409: ".", 57410: "/",
    57411: "*", 57412: "-", 57413: "+", 57414: "enter", 57415: "=",
    57417: "left", 57418: "right", 57419: "up", 57420: "down", 57421: "pgup",
    57422: "pgdn", 57423: "home", 57424: "end", 57425: "ins", 57426: "del",
}


class Decoder:
    """Incremental decoder. Feed bytes; get events."""

    def __init__(self):
        self._buf = b""
        self._esc_at = None
        self._paste = None  # list of str while inside a bracketed paste

    def feed(self, data):
        """Consume raw bytes; return a list of Events decoded so far."""
        events = []
        if not data:
            return events
        self._buf += data
        self._esc_at = None
        while self._buf:
            n, ev = self._parse_one(self._buf)
            if n == 0:
                # incomplete: wait for more bytes (or the ESC timeout)
                if self._buf[:1] == b"\x1b":
                    self._esc_at = time.monotonic()
                break
            self._buf = self._buf[n:]
            if ev is None:
                continue
            if isinstance(ev, list):
                events.extend(ev)
            else:
                events.append(ev)
        return [e for e in self._paste_filter(events)]

    def flush(self):
        """Call on idle ticks: emits a lone ESC when the timeout has passed,
        or decodes an unrecognized ESC-prefixed tail as ESC + text."""
        if not self._buf:
            return []
        if self._buf[:1] == b"\x1b":
            if self._esc_at is None:
                self._esc_at = time.monotonic()
                return []
            if time.monotonic() - self._esc_at < ESC_TIMEOUT:
                return []
            # timeout: a lone escape (possibly followed by literal bytes → alt-key)
            buf = self._buf
            self._buf = b""
            self._esc_at = None
            if len(buf) == 1:
                return [Event("key", "esc")]
            # ESC + printable = alt+key (legacy meta)
            rest = buf[1:]
            try:
                txt = rest.decode("utf-8")
            except UnicodeDecodeError:
                txt = rest.decode("latin-1")
            evs = []
            for ch in txt:
                evs.append(Event("key", "char", char=ch, mods=ALT))
            return evs
        # non-ESC leftover means an incomplete UTF-8 sequence; keep waiting
        return []

    # -- internals ---------------------------------------------------------

    def _paste_filter(self, events):
        for ev in events:
            if ev.kind == "_paste_start":
                self._paste = []
                continue
            if ev.kind == "_paste_end":
                text = "".join(self._paste or [])
                self._paste = None
                yield Event("paste", text=text)
                continue
            if self._paste is not None:
                if ev.kind == "key":
                    if ev.name == "char":
                        self._paste.append(ev.char)
                    elif ev.name == "enter":
                        self._paste.append("\n")
                    elif ev.name == "tab":
                        self._paste.append("\t")
                continue
            yield ev

    def _parse_one(self, buf):
        """Return (bytes_consumed, Event|list|None). 0 = need more data."""
        b0 = buf[0]
        if b0 == 0x1b:
            if len(buf) == 1:
                return 0, None
            b1 = buf[1]
            if b1 == 0x5b:      # CSI
                return self._parse_csi(buf)
            if b1 == 0x4f:      # SS3
                if len(buf) < 3:
                    return 0, None
                ch = chr(buf[2])
                name = _SS3.get(ch)
                if name:
                    return 3, Event("key", name)
                return 3, None
            if b1 == 0x1b:
                # ESC ESC: emit one esc, keep the other
                return 1, Event("key", "esc")
            if b1 in (0x50, 0x5d, 0x5f, 0x5e, 0x58):   # DCS ] APC PM SOS: a terminal reply, swallow to ST/BEL
                st = buf.find(b"\x1b\\", 2)
                bel = buf.find(b"\x07", 2) if b1 == 0x5d else -1
                ends = [e for e in (st, bel) if e != -1]
                if not ends:
                    if len(buf) > 4096:
                        return len(buf), None
                    return 0, None
                e = min(ends)
                return e + (2 if e == st else 1), None
            # ESC + byte: alt-modified key (legacy meta) — but only if the byte is
            # a complete printable char; otherwise wait for timeout in flush()
            n, ev = self._parse_one(buf[1:])
            if n == 0:
                return 0, None
            if ev is not None and not isinstance(ev, list) and ev.kind == "key":
                ev.mods |= ALT
                ev.id = ev._make_id()
                return 1 + n, ev
            return 1 + n, ev
        if b0 == 0x0d or b0 == 0x0a:
            return 1, Event("key", "enter")
        if b0 == 0x09:
            return 1, Event("key", "tab")
        if b0 == 0x7f or b0 == 0x08:
            return 1, Event("key", "backspace")
        if b0 == 0x00:
            return 1, Event("key", "char", char=" ", mods=CTRL)
        if b0 < 0x20:
            # Ctrl+letter (0x01..0x1a) and a few punctuation ctrls
            if 1 <= b0 <= 26:
                return 1, Event("key", "char", char=chr(b0 + 96), mods=CTRL)
            mapping = {0x1c: "\\", 0x1d: "]", 0x1e: "^", 0x1f: "_"}
            return 1, Event("key", "char", char=mapping.get(b0, chr(b0)), mods=CTRL)
        # UTF-8 text
        if b0 < 0x80:
            return 1, Event("key", "char", char=chr(b0))
        need = 2 if b0 >> 5 == 0b110 else 3 if b0 >> 4 == 0b1110 else 4 if b0 >> 3 == 0b11110 else 1
        if len(buf) < need:
            return 0, None
        try:
            ch = buf[:need].decode("utf-8")
        except UnicodeDecodeError:
            return 1, Event("key", "char", char=chr(b0))
        return need, Event("key", "char", char=ch)

    def _parse_csi(self, buf):
        # find final byte 0x40..0x7e after ESC [
        i = 2
        n = len(buf)
        while i < n:
            c = buf[i]
            if 0x40 <= c <= 0x7e:
                break
            if c < 0x20 or c > 0x3f:
                # not a CSI byte — bail: treat ESC as lone
                return 1, Event("key", "esc")
            i += 1
        else:
            if n > 64:   # garbage guard
                return 1, Event("key", "esc")
            return 0, None
        body = buf[2:i].decode("ascii", "replace")
        final = chr(buf[i])
        length = i + 1
        # SGR mouse: CSI < b ; x ; y M|m
        if body.startswith("<") and final in "Mm":
            try:
                b, x, y = (int(p) for p in body[1:].split(";")[:3])
            except ValueError:
                return length, None
            pressed = final == "M"
            mods = 0
            if b & 4:
                mods |= SHIFT
            if b & 8:
                mods |= ALT
            if b & 16:
                mods |= CTRL
            motion = bool(b & 32)
            btn = b & 3
            if b & 64:
                name = "wheel_up" if btn == 0 else "wheel_down" if btn == 1 else "wheel_left" if btn == 2 else "wheel_right"
                return length, Event("mouse", name, mods=mods, x=x - 1, y=y - 1, button=b, pressed=True)
            name = "drag" if motion else ("press" if pressed else "release")
            if motion and btn == 3:
                name = "move"
            return length, Event("mouse", name, mods=mods, x=x - 1, y=y - 1, button=btn, pressed=pressed)
        if final == "I":
            return length, Event("focus", pressed=True)
        if final == "O":
            return length, Event("focus", pressed=False)
        params = body
        if params.startswith("?") or params.startswith(">") or params.startswith("="):
            # DA / mode reports — ignore
            return length, None
        parts = params.split(";") if params else []
        nums = []
        for p in parts:
            try:
                nums.append(int(p.split(":")[0]) if p else 1)
            except ValueError:
                nums.append(1)
        if final == "~":
            code = nums[0] if nums else 0
            if code == 200:
                return length, Event("_paste_start")
            if code == 201:
                return length, Event("_paste_end")
            name = _CSI_TILDE.get(code)
            if name is None:
                return length, None
            mods = _xterm_mods(nums[1]) if len(nums) > 1 else 0
            return length, Event("key", name, mods=mods)
        if final == "u":
            # kitty CSI-u: codepoint[:shifted[:base]] ; mods[:event] u
            cp = nums[0] if nums else 0
            mods = _xterm_mods(nums[1]) if len(nums) > 1 else 0
            # event type (press/repeat/release) rides in the mods field after ':'
            evtype = 1
            if len(parts) > 1 and ":" in parts[1]:
                try:
                    evtype = int(parts[1].split(":")[1])
                except ValueError:
                    evtype = 1
            if evtype == 3:      # release — ignore
                return length, None
            if cp == 27:
                return length, Event("key", "esc", mods=mods)
            if cp == 13:
                return length, Event("key", "enter", mods=mods)
            if cp == 9:
                return length, Event("key", "backtab" if mods & SHIFT else "tab", mods=mods & ~SHIFT)
            if cp == 127 or cp == 8:
                return length, Event("key", "backspace", mods=mods)
            if cp == 32:
                return length, Event("key", "char", char=" ", mods=mods)
            if cp in _KITTY_FUNC:
                return length, Event("key", _KITTY_FUNC[cp], mods=mods)
            try:
                ch = chr(cp)
            except (ValueError, OverflowError):
                return length, None
            # with shift, kitty reports the base key; use the shifted codepoint if given
            if mods & SHIFT and parts and ":" in parts[0]:
                try:
                    ch = chr(int(parts[0].split(":")[1]))
                except (ValueError, IndexError):
                    pass
            if ch.isalpha() and (mods & SHIFT):
                ch = ch.upper()
            return length, Event("key", "char", char=ch, mods=mods)
        name = _CSI_FINAL.get(final)
        if name:
            mods = _xterm_mods(nums[1]) if len(nums) > 1 else 0
            if final == "Z":
                mods &= ~SHIFT
            return length, Event("key", name, mods=mods)
        return length, None

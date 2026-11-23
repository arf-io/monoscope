#!/usr/bin/env python3
"""End-to-end pty proofs for MONOSCOPE: launch the real panel (`crtctl panel`)
on real pseudo-terminals, drive it with keys, and assert against the
reconstructed screen and the side effects (state.json, generated shaders,
the reload sent through a fake gdbus on PATH) — plus the terminal-hygiene
contract of the raw byte stream: truecolor SGR only (never OSC 4 / 104),
DEC 2026 brackets around frames, alt screen entered and left, cursor shown
again on exit. Stdlib only; skipped where pty is unavailable."""

import codecs
import fcntl
import json
import os
import pty
import random
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

CRT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_PATH = os.path.join(CRT_DIR, "tools", "crtctl")
sys.path.insert(0, os.path.join(CRT_DIR, "tools"))
from monoscope.canvas import (Canvas, Renderer, BOLD, DIM, UNDERLINE,   # noqa: E402
                              REVERSE)

TEMPLATE = "// pty test template\n//@CRT_PARAMS@\nvoid mainImage() {}\n"

FAKE_GDBUS = """#!/bin/sh
echo "$@" >> "$GDBUS_LOG"
echo "()"
exit 0
"""


class Screen:
    """Minimal VT screen: CUP/CUU/CUD/CUF/CUB/CHA/VPA/ED/EL + BS/HT/CR/LF;
    SGR/modes ignored. Reconstructs the glyph grid; also keeps the raw bytes."""

    # ECMA-48 CSI: parameter bytes 0x30-0x3F, then *intermediate* bytes
    # 0x20-0x2F, then one final byte 0x40-0x7E. The intermediates matter:
    # DECRQM is CSI ? Pd $ p, and a parser that stops at the "$" swallows
    # the rest of the stream.
    _CSI = re.compile(r"^\[([0-9;?<>=:]*)([ -/]*)([@-~])")

    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.grid = [[" "] * cols for _ in range(rows)]
        # Per-cell colour, so a stateful SGR differ cannot quietly paint the
        # right glyphs in the wrong colours.
        self.fg_grid = [[None] * cols for _ in range(rows)]
        self.bg_grid = [[None] * cols for _ in range(rows)]
        self.cur_fg = None
        self.cur_bg = None
        self.cur_at = 0
        self.y = self.x = 0
        self._pending = ""
        self.raw = bytearray()
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._last_graphic = " "
        # Replies this terminal owes the panel (DECRPM / CPR / DA1). A real
        # terminal answers capability probes; a fake one that stays mute makes
        # the panel correctly conclude it has no synchronized output, so the
        # emulator has to answer them for the probe to be exercised at all.
        self.replies = bytearray()

    def feed(self, data):
        self.raw += data
        text = self._pending + self._decoder.decode(data)
        self._pending = ""
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ch == "\x1b":
                rest = text[i + 1:]
                if not rest:
                    self._pending = text[i:]
                    return
                m = self._CSI.match(rest)
                if m:
                    params, inter, final = m.group(1), m.group(2), m.group(3)
                    if inter:
                        # A sequence carrying intermediates (DECRQM,
                        # DECSCUSR, …) is a query or a mode set — none of them
                        # paint. Answer the ones that expect an answer.
                        if inter == "$" and final == "p" and params == "?2026":
                            # DECRPM: 2 = "recognised, currently reset".
                            self.replies += b"\x1b[?2026;2$y"
                    else:
                        if final == "n" and params == "6":
                            # CPR — 1-based. This is what tells the panel
                            # whether the REP just above it actually repeated.
                            self.replies += ("\x1b[%d;%dR" % (self.y + 1, self.x + 1)).encode()
                        elif final == "c":
                            self.replies += b"\x1b[?62;22c"
                        else:
                            self._csi(params, final)
                    i += 1 + m.end()
                    continue
                if rest[0] == "[":
                    self._pending = text[i:]
                    return
                if rest[0] == "]":
                    bel = rest.find("\x07")
                    st = rest.find("\x1b\\")
                    cands = [c for c in ((bel, 2 + bel), (st, 3 + st)) if c[0] != -1]
                    if not cands:
                        self._pending = text[i:]
                        return
                    cands.sort()
                    i += cands[0][1]
                    continue
                i += 2
                continue
            if ch == "\r":
                self.x = 0
            elif ch == "\n":
                self.y = min(self.rows - 1, self.y + 1)
            elif ch == "\b":
                self.x = max(0, self.x - 1)
            elif ch == "\t":
                self.x = min(self.cols - 1, (self.x // 8 + 1) * 8)
            elif ch >= " ":
                self._putc(ch)
            i += 1

    def _putc(self, ch):
        self._last_graphic = ch
        if self.y < self.rows and self.x < self.cols:
            self.grid[self.y][self.x] = ch
            self.fg_grid[self.y][self.x] = self.cur_fg
            self.bg_grid[self.y][self.x] = self.cur_bg
        self.x += 1
        if self.x >= self.cols:
            self.x = self.cols - 1

    def _csi(self, params, final):
        # NB: `params[:1] in "?<>="` looks equivalent and is not — the empty
        # string is a substring of every string, so that form swallows every
        # parameterless sequence (CSI C, CSI H, CSI K …).
        if params and params[0] in "?<>=":
            return
        p = [int(v) if v else 0 for v in params.split(";")]
        a = p[0] if p else 0
        if final in "Hf":
            self.y = min(self.rows - 1, max(0, (p[0] if len(p) > 0 else 1) - 1))
            self.x = min(self.cols - 1, max(0, (p[1] if len(p) > 1 else 1) - 1))
        elif final == "A":
            self.y = max(0, self.y - max(1, a))
        elif final == "B":
            self.y = min(self.rows - 1, self.y + max(1, a))
        elif final == "C":
            self.x = min(self.cols - 1, self.x + max(1, a))
        elif final == "D":
            self.x = max(0, self.x - max(1, a))
        elif final in "G`":
            self.x = min(self.cols - 1, max(0, a - 1))
        elif final == "d":
            self.y = min(self.rows - 1, max(0, a - 1))
        elif final == "J" and a == 2:
            self.grid = [[" "] * self.cols for _ in range(self.rows)]
        elif final == "m":
            self._sgr(p)
        elif final == "b":
            # REP — repeat the last graphic character.
            for _ in range(max(1, a)):
                self._putc(self._last_graphic)
        elif final == "K":
            rng = range(self.x, self.cols) if a == 0 else range(0, self.x + 1) if a == 1 else range(self.cols)
            for x in rng:
                self.grid[self.y][x] = " "

    def _sgr(self, p):
        """Apply an SGR sequence, exactly as a terminal would: it is *state*,
        not per-cell decoration. This is what makes the differ's delta
        encoding testable — get the state machine wrong and the colours drift
        even though every glyph lands in the right place."""
        i = 0
        if not p:
            p = [0]
        while i < len(p):
            v = p[i]
            if v == 0:
                self.cur_fg = self.cur_bg = None
                self.cur_at = 0
            elif v in (1, 2, 3, 4, 7):
                self.cur_at |= 1 << v
            elif v in (22, 23, 24, 27):
                self.cur_at &= ~(1 << (v - 21)) & ~(1 << (v - 20))
            elif v == 39:
                self.cur_fg = None
            elif v == 49:
                self.cur_bg = None
            elif v in (38, 48) and i + 1 < len(p):
                if p[i + 1] == 2 and i + 4 < len(p):
                    col = (p[i + 2], p[i + 3], p[i + 4])
                    i += 4
                elif p[i + 1] == 5 and i + 2 < len(p):
                    col = ("idx", p[i + 2])
                    i += 2
                else:
                    col = None
                    i += 1
                if v == 38:
                    self.cur_fg = col
                else:
                    self.cur_bg = col
            i += 1

    def text(self):
        return "\n".join("".join(r) for r in self.grid)


class PtyPanel:
    def __init__(self, rows, cols, env, argv=None):
        self.rows, self.cols = rows, cols
        self.screen = Screen(rows, cols)
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        if argv is None:
            override = os.environ.get("MONOSCOPE_PTY_ARGV")
            argv = override.split("|") if override else [sys.executable, TOOLS_PATH, "panel", "--no-splash", "--no-mouse"]
        self.proc = subprocess.Popen(
            argv,
            stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True, start_new_session=True)
        os.close(slave)

    def drain(self, quiet=0.15, timeout=1.0):
        deadline = time.monotonic() + timeout
        last = time.monotonic()
        while time.monotonic() < deadline:
            r, _w, _x = select.select([self.master], [], [], 0.05)
            if r:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    break
                if not data:
                    break
                self.screen.feed(data)
                if self.screen.replies:
                    os.write(self.master, bytes(self.screen.replies))
                    del self.screen.replies[:]
                last = time.monotonic()
            elif time.monotonic() - last >= quiet:
                break
        return self.screen

    def wait_for(self, needle, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.drain(quiet=0.1, timeout=0.4)
            if needle in self.screen.text():
                return True
        return False

    def send(self, keys):
        os.write(self.master, keys.encode())

    def close(self):
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        try:
            os.close(self.master)
        except OSError:
            pass


@unittest.skipUnless(sys.platform.startswith("linux") or sys.platform == "darwin", "needs a POSIX pty")
class MonoscopePtyCase(unittest.TestCase):
    ACTIVE = "commodore-1702-1983"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="monoscope-pty-")
        base = self._tmp.name
        crt = os.path.join(base, "crt")
        os.makedirs(os.path.join(crt, "templates"))
        shutil.copy(os.path.join(CRT_DIR, "params.json"), os.path.join(crt, "params.json"))
        shutil.copytree(os.path.join(CRT_DIR, "presets"), os.path.join(crt, "presets"))
        with open(os.path.join(crt, "templates", "t.glsl.tmpl"), "w") as f:
            f.write(TEMPLATE)
        with open(os.path.join(crt, "state.json"), "w") as f:
            json.dump({"version": 1, "active_preset": self.ACTIVE, "values": {}}, f)
        bindir = os.path.join(base, "bin")
        os.makedirs(bindir)
        gdbus = os.path.join(bindir, "gdbus")
        with open(gdbus, "w") as f:
            f.write(FAKE_GDBUS)
        os.chmod(gdbus, 0o755)
        self.gdbus_log = os.path.join(base, "gdbus.log")
        self.base = base
        self.env = dict(os.environ)
        self.env.update({
            "GHOSTTY_CRT_HOME": base,
            "PATH": bindir + os.pathsep + self.env.get("PATH", ""),
            "GDBUS_LOG": self.gdbus_log,
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "MONOSCOPE_MOTION": "off",     # deterministic frames
        })
        self.env.pop("GHOSTTY_CRT_RELOAD_CMD", None)
        self.env.pop("TMUX", None)
        self.panel = None

    def tearDown(self):
        if self.panel is not None:
            self.panel.close()
        self._tmp.cleanup()

    def open(self, rows, cols):
        self.panel = PtyPanel(rows, cols, self.env)
        self.assertTrue(self.panel.wait_for("BRIGHTNESS"), "panel never drew:\n" + self.panel.screen.text())
        return self.panel

    def test_splash_waits_for_the_operator(self):
        """The logon splash holds until a key arrives — it is not a timer.

        The reveal budget (SPLASH_TICKS) only paces how fast the banner loads
        in. After that the panel must sit on the splash indefinitely; the
        operator decides when to go in.
        """
        env = dict(self.env)
        env["MONOSCOPE_MOTION"] = "full"          # the splash needs motion
        p = PtyPanel(40, 160, env, argv=[sys.executable, TOOLS_PATH, "panel", "--no-mouse"])
        self.panel = p
        self.assertTrue(p.wait_for("press any key"), "splash never drew:\n" + p.screen.text())
        # SPLASH_TICKS is ~2 s of reveal; wait well past it and stay put.
        time.sleep(4.0)
        p.drain(timeout=1.0)
        txt = p.screen.text()
        self.assertIn("CONNECT 14400", txt)
        self.assertNotIn("BRIGHTNESS", txt)       # the bench has NOT taken over
        # any key goes in
        p.send(" ")
        self.assertTrue(p.wait_for("BRIGHTNESS"), "key did not dismiss the splash")
        p.send("q")
        p.drain(timeout=1.0)
        self.assertEqual(p.proc.wait(timeout=5), 0)

    def test_splash_is_skipped_when_stdin_is_not_a_tty(self):
        """A splash that waits for a key must never be entered where no key
        can arrive, or a non-interactive run deadlocks forever."""
        env = dict(self.env)
        env["MONOSCOPE_MOTION"] = "full"
        proc = subprocess.Popen(
            [sys.executable, TOOLS_PATH, "panel", "--no-mouse"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=env)
        out = proc.communicate(timeout=15)[0]
        # No tty at all: the panel refuses rather than hanging on a key.
        self.assertNotEqual(proc.returncode, None)
        self.assertNotIn(b"CONNECT 14400", out)

    def test_probe_detects_sync_and_rep(self):
        """The panel asks the terminal what it can do and believes the answer.

        Our emulator answers DECRQM (recognised) and honours REP, so the panel
        must come out of the probe with both enabled — sync brackets around
        frames and CSI b run-collapsing in the payload.
        """
        p = self.open(40, 160)
        p.send("q")
        p.drain(timeout=1.5)
        p.proc.wait(timeout=5)
        raw = bytes(p.screen.raw)
        self.assertIn(b"\x1b[?2026$p", raw)         # DECRQM went out
        self.assertIn(b"\x1b[6n", raw)              # REP probe went out
        self.assertIn(b"\x1b[?2026h", raw)          # ... and sync was enabled
        self.assertRegex(raw, rb"\x1b\[\d+b")       # ... and REP is in use

    def test_renderer_output_matches_a_terminal_exactly(self):
        """Fuzz the differ against the emulator.

        Every byte-saving trick in the renderer (relative cursor motion, REP
        run-collapsing, row fast-skip) is a chance to put a glyph in the wrong
        cell. Drive 400 random frames through both and require the terminal's
        grid to equal the canvas after every single one.
        """
        alphabet = " ABCDE\u00b7\u2593\u2592\u2591"
        PALETTE = [(200, 200, 200), (9, 9, 9), (255, 0, 0), (0, 128, 64),
                   (12, 34, 56), (240, 248, 255)]
        for rep in (False, True):
            rng = random.Random(1234)
            w, h = 40, 8
            screen = Screen(h, w)
            rend = Renderer(truecolor=True, rep=rep)
            for frame in range(400):
                cv = Canvas(w, h)
                for y in range(h):
                    for x in range(w):
                        # A small palette with a dominant background is what
                        # the real panel looks like, and it is the case the
                        # delta encoder is tuned for; the attribute bits make
                        # it exercise the "must fall back to a full reset"
                        # path too.
                        fg = rng.choice(PALETTE)
                        bg = (0, 0, 0) if rng.random() < 0.8 else rng.choice(PALETTE)
                        at = rng.choice((0, 0, 0, BOLD, DIM, BOLD | UNDERLINE, REVERSE))
                        cv.put(x, y, rng.choice(alphabet), fg=fg, bg=bg, at=at)
                if frame % 37 == 0:
                    rend.heal_band(frame % h, frame % h + 3)
                screen.feed(rend.render(cv))
                want = "\n".join("".join(cv.ch[y * w + x] or " " for x in range(w))
                                 for y in range(h))
                self.assertEqual(want, screen.text(),
                                 "rep=%s frame=%d" % (rep, frame))
                for y in range(h):
                    for x in range(w):
                        i = y * w + x
                        self.assertEqual(
                            (screen.fg_grid[y][x], screen.bg_grid[y][x]),
                            (cv.fg[i], cv.bg[i]),
                            "colour drift rep=%s frame=%d at %d,%d" % (rep, frame, x, y))

    def test_bench_draws_at_200x60_and_100x30(self):
        for rows, cols in ((60, 200), (30, 100)):
            p = self.open(rows, cols)
            txt = p.screen.text()
            self.assertIn("MONOSCOPE", txt)
            self.assertIn("VIDEO", txt)
            self.assertIn(self.ACTIVE.upper(), txt)
            if cols >= 150:
                self.assertIn("SCOPE", txt)
                self.assertIn("GROUPS", txt)
            for line in p.screen.grid:
                self.assertEqual(len(line), cols)
            p.send("q")
            p.drain(timeout=1.0)
            self.assertEqual(p.proc.wait(timeout=5), 0)
            p.close()
            self.panel = None

    def test_terminal_hygiene(self):
        p = self.open(40, 140)
        p.send("q")
        p.drain(timeout=1.5)
        p.proc.wait(timeout=5)
        raw = bytes(p.screen.raw)
        self.assertIn(b"\x1b[?1049h", raw)          # alt screen entered
        self.assertIn(b"\x1b[?1049l", raw)          # ... and left
        self.assertIn(b"\x1b[?25h", raw)            # cursor visible again
        self.assertIn(b"\x1b[?2026h", raw)          # frames are sync-bracketed
        self.assertIn(b"\x1b[?2026l", raw)
        self.assertIn(b";38;2;", raw)               # truecolor SGR
        self.assertIn(b";48;2;", raw)
        self.assertNotIn(b"\x1b]4;", raw)           # never touches the palette
        self.assertNotIn(b"\x1b]104", raw)
        self.assertNotIn(b";38;5;", raw)            # no 256-colour quantisation on a truecolor terminal
        # every sync bracket is closed (close() emits one extra ESU on the way out)
        self.assertEqual(raw.count(b"\x1b[?2026h") + 1, raw.count(b"\x1b[?2026l"))

    def test_knob_change_regenerates_saves_and_reloads(self):
        p = self.open(40, 140)
        p.send("3")               # jump to SCAN
        p.send("\x1b[C")          # right: RASTER LINES +1
        p.drain(timeout=1.0)
        time.sleep(0.5)           # debounce
        p.drain(timeout=1.0)
        st = json.load(open(os.path.join(self.base, "crt", "state.json")))
        self.assertIn("scan_lines", st["values"])
        self.assertTrue(os.path.exists(os.path.join(self.base, "shaders", "t.glsl")))
        with open(self.gdbus_log) as f:
            log = f.read()
        self.assertIn("reload-config", log)
        self.assertIn("org.gtk.Actions.Activate", log)
        p.send("q")
        p.drain(timeout=1.0)
        self.assertEqual(p.proc.wait(timeout=5), 0)

    def test_bank_sort_cycles_and_apply(self):
        p = self.open(40, 160)
        p.send("p")
        self.assertTrue(p.wait_for("TUBE BANK"))
        self.assertIn("SORT NAME", p.screen.text())
        p.send("s")
        self.assertTrue(p.wait_for("SORT YEAR"))
        for mode in ("TYPE", "MANUFACTURER", "PRICE", "RESOLUTION", "NAME"):
            p.send("s")
            self.assertTrue(p.wait_for("SORT " + mode), mode)
        # the details show the selected tube's prose
        self.assertIn("hearth", p.screen.text())     # commodore-1702 description
        p.send("j")
        p.drain(timeout=0.6)
        p.send("\r")
        self.assertTrue(p.wait_for("applied"))
        st = json.load(open(os.path.join(self.base, "crt", "state.json")))
        self.assertEqual(st["active_preset"], "conrac-reference-1978")
        time.sleep(0.5)
        p.drain(timeout=0.8)
        with open(self.gdbus_log) as f:
            self.assertIn("reload-config", f.read())
        p.send("q")
        p.drain(timeout=1.0)
        self.assertEqual(p.proc.wait(timeout=5), 0)

    def test_type_a_value_and_help(self):
        p = self.open(40, 140)
        p.send("3\r640\r")        # SCAN → RASTER LINES → type 640 → commit
        p.drain(timeout=1.0)
        self.assertTrue(p.wait_for(" 640"))
        st = json.load(open(os.path.join(self.base, "crt", "state.json")))
        self.assertEqual(st["values"]["scan_lines"], 640)
        p.send("?")
        self.assertTrue(p.wait_for("TYPING A VALUE"))
        p.send("\x1b")
        time.sleep(0.2)
        p.send("q")
        p.drain(timeout=1.0)
        self.assertEqual(p.proc.wait(timeout=5), 0)


if __name__ == "__main__":
    unittest.main()

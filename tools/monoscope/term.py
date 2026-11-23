"""monoscope.term — the terminal driver.

Raw mode, alternate screen, cursor, synchronized output (DEC 2026), mouse,
bracketed paste, kitty keyboard flags, SIGWINCH-driven resize, and a
restore-no-matter-what teardown (atexit + signal handlers + context manager).

Design rules (all of them are the difference between "works on my box" and
"never leaves the terminal wrecked"):

* Every mode we turn on is turned off in :meth:`Terminal.close`, in reverse
  order, and close() is idempotent. It runs from ``atexit``, from SIGTERM/
  SIGHUP handlers, from ``__exit__`` and from the panic path.
* We never touch the terminal palette (no OSC 4, no init_color). Colors are
  emitted per cell as SGR 38;2 / 48;2 (truecolor) or, when the terminal
  declares no truecolor, quantized to the xterm-256 cube by the canvas.
* Output is buffered per frame and flushed with a single ``os.write`` inside
  a ``?2026h … ?2026l`` bracket, so the terminal paints the frame atomically
  (no tearing, no half-drawn frames under a slow shader pipeline).
* Input is read non-blocking with ``select`` and decoded by :mod:`keys`.

Python 3 stdlib only.
"""

from __future__ import annotations

import atexit
import errno
import fcntl
import os
import re
import select
import signal
import struct
import sys
import termios
import time
import tty

__all__ = ["Terminal", "TermCaps", "detect_caps"]

# --- escape sequences ------------------------------------------------------
ESC = "\x1b"
CSI = ESC + "["
ALT_SCREEN_ON = CSI + "?1049h"
ALT_SCREEN_OFF = CSI + "?1049l"
CURSOR_HIDE = CSI + "?25l"
CURSOR_SHOW = CSI + "?25h"
SYNC_ON = CSI + "?2026h"
SYNC_OFF = CSI + "?2026l"
MOUSE_ON = CSI + "?1000h" + CSI + "?1002h" + CSI + "?1006h"   # press/release, drag, SGR
MOUSE_OFF = CSI + "?1006l" + CSI + "?1002l" + CSI + "?1000l"
PASTE_ON = CSI + "?2004h"
PASTE_OFF = CSI + "?2004l"
FOCUS_ON = CSI + "?1004h"
FOCUS_OFF = CSI + "?1004l"
# kitty keyboard protocol: push flags 1 (disambiguate escape codes) so that
# Esc, Shift+arrows, Ctrl+letters arrive unambiguously; pop on exit.
KITTY_PUSH = CSI + ">1u"
KITTY_POP = CSI + "<u"
# Capability probes, all answered on stdin (see Terminal._probe):
#   DECRQM ?2026  — does the terminal actually implement synchronized output?
#                   Emitting ?2026h blind is how you *think* you have atomic
#                   frames while the terminal tears happily underneath you.
#   REP           — write one glyph, ask for two more, read the cursor column.
#                   A terminal without REP ignores the CSI b and leaves the
#                   cursor one column along instead of three.
#   DA1           — every terminal answers this, so it terminates the read
#                   even when the two probes above are silently dropped.
DECRQM_2026 = CSI + "?2026$p"
REP_PROBE = CSI + "H" + "X" + CSI + "2b" + CSI + "6n"
DA1 = CSI + "c"

# Probe replies. They arrive interleaved with real keystrokes, so each is
# matched precisely and stripped; whatever is left over is real input.
_DECRPM_2026_RE = re.compile(rb"\x1b\[\?2026;(\d+)\$y")
_CPR_RE = re.compile(rb"\x1b\[(?:\d+);(\d+)R")
_DA1_RE = re.compile(rb"\x1b\[\?[0-9;]*c")
_PROBE_REPLY_RE = re.compile(
    rb"\x1b\[\?2026;\d+\$y|\x1b\[\d+;\d+R|\x1b\[\?[0-9;]*c")
# A probe reply that has only half-arrived: ESC [ followed by parameter and
# intermediate bytes and nothing else, sitting at the very end of the buffer.
_PARTIAL_CSI_RE = re.compile(rb"\x1b\[[0-9;?]*[$]?$")
# How long after open() a probe reply may still turn up. Terminals answer in
# microseconds; a loaded box under tmux can take longer. Outside this window
# no query is outstanding, so nothing is filtered and every byte is input.
PROBE_GRACE_S = 2.0

_now = time.monotonic
SGR_RESET = CSI + "0m"
CLEAR = CSI + "2J" + CSI + "H"
# Terminals that do not know these private modes ignore them (DECSET with an
# unknown parameter is a no-op by spec), so it is safe to emit them blind.


class TermCaps:
    """What we believe about the terminal, from environment + probes."""

    __slots__ = ("truecolor", "utf8", "tmux", "term", "kitty_kb", "colorterm",
                 "columns", "rows", "program", "sync_2026", "rep")

    def __init__(self):
        env = os.environ
        self.term = env.get("TERM", "")
        self.colorterm = env.get("COLORTERM", "")
        self.tmux = bool(env.get("TMUX")) or self.term.startswith("tmux") or self.term.startswith("screen")
        self.program = env.get("TERM_PROGRAM", "") or ("ghostty" if env.get("GHOSTTY_RESOURCES_DIR") else "")
        # Truecolor: COLORTERM is the de-facto contract; ghostty/kitty/wezterm/
        # alacritty/foot all set it. Inside tmux COLORTERM may be inherited
        # from the outer terminal (fine) or absent — tmux ≥3.2 passes RGB
        # through when the outer terminal supports it; assume yes on tmux
        # unless NO_COLOR/MONOSCOPE_COLOR=256 says otherwise.
        ct = self.colorterm.lower()
        forced = env.get("MONOSCOPE_COLOR", "").lower()
        if forced in ("24bit", "truecolor", "rgb"):
            self.truecolor = True
        elif forced in ("256", "8bit"):
            self.truecolor = False
        else:
            self.truecolor = (ct in ("truecolor", "24bit")
                              or self.program.lower() in ("ghostty", "kitty", "wezterm", "alacritty", "iterm.app", "foot")
                              or "ghostty" in self.term or "kitty" in self.term
                              or self.tmux)
        lang = (env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG") or "").lower()
        self.utf8 = ("utf-8" in lang or "utf8" in lang) or env.get("MONOSCOPE_UTF8", "") == "1"
        if not lang and sys.stdout.encoding and "utf" in sys.stdout.encoding.lower():
            self.utf8 = True
        # kitty keyboard flags: ghostty, kitty, wezterm, foot implement them;
        # tmux 3.5+ translates. We push blind (unknown → ignored) but only
        # *rely* on it where we saw the CSI-u shape arrive.
        self.kitty_kb = True
        self.columns, self.rows = 80, 24
        # Filled in by Terminal._probe() against the live terminal.
        # Never assumed: assuming these is how a panel tears.
        self.sync_2026 = False
        self.rep = False

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


def detect_caps():
    return TermCaps()


def _winsize(fd):
    try:
        packed = fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
        rows, cols, _, _ = struct.unpack("HHHH", packed)
        if rows > 0 and cols > 0:
            return cols, rows
    except (OSError, ValueError):
        pass
    try:
        sz = os.get_terminal_size(fd)
        return sz.columns, sz.lines
    except OSError:
        return 80, 24


class Terminal:
    """Owns the tty for the lifetime of the panel.

    Usage::

        with Terminal(mouse=True) as term:
            while running:
                for ev in term.read_events(timeout=0.05): ...
                term.write_frame(bytes_or_str)
    """

    def __init__(self, mouse=False, focus=False, kitty=True, sync=True):
        self.in_fd = sys.stdin.fileno()
        self.out_fd = sys.stdout.fileno()
        self.caps = detect_caps()
        self.mouse = mouse
        self.focus = focus
        self.kitty = kitty and self.caps.kitty_kb
        self.sync = sync
        self._saved = None
        self._open = False
        self._resized = False
        self._prev_handlers = {}
        self._pending = b""
        self._probe_grace_until = 0.0
        self.cols, self.rows = _winsize(self.out_fd)
        self.caps.columns, self.caps.rows = self.cols, self.rows

    # -- lifecycle ---------------------------------------------------------

    def open(self):
        if self._open:
            return self
        if not os.isatty(self.in_fd) or not os.isatty(self.out_fd):
            raise RuntimeError("monoscope needs a tty on stdin and stdout")
        self._saved = termios.tcgetattr(self.in_fd)
        tty.setraw(self.in_fd, termios.TCSANOW)
        # keep output post-processing (ONLCR) off in raw mode: we emit \r\n never \n
        seq = [ALT_SCREEN_ON, CURSOR_HIDE, CLEAR]
        if self.kitty:
            seq.append(KITTY_PUSH)
        seq.append(PASTE_ON)
        if self.mouse:
            seq.append(MOUSE_ON)
        if self.focus:
            seq.append(FOCUS_ON)
        self._raw_write("".join(seq))
        self._open = True
        # Register the teardown BEFORE anything that can raise. From here on
        # raw mode is set and the alt screen is entered, so an exception with
        # no atexit hook in place leaves the operator's terminal wrecked —
        # which is exactly what this module's first design rule forbids.
        atexit.register(self.close)
        self._probe()
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGQUIT):
            try:
                self._prev_handlers[sig] = signal.signal(sig, self._on_signal)
            except (ValueError, OSError):
                pass
        try:
            self._prev_handlers[signal.SIGWINCH] = signal.signal(signal.SIGWINCH, self._on_winch)
        except (ValueError, OSError):
            pass
        # SIGTSTP (Ctrl-Z): restore before suspending, re-enter after
        try:
            self._prev_handlers[signal.SIGTSTP] = signal.signal(signal.SIGTSTP, self._on_tstp)
            self._prev_handlers[signal.SIGCONT] = signal.signal(signal.SIGCONT, self._on_cont)
        except (ValueError, OSError, AttributeError):
            pass
        return self

    def _probe(self, timeout=0.25):
        """Ask the terminal what it can actually do, and believe the answer.

        Two capabilities decide whether the panel tears:

        * **Synchronized output (DEC 2026).** Without it every frame is
          painted incrementally and a fast update rate shows as tearing.
          ``?2026h`` is a private mode, so an unknown terminal ignores it
          silently — we would never find out. DECRQM asks instead.
        * **REP (``CSI Pn b``).** Collapsing runs is the single biggest
          payload reduction available on a block-shading panel, but a
          terminal without REP would drop the repeats and leave holes in the
          picture. So we test it for real rather than reading tea leaves from
          ``$TERM``: print one ``X``, ask for two more, and read back the
          cursor column. Column 4 means REP works; column 2 means it does not.

        DA1 goes out last as the backstop — every terminal answers it, so the
        read ends promptly even when both probes are dropped on the floor.
        The whole exchange happens in the alt screen, before the first frame,
        and the screen is cleared afterwards.
        """
        env = os.environ
        forced_sync = env.get("MONOSCOPE_SYNC", "").lower()
        forced_rep = env.get("MONOSCOPE_REP", "").lower()
        self.caps.sync_2026 = False
        self.caps.rep = False
        self._probe_grace_until = _now() + PROBE_GRACE_S
        try:
            self._raw_write(DECRQM_2026 + REP_PROBE + DA1)
        except OSError:
            return
        buf = b""
        deadline = _now() + timeout
        while True:
            remaining = deadline - _now()
            if remaining <= 0:
                break
            try:
                r, _, _ = select.select([self.in_fd], [], [], remaining)
            except (InterruptedError, OSError):
                break
            if not r:
                break
            try:
                chunk = os.read(self.in_fd, 1024)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if _DA1_RE.search(buf):      # the backstop answered: everyone is done
                break
        m = _DECRPM_2026_RE.search(buf)
        if m:
            # 0 = not recognised, 4 = permanently reset. 1/2/3 = implemented.
            self.caps.sync_2026 = m.group(1) in (b"1", b"2", b"3")
        m = _CPR_RE.search(buf)
        if m:
            self.caps.rep = int(m.group(1)) >= 4
        if forced_sync in ("0", "off", "no"):
            self.caps.sync_2026 = False
        elif forced_sync in ("1", "on", "yes", "force"):
            self.caps.sync_2026 = True
        if forced_rep in ("0", "off", "no"):
            self.caps.rep = False
        elif forced_rep in ("1", "on", "yes", "force"):
            self.caps.rep = True
        # Only bracket frames the terminal will actually honour; emitting
        # ?2026h/l around every frame otherwise is two wasted writes a frame
        # and a false sense of atomicity.
        self.sync = self.sync and self.caps.sync_2026
        # Whatever the probe printed, wipe it: the first frame must start from
        # a screen we fully own.
        self._raw_write(CLEAR)
        # Anything the user typed during the probe (or a probe reply we did
        # not match) is handed to the key decoder rather than dropped.
        leftover = _PROBE_REPLY_RE.sub(b"", buf)
        if leftover:
            self._pending += leftover

    def close(self):
        if not self._open:
            return
        self._open = False
        seq = [SYNC_OFF]
        if self.focus:
            seq.append(FOCUS_OFF)
        if self.mouse:
            seq.append(MOUSE_OFF)
        seq.append(PASTE_OFF)
        if self.kitty:
            seq.append(KITTY_POP)
        seq += [SGR_RESET, CURSOR_SHOW, ALT_SCREEN_OFF]
        try:
            self._raw_write("".join(seq))
        except OSError:
            pass
        if self._saved is not None:
            try:
                termios.tcsetattr(self.in_fd, termios.TCSADRAIN, self._saved)
            except termios.error:
                pass
        for sig, h in self._prev_handlers.items():
            try:
                signal.signal(sig, h)
            except (ValueError, OSError):
                pass
        self._prev_handlers = {}
        try:
            atexit.unregister(self.close)
        except Exception:
            pass

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
        return False

    # -- signals -----------------------------------------------------------

    def _on_signal(self, signum, frame):
        self.close()
        # re-raise default behaviour so the process actually terminates
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    def _on_winch(self, signum, frame):
        self._resized = True

    def _on_tstp(self, signum, frame):
        was_open = self._open
        self.close()
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)
        # on SIGCONT we come back through _on_cont
        self._suspended_open = was_open

    def _on_cont(self, signum, frame):
        if getattr(self, "_suspended_open", False):
            self._suspended_open = False
            self.open()
            self._resized = True

    # -- geometry ----------------------------------------------------------

    def poll_resize(self):
        """Returns True (and refreshes cols/rows) if a resize happened since
        the last call. Also re-checks the size every call — some multiplexers
        deliver no SIGWINCH."""
        cols, rows = _winsize(self.out_fd)
        changed = self._resized or cols != self.cols or rows != self.rows
        self._resized = False
        self.cols, self.rows = cols, rows
        self.caps.columns, self.caps.rows = cols, rows
        return changed

    # -- output ------------------------------------------------------------

    def _raw_write(self, s):
        data = s.encode("utf-8", "replace") if isinstance(s, str) else s
        view = memoryview(data)
        while view:
            try:
                n = os.write(self.out_fd, view)
            except InterruptedError:
                continue
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    select.select([], [self.out_fd], [], 0.05)
                    continue
                raise
            view = view[n:]

    def write_frame(self, payload):
        """Emit one frame atomically (DEC 2026 bracket when enabled)."""
        if not payload:
            return
        if isinstance(payload, str):
            payload = payload.encode("utf-8", "replace")
        if self.sync:
            payload = SYNC_ON.encode() + payload + SYNC_OFF.encode()
        self._raw_write(payload)

    def bell(self):
        self._raw_write("\x07")

    def set_mouse(self, on):
        """Toggle mouse reporting live (off lets the user select text)."""
        on = bool(on)
        if on == self.mouse:
            return
        self.mouse = on
        self._raw_write(MOUSE_ON if on else MOUSE_OFF)

    # -- input -------------------------------------------------------------

    def read_bytes(self, timeout):
        """Block up to `timeout` seconds for input; return raw bytes ('' on
        timeout). Reads everything available once something arrives."""
        # Bytes held back as a possible half-arrived probe reply are released
        # the moment the probe window closes, so a real keystroke that merely
        # looked like one is never swallowed for good.
        if self._pending and _now() > self._probe_grace_until:
            held, self._pending = self._pending, b""
            return held
        try:
            r, _, _ = select.select([self.in_fd], [], [], max(0.0, timeout))
        except InterruptedError:
            return b""
        except (ValueError, OSError):
            return b""
        if not r:
            # Nothing arrived. A byte held back as a possible half-arrived
            # probe reply can only be completed by the bytes right behind it,
            # so a timeout means it never was one — release it rather than sit
            # on a real keystroke until the grace window closes.
            if self._pending:
                held, self._pending = self._pending, b""
                return held
            return b""
        chunks = []
        while True:
            try:
                data = os.read(self.in_fd, 4096)
            except InterruptedError:
                continue
            except BlockingIOError:
                break
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
            if len(data) < 4096:
                break
            r, _, _ = select.select([self.in_fd], [], [], 0)
            if not r:
                break
        return self._filter_probe_replies(b"".join(chunks))

    def _filter_probe_replies(self, data):
        """Keep capability-probe answers out of the keystroke stream.

        A DECRPM/CPR/DA1 answer that reaches the key decoder is not ignored —
        it is *decoded*, and ``ESC [ 1 ; 4 R`` comes out the other side as a
        Shift-Alt-F3 keypress that the operator never made. Terminals normally
        answer in microseconds, but a slow one (or tmux) can reply after the
        probe window has closed, so the replies are stripped for a grace
        period rather than only during the probe itself.

        Outside that window nothing is outstanding, so nothing is filtered.
        """
        data = self._pending + data
        self._pending = b""
        if not data:
            return b""
        if _now() > self._probe_grace_until:
            return data
        # Hold back a reply that has only half-arrived so it is not decoded as
        # a lone Esc followed by garbage.
        m = _PARTIAL_CSI_RE.search(data)
        if m:
            self._pending = data[m.start():]
            data = data[:m.start()]
        return _PROBE_REPLY_RE.sub(b"", data)

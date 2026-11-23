"""monoscope.app — the event loop and the update function.

    poll → update(model, event) → tick → render(model) → diff → write

One loop, one frame buffer, modes as model fields (bench / entry / bank /
sheet / confirm / help / flatfield). Two clocks: an ambient tick rate for
color motion, and a 30 fps response window after any input.

Value changes: every knob change regenerates the shaders and saves state at
once (cheap, atomic), then arms a debounced reload (150 ms) that fires in a
worker thread so a slow D-Bus never freezes the panel.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time

from .term import Terminal
from .keys import Decoder, SHIFT, CTRL, ALT
from .canvas import Canvas, Renderer
from .model import Model, DEBOUNCE_S, ACCEL_WINDOW_S, ACCEL_AFTER, ACCEL_MULT, RESPONSE_S, MOTION_MODES
from .bankstate import BankState
from .sheetstate import SheetState
from . import views
from . import color as C

__all__ = ["App", "run_panel"]

AMBIENT_FPS_DEFAULT = 8
RESPONSE_FPS = 30
# The self-heal repaints the screen against terminal state drift (a stray
# write from another process, a shader reload that ate a cell). It used to do
# that as one whole-screen repaint, which on a 200x50 panel is a ~100 kB
# single write — the largest payload the panel ever produces and a prime
# cause of visible tearing. It now walks the screen a band at a time, so the
# whole surface is still refreshed every HEAL_S but no individual frame ever
# costs more than HEAL_BAND_ROWS rows.
HEAL_S = 20.0
HEAL_BAND_ROWS = 6

ENTRY_CHARS = set("0123456789.-+eE")


class App:
    def __init__(self, ctl, dest, crtctl_mod, motion=None, flat_field=False, mouse=True, ambient_fps=None, splash=True):
        self.ctl = ctl
        self.dest = dest
        self.cm = crtctl_mod
        motion = motion or os.environ.get("MONOSCOPE_MOTION") or "full"
        self.model = Model(ctl, dest, crtctl_mod, motion=motion)
        if flat_field:
            self.model.mode = "flatfield"
        elif (splash and self.model.motion != "off"
              and os.environ.get("MONOSCOPE_SPLASH", "1") != "0"
              # the splash blocks until a key arrives, so it must never be
              # entered where no key can ever arrive (piped stdin, CI).
              and sys.stdin.isatty()):
            self.model.mode = "splash"
            self.model.splash_t0 = 0
        self.mouse = mouse
        self.model.mouse_on = bool(mouse)
        self.ambient_fps = float(ambient_fps or os.environ.get("MONOSCOPE_FPS") or AMBIENT_FPS_DEFAULT)
        self.running = True
        self.dirty = True
        self.term = None
        self.rend = None
        self.cv = None
        self.reload_q = queue.Queue()
        self.reload_thread = None
        self.last_heal = 0.0
        self.heal_band = 0
        self.exit_code = 0
        self._timing = open(os.environ["MONOSCOPE_TIMING"], "a") if os.environ.get("MONOSCOPE_TIMING") else None
        ctl.on_warn = self._on_warn

    # -- infrastructure -------------------------------------------------------

    def _invalidate(self):
        if self.rend is not None:
            self.rend.invalidate()

    def _on_warn(self, msg):
        m = self.model
        m.warnings.append(msg)
        m.toast(msg, "warn", 5.0)

    def run(self):
        m = self.model
        with Terminal(mouse=self.mouse, focus=False) as term:
            self.term = term
            self.rend = Renderer(truecolor=term.caps.truecolor, rep=term.caps.rep)
            self.cv = Canvas(term.cols, term.rows, bg=m.fam.ground, fg=m.fam.ink)
            dec = Decoder()
            last_frame = 0.0
            m.last_input_t = time.monotonic()
            while self.running:
                now = time.monotonic()
                # frame cadence
                if m.mode == "splash":
                    from .splashview import SPLASH_TICKS
                    # The splash waits for the operator — it never dismisses
                    # itself. SPLASH_TICKS is the *reveal* budget only: hold
                    # the 30 fps response clock while the banner loads in, then
                    # drop to ambient so an unattended panel is not a busy loop.
                    if m.tick - m.splash_t0 <= SPLASH_TICKS:
                        m.last_input_t = now
                if m.motion == "off":
                    interval = 1.0 / RESPONSE_FPS if self.dirty else 0.25
                else:
                    burst = (now - m.last_input_t) < RESPONSE_S
                    ambient = self.ambient_fps if m.motion == "full" else min(self.ambient_fps, 4.0)
                    interval = 1.0 / RESPONSE_FPS if burst else 1.0 / ambient
                wait = max(0.0, (last_frame + interval) - now)
                if m.reload_deadline is not None:
                    wait = min(wait, max(0.0, m.reload_deadline - now))
                data = term.read_bytes(wait)
                events = dec.feed(data) if data else dec.flush()
                if events:
                    m.last_input_t = time.monotonic()
                for ev in events:
                    try:
                        self.update(ev)
                    except Exception as e:  # never let a handler kill the panel
                        m.toast("error: %s" % e, "bad", 6.0)
                        m.warnings.append("handler error: %r" % (e,))
                    self.dirty = True
                    if not self.running:
                        break
                if not self.running:
                    break
                self._service_reload()
                if term.poll_resize():
                    self.cv = Canvas(term.cols, term.rows, bg=m.fam.ground, fg=m.fam.ink)
                    self._invalidate()
                    self.dirty = True
                now = time.monotonic()
                if now - last_frame >= interval * 0.999 or (self.dirty and m.motion == "off"):
                    if m.motion != "off" or self.dirty:
                        m.tick += 1
                        bands = max(1, -(-term.rows // HEAL_BAND_ROWS))
                        if now - self.last_heal > HEAL_S / bands:
                            self.last_heal = now
                            y0 = self.heal_band * HEAL_BAND_ROWS
                            self.rend.heal_band(y0, y0 + HEAL_BAND_ROWS)
                            self.heal_band = (self.heal_band + 1) % bands
                        _t0 = time.perf_counter()
                        views.render(m, self.cv, m.tick)
                        _t1 = time.perf_counter()
                        payload = self.rend.render(self.cv)
                        _t2 = time.perf_counter()
                        term.write_frame(payload)
                        _t3 = time.perf_counter()
                        if self._timing is not None:
                            self._timing.write("%d render=%.1f diff=%.1f write=%.1f bytes=%d\n" % (m.tick, (_t1-_t0)*1e3, (_t2-_t1)*1e3, (_t3-_t2)*1e3, len(payload)))
                        self.dirty = False
                    last_frame = now
            # flush a pending reload before leaving
            if m.reload_deadline is not None:
                m.reload_deadline = None
                self._do_reload_sync()
        return self.exit_code

    # -- reload -----------------------------------------------------------------

    def _service_reload(self):
        m = self.model
        now = time.monotonic()
        if m.reload_deadline is not None and now >= m.reload_deadline and self.reload_thread is None:
            m.reload_deadline = None
            self._start_reload()
        try:
            while True:
                ok, detail = self.reload_q.get_nowait()
                m.last_reload = (ok, detail, time.strftime("%H:%M:%S"))
                m.reload_count += 1
                self.reload_thread = None
                if not ok:
                    m.toast("reload failed: %s" % detail, "bad", 6.0)
                self.dirty = True
        except queue.Empty:
            pass

    def _start_reload(self):
        ctl, dest, q = self.ctl, self.dest, self.reload_q

        def work():
            try:
                ok, detail = ctl.reload(dest)
            except Exception as e:
                ok, detail = False, str(e)
            q.put((ok, detail))
        t = threading.Thread(target=work, name="monoscope-reload", daemon=True)
        self.reload_thread = t
        t.start()

    def _do_reload_sync(self):
        try:
            ok, detail = self.ctl.reload(self.dest)
        except Exception as e:
            ok, detail = False, str(e)
        self.model.last_reload = (ok, detail, time.strftime("%H:%M:%S"))

    def _commit(self, regen=True):
        """Persist a change: regenerate shaders + save state, arm the reload."""
        m = self.model
        try:
            if regen:
                self.ctl.generate()
            self.ctl.save_state()
        except Exception as e:
            m.toast("write failed: %s" % e, "bad", 6.0)
            return
        m.arm_reload()

    # -- value changes -----------------------------------------------------------

    def _set_value(self, key, new, record=True, force=False):
        m = self.model
        old = self.ctl.values.get(key)
        if new == old:
            return False
        self.ctl.values[key] = new
        if record:
            m.undo.append((key, old, new))
            m.undo = m.undo[-200:]
            m.redo.clear()
        if key in ("phosphor", "mask_type", "mask_strength"):
            m.refresh_family()
            self._invalidate()
        self._commit()
        return True

    def _adjust(self, row, direction, big):
        m = self.model
        ctl = self.ctl
        spec = row.spec
        # acceleration on rapid repeats
        now = time.monotonic()
        if now - m.accel_last < ACCEL_WINDOW_S:
            m.accel_n += 1
        else:
            m.accel_n = 0
        m.accel_last = now
        mult = (5 if big else 1) * (ACCEL_MULT if m.accel_n >= ACCEL_AFTER else 1)
        if row.kind == "rotary":
            step = spec.get("step") or (1 if spec.get("type") == "int" else 0.01)
            cur = ctl.values.get(row.key)
            new = cur + direction * step * mult
            lo, hi = spec.get("min"), spec.get("max")
            t = spec.get("type")
            # arrow-key travel stays inside the nominal range unless already outside
            # (typing is the door out; arrows bring you back in)
            if lo is not None and hi is not None:
                if cur < lo or cur > hi:
                    pass
                else:
                    new = max(float(lo), min(float(hi), new))
            new = self.cm.normalize_value(row.key, spec, new) if (lo is None or hi is None or (float(lo) <= new <= float(hi))) else (int(round(new)) if t == "int" else round(new, 10))
            self._set_value(row.key, new)
        elif row.kind == "switch":
            self._set_value(row.key, not bool(ctl.values.get(row.key)))
        elif row.kind == "selector":
            members = list((spec.get("values") or {}).keys())
            cur = ctl.values.get(row.key)
            i = members.index(cur) if cur in members else 0
            self._set_value(row.key, members[(i + direction) % len(members)])
        elif row.kind == "swapstyle":
            styles = list(getattr(self.cm, "SWAP_STYLES", ("carry", "degauss", "fresh")))
            cur = getattr(ctl, "swap_style", "carry")
            i = styles.index(cur) if cur in styles else 0
            ctl.swap_style = styles[(i + direction) % len(styles)]
            ctl.save_state()
            m.toast("swap style: %s" % ctl.swap_style, "info", 2.0)
        elif row.kind == "terminal" and row.key == "font-size":
            cur = ctl.terminal.get("font-size")
            new = (float(cur) if cur is not None else 14.0) + direction * mult
            new = max(6.0, min(40.0, new))
            try:
                ctl.set_terminal("font-size", new)
            except Exception as e:
                m.toast(str(e), "bad")
                return
            self._commit()
        elif row.kind in ("button", "action"):
            self._activate(row)

    def _activate(self, row):
        m = self.model
        ctl = self.ctl
        if row.kind == "button" and row.key == "power_on":
            state, changed = ctl.power("toggle")
            m.fired[row.key] = time.monotonic()
            m.toast("power %s" % ("on" if state else "off"), "ok", 2.0)
            self._commit()
        elif row.kind == "action" and row.key == "degauss":
            ctl.degauss()
            m.fired[row.key] = time.monotonic()
            m.toast("degauss fired", "ok", 2.0)
            self._commit()
        elif row.kind == "action" and row.key == "erase":
            self._fire_erase()
        elif row.kind == "switch":
            self._adjust(row, 1, False)
        elif row.kind in ("selector", "swapstyle"):
            self._adjust(row, 1, False)
        elif row.kind == "rotary" or (row.kind == "terminal" and row.key == "font-size"):
            self._begin_entry(row)
        elif row.kind == "terminal":
            self._begin_entry(row)

    def _fire_erase(self):
        m = self.model
        self.ctl.erase()
        m.fired["erase"] = time.monotonic()
        m.toast("erase / tube-swap fired", "ok", 2.0)
        self._commit()

    def _reset_default(self, row):
        m = self.model
        if row.kind in ("rotary", "switch", "selector"):
            d = self.ctl.defaults.get(row.key)
            if self._set_value(row.key, d):
                m.toast("%s → default %s" % (row.label, self.cm.display_value(row.spec, d)), "info", 2.0)
        elif row.kind == "terminal":
            if self.ctl.unset_terminal(row.key):
                self._commit()
                m.toast("%s cleared" % row.key, "info", 2.0)

    def _revert_inherited(self, row):
        m = self.model
        if row.kind in ("rotary", "switch", "selector"):
            b = m.baseline().get(row.key)
            if self._set_value(row.key, b):
                m.toast("%s ◂ %s" % (row.label, self.cm.display_value(row.spec, b)), "info", 2.0)

    def _undo(self):
        m = self.model
        if not m.undo:
            m.toast("nothing to undo", "info", 1.5)
            return
        key, old, new = m.undo.pop()
        m.redo.append((key, old, new))
        self.ctl.values[key] = old
        if key == "phosphor":
            m.refresh_family()
        self._commit()
        m.toast("undo %s" % key, "info", 1.5)
        for i, r in enumerate(m.rows):
            if r.key == key:
                m.sel = i
                break

    def _redo(self):
        m = self.model
        if not m.redo:
            m.toast("nothing to redo", "info", 1.5)
            return
        key, old, new = m.redo.pop()
        m.undo.append((key, old, new))
        self.ctl.values[key] = new
        if key == "phosphor":
            m.refresh_family()
        self._commit()
        m.toast("redo %s" % key, "info", 1.5)

    # -- entry mode -------------------------------------------------------------

    def _begin_entry(self, row):
        m = self.model
        if row.kind == "terminal" and row.key == "font-family":
            cur = self.ctl.terminal.get("font-family") or ""
            m.entry = {"key": row.key, "row": row, "text": cur, "kind": "text", "preview": cur, "over": False, "value": None, "note": ""}
        else:
            spec = row.spec
            if row.kind == "terminal":
                cur = self.ctl.terminal.get("font-size")
                cur_s = "" if cur is None else ("%g" % float(cur))
            else:
                cur_s = self.cm.display_value(spec, self.ctl.values.get(row.key))
            m.entry = {"key": row.key, "row": row, "text": "", "kind": "number", "preview": cur_s, "over": False, "value": None, "note": ""}
        m.mode = "entry"
        self._entry_preview()

    def _entry_preview(self):
        m = self.model
        e = m.entry
        if e is None or e["kind"] != "number":
            return
        row = e["row"]
        spec = row.spec
        txt = e["text"].strip()
        e["over"] = False
        e["value"] = None
        e["note"] = ""
        if not txt:
            return
        try:
            v = float(txt)
        except ValueError:
            e["preview"] = "?"
            e["note"] = "not a number"
            return
        lo, hi = spec.get("min"), spec.get("max")
        e["value"] = v
        e["preview"] = ("%g" % v)
        if lo is not None and hi is not None:
            if v > float(hi):
                e["over"] = True
                e["note"] = "OVER cap %s" % self.cm.display_value(spec, hi)
            elif v < float(lo):
                e["over"] = True
                e["note"] = "UNDER floor %s" % self.cm.display_value(spec, lo)
        hmin, hmax = spec.get("hard_min"), spec.get("hard_max")
        if hmin is not None and v < float(hmin):
            e["note"] = "HARD floor %s" % hmin
        if hmax is not None and v > float(hmax):
            e["note"] = "HARD cap %s" % hmax

    def _entry_commit(self):
        m = self.model
        e = m.entry
        if e is None:
            return
        row = e["row"]
        if e["kind"] == "text":
            txt = e["text"].strip()
            try:
                if not txt or txt.lower() == "default":
                    self.ctl.unset_terminal(row.key)
                else:
                    self.ctl.set_terminal(row.key, txt)
            except Exception as ex:
                m.toast(str(ex), "bad", 4.0)
                return
            m.entry = None
            m.mode = "bench"
            self._commit()
            return
        txt = e["text"].strip()
        if not txt:
            m.entry = None
            m.mode = "bench"
            return
        if row.kind == "terminal":
            try:
                if txt.lower() == "default":
                    self.ctl.unset_terminal("font-size")
                else:
                    self.ctl.set_terminal("font-size", float(txt))
            except Exception as ex:
                m.toast(str(ex), "bad", 4.0)
                return
            m.entry = None
            m.mode = "bench"
            self._commit()
            return
        spec = row.spec
        try:
            v = float(txt)
        except ValueError:
            m.toast("not a number: %r" % txt, "bad", 3.0)
            return
        if spec.get("type") == "int":
            v = int(round(v))
        lo, hi = spec.get("min"), spec.get("max")
        # quantise + enforce hard bounds through the core's soft path when it has one
        try:
            v = self.cm.normalize_value(row.key, spec, v, soft=True)
        except TypeError:
            v = v   # older core without soft=: keep the raw value (hard bounds checked below)
        except Exception as ex:      # ParamError: beyond a hard bound
            m.toast(str(ex), "bad", 6.0)
            return
        hmin, hmax = spec.get("hard_min"), spec.get("hard_max")
        inside = lo is None or hi is None or (float(lo) <= v <= float(hi))
        if inside:
            v = self.cm.normalize_value(row.key, spec, v)
            m.entry = None
            m.mode = "bench"
            self._set_value(row.key, v)
            return
        # outside the nominal range: a conversation, not a rejection
        consequence = spec.get("range_note") or (
            "The schema's nominal range is %s … %s; the shader will run %s but the physics past the "
            "nominal band is unmodelled — expect the effect to saturate, alias, or invert." % (
                self.cm.display_value(spec, lo), self.cm.display_value(spec, hi), self.cm.display_value(spec, v)))
        old = self.ctl.values.get(row.key)
        key = row.key

        def on_yes():
            self._set_value(key, v)
            m.toast("%s = %s (outside nominal) · ⌫ reverts" % (row.label, self.cm.display_value(spec, v)), "warn", 5.0)

        m.entry = None
        m.confirm = {
            "title": "OUTSIDE NOMINAL RANGE",
            "lines": ["%s → %s   (nominal %s … %s)" % (row.label, self.cm.display_value(spec, v), self.cm.display_value(spec, lo), self.cm.display_value(spec, hi)),
                      ""] + views.W.wrap_text(consequence, 60) + ["", "now %s · the value is saved into state and presets like any other" % self.cm.display_value(spec, old)],
            "yes": "commit", "no": "whoopsiedaisy",
            "on_yes": on_yes, "on_no": None,
        }
        m.mode = "confirm"

    # -- update ------------------------------------------------------------------

    def update(self, ev):
        m = self.model
        if ev.kind == "focus":
            return
        if ev.kind == "paste":
            if m.mode == "entry" and m.entry is not None:
                m.entry["text"] += ev.text.strip()
                self._entry_preview()
            elif m.mode == "sheet" and m.sheet is not None:
                m.sheet.insert(ev.text.replace("\n", " "))
            elif m.filter_active:
                m.filter += ev.text.strip()
            elif m.mode == "bank" and m.bank is not None and m.bank.filter_active:
                m.bank.filter += ev.text.strip()
                m.bank.apply_sort_filter()
            return
        if ev.kind == "mouse":
            self._mouse(ev)
            return
        # keys
        k = ev.id
        if k == "C-c":
            self._quit()
            return
        if m.mode == "splash":
            self._end_splash()
            if k in ("q",):
                self._quit()
            return
        if m.mode == "flatfield":
            if k in ("q", "esc", "C-f"):
                m.mode = "bench"
                self._invalidate()
            elif k == "space":
                m.tick += 40
            return
        if k == "C-f":
            m.mode = "flatfield"
            self._invalidate()
            return
        if m.mode == "help":
            if k in ("q", "esc", "?", "enter"):
                m.mode = "bench"
                self._invalidate()
            elif k in ("down", "j"):
                m.help_scroll += 1
            elif k in ("up", "k"):
                m.help_scroll = max(0, m.help_scroll - 1)
            elif k in ("pgdn", "space"):
                m.help_scroll += 10
            elif k == "pgup":
                m.help_scroll = max(0, m.help_scroll - 10)
            return
        if m.mode == "confirm":
            c = m.confirm
            if k == "enter" or k == "y":
                m.confirm = None
                m.mode = c.get("back", "bench")
                if c.get("on_yes"):
                    c["on_yes"]()
            elif k in ("esc", "n", "q"):
                m.confirm = None
                m.mode = c.get("back", "bench")
                if c.get("on_no"):
                    c["on_no"]()
            return
        if m.mode == "entry":
            self._update_entry(ev)
            return
        if m.mode == "bank":
            self._update_bank(ev)
            return
        if m.mode == "sheet":
            self._update_sheet(ev)
            return
        # bench
        if m.filter_active:
            if k == "esc":
                m.filter = ""
                m.filter_active = False
                m.sel = m._clamp_sel(m.sel)
            elif k == "enter":
                m.filter_active = False
                m.sel = m._clamp_sel(m.sel)
            elif k == "backspace":
                m.filter = m.filter[:-1]
                m.sel = m._clamp_sel(m.sel)
            elif ev.name == "char" and not ev.ctrl and not ev.alt:
                m.filter += ev.char
                m.sel = m._clamp_sel(m.sel)
            elif k in ("down", "up"):
                m.move(1 if k == "down" else -1)
            return
        self._update_bench(ev)

    def _quit(self):
        self.running = False

    def _end_splash(self):
        m = self.model
        if m.mode == "splash":
            m.mode = "bench"
            self._invalidate()

    def _update_bench(self, ev):
        m = self.model
        k = ev.id
        row = m.selected_row()
        if m.focus == "rail":
            if k in ("down", "j"):
                m.rail_sel = min(len(m.group_ids) - 1, m.rail_sel + 1)
                m.jump_group(m.group_ids[m.rail_sel])
                return
            if k in ("up", "k"):
                m.rail_sel = max(0, m.rail_sel - 1)
                m.jump_group(m.group_ids[m.rail_sel])
                return
            if k in ("enter", "right", "l", "tab"):
                m.focus = "bench"
                return
            if k in ("esc", "backtab"):
                m.focus = "bench"
                return
        if k in ("q",):
            self._quit()
        elif k == "?":
            m.mode = "help"
            m.help_scroll = 0
            self._invalidate()
        elif k in ("down", "j"):
            m.move(1)
        elif k in ("up", "k"):
            m.move(-1)
        elif k == "pgdn":
            m.move(5)
        elif k == "pgup":
            m.move(-5)
        elif k in ("home", "g"):
            m.move(-10000)
        elif k in ("end", "G"):
            m.move(10000)
        elif k in ("tab",):
            m.focus = "rail" if m.focus == "bench" else "bench"
            if m.focus == "rail" and row is not None and row.gid in m.group_ids:
                m.rail_sel = m.group_ids.index(row.gid)
        elif k == "backtab":
            m.section_jump(-1)
        elif k in ("right", "l") and row is not None:
            self._adjust(row, 1, False)
        elif k in ("left", "h") and row is not None:
            self._adjust(row, -1, False)
        elif k in (">", "S-right", "C-right") and row is not None:
            self._adjust(row, 1, True)
        elif k in ("<", "S-left", "C-left") and row is not None:
            self._adjust(row, -1, True)
        elif k == "enter" and row is not None:
            self._activate(row)
        elif k == "0" and row is not None:
            self._reset_default(row)
        elif k in ("backspace", "del") and row is not None:
            self._revert_inherited(row)
        elif k in tuple("123456789"):
            i = int(k) - 1
            if i < len(m.group_ids):
                m.jump_group(m.group_ids[i])
        elif k == "/":
            m.filter_active = True
        elif k == "*":
            m.modified_only = not m.modified_only
            m.sel = m._clamp_sel(m.sel)
            m.toast("modified only: %s" % ("on" if m.modified_only else "off"), "info", 1.5)
        elif k == "p":
            self._open_bank("presets")
        elif k == "P":
            self._open_sheet("preset")
        elif k == "S":
            self._open_sheet("profile")
        elif k == "L":
            self._open_bank("profiles")
        elif k == "E":
            self._fire_erase()
        elif k == "r":
            m.reload_deadline = None
            self._start_reload()
            m.toast("reload sent", "info", 1.5)
        elif k == "u":
            self._undo()
        elif k in ("U", "C-r"):
            self._redo()
        elif k == "M":
            m.mouse_on = not m.mouse_on
            if self.term is not None:
                self.term.set_mouse(m.mouse_on)
            m.toast("mouse %s — %s" % ("on" if m.mouse_on else "off", "click rows, drag meters" if m.mouse_on else "select text freely"), "info", 2.5)
        elif k == "m":
            i = MOTION_MODES.index(m.motion) if m.motion in MOTION_MODES else 0
            m.motion = MOTION_MODES[(i + 1) % len(MOTION_MODES)]
            self._invalidate()
            m.toast("motion: %s" % m.motion, "info", 1.5)
        elif k in ("[", "]"):
            self.ambient_fps = max(2.0, min(30.0, self.ambient_fps + (2 if k == "]" else -2)))
            m.toast("ambient %.0f fps" % self.ambient_fps, "info", 1.5)
        elif k == "esc":
            if m.filter:
                m.filter = ""
                m.sel = m._clamp_sel(m.sel)
            elif m.modified_only:
                m.modified_only = False
                m.sel = m._clamp_sel(m.sel)

    def _update_entry(self, ev):
        m = self.model
        e = m.entry
        k = ev.id
        if e is None:
            m.mode = "bench"
            return
        if k == "esc":
            m.entry = None
            m.mode = "bench"
        elif k == "enter":
            self._entry_commit()
        elif k == "backspace":
            e["text"] = e["text"][:-1]
            self._entry_preview()
        elif k == "C-u":
            e["text"] = ""
            self._entry_preview()
        elif ev.name == "char" and not ev.ctrl and not ev.alt:
            if e["kind"] == "text" or ev.char in ENTRY_CHARS or (ev.char.isalpha() and e["kind"] == "text"):
                e["text"] += ev.char
                self._entry_preview()
            elif e["kind"] == "number" and ev.char in ("d",) and not e["text"]:
                # 'd' shortcut: type "default"
                e["text"] = "default"
        elif k in ("up", "down") and e["kind"] == "number":
            # nudge the typed value by one step
            row = e["row"]
            step = row.spec.get("step") or 1
            try:
                v = float(e["text"]) if e["text"] else float(self.ctl.values.get(row.key) or 0)
            except ValueError:
                return
            v += step if k == "up" else -step
            e["text"] = ("%g" % v)
            self._entry_preview()

    # -- bank ---------------------------------------------------------------------

    def _open_bank(self, source):
        m = self.model
        m.bank = BankState(m, source)
        m.mode = "bank"
        self._invalidate()

    def _close_bank(self):
        m = self.model
        m.bank = None
        m.mode = "bench"
        self._invalidate()

    def _update_bank(self, ev):
        m = self.model
        b = m.bank
        k = ev.id
        if b is None:
            m.mode = "bench"
            return
        if b.filter_active:
            if k == "esc":
                b.filter = ""
                b.filter_active = False
                b.apply_sort_filter()
            elif k == "enter":
                b.filter_active = False
            elif k == "backspace":
                b.filter = b.filter[:-1]
                b.apply_sort_filter()
            elif ev.name == "char" and not ev.ctrl and not ev.alt:
                b.filter += ev.char
                b.apply_sort_filter()
            elif k in ("down", "up"):
                b.move(1 if k == "down" else -1)
            return
        if k in ("esc", "q", "p") and not (k == "p" and b.source != "presets"):
            self._close_bank()
        elif k in ("down", "j"):
            b.move(1)
        elif k in ("up", "k"):
            b.move(-1)
        elif k == "pgdn":
            b.move(10)
        elif k == "pgup":
            b.move(-10)
        elif k in ("home", "g"):
            b.sel = 0
        elif k in ("end", "G"):
            b.sel = max(0, len(b.entries) - 1)
        elif k == "s" and b.source == "presets":
            b.cycle_sort()
        elif k == "/":
            b.filter_active = True
        elif k == "w":
            styles = list(getattr(self.cm, "SWAP_STYLES", ("carry", "degauss", "fresh")))
            cur = getattr(self.ctl, "swap_style", "carry")
            i = styles.index(cur) if cur in styles else 0
            self.ctl.swap_style = styles[(i + 1) % len(styles)]
            self.ctl.save_state()
            m.toast("swap style: %s" % self.ctl.swap_style, "info", 2.0)
        elif k == "enter":
            e = b.current()
            if e is None:
                return
            if b.source == "presets":
                self._apply_preset(e["name"])
            else:
                self._load_profile(e["name"])
        elif k in ("del", "x", "D") and b.current() is not None:
            e = b.current()
            self._confirm_delete(b, e)
        elif k == "L" and b.source == "presets":
            self._open_bank("profiles")
        elif k == "P" and b.source == "profiles":
            self._open_bank("presets")

    def _apply_preset(self, name):
        m = self.model
        try:
            self.ctl.apply_preset(name)
        except Exception as e:
            m.toast("preset failed: %s" % e, "bad", 5.0)
            return
        m.refresh_family()
        m.invalidate_baseline()
        m.undo.clear()
        m.redo.clear()
        self._commit()
        m.toast("applied %s" % name, "ok", 2.5)
        self._close_bank()
        m.rebuild_rows(keep_key=(m.selected_row().key if m.selected_row() else None))
        m.preset_index = None

    def _load_profile(self, name):
        m = self.model
        try:
            self.ctl.load_profile(name)
        except Exception as e:
            m.toast("profile failed: %s" % e, "bad", 5.0)
            return
        m.refresh_family()
        m.invalidate_baseline()
        m.undo.clear()
        m.redo.clear()
        self._commit()
        m.toast("loaded profile %s" % name, "ok", 2.5)
        self._close_bank()

    def _confirm_delete(self, b, e):
        m = self.model
        path = e.get("path")
        what = "preset" if b.source == "presets" else "profile"
        m.confirm = {
            "title": "DELETE %s" % what.upper(),
            "lines": ["delete %s %r ?" % (what, e["name"]), "", path or ""],
            "yes": "delete", "no": "keep",
            "back": "bank",
            "on_yes": lambda: self._delete_entry(b, e),
            "on_no": None,
        }
        m.mode = "confirm"

    def _delete_entry(self, b, e):
        m = self.model
        try:
            os.remove(e["path"])
        except OSError as ex:
            m.toast("delete failed: %s" % ex, "bad", 5.0)
            return
        m.toast("deleted %s" % e["name"], "ok", 2.0)
        b.load()
        m.preset_index = None

    # -- sheet ---------------------------------------------------------------------

    def _open_sheet(self, kind):
        m = self.model
        m.sheet = SheetState(m, kind)
        m.mode = "sheet"
        self._invalidate()

    def _close_sheet(self):
        m = self.model
        m.sheet = None
        m.mode = "bench"
        self._invalidate()

    def _update_sheet(self, ev):
        m = self.model
        s = m.sheet
        k = ev.id
        if s is None:
            m.mode = "bench"
            return
        if k == "esc":
            self._close_sheet()
        elif k == "tab":
            order = ("name", "description", "diff") if s.kind == "preset" else ("name",)
            i = order.index(s.focus) if s.focus in order else 0
            s.focus = order[(i + 1) % len(order)]
        elif k == "backtab":
            order = ("name", "description", "diff") if s.kind == "preset" else ("name",)
            i = order.index(s.focus) if s.focus in order else 0
            s.focus = order[(i - 1) % len(order)]
        elif k == "enter":
            if s.focus == "diff":
                key = s.drop_current()
                if key:
                    m.toast("dropped %s from the save" % key, "info", 2.0)
            else:
                self._sheet_save()
        elif k == "C-r" and s.kind == "preset":
            s.rewrite_description()
        elif k == "C-d" and s.kind == "preset":
            key = s.drop_current()
            if key:
                m.toast("dropped %s from the save" % key, "info", 2.0)
        elif k == "C-z" and s.kind == "preset":
            s.undrop_all()
        elif s.focus == "diff":
            if k in ("down", "j"):
                s.diff_sel = min(max(0, len(s.diff()) - 1), s.diff_sel + 1)
            elif k in ("up", "k"):
                s.diff_sel = max(0, s.diff_sel - 1)
        else:
            if k == "backspace":
                s.backspace()
            elif k == "del":
                s.delete()
            elif k == "left":
                s.move_cursor(-1)
            elif k == "right":
                s.move_cursor(1)
            elif k == "home" or k == "C-a":
                s.home_end(False)
            elif k == "end" or k == "C-e":
                s.home_end(True)
            elif k == "C-u":
                s.clear_field()
            elif ev.name == "char" and not ev.ctrl and not ev.alt:
                s.insert(ev.char)

    def _sheet_save(self):
        m = self.model
        s = m.sheet
        slug = s.slug
        if s.kind == "preset":
            path = os.path.join(self.ctl.presets_dir, slug + ".json")
        else:
            path = os.path.join(self.ctl.profiles_dir, slug + ".json")
        if os.path.exists(path):
            m.confirm = {
                "title": "OVERWRITE",
                "lines": ["%s already exists:" % slug, path, "", "overwrite it?"],
                "yes": "overwrite", "no": "back",
                "back": "sheet",
                "on_yes": lambda: self._sheet_write(slug),
                "on_no": None,
            }
            m.mode = "confirm"
            return
        self._sheet_write(slug)

    def _sheet_write(self, slug):
        m = self.model
        s = m.sheet
        ctl = self.ctl
        try:
            if s.kind == "preset":
                # temporarily revert dropped keys so they are not saved, then restore
                dropped = {}
                base = m.baseline()
                for key in s.dropped:
                    dropped[key] = ctl.values[key]
                    ctl.values[key] = base.get(key, ctl.defaults.get(key))
                try:
                    path = ctl.save_preset(slug, s.description.strip())
                    # write the display name + meta into the doc
                    import json
                    with open(path, encoding="utf-8") as f:
                        doc = json.load(f)
                    doc["name"] = slug
                    doc["display_name"] = s.name.strip()
                    doc["inherits"] = m.ctl.active_preset if s.dropped or True else None
                    self.cm.atomic_write(path, json.dumps(doc, indent=2) + "\n")
                finally:
                    for key, v in dropped.items():
                        ctl.values[key] = v
                ctl.active_preset = slug
                ctl.save_state()
                m.invalidate_baseline()
                m.toast("saved tube %s" % slug, "ok", 3.0)
                m.preset_index = None
            else:
                ctl.save_profile(slug)
                m.toast("saved profile %s" % slug, "ok", 3.0)
        except Exception as e:
            m.toast("save failed: %s" % e, "bad", 6.0)
            return
        # if the sheet dropped keys, those knobs are now reverted for real:
        if s.kind == "preset" and s.dropped:
            base = m.baseline()
            for key in s.dropped:
                ctl.values[key] = base.get(key, ctl.defaults.get(key))
            self._commit()
        self._close_sheet()

    # -- mouse -----------------------------------------------------------------------

    def _mouse(self, ev):
        m = self.model
        if m.mode == "bank" and m.bank is not None:
            b = m.bank
            if ev.name == "wheel_up":
                b.move(-1)
            elif ev.name == "wheel_down":
                b.move(1)
            elif ev.name == "press" and ev.button == 0:
                hit = m.hit_at(ev.x, ev.y)
                if hit and hit[0] == "bankrow":
                    idx = hit[1]
                    if idx == b.sel:
                        e = b.current()
                        if e is not None:
                            if b.source == "presets":
                                self._apply_preset(e["name"])
                            else:
                                self._load_profile(e["name"])
                    else:
                        b.sel = idx
                elif hit and hit[0] == "banksort":
                    b.cycle_sort()
            return
        if m.mode not in ("bench", "entry"):
            return
        if ev.name == "wheel_up":
            m.move(-1)
            return
        if ev.name == "wheel_down":
            m.move(1)
            return
        if ev.name in ("press", "drag") and ev.button == 0:
            hit = m.hit_at(ev.x, ev.y)
            if hit is None:
                return
            kind, payload = hit
            if kind == "row":
                idx = payload
                if m.mode == "entry":
                    m.entry = None
                    m.mode = "bench"
                m.sel = idx
                r = m.rows[idx]
                geo = m.meter_geo.get(idx)
                if geo and r.kind == "rotary":
                    mx, mw = geo
                    if mx <= ev.x < mx + mw and mw > 1:
                        t = (ev.x - mx + 0.5) / mw
                        spec = r.spec
                        lo, hi = spec.get("min"), spec.get("max")
                        if lo is not None and hi is not None:
                            v = float(lo) + t * (float(hi) - float(lo))
                            v = self.cm.normalize_value(r.key, spec, v)
                            self._set_value(r.key, v)
                elif ev.name == "press" and r.kind in ("switch", "selector", "swapstyle", "button", "action"):
                    if geo and geo[0] <= ev.x:
                        self._activate(r)
            elif kind == "group":
                m.jump_group(payload)
                m.focus = "bench"
            elif kind == "hint":
                # a hint key acts like pressing it
                from .keys import Event
                self.update(Event("key", "char", char=payload) if len(payload) == 1 else Event("key", payload))


def run_panel(ctl, dest, crtctl_mod, **kw):
    app = App(ctl, dest, crtctl_mod, **kw)
    prof_path = os.environ.get("MONOSCOPE_PROFILE")
    prof = None
    if prof_path:
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
    try:
        return app.run()
    except KeyboardInterrupt:
        return 0
    finally:
        if prof is not None:
            prof.disable()
            prof.dump_stats(prof_path)

#!/usr/bin/env python3
"""Unit tests for MONOSCOPE (tools/monoscope) — headless, no terminal.

Covers: key decoding, the canvas + diff renderer, colour-math conformance
with the Scanhound golden vectors, TheDraw font loading, the model, every
view at several sizes (total frames: every cell has an explicit bg), the
update logic driven by synthetic events, and the state/shader side effects
of a knob change. Runs against a temp GHOSTTY_CRT_HOME with the real
params.json + presets and an injected fake reload runner.
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
CRT = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

from monoscope import keys as K            # noqa: E402
from monoscope import canvas as CV         # noqa: E402
from monoscope import color as C           # noqa: E402
from monoscope import tdf                  # noqa: E402
from monoscope import banners              # noqa: E402
from monoscope.model import Model          # noqa: E402
from monoscope import views                # noqa: E402
from monoscope.bankstate import BankState, signature_values  # noqa: E402
from monoscope.sheetstate import SheetState, slugify, auto_name  # noqa: E402
from monoscope.app import App              # noqa: E402


def load_crtctl():
    path = os.path.join(TOOLS, "crtctl")
    loader = importlib.machinery.SourceFileLoader("crtctl_for_monoscope", path)
    spec = importlib.util.spec_from_loader("crtctl_for_monoscope", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


class Env:
    """A temp GHOSTTY_CRT_HOME with the real schema + presets."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="monoscope-test-")
        crt = os.path.join(self.tmp, "crt")
        os.makedirs(crt)
        shutil.copy(os.path.join(CRT, "params.json"), crt)
        shutil.copytree(os.path.join(CRT, "presets"), os.path.join(crt, "presets"))
        os.makedirs(os.path.join(crt, "templates"))
        with open(os.path.join(crt, "templates", "t.glsl.tmpl"), "w") as f:
            f.write("// test\n//@CRT_PARAMS@\nvoid main(){}\n")
        self.old = os.environ.get("GHOSTTY_CRT_HOME")
        os.environ["GHOSTTY_CRT_HOME"] = self.tmp
        self.calls = []

    def runner(self, argv, timeout=5.0):
        self.calls.append(list(argv))
        return 0, "()", ""

    def close(self):
        if self.old is None:
            os.environ.pop("GHOSTTY_CRT_HOME", None)
        else:
            os.environ["GHOSTTY_CRT_HOME"] = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestKeys(unittest.TestCase):
    def ids(self, data):
        d = K.Decoder()
        evs = d.feed(data)
        evs += d.flush()
        return [e.id if e.kind == "key" else repr(e) for e in evs]

    def test_plain_and_ctrl(self):
        self.assertEqual(self.ids(b"aA1 "), ["a", "A", "1", "space"])
        self.assertEqual(self.ids(b"\x01\x03"), ["C-a", "C-c"])
        self.assertEqual(self.ids(b"\r\t\x7f"), ["enter", "tab", "backspace"])

    def test_csi_arrows_and_modifiers(self):
        self.assertEqual(self.ids(b"\x1b[A\x1b[B\x1b[C\x1b[D"), ["up", "down", "right", "left"])
        self.assertEqual(self.ids(b"\x1b[1;2A\x1b[1;5C\x1b[1;3D"), ["S-up", "C-right", "A-left"])
        self.assertEqual(self.ids(b"\x1b[5~\x1b[6~\x1b[3~\x1b[Z"), ["pgup", "pgdn", "del", "backtab"])
        self.assertEqual(self.ids(b"\x1bOP\x1b[15~\x1b[24~"), ["f1", "f5", "f12"])
        self.assertEqual(self.ids(b"\x1b[H\x1b[F"), ["home", "end"])

    def test_kitty_csi_u(self):
        self.assertEqual(self.ids(b"\x1b[27u"), ["esc"])
        self.assertEqual(self.ids(b"\x1b[97;5u"), ["C-a"])
        self.assertEqual(self.ids(b"\x1b[97:65;2u"), ["A"])
        self.assertEqual(self.ids(b"\x1b[13;2u"), ["S-enter"])
        self.assertEqual(self.ids(b"\x1b[57421;1u"), ["pgup"])

    def test_esc_alone_needs_timeout(self):
        d = K.Decoder()
        self.assertEqual(d.feed(b"\x1b"), [])
        import time
        time.sleep(K.ESC_TIMEOUT + 0.02)
        evs = d.flush()
        self.assertEqual([e.id for e in evs], ["esc"])

    def test_alt_letter(self):
        self.assertEqual(self.ids(b"\x1bx"), ["A-x"])

    def test_mouse_sgr(self):
        d = K.Decoder()
        evs = d.feed(b"\x1b[<0;10;5M\x1b[<0;10;5m\x1b[<64;1;1M\x1b[<32;3;4M")
        self.assertEqual([(e.name, e.x, e.y, e.button) for e in evs],
                         [("press", 9, 4, 0), ("release", 9, 4, 0), ("wheel_up", 0, 0, 64), ("drag", 2, 3, 0)])

    def test_bracketed_paste(self):
        d = K.Decoder()
        evs = d.feed(b"\x1b[200~hello\rworld\x1b[201~")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].kind, "paste")
        self.assertEqual(evs[0].text, "hello\nworld")

    def test_utf8_split_across_reads(self):
        d = K.Decoder()
        self.assertEqual(d.feed("é".encode()[:1]), [])
        evs = d.feed("é".encode()[1:])
        self.assertEqual([e.char for e in evs], ["é"])


class TestCanvas(unittest.TestCase):
    def test_put_clips_and_returns_x(self):
        cv = CV.Canvas(10, 2, bg=(0, 0, 0))
        x = cv.put(8, 0, "abcd", fg=(1, 2, 3))
        self.assertEqual(x, 10)
        self.assertEqual(cv.get(9, 0)[0], "b")
        self.assertIsNone(cv.get(10, 0))
        cv.put(-1, 1, "xy")
        self.assertEqual(cv.get(0, 1)[0], "y")

    def test_wide_glyph_takes_two_cells(self):
        cv = CV.Canvas(6, 1)
        cv.put(0, 0, "日x")
        self.assertEqual(cv.ch[0], "日")
        self.assertEqual(cv.ch[1], "")
        self.assertEqual(cv.ch[2], "x")

    def test_diff_emits_only_changes(self):
        cv = CV.Canvas(20, 3, bg=(1, 1, 1))
        r = CV.Renderer(truecolor=True)
        first = r.render(cv)
        self.assertIn(b"\x1b[H", first)
        self.assertEqual(r.render(cv), b"")           # nothing changed
        cv.put(3, 1, "Z", fg=(9, 9, 9))
        d = r.render(cv)
        self.assertIn(b"\x1b[2;4H", d)
        self.assertIn(b"38;2;9;9;9", d)
        self.assertEqual(d.count(b"Z"), 1)
        self.assertLess(len(d), 60)
        # full repaint after invalidate
        r.invalidate()
        self.assertGreater(len(r.render(cv)), len(d))

    def test_256_quantization_path(self):
        cv = CV.Canvas(4, 1, bg=(0, 0, 0))
        cv.put(0, 0, "a", fg=(255, 0, 0), bg=(0, 0, 255))
        r = CV.Renderer(truecolor=False)
        d = r.render(cv)
        self.assertIn(b"38;5;", d)
        self.assertNotIn(b"38;2;", d)
        self.assertEqual(CV.xterm256_index((0, 0, 0)), 16)
        self.assertEqual(CV.xterm256_index((255, 255, 255)), 231)

    def test_cursor_is_hidden_while_cells_are_painted(self):
        """The cursor must never be visible while dirty runs are emitted.

        Left showing, it is dragged over every run on its way to its home
        square — which is what "the cursor redraws across the screen" looks
        like to an operator.
        """
        cv = CV.Canvas(20, 3, bg=(1, 1, 1))
        r = CV.Renderer(truecolor=True)
        cv.cursor = (5, 1)
        d = r.render(cv)
        self.assertIn(b"\x1b[?25h", d)                  # shown at the end
        self.assertLess(d.index(b"\x1b[2;6H"), d.index(b"\x1b[?25h"))
        # Next frame paints: hide must come first, and before any cell write.
        cv.put(0, 0, "Z", fg=(9, 9, 9))
        d = r.render(cv)
        self.assertTrue(d.startswith(b"\x1b[?25l"), d[:20])
        self.assertLess(d.index(b"\x1b[?25l"), d.index(b"Z"))
        self.assertLess(d.index(b"Z"), d.index(b"\x1b[?25h"))

    def test_parked_cursor_does_not_blink_on_an_idle_frame(self):
        """An unchanged frame emits nothing at all — no hide/show churn."""
        cv = CV.Canvas(20, 3, bg=(1, 1, 1))
        cv.cursor = (5, 1)
        r = CV.Renderer(truecolor=True)
        r.render(cv)
        self.assertEqual(r.render(cv), b"")
        self.assertEqual(r.render(cv), b"")

    def test_relative_motion_is_used_when_it_is_shorter(self):
        cv = CV.Canvas(60, 2, bg=(1, 1, 1))
        r = CV.Renderer(truecolor=True)
        r.render(cv)
        # two dirty cells on row 1 with one clean cell between them: the
        # second is reached with CUF, not a full absolute address.
        cv.put(40, 1, "A", fg=(9, 9, 9))
        cv.put(42, 1, "B", fg=(9, 9, 9))
        d = r.render(cv)
        self.assertIn(b"\x1b[C", d)
        self.assertEqual(d.count(b"\x1b[2;"), 1)        # only one absolute move

    def test_rep_collapses_runs_only_when_enabled(self):
        cv = CV.Canvas(40, 1, bg=(1, 1, 1))
        cv.put(0, 0, "\u2591" * 30, fg=(9, 9, 9))
        plain = CV.Renderer(truecolor=True, rep=False).render(cv)
        with_rep = CV.Renderer(truecolor=True, rep=True).render(cv)
        self.assertNotIn(b"b", plain.replace(b"\x1b[", b""))
        self.assertIn(b"\x1b[29b", with_rep)
        self.assertLess(len(with_rep), len(plain))

    def test_a_colour_reverting_to_none_is_not_lost(self):
        """`None` means "the terminal default", which no additive SGR delta
        can express — it needs a full reset. The delta encoder must not treat
        it as "nothing changed" and emit an empty string."""
        cv = CV.Canvas(4, 1)
        r = CV.Renderer(truecolor=True)
        cv.ch[:] = list("ABCD")
        cv.fg[:] = [(200, 200, 200)] * 4
        cv.bg[:] = [(0, 0, 0)] * 4
        r.render(cv)
        cv.ch[1] = "X"
        cv.fg[1] = None
        d = r.render(cv)
        self.assertIn(b"\x1b[0", d, "no reset emitted: the old colour survives")
        self.assertIn(b"X", d)

    def test_heal_band_repaints_only_its_rows(self):
        cv = CV.Canvas(40, 20, bg=(1, 1, 1))
        cv.put(0, 0, "x" * 40, fg=(9, 9, 9))
        r = CV.Renderer(truecolor=True)
        r.render(cv)
        self.assertEqual(r.render(cv), b"")
        r.heal_band(4, 8)
        d = r.render(cv)
        self.assertGreater(len(d), 0)
        for y in (5, 6, 7, 8):                          # 1-based rows 5..8
            self.assertIn(b"\x1b[%d;1H" % y, d)
        self.assertNotIn(b"\x1b[1;1H", d)               # row 0 was left alone
        self.assertNotIn(b"\x1b[20;1H", d)
        # and a whole-screen repaint is strictly larger than one band
        r.invalidate()
        self.assertGreater(len(r.render(cv)), len(d))

    def test_never_emits_palette_changes(self):
        cv = CV.Canvas(8, 2)
        r = CV.Renderer()
        d = r.render(cv)
        self.assertNotIn(b"\x1b]4;", d)
        self.assertNotIn(b"\x1b]104", d)


class TestColorConformance(unittest.TestCase):
    """Bit-exact against the Scanhound golden vectors (vendored copy)."""

    def setUp(self):
        p = os.path.join(HERE, "golden", "scanhound_vectors.json")
        if not os.path.exists(p):
            self.skipTest("golden vectors not vendored")
        self.d = json.load(open(p))

    def test_hsl_hue_plasma_breathing_palette(self):
        d = self.d
        for v in d["hsl_to_rgb"]:
            self.assertEqual(list(C.hsl_to_rgb(*v["in"])), v["out"])
        for v in d["hue_to_rgb"]:
            self.assertEqual(list(C.hue_to_rgb(*v["in"])), v["out"])
        for v in d["plasma_hue"]:
            self.assertLessEqual(abs(int(round(C.plasma_hue(*v["in"]) * 1e6)) - v["out_deg_1e6"]), 1)
        for v in d["plasma_color"]:
            self.assertEqual(list(C.plasma_color(*v["in"])), v["out"])
        for v in d["breathing"]:
            self.assertLessEqual(abs(int(round(C.breathing(v["in"][0], v["in"][1] / 1000.0) * 1e6)) - v["out_1e6"]), 1)
        pals = {"synthwave": (320.0, 280.0, 200.0), "cyberpunk": (300.0, 270.0, 180.0, 120.0), "aurora": (150.0, 180.0, 270.0, 300.0)}
        for v in d["sample_palette"]:
            self.assertLessEqual(abs(int(round(C.sample_hue_stops(pals[v["palette"]], v["t_1e3"] / 1000.0) * 1e6)) - v["out_deg_1e6"]), 1)

    def test_crt_safe_caps_saturation(self):
        C.set_sat_ceiling("grille", 0.45)
        h, s, v = C.rgb_to_hsv(C.crt_safe((255, 0, 0)))
        self.assertLessEqual(s, C.SAT_CEILING + 0.02)
        self.assertEqual(C.crt_safe((100, 100, 100)), (100, 100, 100))
        # no mask → full colour is real
        C.set_sat_ceiling("none", 0.0)
        self.assertEqual(C.crt_safe((255, 0, 0)), (255, 0, 0))
        C.set_sat_ceiling("grille", 0.45)

    def test_family_for_every_phosphor(self):
        cm = load_crtctl()
        params = json.load(open(os.path.join(CRT, "params.json")))["params"]
        for name in params["phosphor"]["values"]:
            fam = C.family_for_phosphor(name)
            self.assertTrue(fam.name)
            self.assertEqual(len(fam.face) >= 4, True)


class TestGroundWave(unittest.TestCase):
    """The travelling background gradient (views.apply_ground_wave)."""

    def test_off_is_exactly_the_untouched_ground(self):
        base = (8, 6, 14)
        self.assertEqual(C.bg_wave(base, 3, 40, 99, "off"), base)

    def test_reduced_is_static_banding_with_no_travel(self):
        base = (8, 6, 14)
        a = [C.bg_wave(base, y, 40, 0, "reduced") for y in range(40)]
        b = [C.bg_wave(base, y, 40, 500, "reduced") for y in range(40)]
        self.assertEqual(a, b)                    # does not move
        self.assertGreater(len(set(a)), 1)        # but does band

    def test_the_wave_travels(self):
        base = (8, 6, 14)
        a = [C.bg_wave(base, y, 40, 0, "full") for y in range(40)]
        b = [C.bg_wave(base, y, 40, 40, "full") for y in range(40)]
        self.assertNotEqual(a, b)
        # ... and it is the *same* wave, shifted: the multiset of levels is
        # near-identical, it has just moved up the screen.
        self.assertGreater(len(set(a) & set(b)), len(set(a)) // 2)

    def test_quantised_so_most_rows_hold_still_between_ticks(self):
        """The property that keeps the wave from undoing the payload work.

        An unquantised wave changes every row every tick, which defeats the
        renderer's row-level fast skip and makes every frame a full repaint.
        """
        base = (8, 6, 14)
        rows = 60
        changed = 0
        for tick in range(60):
            a = [C.bg_wave(base, y, rows, tick, "full") for y in range(rows)]
            b = [C.bg_wave(base, y, rows, tick + 1, "full") for y in range(rows)]
            changed += sum(1 for x, y_ in zip(a, b) if x != y_)
        self.assertLess(changed / (60.0 * rows), 0.5,
                        "more than half of all rows change every tick")

    def test_monochrome_families_keep_their_colour(self):
        """The panel wears the tube: a P1 green ground must not drift violet.

        Stated as channel *ordering* rather than a hue angle, because these
        grounds sit at RGB values like (3, 12, 5) where one unit of 8-bit
        rounding is several degrees of hue, and P4's near-neutral (8, 8, 9)
        has no meaningful hue at all. Saturation is checked separately and
        only in one direction: `crt_safe` may legitimately pull a colour in
        (that ceiling governs every other colour on the panel too), but the
        wave must never push one out.
        """
        for name, fam in C.FAMILIES.items():
            if fam.hues:                          # colour tubes may drift
                continue
            base = fam.ground
            s_base = C.rgb_to_hsv(base)[1]
            for tick in range(0, 60, 7):
                for y in (0, 9, 21, 30, 45):
                    out = C.bg_wave(base, y, 60, tick, "full", hues=False)
                    for i in range(3):
                        for j in range(3):
                            if base[i] - base[j] >= 2:
                                self.assertGreaterEqual(
                                    out[i], out[j],
                                    "%s row %d tick %d: %r reorders %r"
                                    % (name, y, tick, out, base))
                    # Saturation is (max-min)/max, so on a ground this dark
                    # one unit of 8-bit rounding is worth 1/max of it. That
                    # quantisation floor — not a slack constant — is the
                    # tolerance.
                    floor = 2.0 / max(1, max(out))
                    self.assertLessEqual(C.rgb_to_hsv(out)[1], s_base + floor,
                                         "%s gained saturation: %r" % (name, out))

    def test_wave_never_crushes_to_black(self):
        base = (8, 6, 14)
        vals = [sum(C.bg_wave(base, y, 40, t, "full")) for y in range(40) for t in range(40)]
        self.assertGreater(min(vals), sum(base) * 0.3)


class TestFonts(unittest.TestCase):
    def test_vendored_fonts_load_and_render(self):
        for kind in ("big", "mid", "small", "tiny", "hero"):
            f = banners.font_for(kind)
            self.assertIsNotNone(f, kind)
            rows = banners.banner_rows(kind, "MONOSCOPE")
            self.assertTrue(rows, kind)
            self.assertEqual(len(rows), banners.banner_height(kind))
            w = max(len(r) for r in rows)
            self.assertGreater(w, 20)
            for r in rows:
                for ch, level in r:
                    self.assertTrue(0.0 <= level <= 1.0)

    def test_tdf_parser_matches_tdfiglet_shape(self):
        f = banners.font_for("hero")
        gw, gh, rows = f.glyphs["M"]
        self.assertEqual((gw, len(rows)), (13, 10))
        self.assertEqual("".join(c[0] for c in rows[0]), " ▄▄▄▄▄ ▄▄▄▄▄ ")


class ModelCase(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.cm = load_crtctl()
        self.ctl = self.cm.CrtCtl(runner=self.env.runner, on_warn=lambda m: None)
        self.now = [1000.0]
        self.m = Model(self.ctl, "io.test.dest", self.cm, now=lambda: self.now[0])

    def tearDown(self):
        self.env.close()


class TestModel(ModelCase):
    def test_rows_cover_every_visible_param(self):
        keys = {r.key for r in self.m.rows if r.kind in ("rotary", "switch", "selector", "button")}
        for k, spec in self.ctl.params.items():
            if spec.get("knob") in ("rotary", "switch", "selector") or k == "power_on":
                self.assertIn(k, keys)
        kinds = [(r.kind, r.key) for r in self.m.rows if r.gid == "system"]
        self.assertIn(("action", "degauss"), kinds)
        self.assertIn(("action", "erase"), kinds)
        self.assertIn(("swapstyle", "swap_style"), kinds)
        self.assertIn(("terminal", "font-size"), kinds)
        self.assertIn(("terminal", "font-family"), kinds)
        # a header per group
        self.assertEqual([r.gid for r in self.m.rows if r.kind == "header"], list(self.ctl.groups.keys()))

    def test_move_skips_headers_and_jump_group(self):
        m = self.m
        self.assertNotEqual(m.rows[m.sel].kind, "header")
        m.move(1)
        self.assertNotEqual(m.rows[m.sel].kind, "header")
        m.jump_group("mask")
        self.assertEqual(m.rows[m.sel].gid, "mask")
        m.section_jump(1)
        self.assertEqual(m.rows[m.sel].gid, "phosphor")

    def test_filter_and_modified_only(self):
        m = self.m
        m.filter = "bloom"
        vis = m.visible_rows()
        labels = [r.label for _i, r in vis if r.kind != "header"]
        self.assertIn("BEAM BLOOM", labels)
        self.assertLess(len(labels), 10)
        m.filter = ""
        m.modified_only = True
        self.assertEqual([r for _i, r in m.visible_rows() if r.kind != "header"], [])
        self.ctl.values["scan_bloom"] = 0.9
        vis = [r.key for _i, r in m.visible_rows() if r.kind != "header"]
        self.assertEqual(vis, ["scan_bloom"])
        self.assertEqual(m.modified_counts(), {"scan": 1})

    def test_family_follows_phosphor(self):
        m = self.m
        self.ctl.values["phosphor"] = "p1"
        m.refresh_family()
        self.assertEqual(m.fam.name, "p1")
        self.ctl.values["phosphor"] = "pdp"
        m.refresh_family()
        self.assertEqual(m.fam.name, "pdp")

    def test_signature_is_eight_unit_values(self):
        sig = signature_values(self.ctl.values, self.ctl.params)
        self.assertEqual(len(sig), 8)
        for v in sig:
            self.assertTrue(0.0 <= v <= 1.0)


class TestGroundWaveInFrame(ModelCase):
    def test_only_the_ground_breathes(self):
        """Every deliberate colour on the panel survives the post-pass."""
        cv = CV.Canvas(100, 30, bg=self.m.fam.ground, fg=self.m.fam.ink)
        views.render(self.m, cv, 0)
        before = list(cv.bg)
        marker = (123, 45, 67)                    # not a family ground
        cv.bg[5 * 100 + 10] = marker
        views_bg_before = list(cv.bg)
        views.apply_ground_wave(self.m, cv, 25)
        self.assertEqual(cv.bg[5 * 100 + 10], marker, "an instrument colour was tinted")
        self.assertNotEqual(cv.bg, views_bg_before, "the ground did not move at all")
        del before

    def test_motion_off_leaves_the_frame_flat(self):
        m = Model(self.ctl, "io.test.dest", self.cm, motion="off", now=lambda: self.now[0])
        cv = CV.Canvas(80, 24, bg=m.fam.ground, fg=m.fam.ink)
        views.render(m, cv, 0)
        a = list(cv.bg)
        views.apply_ground_wave(m, cv, 900)
        self.assertEqual(a, cv.bg)


class TestViews(ModelCase):
    SIZES = ((80, 24), (100, 30), (120, 36), (150, 40), (160, 48), (200, 60), (44, 9))

    def _frame(self, w, h, tick=37):
        cv = CV.Canvas(w, h)
        views.render(self.m, cv, tick)
        return cv

    def _assert_total(self, cv):
        # every cell has an explicit bg colour and a printable glyph
        for i, bg in enumerate(cv.bg):
            self.assertIsNotNone(bg, "cell %d has no bg" % i)
        for ch in cv.ch:
            self.assertNotIn(ch, ("\n", "\r", "\t"))

    def test_bench_all_sizes(self):
        for w, h in self.SIZES:
            cv = self._frame(w, h)
            self._assert_total(cv)
            text = "\n".join(cv.snapshot_text())
            self.assertIn("BRIGHTNESS", text)
            if w >= 100:
                self.assertIn("GROUPS", text)
            if w >= 150:
                self.assertIn("SCOPE", text)

    def test_every_mode_renders_at_every_size(self):
        m = self.m
        m.bank = BankState(m, "presets")
        m.sheet = SheetState(m, "preset")
        m.confirm = {"title": "T", "lines": ["a", "b"], "yes": "y", "no": "n"}
        m.entry = {"key": "scan_lines", "row": m.rows[m.sel], "text": "2000", "kind": "number", "preview": "2000", "over": True, "value": 2000.0, "note": "OVER cap 1200"}
        for mode in ("bench", "entry", "bank", "sheet", "confirm", "help", "flatfield"):
            m.mode = mode
            for w, h in self.SIZES:
                cv = self._frame(w, h)
                self._assert_total(cv)
        m.bank = BankState(m, "profiles")
        m.mode = "bank"
        self._assert_total(self._frame(120, 36))

    def test_bench_frame_is_deterministic(self):
        a = self._frame(120, 36, tick=5)
        b = self._frame(120, 36, tick=5)
        self.assertEqual(a.ch, b.ch)
        self.assertEqual(a.bg, b.bg)

    def test_motion_off_frames_do_not_depend_on_tick(self):
        self.m.motion = "off"
        a = self._frame(120, 36, tick=1)
        b = self._frame(120, 36, tick=999)
        self.assertEqual(a.ch, b.ch)
        self.assertEqual(a.fg, b.fg)
        self.assertEqual(a.bg, b.bg)

    def test_no_row_wider_than_canvas(self):
        for w, h in self.SIZES:
            cv = self._frame(w, h)
            for row in cv.snapshot_text():
                self.assertLessEqual(CV.swidth(row), w)


class TestApp(ModelCase):
    def setUp(self):
        super().setUp()
        self.app = App(self.ctl, "io.test.dest", self.cm, motion="off", mouse=False)
        self.app.model.now = lambda: self.now[0]

    def key(self, *ids):
        for k in ids:
            if len(k) == 1:
                ev = K.Event("key", "char", char=k)
            elif k.startswith("S-") and len(k) == 3:
                ev = K.Event("key", "char", char=k[2].upper())
            else:
                ev = K.Event("key", k)
            self.app.update(ev)

    def sel(self):
        return self.app.model.selected_row()

    def test_adjust_writes_state_shader_and_arms_reload(self):
        m = self.app.model
        m.jump_group("scan")
        r = self.sel()
        self.assertEqual(r.key, "scan_lines")
        before = self.ctl.values["scan_lines"]
        self.key("right")
        self.assertEqual(self.ctl.values["scan_lines"], before + 1)
        st = json.load(open(self.ctl.state_path))
        self.assertEqual(st["values"]["scan_lines"], before + 1)
        self.assertTrue(os.path.exists(os.path.join(self.ctl.shaders_dir, "t.glsl")))
        self.assertTrue(m.reload_pending())
        # debounce fires the reload
        m.reload_deadline = -1
        self.app._service_reload()
        import time
        for _ in range(50):
            self.app._service_reload()
            if m.last_reload:
                break
            time.sleep(0.02)
        self.assertTrue(m.last_reload and m.last_reload[0])
        self.assertIn(self.cm.reload_argv("io.test.dest"), self.env.calls)

    def test_undo_redo(self):
        m = self.app.model
        m.jump_group("scan")
        v0 = self.ctl.values["scan_lines"]
        self.key("right", "right", "u")
        self.assertEqual(self.ctl.values["scan_lines"], v0 + 1)
        self.key("U")
        self.assertEqual(self.ctl.values["scan_lines"], v0 + 2)

    def test_reset_and_revert(self):
        m = self.app.model
        m.jump_group("scan")
        self.key("right", "0")
        self.assertEqual(self.ctl.values["scan_lines"], self.ctl.defaults["scan_lines"])
        self.key("right", "backspace")
        self.assertEqual(self.ctl.values["scan_lines"], self.ctl.baseline_values()["scan_lines"])

    def test_switch_selector_button(self):
        m = self.app.model
        for i, r in enumerate(m.rows):
            if r.key == "interlace":
                m.sel = i
        self.key("enter")
        self.assertTrue(self.ctl.values["interlace"])
        for i, r in enumerate(m.rows):
            if r.key == "mask_type":
                m.sel = i
        cur = self.ctl.values["mask_type"]
        self.key("right")
        self.assertNotEqual(self.ctl.values["mask_type"], cur)
        for i, r in enumerate(m.rows):
            if r.key == "power_on":
                m.sel = i
        n = self.ctl.values["power_nonce"]
        self.key("enter")
        self.assertEqual(self.ctl.values["power_nonce"], n + 1)
        n = self.ctl.values["erase_nonce"]
        self.key("E")
        self.assertEqual(self.ctl.values["erase_nonce"], n + 1)

    def test_entry_inside_and_outside_nominal(self):
        m = self.app.model
        m.jump_group("scan")
        self.key("enter")
        self.assertEqual(m.mode, "entry")
        for ch in "600":
            self.key(ch)
        self.key("enter")
        self.assertEqual(m.mode, "bench")
        self.assertEqual(self.ctl.values["scan_lines"], 600)
        # outside nominal → confirm → commit
        self.key("enter")
        for ch in "2000":
            self.key(ch)
        self.assertTrue(m.entry["over"])
        self.key("enter")
        self.assertEqual(m.mode, "confirm")
        self.key("enter")
        self.assertEqual(m.mode, "bench")
        self.assertEqual(self.ctl.values["scan_lines"], 2000)
        st = json.load(open(self.ctl.state_path))
        self.assertEqual(st["values"]["scan_lines"], 2000)
        # whoopsiedaisy path
        self.key("enter")
        for ch in "5000":
            self.key(ch)
        self.key("enter", "esc")
        self.assertEqual(self.ctl.values["scan_lines"], 2000)

    def test_bank_apply_preset(self):
        m = self.app.model
        self.key("p")
        self.assertEqual(m.mode, "bank")
        names = [e["name"] for e in m.bank.entries]
        self.assertIn("ibm5151-green", names)
        m.bank.sel = names.index("ibm5151-green")
        self.key("enter")
        self.assertEqual(m.mode, "bench")
        self.assertEqual(self.ctl.active_preset, "ibm5151-green")
        self.assertEqual(m.fam.name, "p1")   # the panel wears the tube
        st = json.load(open(self.ctl.state_path))
        self.assertEqual(st["active_preset"], "ibm5151-green")

    def test_bank_sort_and_filter(self):
        m = self.app.model
        self.key("p")
        self.key("s")
        self.assertEqual(m.bank.sort, "year")
        self.key("/")
        for ch in "sony":
            self.key(ch)
        self.assertTrue(m.bank.entries)
        for e in m.bank.entries:
            hay = (e["name"] + " " + e.get("description", "") + " " + str((e.get("meta") or {}).get("manufacturer", ""))).lower()
            self.assertIn("sony", hay)
        self.key("esc")
        self.assertEqual(m.bank.filter, "")

    def test_save_sheet_writes_preset_with_display_name(self):
        m = self.app.model
        m.jump_group("scan")
        self.key("right", "right", "P")
        self.assertEqual(m.mode, "sheet")
        s = m.sheet
        self.assertTrue(s.name.endswith("Custom"))
        self.assertEqual(len(s.diff()), 1)
        self.key("C-u")
        for ch in "My Tube":
            self.key(ch)
        self.assertEqual(s.slug, "my-tube")
        self.key("enter")
        self.assertEqual(m.mode, "bench")
        path = os.path.join(self.ctl.presets_dir, "my-tube.json")
        self.assertTrue(os.path.exists(path))
        doc = json.load(open(path))
        self.assertEqual(doc["display_name"], "My Tube")
        self.assertIn("scan_lines", doc["params"])
        self.assertIn("Differs from that tube in 1 setting", doc["description"])
        # overwrite asks
        self.key("P")
        self.key("C-u")
        for ch in "My Tube":
            self.key(ch)
        self.key("enter")
        self.assertEqual(m.mode, "confirm")
        self.key("esc")
        self.assertEqual(m.mode, "sheet")

    def test_help_and_flatfield_toggle(self):
        m = self.app.model
        self.key("?")
        self.assertEqual(m.mode, "help")
        self.key("esc")
        self.assertEqual(m.mode, "bench")
        self.key("C-f")
        self.assertEqual(m.mode, "flatfield")
        self.key("q")
        self.assertEqual(m.mode, "bench")
        self.assertTrue(self.app.running)
        self.key("q")
        self.assertFalse(self.app.running)

    def test_terminal_override_rows(self):
        m = self.app.model
        for i, r in enumerate(m.rows):
            if r.key == "font-size":
                m.sel = i
        self.key("enter")
        for ch in "22":
            self.key(ch)
        self.key("enter")
        self.assertEqual(self.ctl.terminal["font-size"], 22.0)
        self.assertIn("font-size = 22", open(self.ctl.overrides_path).read())
        self.key("0")
        self.assertNotIn("font-size", self.ctl.terminal)


class TestSheetHelpers(unittest.TestCase):
    def test_slug_and_name(self):
        self.assertEqual(slugify("Wells-Gardner K4600 Bench Custom"), "wells-gardner-k4600-bench-custom")
        self.assertEqual(slugify("  weird!! name??"), "weird-name")
        self.assertEqual(auto_name("wells-gardner-k4600-1979", "bench"), "Wells Gardner K4600 1979 bench Custom")
        self.assertEqual(auto_name("", None), "Custom Custom")


if __name__ == "__main__":
    unittest.main()

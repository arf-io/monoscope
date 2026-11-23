# Tests for tools/crtctl (Ghostty CRT control surface).
# Run from the crt/ directory:  python3 -m unittest discover -s tests
# Stdlib only. Never touches the real ~/.config and never executes gdbus:
# every CrtCtl gets a tempfile base dir (via GHOSTTY_CRT_HOME) and an
# injected fake runner.

import copy
import sys
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

TOOLS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tools", "crtctl")


def _load_module():
    loader = importlib.machinery.SourceFileLoader("crtctl", TOOLS_PATH)
    spec = importlib.util.spec_from_loader("crtctl", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


crtctl = _load_module()

# Synthetic params.json: one param of each type, plus the system group
# (power/degauss machinery). Order matters for the golden define-block test.
SYNTH_PARAMS = {
    "version": 1,
    "groups": {"video": "Video pots", "system": "Power state"},
    "params": {
        "gain": {
            "define": "T_GAIN", "type": "float", "default": 1.0,
            "min": 0.0, "max": 2.0, "step": 0.05,
            "group": "video", "label": "GAIN", "knob": "rotary", "desc": ""
        },
        "huge": {
            "define": "T_HUGE", "type": "float", "default": 1000000.0,
            "min": 0.0, "max": 10000000.0, "step": 1.0,
            "group": "video", "label": "HUGE", "knob": "rotary", "desc": ""
        },
        "lines": {
            "define": "T_LINES", "type": "int", "default": 480,
            "min": 200, "max": 1200, "step": 10,
            # nominal 200..1200 is a band; the hard bounds are the wall
            # (synthetic stand-in for scan_lines' divide-by-zero floor)
            "hard_min": 10, "hard_max": 100000,
            "hard_why": "line count divides the raster pitch: zero is a divide-by-zero",
            "range_note": "past 1200 the raster comb goes sub-pixel and aliases",
            "group": "video", "label": "LINES", "knob": "rotary", "desc": ""
        },
        "mode": {
            "define": "T_MODE", "type": "enum", "default": "b",
            "values": {"a": 0, "b": 1, "c": 2},
            "group": "video", "label": "MODE", "knob": "selector", "desc": ""
        },
        "flag": {
            "define": "T_FLAG", "type": "bool", "default": True,
            "group": "video", "label": "FLAG", "knob": "switch", "desc": ""
        },
        "power_on": {
            "define": "T_POWER_ON", "type": "bool", "default": True,
            "group": "system", "label": "POWER", "knob": "button", "desc": ""
        },
        "power_nonce": {
            "define": "T_POWER_NONCE", "type": "int", "default": 1,
            "min": 0, "max": 1000000, "step": 1,
            "group": "system", "label": "power seq", "knob": "hidden", "desc": ""
        },
        "degauss_nonce": {
            "define": "T_DEGAUSS_NONCE", "type": "int", "default": 0,
            "min": 0, "max": 1000000, "step": 1,
            "group": "system", "label": "degauss seq", "knob": "hidden", "desc": ""
        },
    },
}

TEMPLATE = (
    "// synthetic shader template\n"
    "float pre;\n"
    "//@CRT_PARAMS@\n"
    "void mainImage(out vec4 c, in vec2 f) {}\n"
)


class FakeRunner:
    """Injectable subprocess layer; records argv, returns canned results."""

    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def __call__(self, argv, timeout=5.0):
        self.calls.append(list(argv))
        if self.results:
            return self.results.pop(0)
        return (0, "()\n", "")


class CrtctlTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="crtctl-test-")
        self.base = self._tmp.name
        self.crt = os.path.join(self.base, "crt")
        os.makedirs(os.path.join(self.crt, "templates"))
        os.makedirs(os.path.join(self.crt, "presets"))
        self._old_env = os.environ.get("GHOSTTY_CRT_HOME")
        os.environ["GHOSTTY_CRT_HOME"] = self.base
        # A reload-command override in the invoking environment would leak
        # into every reload test; park it for the duration.
        self._old_reload_cmd = os.environ.pop(crtctl.RELOAD_CMD_ENV, None)
        self.write_params(SYNTH_PARAMS)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("GHOSTTY_CRT_HOME", None)
        else:
            os.environ["GHOSTTY_CRT_HOME"] = self._old_env
        if self._old_reload_cmd is not None:
            os.environ[crtctl.RELOAD_CMD_ENV] = self._old_reload_cmd
        self._tmp.cleanup()

    # helpers ---------------------------------------------------------------

    def write_params(self, doc):
        with open(os.path.join(self.crt, "params.json"), "w") as f:
            json.dump(doc, f)

    def write_state(self, doc):
        with open(os.path.join(self.crt, "state.json"), "w") as f:
            json.dump(doc, f)

    def write_template(self, name="test", text=TEMPLATE):
        path = os.path.join(self.crt, "templates", name + ".glsl.tmpl")
        with open(path, "w") as f:
            f.write(text)
        return path

    def ctl(self, runner=None):
        # No base argument: proves resolution via GHOSTTY_CRT_HOME.
        # on_warn sink keeps test output clean; warnings list still records.
        return crtctl.CrtCtl(runner=runner or FakeRunner(),
                             on_warn=lambda m: None)

    def shader_path(self, name="test"):
        return os.path.join(self.base, "shaders", name + ".glsl")


# ----------------------------------------------------------------------------
# loading / defaults / state
# ----------------------------------------------------------------------------

class TestLoadAndState(CrtctlTestCase):
    def test_defaults_loaded(self):
        ctl = self.ctl()
        self.assertEqual(ctl.values["gain"], 1.0)
        self.assertEqual(ctl.values["lines"], 480)
        self.assertEqual(ctl.values["mode"], "b")
        self.assertIs(ctl.values["flag"], True)
        self.assertEqual(ctl.values["power_nonce"], 1)

    def test_base_dir_from_env(self):
        ctl = self.ctl()
        self.assertEqual(ctl.base, os.path.abspath(self.base))
        self.assertEqual(ctl.params_path, os.path.join(self.crt, "params.json"))

    def test_state_merges_over_defaults(self):
        self.write_state({"values": {"gain": 1.5, "mode": "c"},
                          "active_preset": "warm"})
        ctl = self.ctl()
        self.assertEqual(ctl.values["gain"], 1.5)
        self.assertEqual(ctl.values["mode"], "c")
        self.assertEqual(ctl.values["lines"], 480)  # untouched default
        self.assertEqual(ctl.active_preset, "warm")

    def test_state_unknown_keys_dropped_with_warning(self):
        self.write_state({"values": {"gain": 1.4, "bogus_knob": 3}})
        ctl = self.ctl()
        self.assertEqual(ctl.values["gain"], 1.4)
        self.assertNotIn("bogus_knob", ctl.values)
        self.assertTrue(any("bogus_knob" in w for w in ctl.warnings))
        # and the unknown key does not survive a save round-trip
        ctl.save_state()
        with open(ctl.state_path) as f:
            saved = json.load(f)
        self.assertNotIn("bogus_knob", saved["values"])

    def test_state_values_outside_nominal_survive_load(self):
        # Appendix A: min/max are the nominal band, not a wall. A value the
        # user committed past it survives the state.json round trip
        # (quantized to step); only a hard bound sends it back to default.
        self.write_state({"values": {"gain": 99.0, "lines": 2004}})
        ctl = self.ctl()
        self.assertEqual(ctl.values["gain"], 99.0)
        self.assertEqual(ctl.values["lines"], 2000)   # step 10, past max 1200
        self.assertEqual(ctl.warnings, [])            # silent: it is legitimate
        # save round trip keeps the out-of-nominal values verbatim
        ctl.save_state()
        with open(ctl.state_path) as f:
            saved = json.load(f)
        self.assertEqual(saved["values"], {"gain": 99.0, "lines": 2000})
        self.assertEqual(self.ctl().values["lines"], 2000)

    def test_state_values_beyond_hard_bound_fall_back_with_reason(self):
        self.write_state({"values": {"lines": -5, "gain": 1.5}})
        ctl = self.ctl()
        self.assertEqual(ctl.values["lines"], 480)   # default, not clamped
        self.assertEqual(ctl.values["gain"], 1.5)    # the rest still loads
        msg = [w for w in ctl.warnings if "lines" in w]
        self.assertEqual(len(msg), 1)
        self.assertIn("hard minimum 10", msg[0])
        self.assertIn("divide-by-zero", msg[0])      # hard_why is named
        self.assertIn("using default", msg[0])


# ----------------------------------------------------------------------------
# clamping and quantization
# ----------------------------------------------------------------------------

class TestClampQuantize(CrtctlTestCase):
    def test_float_clamp(self):
        # soft=False keeps dial semantics: clamp to the nominal [min, max]
        ctl = self.ctl()
        self.assertEqual(ctl.set("gain", 99, soft=False), 2.0)
        self.assertEqual(ctl.set("gain", -5, soft=False), 0.0)
        self.assertEqual(ctl.warnings, [])

    def test_float_soft_keeps_out_of_nominal(self):
        # soft (the default): the value is kept, quantized, and reported once
        ctl = self.ctl()
        self.assertEqual(ctl.set("gain", 99), 99.0)
        self.assertEqual(ctl.set("gain", -5), -5.0)
        self.assertEqual(ctl.set("gain", 3.03), 3.05)      # still on the step grid
        self.assertEqual(ctl.set("gain", 1.5), 1.5)         # inside: no warning
        self.assertEqual(len(ctl.warnings), 3)
        self.assertEqual(ctl.range_status("gain"), ("ok", 0.0, 2.0))
        ctl.set("gain", 99)
        self.assertEqual(ctl.range_status("gain"), ("over", 0.0, 2.0))
        ctl.set("gain", -1)
        self.assertEqual(ctl.range_status("gain"), ("under", 0.0, 2.0))

    def test_normalize_value_soft_and_strict(self):
        spec = SYNTH_PARAMS["params"]["gain"]
        self.assertEqual(crtctl.normalize_value("gain", spec, 7.5), 2.0)
        self.assertEqual(crtctl.normalize_value("gain", spec, 7.5, soft=False), 2.0)
        self.assertEqual(crtctl.normalize_value("gain", spec, 7.5, soft=True), 7.5)
        # quantize anchored at min on both paths, fuzz-free
        self.assertEqual(repr(crtctl.normalize_value("gain", spec, 7.03, soft=True)),
                         "7.05")
        self.assertEqual(crtctl.quantize_float(7.03, spec, soft=True), 7.05)
        self.assertEqual(crtctl.quantize_float(7.03, spec), 2.0)
        ispec = SYNTH_PARAMS["params"]["lines"]
        self.assertEqual(crtctl.quantize_int(5004, ispec, soft=True), 5000)
        self.assertEqual(crtctl.quantize_int(5004, ispec), 1200)

    def test_hard_bounds_raise_naming_bound_and_reason(self):
        ctl = self.ctl()
        with self.assertRaises(crtctl.ParamError) as cm:
            ctl.set("lines", 0)
        self.assertIn("lines: 0 is below the hard minimum 10", str(cm.exception))
        self.assertIn("divide-by-zero", str(cm.exception))
        with self.assertRaises(crtctl.ParamError) as cm:
            ctl.set("lines", "250000")
        self.assertIn("250000 is above the hard maximum 100000", str(cm.exception))
        self.assertEqual(ctl.values["lines"], 480)   # nothing changed
        # the strict path never reaches a hard bound (nominal sits inside it)
        self.assertEqual(ctl.set("lines", 0, soft=False), 200)
        # module-level: hard_bounds() reports what the schema declares
        self.assertEqual(crtctl.hard_bounds(SYNTH_PARAMS["params"]["lines"]),
                         (10, 100000))
        self.assertEqual(crtctl.hard_bounds(SYNTH_PARAMS["params"]["gain"]),
                         (None, None))

    def test_glsl_literal_limits_refused_on_every_path(self):
        # an int past 32 bits wraps or fails in glslang; a float past 3.4e38
        # folds to inf — neither may reach define_value.
        ctl = self.ctl()
        with self.assertRaises(crtctl.ParamError) as cm:
            ctl.set("huge", 1e39)
        self.assertIn("32-bit GLSL float", str(cm.exception))
        self.assertEqual(ctl.set("huge", 3e38), 3e38)   # inside float32: fine
        # strict path: the nominal clamp lands inside int32 first
        self.assertEqual(ctl.set("lines", 3000000000, soft=False), 1200)
        # soft path: refused before any hard-bound check (int32 is the wall
        # for every int param, declared or not)
        with self.assertRaises(crtctl.ParamError) as cm:
            ctl.set("lines", 3000000000)
        self.assertIn("32-bit GLSL int", str(cm.exception))
        with self.assertRaises(crtctl.ParamError) as cm:
            crtctl.normalize_value("n", {"type": "int", "step": 1}, -3000000000,
                                   soft=True)
        self.assertIn("32-bit GLSL int", str(cm.exception))
        # state.json carrying such a value falls back to default with a warning
        self.write_state({"values": {"huge": 1e39}})
        ctl = self.ctl()
        self.assertEqual(ctl.values["huge"], 1000000.0)
        self.assertTrue(any("32-bit GLSL float" in w for w in ctl.warnings))

    def test_float_quantize_to_step(self):
        ctl = self.ctl()
        self.assertEqual(ctl.set("gain", 1.03), 1.05)  # step 0.05
        self.assertEqual(ctl.set("gain", 1.02), 1.0)
        self.assertEqual(ctl.set("gain", "0.976"), 1.0)  # string input ok

    def test_float_quantize_no_fp_fuzz(self):
        # 0.05 * 21 = 1.0500000000000002 without the rounding guard
        ctl = self.ctl()
        v = ctl.set("gain", 1.05)
        self.assertEqual(repr(v), "1.05")

    def test_int_clamp_and_quantize(self):
        ctl = self.ctl()
        self.assertEqual(ctl.set("lines", 487, soft=False), 490)   # step 10
        self.assertEqual(ctl.set("lines", 5000, soft=False), 1200)
        self.assertEqual(ctl.set("lines", "484", soft=False), 480)
        self.assertIsInstance(ctl.values["lines"], int)
        # soft: past nominal survives (quantized), hard bound still refuses
        self.assertEqual(ctl.set("lines", 5000), 5000)
        self.assertEqual(ctl.set("lines", "2004"), 2000)
        self.assertIsInstance(ctl.values["lines"], int)
        with self.assertRaises(crtctl.ParamError):
            ctl.set("lines", 4)                                    # < hard_min 10
        self.assertEqual(ctl.values["lines"], 2000)

    def test_nominal_note_generic_and_schema(self):
        gain = SYNTH_PARAMS["params"]["gain"]      # no range_note
        lines = SYNTH_PARAMS["params"]["lines"]    # has range_note
        self.assertEqual(crtctl.nominal_note(gain, 1.0), "")
        self.assertIn("above the nominal maximum 2", crtctl.nominal_note(gain, 9.0))
        self.assertIn("below the nominal minimum 0", crtctl.nominal_note(gain, -1.0))
        self.assertEqual(crtctl.nominal_note(lines, 480), "")
        self.assertEqual(crtctl.nominal_note(lines, 2000),
                         "past 1200 the raster comb goes sub-pixel and aliases")
        # bool/enum specs are never out of range
        self.assertEqual(crtctl.range_status(SYNTH_PARAMS["params"]["flag"], True),
                         ("ok", None, None))
        self.assertEqual(crtctl.nominal_note(SYNTH_PARAMS["params"]["mode"], "c"), "")

    def test_set_warning_text(self):
        seen = []
        ctl = crtctl.CrtCtl(runner=FakeRunner(), on_warn=seen.append)
        ctl.set("lines", 2000)
        self.assertEqual(seen, [
            "lines = 2000 is outside the nominal range 200..1200: "
            "past 1200 the raster comb goes sub-pixel and aliases"])
        ctl.set("gain", -0.5)
        self.assertEqual(seen[-1],
                         "gain = -0.5 is outside the nominal range 0..2: below the "
                         "nominal minimum 0 the shader applies the value literally; "
                         "the look is uncalibrated there")
        ctl.set("gain", 1.0)             # back inside: silent
        self.assertEqual(len(seen), 2)
        # default sink prints to stderr as a one-liner
        import io
        import contextlib
        err = io.StringIO()
        ctl2 = crtctl.CrtCtl(runner=FakeRunner())
        with contextlib.redirect_stderr(err):
            ctl2.set("gain", 5)
        self.assertEqual(err.getvalue().count("\n"), 1)
        self.assertTrue(err.getvalue().startswith(
            "crtctl: warning: gain = 5 is outside the nominal range 0..2: "))

    def test_cmd_set_prints_value_and_warns_on_stderr(self):
        import io
        import contextlib
        self.write_template("t")
        ctl = crtctl.CrtCtl(runner=FakeRunner())     # default warn sink: stderr
        parser = crtctl.build_parser()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = crtctl.cmd_set(ctl, parser.parse_args(["set", "lines", "2000"]),
                                "com.example.x")
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue(), "lines = 2000\n")   # stdout format unchanged
        self.assertEqual(err.getvalue(),
                         "crtctl: warning: lines = 2000 is outside the nominal range "
                         "200..1200: past 1200 the raster comb goes sub-pixel and "
                         "aliases\n")
        with open(self.shader_path("t")) as f:
            self.assertIn("#define T_LINES 2000", f.read())  # applied verbatim
        # a hard-bound violation is a refusal (ParamError -> main exits 1):
        # nothing regenerated, value unchanged
        os.remove(self.shader_path("t"))
        with self.assertRaises(crtctl.ParamError) as cm:
            crtctl.cmd_set(ctl, parser.parse_args(["set", "lines", "0"]),
                           "com.example.x")
        self.assertIn("hard minimum 10", str(cm.exception))
        self.assertFalse(os.path.exists(self.shader_path("t")))
        self.assertEqual(ctl.values["lines"], 2000)

    def test_list_marks_values_outside_nominal(self):
        import io
        import contextlib
        ctl = self.ctl()
        ctl.set("lines", 2000)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            crtctl.cmd_list(ctl, crtctl.build_parser().parse_args(["list"]))
        rows = {l.split()[0]: l for l in out.getvalue().splitlines() if l.startswith("  ")}
        self.assertTrue(rows["lines"].rstrip().endswith("outside nominal"), rows["lines"])
        self.assertIn(rows["lines"].split("]")[1].strip().split(" outside")[0], ("⚠", "!"))
        self.assertFalse(rows["gain"].endswith("outside nominal"), rows["gain"])
        # _range_text itself: value optional, marker only when outside
        spec = SYNTH_PARAMS["params"]["gain"]
        self.assertEqual(crtctl._range_text(spec), "[0 .. 2 step 0.05]")
        self.assertEqual(crtctl._range_text(spec, 1.0), "[0 .. 2 step 0.05]")
        self.assertTrue(crtctl._range_text(spec, 3.0).endswith(" outside nominal"))
        self.assertIn(crtctl.outside_nominal_mark(io.StringIO()),
                      (crtctl.OUTSIDE_NOMINAL_UTF, crtctl.OUTSIDE_NOMINAL_ASCII))
        class Latin1:
            encoding = "latin-1"
        self.assertEqual(crtctl.outside_nominal_mark(Latin1()),
                         crtctl.OUTSIDE_NOMINAL_ASCII)

    def test_bool_parsing(self):
        ctl = self.ctl()
        for raw in (True, 1, "1", "on", "true", "yes"):
            self.assertIs(ctl.set("flag", raw), True, raw)
        for raw in (False, 0, "0", "off", "false", "no"):
            self.assertIs(ctl.set("flag", raw), False, raw)
        with self.assertRaises(crtctl.ParamError):
            ctl.set("flag", "maybe")

    def test_enum_by_name_and_code(self):
        ctl = self.ctl()
        self.assertEqual(ctl.set("mode", "c"), "c")
        self.assertEqual(ctl.set("mode", 0), "a")
        self.assertEqual(ctl.set("mode", "2"), "c")
        with self.assertRaises(crtctl.ParamError):
            ctl.set("mode", "zzz")
        with self.assertRaises(crtctl.ParamError):
            ctl.set("mode", 99)

    def test_unknown_param_rejected(self):
        ctl = self.ctl()
        with self.assertRaises(crtctl.ParamError):
            ctl.set("no_such_knob", 1)
        with self.assertRaises(crtctl.ParamError):
            ctl.get("no_such_knob")

    def test_nonfinite_rejected(self):
        ctl = self.ctl()
        with self.assertRaises(crtctl.ParamError):
            ctl.set("gain", "nan")
        with self.assertRaises(crtctl.ParamError):
            ctl.set("gain", "inf")


# ----------------------------------------------------------------------------
# define block generation (golden)
# ----------------------------------------------------------------------------

class TestDefineBlock(CrtctlTestCase):
    def test_golden_block(self):
        ctl = self.ctl()
        self.assertEqual(ctl.define_block(), [
            "#define CRT_PARAMS_INJECTED 1",
            "#define T_GAIN 1.0",
            "#define T_HUGE 1e+06",
            "#define T_LINES 480",
            "#define T_MODE 1",
            "#define T_FLAG 1",
            "#define T_POWER_ON 1",
            "#define T_POWER_NONCE 1",
            "#define T_DEGAUSS_NONCE 0",
        ])

    def test_floats_always_have_point_or_exponent(self):
        ctl = self.ctl()
        for raw in (0, 1, 2, 0.5, 1.25, 1.999):
            ctl.set("gain", raw)
            line = [l for l in ctl.define_block() if "T_GAIN" in l][0]
            token = line.split()[-1]
            self.assertTrue("." in token or "e" in token or "E" in token,
                            "GLSL float literal %r lacks . or e" % token)
        ctl.set("huge", 3000000)
        line = [l for l in ctl.define_block() if "T_HUGE" in l][0]
        self.assertEqual(line, "#define T_HUGE 3e+06")

    def test_format_float_glsl(self):
        self.assertEqual(crtctl.format_float_glsl(1), "1.0")
        self.assertEqual(crtctl.format_float_glsl(-0.25), "-0.25")
        self.assertEqual(crtctl.format_float_glsl(6500.0), "6500.0")
        self.assertEqual(crtctl.format_float_glsl(1e7), "1e+07")
        self.assertEqual(crtctl.format_float_glsl(0.0005), "0.0005")

    def test_bool_and_enum_codes(self):
        ctl = self.ctl()
        ctl.set("flag", False)
        ctl.set("mode", "c")
        block = ctl.define_block()
        self.assertIn("#define T_FLAG 0", block)
        self.assertIn("#define T_MODE 2", block)


# ----------------------------------------------------------------------------
# template injection + generation
# ----------------------------------------------------------------------------

class TestTemplates(CrtctlTestCase):
    def test_marker_replaced_rest_byte_identical(self):
        ctl = self.ctl()
        block = ctl.define_block()
        out = crtctl.inject_defines(TEMPLATE, block)
        expected = (
            "// synthetic shader template\n"
            "float pre;\n"
            + "\n".join(block) + "\n"
            + "void mainImage(out vec4 c, in vec2 f) {}\n"
        )
        self.assertEqual(out, expected)

    def test_missing_marker_is_error(self):
        ctl = self.ctl()
        with self.assertRaises(crtctl.CrtError):
            crtctl.inject_defines("void main() {}\n", ctl.define_block())

    def test_generate_writes_shader_with_guard_first(self):
        self.write_template("scan")
        ctl = self.ctl()
        outs = ctl.generate()
        self.assertEqual(outs, [self.shader_path("scan")])
        with open(outs[0]) as f:
            text = f.read()
        lines = text.splitlines()
        idx = lines.index("#define CRT_PARAMS_INJECTED 1")
        self.assertEqual(lines[idx + 1], "#define T_GAIN 1.0")
        self.assertNotIn("//@CRT_PARAMS@", text)
        self.assertIsNotNone(ctl.last_generated)

    def test_generate_all_templates(self):
        self.write_template("one")
        self.write_template("two")
        ctl = self.ctl()
        outs = ctl.generate()
        self.assertEqual(sorted(os.path.basename(o) for o in outs),
                         ["one.glsl", "two.glsl"])

    def test_generate_without_templates_warns(self):
        ctl = self.ctl()
        self.assertEqual(ctl.generate(), [])
        self.assertTrue(any("no templates" in w for w in ctl.warnings))

    def test_generate_missing_marker_names_template(self):
        self.write_template("broken", "void main() {}\n")
        ctl = self.ctl()
        with self.assertRaises(crtctl.CrtError) as cm:
            ctl.generate()
        self.assertIn("broken", str(cm.exception))


# ----------------------------------------------------------------------------
# atomic write
# ----------------------------------------------------------------------------

class TestAtomicWrite(CrtctlTestCase):
    def test_no_partial_file_on_replace_failure(self):
        self.write_template("test")
        shaders_dir = os.path.join(self.base, "shaders")
        os.makedirs(shaders_dir)
        dest = self.shader_path("test")
        with open(dest, "w") as f:
            f.write("OLD CONTENT")
        ctl = self.ctl()

        def boom(src, dst):
            raise OSError("simulated rename failure")

        orig = crtctl._REPLACE
        crtctl._REPLACE = boom
        try:
            with self.assertRaises(OSError):
                ctl.generate()
        finally:
            crtctl._REPLACE = orig
        with open(dest) as f:
            self.assertEqual(f.read(), "OLD CONTENT")  # destination untouched
        leftovers = [n for n in os.listdir(shaders_dir) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])  # tmp file cleaned up

    def test_atomic_write_success(self):
        path = os.path.join(self.base, "out.txt")
        crtctl.atomic_write(path, "hello")
        with open(path) as f:
            self.assertEqual(f.read(), "hello")
        self.assertEqual([n for n in os.listdir(self.base)
                          if n.endswith(".tmp")], [])


# ----------------------------------------------------------------------------
# presets
# ----------------------------------------------------------------------------

class TestPresets(CrtctlTestCase):
    def test_save_apply_round_trip(self):
        ctl = self.ctl()
        ctl.set("gain", 1.5)
        ctl.set("mode", "c")
        ctl.power("toggle")  # system-group churn must NOT be saved
        path = ctl.save_preset("warm", "warmer look")
        with open(path) as f:
            doc = json.load(f)
        self.assertEqual(doc, {"name": "warm", "description": "warmer look",
                               "params": {"gain": 1.5, "mode": "c"}})
        ctl.save_state()

        ctl2 = self.ctl()
        ctl2.set("gain", 0.5)
        ctl2.set("lines", 240)
        ctl2.apply_preset("warm")
        self.assertEqual(ctl2.values["gain"], 1.5)
        self.assertEqual(ctl2.values["mode"], "c")
        self.assertEqual(ctl2.values["lines"], 480)  # reset to default
        self.assertEqual(ctl2.active_preset, "warm")
        ctl2.save_state()
        with open(ctl2.state_path) as f:
            st = json.load(f)
        self.assertEqual(st["active_preset"], "warm")

    def test_apply_preserves_system_group(self):
        ctl = self.ctl()
        ctl.power("toggle")   # power off, nonce 2
        ctl.degauss()         # nonce 1
        ctl.save_preset("look", "")
        ctl.apply_preset("look")
        self.assertIs(ctl.values["power_on"], False)
        self.assertEqual(ctl.values["power_nonce"], 2)
        self.assertEqual(ctl.values["degauss_nonce"], 1)

    def test_apply_unknown_preset_key_warns(self):
        with open(os.path.join(self.crt, "presets", "odd.json"), "w") as f:
            json.dump({"name": "odd", "description": "",
                       "params": {"gain": 1.2, "ghost": 9}}, f)
        ctl = self.ctl()
        ctl.apply_preset("odd")
        self.assertEqual(ctl.values["gain"], 1.2)
        self.assertTrue(any("ghost" in w for w in ctl.warnings))

    def test_missing_preset_is_error(self):
        ctl = self.ctl()
        with self.assertRaises(crtctl.CrtError):
            ctl.apply_preset("nope")

    def test_bad_preset_name_rejected(self):
        ctl = self.ctl()
        with self.assertRaises(crtctl.CrtError):
            ctl.save_preset("../evil", "")
        with self.assertRaises(crtctl.CrtError):
            ctl.save_preset("", "")

    def test_list_presets(self):
        ctl = self.ctl()
        ctl.set("gain", 1.5)
        ctl.save_preset("aaa", "first")
        ctl.save_preset("bbb", "second")
        listed = [(n, d) for n, d, _p in ctl.list_presets()]
        self.assertEqual(listed, [("aaa", "first"), ("bbb", "second")])

    def test_preset_out_of_nominal_round_trips_unchanged(self):
        # Appendix A: a preset may carry values past the nominal band; apply
        # honours them and save writes them back verbatim (no clamp anywhere).
        with open(os.path.join(self.crt, "presets", "experiment.json"), "w") as f:
            json.dump({"name": "experiment", "description": "2000 lines",
                       "params": {"lines": 2000, "gain": 4.5}}, f)
        ctl = self.ctl()
        ctl.apply_preset("experiment")
        self.assertEqual(ctl.values["lines"], 2000)
        self.assertEqual(ctl.values["gain"], 4.5)
        self.assertEqual(ctl.warnings, [])          # legitimate, not noisy
        self.assertEqual(ctl.range_status("lines"), ("over", 200, 1200))
        self.assertEqual(ctl.baseline_values()["lines"], 2000)  # soft here too
        self.assertFalse(ctl.modified_from_baseline())
        path = ctl.save_preset("experiment", "2000 lines")
        with open(path) as f:
            self.assertEqual(json.load(f)["params"], {"gain": 4.5, "lines": 2000})
        # ... and through state.json + a fresh CrtCtl
        ctl.save_state()
        ctl2 = self.ctl()
        self.assertEqual((ctl2.values["lines"], ctl2.values["gain"]), (2000, 4.5))
        self.assertEqual(ctl2.active_preset, "experiment")
        # a preset value beyond a hard bound is the one thing that falls back
        with open(os.path.join(self.crt, "presets", "broken.json"), "w") as f:
            json.dump({"name": "broken", "description": "",
                       "params": {"lines": 0, "gain": 0.5}}, f)
        ctl2.apply_preset("broken")
        self.assertEqual(ctl2.values["lines"], 480)
        self.assertEqual(ctl2.values["gain"], 0.5)
        self.assertTrue(any("hard minimum 10" in w and "preset 'broken'" in w
                            for w in ctl2.warnings))

    def test_profile_out_of_nominal_round_trips_unchanged(self):
        ctl = self.ctl()
        ctl.set("gain", 7.0)
        ctl.set("lines", 3000)
        ctl.save_profile("wild")
        ctl.set("gain", 1.0, soft=False)
        ctl.set("lines", 480, soft=False)
        ctl.load_profile("wild")
        self.assertEqual((ctl.values["gain"], ctl.values["lines"]), (7.0, 3000))


# ----------------------------------------------------------------------------
# power / degauss nonce logic
# ----------------------------------------------------------------------------

class TestPowerDegauss(CrtctlTestCase):
    def test_power_toggle_increments_nonce(self):
        ctl = self.ctl()
        state, changed = ctl.power("toggle")
        self.assertIs(state, False)
        self.assertTrue(changed)
        self.assertEqual(ctl.values["power_nonce"], 2)
        state, changed = ctl.power("toggle")
        self.assertIs(state, True)
        self.assertEqual(ctl.values["power_nonce"], 3)

    def test_power_explicit_noop_does_not_bump(self):
        ctl = self.ctl()
        state, changed = ctl.power("on")  # already on
        self.assertIs(state, True)
        self.assertFalse(changed)
        self.assertEqual(ctl.values["power_nonce"], 1)
        state, changed = ctl.power("off")
        self.assertTrue(changed)
        self.assertEqual(ctl.values["power_nonce"], 2)

    def test_degauss_increments(self):
        ctl = self.ctl()
        self.assertEqual(ctl.degauss(), 1)
        self.assertEqual(ctl.degauss(), 2)
        self.assertEqual(ctl.values["degauss_nonce"], 2)

    def test_nonce_wraps_at_max(self):
        ctl = self.ctl()
        ctl.values["degauss_nonce"] = 1000000
        self.assertEqual(ctl.degauss(), 0)  # wraps to min, keeps changing


# ----------------------------------------------------------------------------
# D-Bus command construction (never executed for real)
# ----------------------------------------------------------------------------

class TestDBus(CrtctlTestCase):
    RELOAD_ARGV = [
        "gdbus", "call", "--session",
        "--dest", "com.mitchellh.ghostty",
        "--object-path", "/com/mitchellh/ghostty",
        "--method", "org.gtk.Actions.Activate",
        "reload-config", "[]", "{}",
    ]

    def test_build_reload_argv_exact(self):
        self.assertEqual(crtctl.build_reload_argv("com.mitchellh.ghostty"),
                         self.RELOAD_ARGV)

    def test_reload_uses_injected_runner_with_exact_argv(self):
        runner = FakeRunner([(0, "()\n", "")])
        ctl = self.ctl(runner=runner)
        ok, detail = ctl.reload("com.mitchellh.ghostty")
        self.assertTrue(ok)
        self.assertEqual(runner.calls, [self.RELOAD_ARGV])

    def test_reload_custom_dest(self):
        runner = FakeRunner()
        ctl = self.ctl(runner=runner)
        ctl.reload("com.mitchellh.ghostty-debug")
        self.assertEqual(runner.calls[0][4], "com.mitchellh.ghostty-debug")

    def test_reload_failure_warns_never_raises(self):
        runner = FakeRunner([(1, "", "Error: no such name\n")])
        ctl = self.ctl(runner=runner)
        ok, detail = ctl.reload("com.mitchellh.ghostty")
        self.assertFalse(ok)
        self.assertIn("no such name", detail)
        self.assertTrue(any("reload" in w for w in ctl.warnings))

    def test_reload_gdbus_missing_warns(self):
        def no_gdbus(argv, timeout=5.0):
            raise FileNotFoundError("gdbus")
        ctl = self.ctl(runner=no_gdbus)
        ok, detail = ctl.reload("com.mitchellh.ghostty")
        self.assertFalse(ok)
        self.assertTrue(any("gdbus" in w for w in ctl.warnings))

    def test_targets_parses_listnames(self):
        out = ("(['org.freedesktop.DBus', ':1.55', 'com.mitchellh.ghostty', "
               "'org.gnome.Shell', 'com.mitchellh.ghostty-debug'],)\n")
        runner = FakeRunner([(0, out, "")])
        ctl = self.ctl(runner=runner)
        self.assertEqual(ctl.targets(),
                         ["com.mitchellh.ghostty", "com.mitchellh.ghostty-debug"])
        self.assertEqual(runner.calls, [[
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.DBus",
            "--object-path", "/org/freedesktop/DBus",
            "--method", "org.freedesktop.DBus.ListNames",
        ]])

    def test_targets_failure_returns_none(self):
        runner = FakeRunner([(1, "", "no bus\n")])
        ctl = self.ctl(runner=runner)
        self.assertIsNone(ctl.targets())

    def test_dest_flag_survives_either_position(self):
        # regression: subparser defaults must not clobber a pre-verb --dest
        parser = crtctl.build_parser()
        args = parser.parse_args(["--dest", "com.example.x", "apply"])
        self.assertEqual(getattr(args, "dest", None), "com.example.x")
        args = parser.parse_args(["apply", "--dest", "com.example.y"])
        self.assertEqual(getattr(args, "dest", None), "com.example.y")
        args = parser.parse_args(["apply"])
        self.assertIsNone(getattr(args, "dest", None))


# ----------------------------------------------------------------------------
# darwin transport + base-dir resolution (platform monkeypatched, never real)
# ----------------------------------------------------------------------------

class DarwinTestCase(CrtctlTestCase):
    """CrtctlTestCase with crtctl._PLATFORM forced to 'darwin'."""

    def setUp(self):
        super().setUp()
        self._plat = crtctl._PLATFORM
        crtctl._PLATFORM = "darwin"

    def tearDown(self):
        crtctl._PLATFORM = self._plat
        super().tearDown()


class TestDarwinReload(DarwinTestCase):
    PKILL_ARGV = ["pkill", "-USR2", "-f", "Ghostty"]

    def test_reload_argv_is_pkill_sigusr2(self):
        self.assertEqual(crtctl.reload_argv("io.arf.ghostty_phosphor"),
                         self.PKILL_ARGV)

    def test_reload_uses_pkill(self):
        runner = FakeRunner([(0, "", "")])
        ctl = self.ctl(runner=runner)
        ok, detail = ctl.reload("io.arf.ghostty_phosphor")
        self.assertTrue(ok)
        self.assertEqual(runner.calls, [self.PKILL_ARGV])

    def test_reload_no_match_is_actionable(self):
        # pkill exits 1 with no output when nothing matched
        runner = FakeRunner([(1, "", "")])
        ctl = self.ctl(runner=runner)
        ok, detail = ctl.reload("io.arf.ghostty_phosphor")
        self.assertFalse(ok)
        self.assertIn("not running", detail)
        self.assertIn("ghostty-phosphor-crt-macos", detail)
        self.assertTrue(any("reload" in w for w in ctl.warnings))

    def test_reload_pkill_missing_warns(self):
        def no_pkill(argv, timeout=5.0):
            raise FileNotFoundError("pkill")
        ctl = self.ctl(runner=no_pkill)
        ok, detail = ctl.reload("io.arf.ghostty_phosphor")
        self.assertFalse(ok)
        self.assertTrue(any("pkill" in w for w in ctl.warnings))

    def test_reload_cmd_env_overrides_transport(self):
        os.environ[crtctl.RELOAD_CMD_ENV] = 'pkill -USR2 -x "ghostty custom"'
        try:
            self.assertEqual(crtctl.reload_argv("x"),
                             ["pkill", "-USR2", "-x", "ghostty custom"])
        finally:
            os.environ.pop(crtctl.RELOAD_CMD_ENV, None)

    def test_reload_cmd_env_overrides_on_linux_too(self):
        crtctl._PLATFORM = "linux"
        os.environ[crtctl.RELOAD_CMD_ENV] = "systemctl --user kill -sUSR2 x"
        try:
            self.assertEqual(crtctl.reload_argv("x")[0], "systemctl")
        finally:
            os.environ.pop(crtctl.RELOAD_CMD_ENV, None)

    def test_reload_cmd_env_invalid_warns_never_raises(self):
        os.environ[crtctl.RELOAD_CMD_ENV] = 'unbalanced "quote'
        try:
            ctl = self.ctl()
            ok, detail = ctl.reload("x")
            self.assertFalse(ok)
            self.assertIn(crtctl.RELOAD_CMD_ENV, detail)
        finally:
            os.environ.pop(crtctl.RELOAD_CMD_ENV, None)

    def test_reload_cmd_env_empty_warns_never_raises(self):
        os.environ[crtctl.RELOAD_CMD_ENV] = "   "
        try:
            ctl = self.ctl()
            ok, detail = ctl.reload("x")
            self.assertFalse(ok)
            self.assertIn("empty", detail)
        finally:
            os.environ.pop(crtctl.RELOAD_CMD_ENV, None)

    def test_linux_reload_argv_unchanged(self):
        crtctl._PLATFORM = "linux"
        self.assertEqual(crtctl.reload_argv("com.mitchellh.ghostty"),
                         crtctl.build_reload_argv("com.mitchellh.ghostty"))


class TestDarwinTargets(DarwinTestCase):
    PGREP_ARGV = ["pgrep", "-fl", "Ghostty"]

    def test_targets_parses_pgrep_lines(self):
        out = ("501 /Applications/Ghostty.app/Contents/MacOS/ghostty\n"
               "777 /tmp/build/ReleaseLocal/Ghostty.app/Contents/MacOS/ghostty\n")
        runner = FakeRunner([(0, out, "")])
        ctl = self.ctl(runner=runner)
        found = ctl.targets()
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0].startswith("501 "))
        self.assertEqual(runner.calls, [self.PGREP_ARGV])

    def test_targets_no_match_is_empty_not_error(self):
        runner = FakeRunner([(1, "", "")])  # pgrep: 1 == nothing matched
        ctl = self.ctl(runner=runner)
        self.assertEqual(ctl.targets(), [])

    def test_targets_real_failure_returns_none(self):
        runner = FakeRunner([(2, "", "pgrep: bad usage\n")])
        ctl = self.ctl(runner=runner)
        self.assertIsNone(ctl.targets())

    def test_dest_reachable_true_false_unknown(self):
        ctl = self.ctl(runner=FakeRunner([(0, "501 Ghostty\n", "")]))
        self.assertIs(ctl.dest_reachable("ignored"), True)
        ctl = self.ctl(runner=FakeRunner([(1, "", "")]))
        self.assertIs(ctl.dest_reachable("ignored"), False)
        os.environ[crtctl.RELOAD_CMD_ENV] = "true"
        try:
            ctl = self.ctl(runner=FakeRunner())
            self.assertIsNone(ctl.dest_reachable("ignored"))
        finally:
            os.environ.pop(crtctl.RELOAD_CMD_ENV, None)


class TestDefaultBase(unittest.TestCase):
    """default_base() resolution; env + platform fully controlled."""

    ENV_KEYS = ("GHOSTTY_CRT_HOME", "XDG_CONFIG_HOME")

    def setUp(self):
        self._plat = crtctl._PLATFORM
        self._saved = {k: os.environ.pop(k, None) for k in self.ENV_KEYS}

    def tearDown(self):
        crtctl._PLATFORM = self._plat
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_crt_home_wins_everywhere(self):
        os.environ["GHOSTTY_CRT_HOME"] = "/tmp/crt-home"
        os.environ["XDG_CONFIG_HOME"] = "/tmp/xdg"
        for plat in ("linux", "darwin"):
            crtctl._PLATFORM = plat
            self.assertEqual(crtctl.default_base(), "/tmp/crt-home", plat)

    def test_xdg_wins_over_platform_default(self):
        os.environ["XDG_CONFIG_HOME"] = "/tmp/xdg"
        for plat in ("linux", "darwin"):
            crtctl._PLATFORM = plat
            self.assertEqual(crtctl.default_base(),
                             os.path.join("/tmp/xdg", "ghostty"), plat)

    def test_darwin_default_is_app_support(self):
        crtctl._PLATFORM = "darwin"
        self.assertEqual(
            crtctl.default_base(),
            os.path.join(os.path.expanduser("~"), "Library",
                         "Application Support", "com.mitchellh.ghostty"))

    def test_linux_default_unchanged(self):
        crtctl._PLATFORM = "linux"
        self.assertEqual(
            crtctl.default_base(),
            os.path.join(os.path.expanduser("~"), ".config", "ghostty"))


# ----------------------------------------------------------------------------
# real params.json sanity (repo file loads and generates floats correctly)
# ----------------------------------------------------------------------------

class TestRealParams(unittest.TestCase):
    REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "params.json")

    def test_real_params_load_and_block(self):
        with tempfile.TemporaryDirectory(prefix="crtctl-real-") as base:
            crt = os.path.join(base, "crt")
            os.makedirs(crt)
            with open(self.REAL) as f:
                doc = json.load(f)
            with open(os.path.join(crt, "params.json"), "w") as f:
                json.dump(doc, f)
            ctl = crtctl.CrtCtl(base=base, runner=FakeRunner())
            block = ctl.define_block()
            self.assertEqual(block[0], "#define CRT_PARAMS_INJECTED 1")
            self.assertEqual(len(block), len(doc["params"]) + 1)
            for line in block[1:]:
                parts = line.split()
                self.assertEqual(parts[0], "#define")
                self.assertTrue(parts[1].startswith("CRT_"))
            # every float define must be a valid GLSL float literal
            for key, spec in doc["params"].items():
                if spec["type"] != "float":
                    continue
                line = [l for l in block if " %s " % spec["define"] in l][0]
                token = line.split()[-1]
                self.assertTrue("." in token or "e" in token.lower(),
                                "%s: %r not float-typed" % (key, token))

    def _real(self):
        with open(self.REAL) as f:
            return json.load(f)["params"]

    def test_hard_bounds_are_declared_consistently(self):
        """Appendix A invariants on the shipped schema: a hard bound is a
        technical limit, so it must (a) contain the nominal band and the
        default, (b) sit on the step grid anchored at min (normalize_value
        quantizes before it checks), and (c) carry a hard_why."""
        params = self._real()
        seen = 0
        for key, spec in params.items():
            has = [b for b in ("hard_min", "hard_max") if b in spec]
            if not has:
                self.assertNotIn("hard_why", spec, key)
                continue
            seen += 1
            self.assertIn(spec["type"], ("float", "int"), key)
            self.assertIn("hard_why", spec, key)
            self.assertTrue(spec["hard_why"].strip(), key)
            lo, hi = spec["min"], spec["max"]
            step = spec.get("step") or 1
            self.assertTrue(lo <= spec["default"] <= hi, key)
            for b in has:
                hb = spec[b]
                n = (hb - lo) / step
                self.assertAlmostEqual(n, round(n), places=6,
                                       msg="%s.%s=%r is off the step grid" % (key, b, hb))
                if spec["type"] == "int":
                    self.assertIsInstance(hb, int, key)
            if "hard_min" in spec:
                self.assertLessEqual(spec["hard_min"], lo, key)
            if "hard_max" in spec:
                self.assertGreaterEqual(spec["hard_max"], hi, key)
        # the schema does declare some (the divide-by-zero floors at least)
        self.assertGreaterEqual(seen, 10)
        for key in ("focus", "scan_min_width", "scan_lines", "mask_triads",
                    "hum_period", "h_bandwidth", "tube_gamma"):
            self.assertIn("hard_min", params[key], key)

    def test_nonces_stay_exact_in_the_half_float_state_texture(self):
        """The state pass stores its copy of each nonce in an RGBA16F texel
        (src/renderer/OpenGL.zig historyTextureOptions, Metal.zig .rgba16float).
        A half float is exact for integers only up to 2048; at 2049 the
        stored != compiled compare re-fires every frame and the power /
        degauss / erase sequence never completes. crtctl._bump_nonce wraps
        at `max`, so both the nominal max and the hard max must stay <= 2048."""
        params = self._real()
        for key in ("power_nonce", "degauss_nonce", "erase_nonce"):
            spec = params[key]
            self.assertLessEqual(spec["max"], 2048, key)
            self.assertLessEqual(spec["hard_max"], 2048, key)
            self.assertGreaterEqual(spec["hard_min"], -2048, key)
            self.assertIn("half float", spec["hard_why"], key)

    def test_bounded_by_and_range_note_are_well_formed(self):
        params = self._real()
        rels = notes = 0
        for key, spec in params.items():
            if "range_note" in spec:
                notes += 1
                self.assertIsInstance(spec["range_note"], str, key)
                self.assertTrue(spec["range_note"].strip(), key)
                self.assertIn(spec["type"], ("float", "int"), key)
            for r in spec.get("bounded_by", []):
                rels += 1
                self.assertEqual(set(r), {"param", "when", "effect"}, (key, r))
                self.assertIn(r["param"], params, (key, r["param"]))
                self.assertNotEqual(r["param"], key, key)   # attributed to ANOTHER control
                self.assertTrue(r["when"].strip() and r["effect"].strip(), (key, r))
        # the mined corpus: >= 30 range_notes on rotaries, the 23-ish help-text
        # relations promoted (and more discovered)
        self.assertGreaterEqual(notes, 30)
        self.assertGreaterEqual(rels, 23)
        # spot checks against the help text the operator cited
        by = {r["param"] for r in params["interlace"]["bounded_by"]}
        self.assertIn("scan_lines", by)
        self.assertIn("scan_rate", by)
        by = {r["param"] for r in params["rolling_gain"]["bounded_by"]}
        self.assertIn("rolling_scan", by)
        by = {r["param"] for r in params["smooth_scroll"]["bounded_by"]}
        self.assertIn("smooth_cell_px", by)
        by = {r["param"] for r in params["damper_wires"]["bounded_by"]}
        self.assertEqual(by, {"mask_type", "phosphor", "mask_triads"})

    def test_real_schema_soft_paths_accept_out_of_nominal(self):
        """End to end on the shipped params.json: 2000 scan lines is a
        legitimate value (Appendix A), 0 is refused with the divide-by-zero
        reason, and the nonce hard cap names the half-float limit."""
        with tempfile.TemporaryDirectory(prefix="crtctl-real-") as base:
            crt = os.path.join(base, "crt")
            os.makedirs(crt)
            with open(self.REAL) as f:
                doc = json.load(f)
            with open(os.path.join(crt, "params.json"), "w") as f:
                json.dump(doc, f)
            seen = []
            ctl = crtctl.CrtCtl(base=base, runner=FakeRunner(), on_warn=seen.append)
            self.assertEqual(ctl.set("scan_lines", 2000), 2000)
            self.assertEqual(seen[-1].split(":")[0],
                             "scan_lines = 2000 is outside the nominal range 200..1200")
            self.assertIn("#define CRT_SCAN_LINES 2000", ctl.define_block())
            with self.assertRaises(crtctl.ParamError) as cm:
                ctl.set("scan_lines", 0)
            self.assertIn("divide-by-zero", str(cm.exception))
            with self.assertRaises(crtctl.ParamError) as cm:
                ctl.set("power_nonce", 2049)
            self.assertIn("hard maximum 2048", str(cm.exception))
            self.assertIn("half float", str(cm.exception))
            self.assertEqual(ctl.set("focus", 0.3), 0.3)         # under nominal, ok
            with self.assertRaises(crtctl.ParamError):
                ctl.set("focus", 0)                             # hard floor
            self.assertEqual(ctl.set("hum_period", 200), 200.0)


if __name__ == "__main__":
    unittest.main()

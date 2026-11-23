# Tests for the crtctl preset-picker helpers: meta derivation goldens,
# sort modes over the real preset bank, centered-cursor windowing math,
# two-pane layout math, details-pane content, characterful-override
# ranking, and list_preset_docs. Stdlib only; pure functions plus the
# repo's real presets/ and params.json — nothing touches ~/.config.

import importlib.machinery
import importlib.util
import json
import os
import unittest

CRT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_PATH = os.path.join(CRT_DIR, "tools", "crtctl")
PRESETS_DIR = os.path.join(CRT_DIR, "presets")


def _load_module():
    loader = importlib.machinery.SourceFileLoader("crtctl_picker", TOOLS_PATH)
    spec = importlib.util.spec_from_loader("crtctl_picker", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


crtctl = _load_module()


# The name of the meta-less preset the no-meta tests drive. It is whichever
# personal preset this tree happens to carry, or the synthetic stand-in
# load_presets() injects when it carries none.
PERSONAL = "personal-bench"


def load_presets():
    """{filename-stem: doc} for every real preset in the repo.

    A personal preset (one a user saved for themselves) is the bank's only
    meta-less kind of document, and several tests use it as the no-meta
    case — but personal presets are deliberately excluded from vendored and
    product copies of this tree, so there may be none present. Inject a
    synthetic one when that is so, and the no-meta code paths stay tested
    everywhere regardless of whose bench this is."""
    out = {}
    for fn in sorted(os.listdir(PRESETS_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(PRESETS_DIR, fn), encoding="utf-8") as f:
                out[fn[:-5]] = json.load(f)
    if not any(not isinstance(d.get("meta"), dict) for d in out.values()):
        out["personal-bench"] = {
            "name": "personal-bench",
            "description": "synthetic stand-in for the personal preset: "
                           "perfect for exercising meta-less handling",
            "params": {},
        }
    return out


def entries_from(presets):
    """Picker-shaped entries from raw preset docs."""
    return [{"name": name,
             "description": doc.get("description") or "",
             "meta": doc.get("meta"),
             "params": doc.get("params") or {},
             "terminal": doc.get("terminal") or {}}
            for name, doc in presets.items()]


# ----------------------------------------------------------------------------
# meta derivation goldens (against the real preset files, so these also
# prove the migration wrote exactly what derive_preset_meta produces)
# ----------------------------------------------------------------------------

class TestMetaDerivation(unittest.TestCase):
    GOLDEN = {
        "commodore-1702-1983": {
            "year": 1983, "type": "PC monitors", "manufacturer": "Commodore",
            "price_usd": 249, "resolution": 240},
        "mil-ppi-radar-p7": {
            "year": 1950, "type": "Instruments",
            "manufacturer": "military surplus",
            "price_usd": 25, "resolution": 300},
        "smartdark-creme": {
            "year": None, "type": "Daily drivers",
            "manufacturer": "ghostcrtty",
            "price_usd": None, "resolution": 960},
        "rca-ct100-1954": {
            "year": 1954, "type": "Consumer TV", "manufacturer": "RCA",
            "price_usd": 1000, "resolution": 480},
        "tek4010-storage": {
            "year": 1972, "type": "Storage tubes",
            "manufacturer": "Tektronix",
            "price_usd": 3950, "resolution": 480},
    }

    @classmethod
    def setUpClass(cls):
        cls.presets = load_presets()

    def test_goldens_derive_and_match_files(self):
        for name, expected in self.GOLDEN.items():
            doc = self.presets[name]
            derived = crtctl.derive_preset_meta(
                doc["name"], doc["description"], doc["params"])
            self.assertEqual(derived, expected, name)
            self.assertEqual(doc.get("meta"), expected,
                             "%s: file meta out of sync with derivation "
                             "(rerun the meta migration)" % name)

    def test_every_curated_meta_matches_derivation(self):
        """The whole bank round-trips: file meta == fresh derivation."""
        for name, doc in self.presets.items():
            if "meta" not in doc:
                continue
            self.assertEqual(
                doc["meta"],
                crtctl.derive_preset_meta(doc["name"], doc["description"],
                                          doc["params"]),
                name)

    def test_year_parsing_rules(self):
        self.assertEqual(crtctl._meta_year("foo-1983", ""), 1983)
        self.assertEqual(crtctl._meta_year("foo-2026", ""), 2026)
        # name digits that are not a year suffix do not count
        self.assertEqual(crtctl._meta_year("pvm1954q", "made in 1990"), 1990)
        self.assertEqual(crtctl._meta_year("x", "a 1960s TV"), 1960)
        # $ figures never read as years
        self.assertIsNone(crtctl._meta_year("x", "costs $1,999 new"))
        self.assertIsNone(crtctl._meta_year("x", "no year at all"))

    def test_price_parsing_rules(self):
        self.assertEqual(crtctl._meta_price("(1983, $249): nice"), 249)
        self.assertEqual(crtctl._meta_price("$1,000 - a fortune"), 1000)
        self.assertEqual(crtctl._meta_price("$3,000-5,000 range"), 3000)
        self.assertEqual(crtctl._meta_price("only $319.95 down"), 319.95)
        self.assertEqual(crtctl._meta_price("surplus $25-75"), 25)
        self.assertIsNone(crtctl._meta_price("priceless"))

    def test_manufacturer_mapping(self):
        m = crtctl._meta_manufacturer
        self.assertEqual(m("sony-bvm-d24-2000"), "Sony")
        self.assertEqual(m("ibm5151-green"), "IBM")          # bare prefix
        self.assertEqual(m("applecolor-rgb-1987"), "Apple")  # bare prefix
        self.assertEqual(m("wells-gardner-k4600-1979"), "Wells-Gardner")
        self.assertEqual(m("tek4010-storage"), "Tektronix")
        self.assertEqual(m("mil-ppi-radar-p7"), "military surplus")
        self.assertEqual(m("smartdark-creme"), "ghostcrtty")
        self.assertIsNone(m("totally-custom-preset"))

    def test_families_cover_exactly_the_curated_bank(self):
        curated = {n for n, d in self.presets.items()
                   if isinstance(d.get("meta"), dict)}
        self.assertEqual(set(crtctl.PRESET_FAMILIES), curated)


# ----------------------------------------------------------------------------
# sort modes over the real preset dir
# ----------------------------------------------------------------------------

class TestSortModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = entries_from(load_presets())

    def _sorted(self, mode):
        return crtctl.sort_preset_entries(self.entries, mode)

    @staticmethod
    def _meta_vals(order, field):
        return [(e.get("meta") or {}).get(field) for e in order]

    def _assert_nulls_last(self, vals, mode):
        seen_null = False
        for v in vals:
            if v is None:
                seen_null = True
            else:
                self.assertFalse(seen_null,
                                 "%s: non-null after null: %r" % (mode, vals))

    def test_modes_are_the_documented_six(self):
        self.assertEqual(crtctl.SORT_MODES,
                         ("name", "year", "type", "manufacturer",
                          "price", "resolution"))

    def test_sort_by_name(self):
        order = [e["name"] for e in self._sorted("name")]
        self.assertEqual(order, sorted(order, key=str.lower))
        self.assertEqual(len(order), len(self.entries))

    def test_sort_by_year(self):
        vals = self._meta_vals(self._sorted("year"), "year")
        nonnull = [v for v in vals if v is not None]
        self.assertEqual(nonnull, sorted(nonnull))
        self._assert_nulls_last(vals, "year")
        self.assertEqual(nonnull[0], 1949)   # zenith-porthole-1949
        self.assertEqual(nonnull[-1], 2026)  # what-if-crts-won-2026
        self.assertIn(None, vals)            # personal + undated archetypes

    def test_sort_by_type_groups_families_then_name(self):
        order = self._sorted("type")
        fams = self._meta_vals(order, "type")
        self._assert_nulls_last(fams, "type")
        # each family is one contiguous block
        seen = []
        for f in fams:
            if f is not None and (not seen or seen[-1] != f):
                self.assertNotIn(f, seen, "family %r split apart" % f)
                seen.append(f)
        # within a family, names ascend
        for fam in set(f for f in fams if f):
            names = [e["name"] for e in order
                     if (e.get("meta") or {}).get("type") == fam]
            self.assertEqual(names, sorted(names, key=str.lower), fam)
        # personal presets have no meta and land at the very end
        self.assertFalse(order[-1].get("meta"), order[-1]["name"])

    def test_sort_by_manufacturer(self):
        vals = self._meta_vals(self._sorted("manufacturer"), "manufacturer")
        nonnull = [v.lower() for v in vals if v is not None]
        self.assertEqual(nonnull, sorted(nonnull))
        self._assert_nulls_last(vals, "manufacturer")

    def test_sort_by_price(self):
        vals = self._meta_vals(self._sorted("price"), "price_usd")
        nonnull = [v for v in vals if v is not None]
        self.assertEqual(nonnull, sorted(nonnull))
        self._assert_nulls_last(vals, "price")
        self.assertEqual(nonnull[0], 25)      # mil-ppi surplus
        self.assertEqual(nonnull[-1], 12000)  # ikegami

    def test_sort_by_resolution(self):
        vals = self._meta_vals(self._sorted("resolution"), "resolution")
        nonnull = [v for v in vals if v is not None]
        self.assertEqual(nonnull, sorted(nonnull))
        self._assert_nulls_last(vals, "resolution")
        self.assertEqual(nonnull[0], 200)
        self.assertEqual(nonnull[-1], 1200)

    def test_sort_is_stable_and_total(self):
        for mode in crtctl.SORT_MODES:
            order = self._sorted(mode)
            self.assertEqual(len(order), len(self.entries), mode)
            self.assertEqual(sorted(e["name"] for e in order),
                             sorted(e["name"] for e in self.entries), mode)

    def test_unknown_mode_raises(self):
        with self.assertRaises(crtctl.CrtError):
            crtctl.sort_preset_entries(self.entries, "bogus")


# ----------------------------------------------------------------------------
# centered-cursor windowing math
# ----------------------------------------------------------------------------

class TestCenterScroll(unittest.TestCase):
    def test_center_behavior(self):
        # 50 rows in an 11-row viewport: cursor pinned to the middle row
        # except near the ends of the list
        for sel, top in ((0, 0), (3, 0), (5, 0), (6, 1), (25, 20),
                         (43, 38), (44, 39), (49, 39)):
            self.assertEqual(crtctl.center_scroll(50, sel, 11), top, sel)

    def test_cursor_always_visible_and_centered_mid_list(self):
        total, vis = 200, 13
        mid = (vis - 1) // 2
        for sel in range(total):
            top = crtctl.center_scroll(total, sel, vis)
            self.assertTrue(0 <= top <= total - vis, sel)
            self.assertTrue(top <= sel < top + vis, sel)
            if mid <= sel <= total - 1 - (vis - 1 - mid):
                self.assertEqual(sel - top, mid, sel)  # dead center

    def test_top_is_monotonic_in_sel(self):
        tops = [crtctl.center_scroll(60, s, 9) for s in range(60)]
        self.assertEqual(tops, sorted(tops))

    def test_short_lists_never_scroll(self):
        for total in (0, 1, 5, 11):
            for sel in range(max(1, total)):
                self.assertEqual(crtctl.center_scroll(total, sel, 11), 0)
        self.assertEqual(crtctl.center_scroll(50, 25, 0), 0)  # degenerate


# ----------------------------------------------------------------------------
# details pane + characterful overrides
# ----------------------------------------------------------------------------

class TestDetailLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(CRT_DIR, "params.json"), encoding="utf-8") as f:
            cls.spec = json.load(f)["params"]
        cls.defaults = {k: crtctl.normalize_value(k, s, s.get("default"))
                        for k, s in cls.spec.items()}
        cls.presets = load_presets()

    def _entry(self, name):
        doc = self.presets[name]
        return {"name": name, "description": doc.get("description") or "",
                "meta": doc.get("meta"), "params": doc.get("params") or {},
                "terminal": doc.get("terminal") or {}}

    def test_commodore_details(self):
        lines = crtctl.preset_detail_lines(self._entry("commodore-1702-1983"),
                                           self.spec, self.defaults, 48)
        text = "\n".join(lines)
        self.assertEqual(lines[0], "commodore-1702-1983")
        self.assertIn("Commodore · 1983 · PC monitors · $249", text)
        self.assertIn("hearth", text)               # wrapped description
        self.assertIn("PHOSPHOR", text)
        self.assertIn("slot", text)                 # mask value
        self.assertIn("RASTER LINES", text)
        self.assertIn("240", text)
        self.assertIn("TUBE GEOMETRY", text)
        self.assertIn("ERA", text)
        self.assertIn("FONT SIZE", text)            # terminal override
        self.assertIn("26 (terminal)", text)
        self.assertIn("character", text)            # characterful section
        self.assertTrue(all(len(l) <= 48 for l in lines))

    def test_tolerates_missing_meta(self):
        lines = crtctl.preset_detail_lines(self._entry(PERSONAL),
                                           self.spec, self.defaults, 40)
        self.assertEqual(lines[0], PERSONAL)
        self.assertIn("perfect", "\n".join(lines))
        self.assertTrue(all(len(l) <= 40 for l in lines))

    def test_zero_width_is_empty(self):
        self.assertEqual(
            crtctl.preset_detail_lines(self._entry(PERSONAL),
                                       self.spec, self.defaults, 0), [])

    def test_characterful_ranked_and_limited(self):
        spec = {
            "gain": {"define": "G", "type": "float", "default": 1.0,
                     "min": 0.0, "max": 2.0, "group": "video"},
            "lines": {"define": "L", "type": "int", "default": 480,
                      "min": 200, "max": 1200, "group": "scan"},
            "mode": {"define": "M", "type": "enum", "default": "b",
                     "values": {"a": 0, "b": 1, "c": 2}, "group": "video"},
            "nonce": {"define": "N", "type": "int", "default": 0,
                      "min": 0, "max": 10, "group": "system"},
            "phosphor": {"define": "P", "type": "enum", "default": "a",
                         "values": {"a": 0, "b": 1}, "group": "phosphor"},
        }
        defaults = {"gain": 1.0, "lines": 480, "mode": "b", "nonce": 0,
                    "phosphor": "a"}
        params = {"gain": 2.0,        # deviation 0.5
                  "lines": 1200,      # deviation 0.72
                  "mode": "c",        # enum flip: 0.5, after gain by name
                  "nonce": 9,         # system group: excluded
                  "phosphor": "b"}    # in exclude list
        got = crtctl.characterful_overrides(params, spec, defaults,
                                            exclude=("phosphor",))
        self.assertEqual(got, [("lines", 1200), ("gain", 2.0), ("mode", "c")])
        got = crtctl.characterful_overrides(params, spec, defaults,
                                            exclude=("phosphor",), limit=2)
        self.assertEqual(got, [("lines", 1200), ("gain", 2.0)])
        # values equal to the default never show up
        got = crtctl.characterful_overrides({"gain": 1.0}, spec, defaults)
        self.assertEqual(got, [])

    def test_real_preset_shows_at_most_six_extras(self):
        for name in ("smartdark-creme", "wornout-office",
                     "sony-gdm-fw900-2000"):
            doc = self.presets[name]
            extras = crtctl.characterful_overrides(
                doc["params"], self.spec, self.defaults,
                exclude=crtctl.DETAIL_KEYS)
            self.assertLessEqual(len(extras), 6, name)
            self.assertGreaterEqual(len(extras), 4, name)


# ----------------------------------------------------------------------------
# list_preset_docs (model layer feeding the picker)
# ----------------------------------------------------------------------------

class TestListPresetDocs(unittest.TestCase):
    def test_real_bank_docs(self):
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory(prefix="crtctl-docs-") as base:
            crt = os.path.join(base, "crt")
            os.makedirs(crt)
            shutil.copy(os.path.join(CRT_DIR, "params.json"),
                        os.path.join(crt, "params.json"))
            shutil.copytree(PRESETS_DIR, os.path.join(crt, "presets"))
            ctl = crtctl.CrtCtl(base=base, runner=lambda argv, timeout=5.0:
                                (0, "()\n", ""), on_warn=lambda m: None)
            docs = ctl.list_preset_docs()
            by_name = {d["name"]: d for d in docs}
            if os.path.exists(os.path.join(PRESETS_DIR, PERSONAL + ".json")):
                # personal preset present (source-of-truth checkout only)
                self.assertIn(PERSONAL, by_name)
                self.assertIsNone(by_name[PERSONAL]["meta"])   # tolerated
            self.assertEqual(by_name["commodore-1702-1983"]["meta"]["year"],
                             1983)
            self.assertEqual(by_name["commodore-1702-1983"]["terminal"],
                             {"font-size": 26})
            # list_presets still returns the historical 3-tuples
            triples = ctl.list_presets()
            self.assertEqual([(d["name"], d["description"], d["path"])
                              for d in docs], triples)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Validate every preset in crt/presets/ against crt/params.json:
every key must exist, values must be in range / valid enum members / of
the right type. Run: python3 tests/test_presets.py  (from the crt dir)
or via unittest discovery."""
import json
import os
import unittest

CRT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The preset families from the README preset-bank table, as encoded in
# meta.type (crtctl PRESET_FAMILIES uses exactly these strings).
FAMILIES = {
    "Daily drivers", "Broadcast/pro", "Consumer TV", "PC monitors",
    "Terminals (mono)", "Storage tubes", "Arcade", "Instruments",
    "Plasma panels", "Fiction", "Character",
}

# A *personal* preset is one a user saved for themselves rather than one of
# the researched tubes in the curated bank. The distinguishing property is
# structural, not a filename: curated presets carry a `meta` object (era,
# manufacturer, type, ...) and personal ones do not. Keying on that rather
# than on a name prefix means the rule needs no knowledge of whose bench it
# is, and personal presets are free-form and excluded from vendored copies.
def _is_personal(doc):
    return not isinstance(doc.get("meta"), dict)


class TestPresets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(CRT_DIR, "params.json")) as f:
            cls.spec = json.load(f)["params"]
        cls.presets = {}
        pdir = os.path.join(CRT_DIR, "presets")
        for fn in sorted(os.listdir(pdir)):
            if fn.endswith(".json"):
                with open(os.path.join(pdir, fn)) as f:
                    cls.presets[fn] = json.load(f)

    def test_presets_exist(self):
        self.assertGreater(len(self.presets), 0)

    def test_schema(self):
        for fn, p in self.presets.items():
            self.assertIn("name", p, fn)
            self.assertIn("description", p, fn)
            self.assertIn("params", p, fn)
            self.assertEqual(p["name"], fn[:-5], fn)

    def test_param_keys_and_values(self):
        for fn, p in self.presets.items():
            for key, val in p["params"].items():
                self.assertIn(key, self.spec, f"{fn}: unknown param {key}")
                s = self.spec[key]
                t = s["type"]
                if t == "float":
                    self.assertIsInstance(val, (int, float), f"{fn}:{key}")
                    self.assertGreaterEqual(val, s["min"], f"{fn}:{key}")
                    self.assertLessEqual(val, s["max"], f"{fn}:{key}")
                elif t == "int":
                    self.assertIsInstance(val, int, f"{fn}:{key}")
                    self.assertGreaterEqual(val, s["min"], f"{fn}:{key}")
                    self.assertLessEqual(val, s["max"], f"{fn}:{key}")
                elif t == "bool":
                    self.assertIsInstance(val, bool, f"{fn}:{key}")
                elif t == "enum":
                    self.assertIn(val, s["values"], f"{fn}:{key}={val}")

    def test_curated_presets_carry_meta(self):
        """Every curated preset ships a meta object; only personal
        presets may omit it (the picker tolerates both)."""
        for fn, p in self.presets.items():
            if _is_personal(p):
                continue
            self.assertIn("meta", p, fn)

    def test_meta_schema(self):
        """Where a meta object is present it must be exactly
        {year, type, manufacturer, price_usd, resolution} with sane types:
        year int-or-null, type a README family, manufacturer a non-empty
        string, price_usd positive-number-or-null, resolution an int equal
        to the preset's scan_lines (default 480)."""
        for fn, p in self.presets.items():
            meta = p.get("meta")
            if meta is None:
                continue
            self.assertIsInstance(meta, dict, fn)
            self.assertEqual(
                set(meta),
                {"year", "type", "manufacturer", "price_usd", "resolution"},
                fn)
            year = meta["year"]
            if year is not None:
                self.assertIsInstance(year, int, fn)
                self.assertTrue(1900 <= year <= 2100, f"{fn}: year {year}")
            self.assertIn(meta["type"], FAMILIES, fn)
            self.assertIsInstance(meta["manufacturer"], str, fn)
            self.assertTrue(meta["manufacturer"].strip(), fn)
            price = meta["price_usd"]
            if price is not None:
                self.assertIsInstance(price, (int, float), fn)
                self.assertNotIsInstance(price, bool, fn)
                self.assertGreater(price, 0, fn)
            res = meta["resolution"]
            self.assertIsInstance(res, int, fn)
            self.assertEqual(res, p["params"].get("scan_lines", 480),
                             f"{fn}: meta.resolution must mirror scan_lines")
            spec = self.spec["scan_lines"]
            self.assertGreaterEqual(res, spec["min"], fn)
            self.assertLessEqual(res, spec["max"], fn)

    def test_mono_phosphors_have_no_mask(self):
        """Physics: monochrome tubes have a continuous phosphor coating.
        A preset that selects a mono phosphor must not enable a mask."""
        mono = {"p1", "p31", "p39", "p3", "p134", "p4", "paperwhite",
                "p7", "p11", "dvst"}
        for fn, p in self.presets.items():
            ph = p["params"].get("phosphor", "p22")
            if ph in mono:
                self.assertEqual(
                    p["params"].get("mask_type", "grille"), "none",
                    f"{fn}: mono phosphor {ph} must use mask_type none")


if __name__ == "__main__":
    unittest.main()

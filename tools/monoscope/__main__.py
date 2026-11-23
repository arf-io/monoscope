"""python3 -m monoscope [--dest NAME] [--motion full|reduced|off] [--flat-field] [--no-mouse] [--fps N]

Standalone launcher: loads the crtctl core (tools/crtctl, same directory as
this package's parent) and runs the panel. `crtctl panel` does the same.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
import sys


def load_crtctl(path=None):
    if path is None:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(here, "crtctl")
    loader = importlib.machinery.SourceFileLoader("crtctl", path)
    spec = importlib.util.spec_from_loader("crtctl", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main(argv=None):
    ap = argparse.ArgumentParser(prog="monoscope", description="MONOSCOPE — the crtctl control surface")
    ap.add_argument("--dest", default=None)
    ap.add_argument("--motion", default=None, choices=["full", "reduced", "off"])
    ap.add_argument("--flat-field", action="store_true")
    ap.add_argument("--no-mouse", action="store_true")
    ap.add_argument("--no-splash", action="store_true")
    ap.add_argument("--fps", type=float, default=None, help="ambient frame rate (default 12)")
    ap.add_argument("--crtctl", default=None, help="path to the crtctl module (default: sibling)")
    a = ap.parse_args(argv)
    cm = load_crtctl(a.crtctl)
    dest = a.dest or cm.DEFAULT_DEST
    try:
        ctl = cm.CrtCtl()
    except cm.CrtError as e:
        print("monoscope: error: %s" % e, file=sys.stderr)
        return 1
    from .app import run_panel
    return run_panel(ctl, dest, cm, motion=a.motion, flat_field=a.flat_field, mouse=not a.no_mouse, ambient_fps=a.fps, splash=not a.no_splash)


if __name__ == "__main__":
    sys.exit(main())

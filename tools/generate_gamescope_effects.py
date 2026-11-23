#!/usr/bin/env python3
"""Bake ReShade presets into gamescope-ready effect files.

gamescope can run a ReShade FX file directly. Its current documented path for
changing options is the gamescope-reshade Wayland protocol; without that,
uniforms use the initializer values inside the .fx file. This utility turns the
generated ReShade preset INI files into separate .fx files with those
initializers already set.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


UNIFORM_RE = re.compile(
    r"(uniform\s+(?:float|int)\s+(Ghost_[A-Za-z0-9_]+)\s*<.*?>\s*=\s*)"
    r"([^;]+)"
    r"(;)",
    re.DOTALL,
)


def read_preset(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    in_effect = False
    saw_effect = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_effect = line == "[ghostcrtty.fx]"
            saw_effect = saw_effect or in_effect
            continue
        if not in_effect or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("Ghost_"):
            values[key] = value.strip()
    if not saw_effect:
        raise ValueError(f"{path}: missing [ghostcrtty.fx] section")
    return values


def bake_effect(base_fx: str, values: dict[str, str]) -> str:
    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        prefix, uniform, current, suffix = match.groups()
        if uniform not in values:
            return match.group(0)
        seen.add(uniform)
        return f"{prefix}{values[uniform]}{suffix}"

    baked = UNIFORM_RE.sub(replace, base_fx)
    missing = sorted(set(values) - seen)
    if missing:
        raise ValueError("preset references uniforms missing from effect: " + ", ".join(missing))
    return baked


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base",
        type=pathlib.Path,
        default=pathlib.Path("crt-sim/reshade/Shaders/ghostcrtty.fx"),
        help="base generated ReShade effect",
    )
    ap.add_argument(
        "--presets",
        type=pathlib.Path,
        default=pathlib.Path("crt-sim/reshade/Presets"),
        help="directory containing generated ReShade preset INI files",
    )
    ap.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("crt-sim/wayland/generated"),
        help="output directory for baked gamescope effect files",
    )
    args = ap.parse_args(argv)

    base_fx = args.base.read_text(encoding="utf-8")
    args.out.mkdir(parents=True, exist_ok=True)

    count = 0
    for preset in sorted(args.presets.glob("*.ini")):
        values = read_preset(preset)
        baked = bake_effect(base_fx, values)
        out = args.out / f"{preset.stem}.fx"
        out.write_text(baked, encoding="utf-8")
        count += 1

    print(f"generated {count} gamescope effects in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

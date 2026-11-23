#!/usr/bin/env bash
# Metal transpile-matrix test: generate every preset through the real
# GLSL -> SPIR-V -> MSL pipeline, then generate the all-numeric runtime
# variant. Fails on any glslangValidator or spirv-cross error.
#
# Usage: test_metal_transpile.sh
# Requires: glslangValidator, spirv-cross, python3.
set -u
set -o pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CRT="$(dirname "$HERE")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

command -v glslangValidator >/dev/null || {
    echo "SKIP: glslangValidator missing"
    exit 77
}
command -v spirv-cross >/dev/null || {
    echo "SKIP: spirv-cross missing"
    exit 77
}
command -v python3 >/dev/null || {
    echo "SKIP: python3 missing"
    exit 77
}

python3 "$CRT/tools/transpile_metal.py" \
    --out "$WORK/metal" \
    --runtime \
    --validate
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FAIL: Metal transpile matrix failed"
    exit "$rc"
fi

preset_count="$(find "$CRT/presets" -maxdepth 1 -name '*.json' | wc -l)"
metal_count="$(find "$WORK/metal" -mindepth 2 -maxdepth 2 -name '*.metal' | wc -l)"
expected=$((preset_count * 2 + 2))

if [ "$metal_count" -ne "$expected" ]; then
    echo "FAIL: expected $expected Metal files, got $metal_count"
    exit 1
fi

echo "MATRIX: $((preset_count * 2))/$((preset_count * 2)) preset passes compiled clean (glslang + spirv-cross)"
echo "RUNTIME: 2/2 runtime passes compiled clean (glslang + spirv-cross)"

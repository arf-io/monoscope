#!/usr/bin/env bash
# Compile-matrix test: assemble both shader templates with every phosphor,
# mask, geometry, and era variant (plus toggle cases) and push each through
# the exact pipeline Ghostty uses at load time: glslang (Vulkan 1.2
# semantics) -> SPIR-V -> spirv-cross back to GLSL 430.
#
# Usage: test_shader_compile.sh [path-to-shadertoy_prefix.glsl]
#   Default prefix: the phosphor-feedback fork checkout.
# Requires: glslangValidator, spirv-cross, python3.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
CRT="$(dirname "$HERE")"
PREFIX="${1:-}"
if [ -z "$PREFIX" ]; then
    for cand in "$HOME/Augments/ghostcrtty" "$HOME/Augments/ghostty-phosphor"; do
        if [ -f "$cand/src/renderer/shaders/shadertoy_prefix.glsl" ]; then
            PREFIX="$cand/src/renderer/shaders/shadertoy_prefix.glsl"
            break
        fi
    done
    PREFIX="${PREFIX:-$HOME/Augments/ghostcrtty/src/renderer/shaders/shadertoy_prefix.glsl}"
fi
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

command -v glslangValidator >/dev/null || { echo "SKIP: glslangValidator missing"; exit 77; }
command -v spirv-cross >/dev/null || { echo "SKIP: spirv-cross missing"; exit 77; }
[ -f "$PREFIX" ] || { echo "SKIP: prefix not found at $PREFIX"; exit 77; }

gen() { # gen key=value... -> writes $WORK/defs.glsl
    python3 - "$CRT/params.json" "$WORK/defs.glsl" "$@" << 'PYEOF'
import json, sys
spec = json.load(open(sys.argv[1]))["params"]
out_path = sys.argv[2]
ov = dict(a.split("=", 1) for a in sys.argv[3:])
def fmt(key, val):
    s = spec[key]; t = s["type"]
    if t == "float":
        o = "%.6g" % float(val)
        return o if ("." in o or "e" in o) else o + ".0"
    if t == "int": return str(int(val))
    if t == "bool": return "1" if str(val).lower() in ("1", "true") else "0"
    if t == "enum": return str(s["values"][val] if val in s["values"] else int(val))
lines = ["#define CRT_PARAMS_INJECTED 1"]
for key, s in spec.items():
    lines.append(f"#define {s['define']} {fmt(key, ov.get(key, s['default']))}")
open(out_path, "w").write("\n".join(lines))
PYEOF
}

fails=0; total=0
run_case() {
    local label="$1"; shift
    gen "$@"
    for tmpl in phosphor-state crt-display; do
        total=$((total + 1))
        python3 - "$CRT/templates/$tmpl.glsl.tmpl" "$WORK/defs.glsl" \
                 "$PREFIX" "$WORK/m.frag" << 'PYEOF'
import sys
body = open(sys.argv[1]).read()
defs = open(sys.argv[2]).read()
prefix = open(sys.argv[3]).read()
out = [prefix, ""]
for line in body.split("\n"):
    out.append(defs if line.strip() == "//@CRT_PARAMS@" else line)
open(sys.argv[4], "w").write("\n".join(out))
PYEOF
        if ! glslangValidator -V --target-env vulkan1.2 -S frag \
                "$WORK/m.frag" -o "$WORK/m.spv" > "$WORK/err.txt" 2>&1; then
            echo "FAIL(glslang) $tmpl [$label]"; head -4 "$WORK/err.txt"
            fails=$((fails + 1)); continue
        fi
        if ! spirv-cross --version 430 --no-es "$WORK/m.spv" \
                > /dev/null 2> "$WORK/err.txt"; then
            echo "FAIL(spirv-cross) $tmpl [$label]"; head -4 "$WORK/err.txt"
            fails=$((fails + 1))
        fi
    done
}

for ph in p22 p22_d93 p1 p31 p39 p3 p134 p4 paperwhite p7 p11 dvst; do
    run_case "phosphor=$ph" phosphor=$ph
done
for mk in none grille slot delta; do run_case "mask=$mk" mask_type=$mk; done
for gm in flat cylindrical spherical; do run_case "geom=$gm" geom_mode=$gm; done
for era in tube60s ss80s modern90s; do run_case "era=$era" era=$era; done
run_case "interlace" interlace=true
run_case "debug" debug_state=true
run_case "power-off" power_on=false
run_case "persistence-0" persistence=0
run_case "post-quick" post_test=quick era=ss80s
run_case "post-full" post_test=full era=tube60s
run_case "smooth-scroll" smooth_scroll=true
run_case "smooth-mono" smooth_scroll=true phosphor=p31 mask_type=none
run_case "dvst-orange" phosphor=dvst mask_type=none dvst_orange_refresh=true
run_case "dvst-post-smooth" phosphor=dvst mask_type=none post_test=full smooth_scroll=true
run_case "dvst-autoerase-off" phosphor=dvst mask_type=none dvst_auto_erase=false
run_case "dvst-progressive-write" phosphor=dvst mask_type=none dvst_write_rate=0.25
run_case "dvst-write-fast" phosphor=dvst mask_type=none dvst_write_rate=8.0 \
    dvst_orange_refresh=true
run_case "rolling-auto" rolling_scan=auto
run_case "rolling-force-mono" rolling_scan=force phosphor=p31 mask_type=none
run_case "rolling-smooth" rolling_scan=auto smooth_scroll=true
run_case "interlace-temporal" interlace=true scan_lines=480
run_case "interlace-rolling" interlace=true rolling_scan=auto scan_rate=50
run_case "pdp" phosphor=pdp mask_type=grille
run_case "pdp-kuro" phosphor=pdp mask_type=grille persistence=0.6 pdp_contour=0.25
run_case "fiction-rolling" rolling_scan=auto scan_lines=1200 mask_triads=1800
run_case "vector-trace" vector_trace=1 phosphor=p31 mask_type=none
run_case "vector-outline-mono" vector_mode=outline phosphor=p4 mask_type=none \
    era=tube60s vector_flicker=0.2 vector_dot_gain=2.0
run_case "vector-stroke-mono" vector_mode=stroke phosphor=p31 mask_type=none \
    vector_grain=0.1
run_case "vector-outline-color" vector_mode=outline phosphor=p22 mask_type=delta \
    misconvergence=1.5 hv_breathing=0.6 vector_beam_halo=6.5
run_case "vector-stroke-color" vector_mode=stroke phosphor=p22 mask_type=delta
run_case "vector-outline-spherical-burnin" vector_mode=outline phosphor=p4 \
    mask_type=none geom_mode=spherical pincushion=0.05 burnin_rate=1 \
    burnin_vintage=0.5 power_on=false
run_case "radar-ppi" phosphor=p7 mask_type=none radar_overlay=0.8 \
    radar_sweep=1 radar_sweep_rate=24
run_case "kitchen-sink" phosphor=p39 era=tube60s geom_mode=spherical \
    mask_type=none interlace=true burnin_rate=1 burnin_vintage=0.5 \
    v_hold=1.5 h_hold=120

echo "MATRIX: $((total - fails))/$total compiled clean (glslang + spirv-cross)"
[ "$fails" -eq 0 ]

#!/usr/bin/env bash
# Full-stack runtime test: the real two-pass CRT simulation (phosphor-state
# + crt-display) running in the phosphor-feedback Ghostty fork, headless.
#
# Uses the bw-tv-p4 preset (era=tube60s, warmup_time_scale=0.2) because its
# power-on choreography is time-observable: heater dead ~1.6s, undeflected
# dot, bright horizontal line ~2.1-2.8s, raster unfold, then full picture.
# Screenshots at staged times assert the sequence actually happens:
#   t=1.0s  -> essentially black (heater warming)
#   t=2.4s  -> a bright horizontal LINE: one row band far brighter than
#              the frame average (vertical deflection not yet awake)
#   t=12s   -> full raster: brighter overall than t=1, no single-line
#              domination, text contrast present
# Also asserts both shaders loaded and no shader compile errors logged.
#
# Usage: test_stack_runtime.sh [ghostty-binary]
# Requires: Xvfb, ImageMagick, dbus-run-session, python3.
set -u

BIN="${1:-ghostty-phosphor}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CRT="$(dirname "$HERE")"
WORK="$(mktemp -d)"
DPY=":96"
trap 'kill $XVFB_PID $APP_PID 2>/dev/null; rm -rf "$WORK"' EXIT

command -v "$BIN" >/dev/null || { echo "SKIP: $BIN not found"; exit 77; }
command -v Xvfb >/dev/null || { echo "SKIP: Xvfb not found"; exit 77; }

# --- generate shaders from templates: defaults + bw-tv-p4 preset ---
python3 - "$CRT" "$WORK" << 'PYEOF'
import json, sys
crt, work = sys.argv[1], sys.argv[2]
spec = json.load(open(f"{crt}/params.json"))["params"]
preset = json.load(open(f"{crt}/presets/bw-tv-p4.json"))["params"]

def fmt(key, val):
    s = spec[key]
    t = s["type"]
    if t == "float":
        out = "%.6g" % float(val)
        return out if ("." in out or "e" in out) else out + ".0"
    if t == "int": return str(int(val))
    if t == "bool": return "1" if val in (True, "true", 1) else "0"
    if t == "enum": return str(s["values"][val] if isinstance(val, str) else int(val))

defs = ["#define CRT_PARAMS_INJECTED 1"]
for key, s in spec.items():
    defs.append(f"#define {s['define']} {fmt(key, preset.get(key, s['default']))}")
block = "\n".join(defs)

for name in ("phosphor-state", "crt-display"):
    body = open(f"{crt}/templates/{name}.glsl.tmpl").read()
    out = []
    for line in body.split("\n"):
        out.append(block if line.strip() == "//@CRT_PARAMS@" else line)
    open(f"{work}/{name}.glsl", "w").write("\n".join(out))
print("shaders generated")
PYEOF

Xvfb "$DPY" -screen 0 1024x768x24 >/dev/null 2>&1 &
XVFB_PID=$!
sleep 1

DISPLAY="$DPY" GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 \
dbus-run-session -- "$BIN" \
    --config-default-files=false \
    --class=io.arf.crt.stacktest \
    --custom-shader="$WORK/phosphor-state.glsl" \
    --custom-shader="$WORK/crt-display.glsl" \
    --custom-shader-animation=always \
    --window-decoration=none \
    --confirm-close-surface=false \
    --font-size=18 \
    -e sh -c "yes 'HELLO PHOSPHOR ##### HELLO PHOSPHOR' | head -30; sleep 60" \
    >"$WORK/ghostty.log" 2>&1 &
APP_PID=$!

snap() { DISPLAY="$DPY" import -window root "$WORK/$1.png" 2>/dev/null; }
sleep 1.0; snap t1
# Burst-sample through the dot/line/unfold window (the line phase is only
# ~0.7s wide and GTK startup time shifts it): any frame showing a dominant
# bright row proves the vertical-deflection-asleep phase happened.
best_ratio=0
for i in $(seq 1 14); do
    sleep 0.45
    snap "burst$i"
    read bm brm <<< "$(magick "$WORK/burst$i.png" -colorspace Gray \
        -format "%[fx:mean*255] " info: ; \
        magick "$WORK/burst$i.png" -colorspace Gray -resize 1x768\! \
        -format "%[fx:maxima*255]" info:)"
    ratio=$(python3 -c "print(float('$brm')/max(float('$bm'),0.5))")
    best_ratio=$(python3 -c "print(max(float('$best_ratio'), float('$ratio')))")
done
sleep 5; snap t3        # ~13s: full raster, warmed up

stats() { magick "$WORK/$1.png" -colorspace Gray -format "%[fx:mean*255] %[fx:maxima*255]" info:; }
read m1 x1 <<< "$(stats t1)"
read m3 x3 <<< "$(stats t3)"
rowmax3=$(magick "$WORK/t3.png" -colorspace Gray -resize 1x768\! -format "%[fx:maxima*255]" info:)

echo "t1 mean=$m1 | burst best row/mean ratio=$best_ratio | t3 mean=$m3 rowmax=$rowmax3"

loads=$(grep -c 'loaded custom shader' "$WORK/ghostty.log")
errs=$(grep -icE 'shader.*(error|fail)|error.*shader' "$WORK/ghostty.log" || true)

python3 - "$m1" "$best_ratio" "$m3" "$rowmax3" "$loads" "$errs" << 'PYEOF'
import sys
m1, ratio, m3, rm3, loads, errs = [float(x) for x in sys.argv[1:7]]
checks = {
    "heater phase dark (t1 mean < 8)": m1 < 8,
    "line phase seen in burst (some frame had row > 4x mean)": ratio > 4,
    "full raster brighter than heater phase": m3 > m1 + 3,
    "full raster: no single-line domination (rowmax < 4x mean)": rm3 < 4 * max(m3, 0.5),
    "both shaders loaded": loads >= 2,
    "no shader errors in log": errs == 0,
}
ok = True
for name, passed in checks.items():
    print(("PASS " if passed else "FAIL ") + name)
    ok &= passed
sys.exit(0 if ok else 1)
PYEOF
rc=$?
if [ $rc -ne 0 ]; then
    echo "--- ghostty log tail ---"; tail -15 "$WORK/ghostty.log"
    cp "$WORK"/t*.png /tmp/crt-stack-test/ 2>/dev/null || { mkdir -p /tmp/crt-stack-test && cp "$WORK"/t*.png /tmp/crt-stack-test/; }
    echo "screenshots kept in /tmp/crt-stack-test/"
fi
exit $rc

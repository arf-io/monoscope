#!/usr/bin/env bash
# DVST progressive-write runtime proof (tek4010-storage preset).
#
# Proves the storage tube now writes its stored page PROGRESSIVELY over time
# (a moving beam laying strokes down), not flashed on all at once, and that a
# DENSE page takes LONGER to finish drawing than a SPARSE one — the real
# random-access-vector DVST behavior (stored writing speed 1500-4000
# vector-in/s => a full screen draws in ~seconds; research/dvst-writing-
# dossier.md).
#
# Method: cold start is the clean draw trigger — the zeroed feedback texture
# gives write-clock 0, so the sweep runs from the first rendered frame. Print
# a page at startup, then burst-sample the screen once per second and measure
# the fraction of pixels above glyph brightness (gray > 35/255, the exact
# metric the auto-erase test uses; it already excludes the DVST_BG_GLOW=0.055
# flood floor). The WRITE SPEED knob is set slow (0.25) so the sweep lasts
# ~8-10s and 1s samples resolve the rise unambiguously.
#
# A stateless flash would read full-bright on the very first sample and stay
# flat. Progressive write instead RISES over successive samples, then
# PLATEAUS once the beam finishes. We assert:
#   - dense page: lit-fraction rises materially from early to mid draw
#     (mid >= 1.5 * early, and early is well below the final plateau),
#   - dense page: lit-fraction plateaus (late samples stop climbing),
#   - a SPARSE page reaches its (small) plateau EARLIER than the dense one.
#
# Usage: test_dvst_progressive_runtime.sh [ghostty-binary]
# Requires: Xvfb, ImageMagick, dbus-run-session, python3.
set -u

BIN="${1:-ghostty-phosphor}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CRT="$(dirname "$HERE")"
WORK="$(mktemp -d)"
DPY=":95"
XVFB_PID=""; APP_PID=""
trap 'kill $XVFB_PID $APP_PID 2>/dev/null; rm -rf "$WORK"' EXIT

command -v "$BIN" >/dev/null || { echo "SKIP: $BIN not found"; exit 77; }
command -v Xvfb >/dev/null || { echo "SKIP: Xvfb not found"; exit 77; }
command -v import >/dev/null || { echo "SKIP: ImageMagick not found"; exit 77; }

# --- generate shaders: defaults + tek4010-storage preset, WRITE SPEED slow ---
gen_shaders() { # $1 = target dir, $2 = dvst_write_rate
    python3 - "$CRT" "$1" "$2" << 'PYEOF'
import json, sys
crt, work, rate = sys.argv[1], sys.argv[2], sys.argv[3]
spec = json.load(open(f"{crt}/params.json"))["params"]
preset = dict(json.load(open(f"{crt}/presets/tek4010-storage.json"))["params"])
preset["dvst_write_rate"] = float(rate)

def fmt(key, val):
    s = spec[key]; t = s["type"]
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
    out = [block if ln.strip() == "//@CRT_PARAMS@" else ln
           for ln in body.split("\n")]
    open(f"{work}/{name}.glsl", "w").write("\n".join(out))
print(f"shaders generated (dvst_write_rate={rate})")
PYEOF
}

# Fraction (percent) of root pixels brighter than glyph level (35/255).
bright() {
    magick "$1" -colorspace Gray -threshold 13.7% \
        -format "%[fx:mean*100]" info: 2>/dev/null || echo 0
}

# Run one cold-start capture: $1 = label, $2 = write_rate, $3 = inner script.
# Prints a space-separated series of lit-fraction% sampled once per second.
run_series() {
    local label="$1" rate="$2" inner="$3"
    local dir="$WORK/$label"; mkdir -p "$dir"
    gen_shaders "$dir" "$rate" >/dev/null

    Xvfb "$DPY" -screen 0 1024x768x24 >/dev/null 2>&1 &
    XVFB_PID=$!
    sleep 1

    DISPLAY="$DPY" GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 \
    dbus-run-session -- "$BIN" \
        --config-default-files=false \
        --class=io.arf.crt.dvstprog \
        --custom-shader="$dir/phosphor-state.glsl" \
        --custom-shader="$dir/crt-display.glsl" \
        --custom-shader-animation=always \
        --window-decoration=none \
        --confirm-close-surface=false \
        --font-size=18 \
        -e "$inner" \
        >"$dir/ghostty.log" 2>&1 &
    APP_PID=$!

    # Let the window map and the first frames render, then sample 1 Hz.
    sleep 2
    local series=""
    for i in $(seq 1 12); do
        DISPLAY="$DPY" import -window root "$dir/s$i.png" 2>/dev/null
        series="$series $(bright "$dir/s$i.png")"
        sleep 1
    done
    kill $APP_PID 2>/dev/null; kill $XVFB_PID 2>/dev/null
    sleep 1
    echo "$series"
}

# Dense page: fill the screen. Sparse page: two short lines. Both idle after.
cat > "$WORK/dense.sh" << 'EOSH'
#!/bin/sh
i=0
while [ $i -lt 22 ]; do
  echo "The quick brown fox jumps over the lazy dog 0123456789 line $i"
  i=$((i+1))
done
sleep 40
EOSH
cat > "$WORK/sparse.sh" << 'EOSH'
#!/bin/sh
echo "hello"
echo "world"
sleep 40
EOSH
chmod +x "$WORK/dense.sh" "$WORK/sparse.sh"

echo "== dense page, WRITE SPEED 0.25 (slow) =="
DENSE=$(run_series dense 0.25 "$WORK/dense.sh")
echo "dense lit-fraction% series (1 Hz):$DENSE"

echo "== sparse page, WRITE SPEED 0.25 (slow) =="
SPARSE=$(run_series sparse 0.25 "$WORK/sparse.sh")
echo "sparse lit-fraction% series (1 Hz):$SPARSE"

python3 - "$DENSE" "$SPARSE" << 'PYEOF'
import sys
dense = [float(x) for x in sys.argv[1].split()]
sparse = [float(x) for x in sys.argv[2].split()]

def plateau(series):
    # final settled value = mean of the last 3 samples
    return sum(series[-3:]) / 3.0

def time_to_frac(series, frac):
    # first 1-based sample index reaching frac*plateau
    tgt = frac * plateau(series)
    for i, v in enumerate(series):
        if v >= tgt:
            return i + 1
    return len(series)

dp, sp = plateau(dense), plateau(sparse)

# The draw does not start until the window maps and the first frame renders
# (leading zeros under llvmpipe cold start). Anchor progression to the moment
# ink first APPEARS, not to sample[0], so the test measures the beam sweep and
# not the startup gap. "first lit" = first sample above a clear ink floor.
def first_lit_idx(series, floor=0.3):
    for i, v in enumerate(series):
        if v > floor:
            return i
    return len(series)

fi = first_lit_idx(dense)
rising = dense[fi:]                       # the draw, from first ink onward
first_lit = rising[0] if rising else 0.0
# Longest run of strictly-increasing successive samples in the draw region:
# a stateless flash is flat here (0 rising steps); a swept beam rises for
# several successive frames as the front advances down the page.
best_run = run = 0
for a, b in zip(rising, rising[1:]):
    run = run + 1 if b > a + 0.05 else 0
    best_run = max(best_run, run)
# dense: 90%-of-plateau time vs sparse: 90%-of-plateau time
dense_t90 = time_to_frac(dense, 0.9)
sparse_t90 = time_to_frac(sparse, 0.9)

print(f"dense: first_lit={first_lit:.3f}@{fi+1}s rising_steps={best_run} "
      f"plateau={dp:.3f} t90={dense_t90}s")
print(f"sparse: plateau={sp:.3f} t90={sparse_t90}s")

checks = {
    "dense drew progressively (>=3 successive brightening frames)": best_run >= 3,
    "dense first ink is a partial page, not a flash (< 0.6x plateau)":
        first_lit < 0.6 * dp,
    "dense reached a real page (plateau > 1.5%)": dp > 1.5,
    "dense plateaued (last 3 within 15% of each other)":
        (max(dense[-3:]) - min(dense[-3:])) <= 0.15 * dp + 0.05,
    "dense takes LONGER to finish than sparse (t90)": dense_t90 > sparse_t90,
}
ok = True
for name, passed in checks.items():
    print(("PASS " if passed else "FAIL ") + name)
    ok &= passed
sys.exit(0 if ok else 1)
PYEOF
rc=$?
if [ $rc -ne 0 ]; then
    echo "--- dense log tail ---"; tail -8 "$WORK/dense/ghostty.log" 2>/dev/null
    mkdir -p /tmp/crt-dvst-prog && cp "$WORK"/dense/*.png "$WORK"/sparse/*.png \
        /tmp/crt-dvst-prog/ 2>/dev/null
    echo "screenshots kept in /tmp/crt-dvst-prog/"
fi
exit $rc

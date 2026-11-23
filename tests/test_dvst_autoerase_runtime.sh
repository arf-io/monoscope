#!/usr/bin/env bash
# DVST auto-erase runtime regression test (tek4010-storage preset).
#
# Guards the bug where dvst_auto_erase could never fire on real terminal
# content: the stored-vs-live mismatch detector point-sampled a 4x4
# axis-aligned grid, but glyph ink is sparse (a full text page lights only
# ~5-15% of texels), so the probes averaged ~1 stored hit against the
# >=4-hit floor and the mismatch IIR stayed at exactly 0 forever. The
# detector now probes 256 R2 low-discrepancy points; the 4010 erase
# envelope itself (12ms flash / 0.75s lockout) is unchanged.
#
# Method: latch a full page of text on the storage tube, then clear the
# terminal (ESC[2J ESC[H). Auto-erase must fire and drop the stored page.
# The decisive, timing-tolerant statistic is the fraction of screen pixels
# above glyph brightness (gray > 35/255):
#   latched page  ~5%    (measured 4.9-5.4 on llvmpipe)
#   erased page   ~0.05% (flood-gun background + blinking cursor only)
# The broken detector leaves the latched page glowing indefinitely (~5%).
# Asserts: latched_max > 1.5, erased_min < 0.4, erased_min < latched_max/8.
#
# Usage: test_dvst_autoerase_runtime.sh [ghostty-binary]
# Requires: Xvfb, ImageMagick, dbus-run-session, python3.
set -u

BIN="${1:-ghostty-phosphor}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CRT="$(dirname "$HERE")"
WORK="$(mktemp -d)"
DPY=":94"
trap 'kill $XVFB_PID $APP_PID 2>/dev/null; rm -rf "$WORK"' EXIT

command -v "$BIN" >/dev/null || { echo "SKIP: $BIN not found"; exit 77; }
command -v Xvfb >/dev/null || { echo "SKIP: Xvfb not found"; exit 77; }
command -v import >/dev/null || { echo "SKIP: ImageMagick not found"; exit 77; }

# --- generate shaders from templates: defaults + tek4010-storage preset ---
python3 - "$CRT" "$WORK" << 'PYEOF'
import json, sys
crt, work = sys.argv[1], sys.argv[2]
spec = json.load(open(f"{crt}/params.json"))["params"]
preset = json.load(open(f"{crt}/presets/tek4010-storage.json"))["params"]

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

# Terminal-side timeline: latch a full page, hold 14s, clear, idle.
cat > "$WORK/inner.sh" << 'EOSH'
#!/bin/sh
i=0
while [ $i -lt 20 ]; do
  echo "The quick brown fox jumps over the lazy dog 0123456789 line $i"
  i=$((i+1))
done
sleep 14
printf '\033[2J\033[H'
sleep 60
EOSH
chmod +x "$WORK/inner.sh"

Xvfb "$DPY" -screen 0 1024x768x24 >/dev/null 2>&1 &
XVFB_PID=$!
sleep 1

DISPLAY="$DPY" GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 \
dbus-run-session -- "$BIN" \
    --config-default-files=false \
    --class=io.arf.crt.dvsttest \
    --custom-shader="$WORK/phosphor-state.glsl" \
    --custom-shader="$WORK/crt-display.glsl" \
    --custom-shader-animation=always \
    --window-decoration=none \
    --confirm-close-surface=false \
    --font-size=18 \
    -e "$WORK/inner.sh" \
    >"$WORK/ghostty.log" 2>&1 &
APP_PID=$!

# Fraction (percent) of root pixels brighter than glyph level (35/255).
bright() {
    magick "$WORK/$1.png" -colorspace Gray -threshold 13.7% \
        -format "%[fx:mean*100]" info: 2>/dev/null || echo 0
}
snap() { DISPLAY="$DPY" import -window root "$WORK/$1.png" 2>/dev/null; }

# Latched-page window (page prints at startup; clear comes at ~16-18s):
# burst-sample and keep the max so slow llvmpipe startup cannot miss it.
latched_max=0
for i in 1 2 3 4 5; do
    sleep 2
    snap "latch$i"
    v=$(bright "latch$i")
    latched_max=$(python3 -c "print(max(float('$latched_max'), float('$v')))")
done

# Erased window: well after the clear (+ flash + 0.75s lockout). Keep the
# min of three samples so a single mistimed frame cannot fail the run.
sleep 15
erased_min=100
for i in 1 2 3; do
    snap "erase$i"
    v=$(bright "erase$i")
    erased_min=$(python3 -c "print(min(float('$erased_min'), float('$v')))")
    sleep 3
done

loads=$(grep -c 'loaded custom shader' "$WORK/ghostty.log")
echo "latched bright% max=$latched_max | erased bright% min=$erased_min | shader loads=$loads"

python3 - "$latched_max" "$erased_min" "$loads" << 'PYEOF'
import sys
latched, erased, loads = [float(x) for x in sys.argv[1:4]]
checks = {
    "page latched on the storage tube (bright > 1.5%)": latched > 1.5,
    "auto-erase dropped the stored page (bright < 0.4%)": erased < 0.4,
    "erased page is <1/8 of latched page": erased < latched / 8.0,
    "both shaders loaded": loads >= 2,
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
    mkdir -p /tmp/crt-dvst-test && cp "$WORK"/*.png /tmp/crt-dvst-test/ 2>/dev/null
    echo "screenshots kept in /tmp/crt-dvst-test/"
fi
exit $rc

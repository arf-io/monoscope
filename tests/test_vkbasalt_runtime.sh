#!/usr/bin/env bash
# vkBasalt runtime proof: the generated ReShade pack compiles in vkBasalt's
# embedded FX compiler and imprints real CRT structure on a real Vulkan app.
#
# Capture path (validated live 2026-07-19, see ../reshade/VKBASALT.md):
# gamescope --backend headless hosts vkcube; VK_LAYER_LUNARG_screenshot
# grabs frames; vkBasalt is enabled on the child via ENABLE_VKBASALT=1 +
# VKBASALT_CONFIG_FILE (generated per-preset conf, fx path resolved).
#
# Assertions per preset: vkBasalt log reaches "created ReshadeEffect" with
# zero FX compile errors; captured frame is non-black; period-3 column
# energy (aperture grille) exceeds the control run by >= 5x. For the
# low-scanline preset, row-periodicity must also beat control.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CRT="$(dirname "$HERE")"
FX="$CRT/reshade/Shaders/ghostcrtty.fx"

for tool in gamescope vkcube; do
    command -v "$tool" >/dev/null || { echo "SKIP: $tool missing"; exit 77; }
done
[ -f /usr/lib/libvkbasalt.so ] || [ -f /usr/lib64/libvkbasalt.so ] || \
    ldconfig -p 2>/dev/null | grep -q vkbasalt || \
    { echo "SKIP: vkBasalt not installed"; exit 77; }
# plain grep (not -q): -q exits at first match and SIGPIPEs vulkaninfo,
# which pipefail then reports as failure.
vulkaninfo --summary 2>/dev/null | grep VK_LAYER_LUNARG_screenshot \
    > /dev/null || { echo "SKIP: screenshot layer missing"; exit 77; }
[ -f "$FX" ] || { echo "SKIP: pack not generated"; exit 77; }

WORK="$(mktemp -d /tmp/vkbasalt-proof-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

capture() { # capture <outdir> [conf]  -> writes 40.ppm
    local out="$1" conf="${2:-}"
    mkdir -p "$out"
    local env_extra=()
    if [ -n "$conf" ]; then
        env_extra=(ENABLE_VKBASALT=1 "VKBASALT_CONFIG_FILE=$conf"
                   VKBASALT_LOG_FILE="$out/vkbasalt.log"
                   VKBASALT_LOG_LEVEL=debug)
    fi
    timeout 120 gamescope --backend headless -W 640 -H 480 -w 640 -h 480 -- \
        env VK_INSTANCE_LAYERS=VK_LAYER_LUNARG_screenshot \
            VK_SCREENSHOT_FRAMES=40 VK_SCREENSHOT_FORMAT=UNORM \
            "VK_SCREENSHOT_DIR=$out" "${env_extra[@]}" \
            vkcube --wsi xcb --width 640 --height 480 --c 60 \
        > "$out/run.log" 2>&1 || true
    [ -f "$out/40.ppm" ]
}

metrics() { # metrics <ppm>  -> "mean colE3 rowE"
    python3 - "$1" <<'PYEOF'
import sys
def read_ppm(p):
    # Token-based header parse: P6 headers may split tokens across any
    # whitespace/newlines and carry # comments (layer writers vary).
    with open(p, "rb") as f:
        toks = []
        while len(toks) < 4:
            line = f.readline()
            if not line:
                raise ValueError("short PPM header")
            if line.lstrip().startswith(b"#"):
                continue
            toks += line.split()
        assert toks[0] == b"P6", toks[0]
        w, h, maxv = int(toks[1]), int(toks[2]), int(toks[3])
        data = f.read(w * h * 3)
    return w, h, data
w, h, d = read_ppm(sys.argv[1])
# Luma column/row means. Row means use a narrow 32-column strip on the
# vertical axis: with spherical tube warp the scanlines curve, and any
# wide row average decorrelates a 2-px comb; on the axis the curvature
# displacement stays sub-pixel.
cols = [0.0] * w
x0, x1 = w // 2 - 16, w // 2 + 16
y0, y1 = h // 3, 2 * h // 3
rows = [0.0] * (y1 - y0)
total = 0.0
for y in range(h):
    base = y * w * 3
    racc = 0.0
    for x in range(w):
        i = base + x * 3
        l = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]
        cols[x] += l
        total += l
        if x0 <= x < x1 and y0 <= y < y1:
            racc += l
    if y0 <= y < y1:
        rows[y - y0] = racc / (x1 - x0) / 255.0
total = total / (w * h) / 255.0
cols = [c / h / 255.0 for c in cols]
def period_energy(sig, p):
    n = len(sig)
    m = sum(sig) / n
    sig = [v - m for v in sig]
    var = sum(v * v for v in sig) / n or 1e-12
    # energy at exact period p via correlation with cos/sin combs
    import math
    cr = sum(sig[i] * math.cos(2 * math.pi * i / p) for i in range(n)) / n
    ci = sum(sig[i] * math.sin(2 * math.pi * i / p) for i in range(n)) / n
    return (cr * cr + ci * ci) / var
print("%.6f %.8f %.8f" % (total, period_energy(cols, 3.0),
                          max(period_energy(rows, 2.0),
                              period_energy(rows, 4.0))))
PYEOF
}

echo "== control (no vkBasalt)"
capture "$WORK/control" || { echo "FAIL: control capture missing"; exit 1; }
read -r C_MEAN C_COL3 C_ROW < <(metrics "$WORK/control/40.ppm")
echo "   mean=$C_MEAN colE3=$C_COL3 rowE=$C_ROW"

fails=0
for preset in trinitron-pvm commodore-1702-1983; do
    echo "== preset $preset"
    conf="$WORK/$preset.conf"
    sed -e "s|@GHOSTCRTTY_FX@|$FX|" \
        -e "s|@GHOSTCRTTY_DIR@|$CRT/reshade/Shaders|" \
        "$CRT/reshade/vkBasalt/$preset.conf" > "$conf"
    if ! capture "$WORK/$preset" "$conf"; then
        echo "FAIL($preset): no captured frame"; fails=$((fails+1)); continue
    fi
    log="$WORK/$preset/vkbasalt.log"
    # vkBasalt logs to stderr of the app when no log file support; accept
    # either the dedicated log or the run log.
    if ! grep -hq "created ReshadeEffect" "$log" "$WORK/$preset/run.log" \
            2>/dev/null; then
        echo "FAIL($preset): effect did not compile"; fails=$((fails+1))
    fi
    if grep -hq "error X" "$log" "$WORK/$preset/run.log" 2>/dev/null; then
        echo "FAIL($preset): FX compile errors present"; fails=$((fails+1))
    fi
    read -r MEAN COL3 ROWE < <(metrics "$WORK/$preset/40.ppm")
    echo "   mean=$MEAN colE3=$COL3 rowE=$ROWE"
    awk -v m="$MEAN" 'BEGIN{exit !(m > 0.02)}' \
        || { echo "FAIL($preset): black/near-black output"; fails=$((fails+1)); }
    awk -v a="$COL3" -v c="$C_COL3" 'BEGIN{exit !(a > 5*c && a > 0.001)}' \
        || { echo "FAIL($preset): no period-3 mask signature"; fails=$((fails+1)); }
    if [ "$preset" = "commodore-1702-1983" ]; then
        awk -v a="$ROWE" -v c="$C_ROW" 'BEGIN{exit !(a > 3*c)}' \
            || { echo "FAIL($preset): no scanline row periodicity"; fails=$((fails+1)); }
    fi
done

echo "VKBASALT: $((2 - fails > 0 ? 2 - fails : 0))/2 presets proven, control mean=$C_MEAN"
[ "$fails" -eq 0 ] && { echo PASS; cp -r "$WORK" /tmp/vkbasalt-proof-last 2>/dev/null || true; }
[ "$fails" -eq 0 ]

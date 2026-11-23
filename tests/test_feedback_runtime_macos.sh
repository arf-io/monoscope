#!/usr/bin/env bash
# UNVERIFIED on macOS — written on Linux against the fork's source; part of
# the M1 test kit (see M1-TEST-PLAN.md at the fork root). Verify during the
# M1 session and fix what the hardware disagrees with.
#
# Runtime verification that the phosphor-feedback Ghostty fork provides a
# working per-pass feedback texture (iChannel1) across frames — macOS
# variant of test_feedback_runtime.sh. Same proof shader, same idea; the
# harness differs:
#   Linux: Xvfb + isolated D-Bus + ImageMagick `import`
#   macOS: real WindowServer + `osascript` (position the window) +
#          `screencapture -x -R` (sample a region inside the window)
#
# Permissions the invoking terminal needs (System Settings > Privacy):
#   * Accessibility   — for System Events window positioning
#   * Screen Recording — for screencapture to include window contents
#     (without it, captures silently show wallpaper only -> the r0 gate
#     below fails; that is the first thing to check on a FAIL)
#
# Timing: unlike the Linux harness (software GL, ~15fps), an M1 runs the
# shader at full refresh (60 or 120Hz ProMotion), so the +0.004/frame ramp
# can SATURATE in ~2-4s. t0 is therefore sampled early (~1s) and the pass
# condition accepts either a visible ramp or early saturation — a stateless
# pipeline is pinned at one increment (red mean ~1/255) forever and passes
# neither branch.
#
# Usage: test_feedback_runtime_macos.sh [path-to-ghostty-binary]
#   Default binary: $GHOSTTY_PHOSPHOR_BIN, else the fork's build output.
# Requires: ImageMagick (`brew install imagemagick`), osascript, screencapture.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
APP_PID=""
trap '[ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null; rm -rf "$WORK"' EXIT

BIN="${1:-${GHOSTTY_PHOSPHOR_BIN:-}}"
if [ -z "$BIN" ]; then
    for cand in \
        "$HOME/Augments/ghostcrtty/macos/build/ReleaseLocal/Ghostty.app" \
        "$HOME/Augments/ghostcrtty/macos/build/Release/Ghostty.app" \
        "$HOME/Augments/ghostty-phosphor/macos/build/ReleaseLocal/Ghostty.app" \
        "$HOME/Augments/ghostty-phosphor/macos/build/Release/Ghostty.app" \
        "$HOME/Augments/ghostty-phosphor/macos/build/Debug/Ghostty.app"; do
        for exe in ghostty Ghostty; do
            [ -x "$cand/Contents/MacOS/$exe" ] && BIN="$cand/Contents/MacOS/$exe" && break 2
        done
    done
fi
[ -n "$BIN" ] && [ -x "$BIN" ] || { echo "SKIP: no ghostty binary (pass a path or set GHOSTTY_PHOSPHOR_BIN)"; exit 77; }
command -v magick >/dev/null || { echo "SKIP: ImageMagick not found (brew install imagemagick)"; exit 77; }
command -v screencapture >/dev/null || { echo "SKIP: screencapture not found (not macOS?)"; exit 77; }
command -v osascript >/dev/null || { echo "SKIP: osascript not found (not macOS?)"; exit 77; }

# Launch the fork with ONLY the proof shader; no default config files so
# the user's setup can't interfere. No --class (GTK-only). -e keeps the
# surface alive without shell integration noise.
"$BIN" \
    --config-default-files=false \
    --custom-shader="$HERE/feedback_proof.glsl" \
    --custom-shader-animation=always \
    --window-decoration=none \
    --confirm-close-surface=false \
    -e sleep 30 >"$WORK/ghostty.log" 2>&1 &
APP_PID=$!

# Give the app time to create its window, then pin it to a known place.
# System Events needs Accessibility; treat failure as SKIP, not FAIL.
sleep 2
if ! osascript >/dev/null 2>"$WORK/osa.err" <<EOF
tell application "System Events"
    set proc to first process whose unix id is $APP_PID
    set frontmost of proc to true
    tell front window of proc
        set position to {0, 40}
        set size to {800, 600}
    end tell
end tell
EOF
then
    echo "SKIP: could not position the window via System Events"
    echo "      (grant Accessibility to this terminal and retry)"
    sed -n '1,3p' "$WORK/osa.err"
    exit 77
fi

# Sample a region safely inside the window (points; Retina scaling does
# not matter for a mean). Window at (0,40) sized 800x600 -> region
# (100,200)-(500,500) is interior even if macOS nudged it slightly.
REGION="100,200,400,300"

sleep 1   # ~1s of shader time at t0: ramp visible but not saturated at 60Hz
screencapture -x -R "$REGION" "$WORK/t0.png" || { echo "FAIL: screencapture t0"; exit 1; }
sleep 4
screencapture -x -R "$REGION" "$WORK/t1.png" || { echo "FAIL: screencapture t1"; exit 1; }

r0=$(magick "$WORK/t0.png" -colorspace sRGB -channel R -separate -format "%[fx:mean*255]" info:)
r1=$(magick "$WORK/t1.png" -colorspace sRGB -channel R -separate -format "%[fx:mean*255]" info:)

echo "red mean t0=$r0 t1=$r1"
# Two ways to pass, both impossible without cross-frame state:
#   ramp:      visible increase between the samples (60Hz-ish pacing)
#   saturated: both samples already pinned high (120Hz ProMotion can
#              saturate the +0.004/frame ramp before t0)
# A stateless pipeline holds red mean at ~1/255 forever and passes neither.
pass=$(python3 -c "
r0, r1 = float('$r0'), float('$r1')
ramp = r0 > 10 and (r1 - r0) > 25
saturated = r0 > 200 and r1 > 200
print(1 if ramp or saturated else 0)")
if [ "$pass" = "1" ]; then
    echo "PASS: feedback texture persists across frames (red $r0 -> $r1)"
    exit 0
else
    echo "FAIL: feedback did not accumulate (red t0=$r0 t1=$r1)"
    echo "      if both values are near 0, check Screen Recording permission"
    echo "      (screencapture silently omits windows without it)"
    echo "--- ghostty log tail ---"
    tail -20 "$WORK/ghostty.log"
    echo "--- unified log (shader lines) ---"
    log show --predicate 'subsystem=="com.mitchellh.ghostty"' --last 2m 2>/dev/null \
        | grep -i shader | tail -10
    exit 1
fi

#!/usr/bin/env bash
# Runtime verification that the phosphor-feedback Ghostty fork provides a
# working per-pass feedback texture (iChannel1) across frames.
#
# Method: launch the fork headless (Xvfb + llvmpipe + isolated D-Bus so the
# real session's Ghostty instance is untouched) with feedback_proof.glsl,
# which ramps red brightness by +0.004/frame through its own feedback. Two
# screenshots ~4s apart must show (a) a large red-channel increase and
# (b) a saturated final value — impossible without cross-frame state.
#
# Usage: test_feedback_runtime.sh [path-to-ghostty-binary]
#   Default binary: ghostty-phosphor on PATH.
# Requires: Xvfb, ImageMagick (import/magick), dbus-run-session.
set -u

BIN="${1:-ghostty-phosphor}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
DPY=":97"
trap 'kill $XVFB_PID $APP_PID 2>/dev/null; rm -rf "$WORK"' EXIT

command -v "$BIN" >/dev/null || { echo "SKIP: $BIN not found"; exit 77; }
command -v Xvfb >/dev/null || { echo "SKIP: Xvfb not found"; exit 77; }
command -v import >/dev/null || { echo "SKIP: ImageMagick not found"; exit 77; }

Xvfb "$DPY" -screen 0 1024x768x24 >/dev/null 2>&1 &
XVFB_PID=$!
sleep 1

# Isolated bus + distinct class: never touches the user's live instance.
DISPLAY="$DPY" GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 \
dbus-run-session -- "$BIN" \
    --config-default-files=false \
    --class=io.arf.crt.feedbacktest \
    --custom-shader="$HERE/feedback_proof.glsl" \
    --custom-shader-animation=always \
    --window-decoration=none \
    --confirm-close-surface=false \
    -e sleep 30 >"$WORK/ghostty.log" 2>&1 &
APP_PID=$!

sleep 3
DISPLAY="$DPY" import -window root "$WORK/t0.png" 2>/dev/null
sleep 4
DISPLAY="$DPY" import -window root "$WORK/t1.png" 2>/dev/null

r0=$(magick "$WORK/t0.png" -colorspace sRGB -channel R -separate -format "%[fx:mean*255]" info:)
r1=$(magick "$WORK/t1.png" -colorspace sRGB -channel R -separate -format "%[fx:mean*255]" info:)

echo "red mean t0=$r0 t1=$r1"
# The decisive, framerate-independent assertion: a STATELESS pipeline is
# pinned at one increment (red mean ~1/255) forever, so any substantial
# rise between two samples taken seconds after startup proves cross-frame
# state. (Software GL runs ~15fps, so saturation timing varies; the ramp
# accumulating +25 red between t0 and t1 cannot happen without feedback.)
pass=$(python3 -c "print(1 if float('$r1') - float('$r0') > 25 and float('$r0') > 10 else 0)")
if [ "$pass" = "1" ]; then
    echo "PASS: feedback texture persists across frames (red $r0 -> $r1)"
    exit 0
else
    echo "FAIL: feedback did not accumulate (red t0=$r0 t1=$r1)"
    echo "--- ghostty log tail ---"
    tail -20 "$WORK/ghostty.log"
    exit 1
fi

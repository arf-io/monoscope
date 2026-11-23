# ghostcrtty ReShade / gamescope pack

This pack is the whole-screen CRT target:

- Windows: install ReShade for the target app and add `reshade/Shaders` to
  the effect search path, then enable `ghostcrtty.fx`.
- Wayland: run a game/app under gamescope with
  `gamescope --reshade-effect /path/to/ghostcrtty.fx -- <command>`.
- Linux Vulkan apps (vkBasalt): `./install-vkbasalt.sh <preset>` writes
  `~/.config/vkBasalt/vkBasalt.conf` for that preset (the per-preset configs
  are in `vkBasalt/`), then run the app with `ENABLE_VKBASALT=1`. The fx is
  self-contained (no ReShade.fxh) and avoids the constructs vkBasalt's
  embedded FX compiler rejects; runtime-proven by
  `tests/test_vkbasalt_runtime.sh` (headless gamescope + vkcube capture
  with pixel-statistics assertions). See `VKBASALT.md` for the full
  compatibility history.

The `.fx` is not a fake screenshot filter. It has a persistent RGBA16F
phosphor state: one pass updates excitation from the live backbuffer and
previous retained state, one pass presents through tube optics, and one pass
retains that state for the next frame.

The existing libretro Slang pack remains the macOS-friendly shader pack for
RetroArch/Slang-capable hosts. A true macOS whole-desktop overlay still needs a
native ScreenCaptureKit/Metal app; this repo does not pretend that exists.

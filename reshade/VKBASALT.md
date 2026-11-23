# vkBasalt compatibility report

Date: 2026-07-19
Host: Arch Linux, RADV NAVI14, vkBasalt 0.3.2.10

## Result

The current `reshade/Shaders/ghostcrtty.fx` pack is **not vkBasalt-compatible
as shipped**.

vkBasalt can load a custom ReShade effect and can preserve internal render
target state across frames, but this pack currently fails vkBasalt's embedded
ReShade compiler:

- `ReShade.fxh` is not included in this pack.
- After installing standard ReShade headers and setting
  `reshadeIncludePath = /opt/reshade/shaders`, vkBasalt still rejects:
  - `fmod(...)` at `ghostcrtty.fx:239`
  - local variable name `vector` at `ghostcrtty.fx:253`

The stock failure is not a harmless warning. In the headless capture run the
stock effect presented a black frame.

## Installation / runtime used

Installed during validation:

- `vkbasalt 0.3.2.10-1`
- `vkbasalt-debug 0.3.2.10-1`
- `reshade-shaders-git r161.dea2bc7-1`
- `weston 15.0.1-3`

Already present:

- `vulkan-tools 1.4.350.1-1`
- `vulkan-extra-layers`
- `imagemagick 7.1.2.27-1`
- `gamescope 3.16.24-1`

Layer registration was confirmed by `vulkaninfo --summary`:

- `VK_LAYER_VKBASALT_post_processing`
- `VK_LAYER_LUNARG_screenshot`

## vkBasalt config shape

vkBasalt does not consume the ReShade preset `.ini` files directly. The tested
config copied the preset's `Ghost_*` assignments into `vkBasalt.conf`:

```ini
effects = ghostcrtty
ghostcrtty = /path/to/reshade/Shaders/ghostcrtty.fx
reshadeTexturePath = /opt/reshade/textures
reshadeIncludePath = /opt/reshade/shaders
enableOnLaunch = True
Ghost_Brightness = 0
...
```

The `trinitron-pvm.ini` preset values were used for the stock and diagnostic
captures.

## Headless capture path

`vkcube` under plain Xvfb was not usable on this host:

```text
MESA: info: vulkan: No DRI3 support detected - required for presentation
```

A headless gamescope compositor with an Xwayland child did work:

```sh
gamescope --backend headless -W 640 -H 480 -w 640 -h 480 -- \
  env VK_INSTANCE_LAYERS=VK_LAYER_LUNARG_screenshot \
      VK_SCREENSHOT_FRAMES=20,40 \
      VK_SCREENSHOT_FORMAT=UNORM \
      VK_SCREENSHOT_DIR=/tmp/vkbasalt-ghostcrtty-20260719-225223/gh-control \
      vkcube --wsi xcb --width 640 --height 480 --c 60
```

The same wrapper was used for stock and diagnostic vkBasalt runs, with
`ENABLE_VKBASALT=1`, `VKBASALT_CONFIG_FILE=...`, and
`VKBASALT_LOG_LEVEL=debug` applied to the child process.

## Evidence

Artifacts are in:

```text
/tmp/vkbasalt-ghostcrtty-20260719-225223
```

Important files:

- `gh-control/40.ppm`
- `gh-stock/40.ppm`
- `gh-stock/vkbasalt.log`
- `gh-diagnostic/40.ppm`
- `gh-diagnostic/vkbasalt.log`
- `feedback-proof/5.ppm`, `20.ppm`, `40.ppm`

ImageMagick frame statistics:

| Run | Frame | Mean | Stddev | Min | Max | RMSE vs control |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Headless control | 40 | 0.226199 | 0.089193 | 0 | 0.956863 | - |
| Stock ghostcrtty | 40 | 0 | 0 | 0 | 0 | 0.243255 |
| Diagnostic ghostcrtty | 40 | 0.158095 | 0.0852964 | 0 | 0.909804 | 0.0960881 |

The stock vkBasalt log contains:

```text
ghostcrtty.fx(239, 11): error X3004: undeclared identifier or no matching intrinsic overload for 'fmod'
ghostcrtty.fx(253, 8): error X3000: syntax error: unexpected 'vector', expected 'identifier'
```

The diagnostic copy made only temporary syntax substitutions:

- `fmod(floor(x), 3.0)` -> arithmetic modulo using `floor`
- `float3 vector` -> `float3 vectorLight`

It then compiled and created all three passes:

```text
fragment entry: F__UpdateStatePS
fragment entry: F__PresentPS
fragment entry: F__CopyStatePS
finished creating Reshade effect
created ReshadeEffect
```

Objective CRT structure checks on the headless frame:

| Metric | Control | Diagnostic | Interpretation |
| --- | ---: | ---: | --- |
| Column period-3 energy | 0.00032710 | 0.01630847 | Diagnostic has a strong 3-pixel aperture-grille mask signature. |
| Column autocorr lag 1 | 0.99696668 | 0.66589294 | Adjacent columns are no longer smooth after the mask. |
| Column autocorr lag 3 | 0.98512417 | 0.96319156 | 3-column repetition remains high, matching RGB grille periodicity. |
| RGB mean | 0.217340 / 0.229695 / 0.231561 | 0.152674 / 0.161130 / 0.160482 | Diagnostic is visibly darker/tinted by CRT glass and phosphor processing. |

The selected `trinitron-pvm` preset uses `Ghost_ScanLines=480` at a 480 px
capture height, so row-period scanline energy is intentionally weak in this
specific measurement. The mask and luminance changes are the reliable
structural assertions for this run.

## Persistent feedback proof

A minimal temporary ReShade FX using the same A/B/copy render-target pattern
was run under vkBasalt. It increments retained brightness each frame:

| Frame | Mean | Stddev | Min | Max |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 0.141176 | 0 | 0.141176 | 0.141176 |
| 20 | 0.494118 | 0 | 0.494118 | 0.494118 |
| 40 | 0.964706 | 0 | 0.964706 | 0.964706 |

vkBasalt logged all three proof passes:

```text
fragment entry: F__AccumPS
fragment entry: F__PresentPS
fragment entry: F__CopyPS
finished creating Reshade effect
created ReshadeEffect
```

Conclusion: vkBasalt can express persistent multi-pass render-target feedback
well enough for ghostcrtty's state-retention model. The blocker is the current
FX source dialect and packaging, not the feedback concept.

## Compatibility matrix

| Capability | Status | Evidence / notes |
| --- | --- | --- |
| Vulkan layer loads | Works | `VK_LAYER_VKBASALT_post_processing` registered and loaded with `ENABLE_VKBASALT=1`. |
| Real Vulkan app capture | Works | `vkcube --wsi xcb` under `gamescope --backend headless`, captured by `VK_LAYER_LUNARG_screenshot`. |
| Stock pack include closure | Fails | Pack does not include `ReShade.fxh`; `/opt/reshade/shaders` was needed. |
| Stock `ghostcrtty.fx` compile under vkBasalt | Fails | vkBasalt rejects `fmod` and `vector`; stock capture was black. |
| Preset `.ini` consumption | Not native | vkBasalt reads `vkBasalt.conf`; preset values must be copied into config or baked into the `.fx`. |
| Three-pass ReShade technique | Works after syntax adaptation | Diagnostic copy created `UpdateStatePS`, `PresentPS`, `CopyStatePS`. |
| Internal render targets | Works after syntax adaptation | Diagnostic copy used `Ghost_StateA` and `Ghost_StateB`; feedback proof confirmed retention across frames. |
| Mask pattern | Works after syntax adaptation | Period-3 column energy increased from `0.00032710` to `0.01630847`. |
| Scanline assertion | Inconclusive in selected preset | `trinitron-pvm` has `Ghost_ScanLines=480` at 480 px output; use a lower-line stress preset for a stronger row-period test after source compatibility fixes land. |

## Recommended fixes before declaring P1c done

1. Ship `ReShade.fxh` or remove the dependency by inlining the small
   `PostProcessVS` prelude this shader actually needs.
2. Replace `fmod` in the generated ReShade FX with vkBasalt-compatible
   arithmetic or a helper function accepted by its parser.
3. Avoid `vector` as an identifier in generated FX.
4. Add a vkBasalt preset export mode that writes `vkBasalt.conf` entries from
   `reshade/Presets/*.ini`, or bake one `.fx` per preset like the gamescope
   flow.
5. Re-run the headless gamescope capture and require nonzero output plus
   period-3 mask detection before marking vkBasalt support green.

## Resolution — 2026-07-19, same day (pack fixed, validation green)

All five recommended fixes landed in `tools/transpile_reshade.py`:

1. `ReShade.fxh` dependency removed — the fullscreen-triangle
   `PostProcessVS` is inlined; the fx is fully self-contained (still valid
   under Windows ReShade, which accepts header-free effects).
2. `fmod` eliminated (explicit floor-mod arithmetic — also the correct
   GLSL `mod` semantics).
3. The `vector` identifier renamed (`stroke`).
4. vkBasalt export mode added: `reshade/vkBasalt/<preset>.conf` for all 57
   presets (+ `install-vkbasalt.sh` resolving the fx path into
   `~/.config/vkBasalt/vkBasalt.conf`). Discovered along the way: vkBasalt
   0.3.2.x asserts on empty `reshadeIncludePath`/`reshadeTexturePath`
   even for a self-contained fx — the generated configs point both at the
   pack's `Shaders/` dir.
5. Durable runtime proof: `tests/test_vkbasalt_runtime.sh` (headless
   gamescope + vkcube + screenshot layer). Measured on this host:

   | Run | Mean | Period-3 column energy | Axis-strip row energy |
   | --- | ---: | ---: | ---: |
   | Control | 0.226214 | 0.00000087 | 0.00004100 |
   | trinitron-pvm | 0.158699 | 0.05557969 (~64,000x control) | 0.00010607 |
   | commodore-1702-1983 | 0.142273 | 0.02678501 | 0.00016918 (4.1x control) |

   Both presets: `created ReshadeEffect` in the debug log, zero FX errors,
   non-black output, mask signature >= 5x control. The row-periodicity
   metric measures a narrow on-axis column strip because spherical warp
   curves the scanlines (a wide row average decorrelates the 2 px comb).

P1c (vkBasalt) is now green with evidence.

# OBS feasibility — what was actually measured

The question was "will the shaders render in OBS?" This directory is the
answer, and the harness that produced it, so it can be re-run rather than
believed.

Everything below was measured on **OBS Studio 32.2.1-6** with
**obs-shaderfilter 2.6.0** on Linux, running headless under Xvfb and
recording losslessly (x264 `qp=0`, I444). `harness.py` builds a throwaway
`XDG_CONFIG_HOME` so it never touches a real OBS configuration.

```
python3 harness.py            # library; see the v*.py drivers in the session notes
```

## 1. The architecture works

The engine is two passes: `phosphor-state` (electrical — needs its **own**
previous output as a feedback texture) and `crt-display` (optical — samples
the phosphor state). In OBS that maps onto **two stacked Shader Filters** on
one source, provided `previous_output` really is per-filter self-feedback.

`ramp.shader` settles it: it returns `previous_output + 0.01` and nothing
else. If `previous_output` were the *prior filter's* output it would sit
flat.

> Measured centre pixel over time:
> `0x12 → 0x36 → 0x63 → 0x90 → 0xbd → 0xea → 0xff`
> — exactly +0.01/frame, accumulating.

**`previous_output` is this filter's own previous output.** The two-pass
architecture is viable in OBS.

## 2. The feedback texture is 8-bit, not fp16

`core/metal/ABI.md` specifies the phosphor state as **RGBA16Float**, because
the long phosphors (P7 radar, the Tektronix storage tubes) depend on many
frames of smooth exponential decay.

You cannot answer this by reading pixel values out of a recording — the
recording is 8-bit either way. So `decay99.shader` makes the shader count for
itself: `.g` holds a state that is seeded to 1.0 and multiplied by 0.99 every
frame, and `.r` is incremented by one LSB for every frame the state is still
non-zero, *as read back from the feedback texture*.

> Measured: the state decayed `249 → 202 → 159 → 133 → 110 → 87 → 65 → 49`
> and then **stuck at exactly 50/255 for 2 468 frames (82.3 s)** and never
> moved again.

That is the 8-bit UNORM round-trip fixed point: `50 × 0.99 = 49.5`, which
rounds straight back to `50`. **The feedback target is 8-bit UNORM.**

### Confirmed in obs-shaderfilter's source, not just inferred

```c
gs_texrender_t *create_or_reset_texrender(gs_texrender_t *render)
{
        if (!render) {
                render = gs_texrender_create(GS_RGBA, GS_ZS_NONE);   /* 8-bit */
        ...
```

`GS_RGBA` is hardcoded, and `previous_output_texrender` is allocated through
that same helper. There is no property, no setting, and no colour-space path
that changes it — the measurement and the source agree exactly.

This is a plugin limitation, **not** an OBS one and **not** ours:

- libobs has had `GS_RGBA16F` and `GS_RGBA32F` all along
  (`/usr/include/obs/graphics/graphics.h`).
- obs-shaderfilter *already knows how to pick a float format* — its
  **source-parameter** path calls
  `gs_get_format_from_space()` with `GS_CS_SRGB_16F` among the preferred
  spaces. Only the input/output/feedback texrenders skip that and take the
  hardcoded `GS_RGBA`.
- Every one of this engine's own hosts is fp16 already: ghostcrtty's OpenGL
  renderer (`.internal_format = .rgba16f`), its Metal renderer
  (`.pixel_format = .rgba16float`), the Metal ABI (`RGBA16Float`), and the
  WebGL2 engine (`gl.RGBA16F` + `gl.HALF_FLOAT`, which *refuses to run*
  without `EXT_color_buffer_float`).

So the tidy fix is a small upstream patch: give `create_or_reset_texrender` a
format argument and hand it `gs_get_format_from_space()` — the call the
plugin already makes a few hundred lines away. That is worth filing upstream;
until it lands, the half-LSB floor below makes the pack correct on stock
obs-shaderfilter.

The consequence is not cosmetic. A P7 radar afterglow or a DVST storage tube
would freeze at ~20 % brightness and never fade — a permanent smear burned
across the scene, not a decay.

## 3. The fix, also measured

Subtract half a least-significant bit after the multiply
(`decayfix.shader`):

```hlsl
float v = max(0.0, prev.g * 0.99 - (1.0 / 510.0));
```

Half an LSB is always enough to cross the rounding boundary, so the tail is
guaranteed to reach zero in bounded time, and it costs the curve less than
one LSB of accuracy anywhere along it.

> Measured with the identical harness: `255 → 252 → 184 → 134 → 93 → 67 →
> 42 → 17 → 0`, reaching zero at frame 192 and staying there.

## Where this leaves the OBS host

| | |
|---|---|
| Two-pass feedback architecture | **verified working** |
| Short/medium phosphors (P22, P4, P31, P39) | expected fine — decay completes in few enough frames that 8-bit is adequate |
| Long phosphors (P7, DVST storage, burn-in aging) | **broken as written** on stock obs-shaderfilter, fixed by the half-LSB floor above; genuinely fixed by an fp16 texrender |
| `params.json` knobs as runtime sliders | obs-shaderfilter's annotation syntax (`string label`, `widget_type = "slider"`, `minimum`/`maximum`/`step`) maps 1:1; not yet built |
| The transpiler and preset pack | **not built.** `tools/transpile_reshade.py` is the right thing to fork — the OBS effect language is HLSL-flavoured and much closer to ReShade than to Metal or slang |

Two further things worth knowing before building the pack:

- "Does a high-precision canvas upgrade the feedback target?" — **no.** This
  was left open when the only evidence was measurement (an `I010` canvas was
  tried; OBS accepted it but x264/high444 could not encode the capture). The
  source settles it: `create_or_reset_texrender` takes no format and passes
  `GS_RGBA` unconditionally, so no canvas or colour-space setting can reach
  it. Stock obs-shaderfilter is 8-bit no matter how OBS is configured.
- Stochastic (dithered) rounding is the more faithful alternative to a fixed
  half-LSB floor, and is already in the engine's idiom — `DESIGN.md` uses
  stochastic fp16 dosing for Coulomb aging. It preserves the *expected*
  decay curve rather than biasing it slightly fast. It was not measured here.

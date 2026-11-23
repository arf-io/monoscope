# Monoscope — Design & Physics Reference

A physically grounded CRT monitor simulation built around a two-pass
phosphor feedback pipeline, with an
analog control surface (`crtctl`). Every simulated behavior traces to a
measured or documented property of real hardware; every approximation is
listed in "Honest approximations" below.

## Architecture

```
terminal frame (sRGB8, premult alpha)
      │  iChannel0
      ▼
┌──────────────────────┐   iChannel1 (self-feedback, RGBA16F)
│ PASS 1 phosphor-state │◄─────────────── its own previous output
│  video amp → gun →    │
│  phosphor excitation, │   RGB = excitation   A = burn-in dose
│  decay, burn-in dose, │   row 0 = data pixels (clocks, nonces, APL)
│  power state machine  │
└──────────┬───────────┘
           │  iChannel0
           ▼
┌──────────────────────┐
│ PASS 2 crt-display    │   deflection geometry, power choreography,
│  (the optics)         │   sync errors, scanlines, mask, damper wires,
└──────────┬───────────┘   halation, hum, degauss, glass, burn-in show
           │
           ▼  internal present pass (fork) → screen
```

- **Templates** (`templates/*.glsl.tmpl`) hold all physics; `crtctl`
  injects a `#define` block (generated from `params.json`) at the
  `//@CRT_PARAMS@` marker and writes `~/.config/ghostty/shaders/`.
- **Hot loop**: knob turn → regenerate → D-Bus `reload-config` →
  A compatible host recompiles shaders when settings change. Feedback textures survive reload
  (fork guarantee), so persistence/burn-in state is not lost while
  adjusting knobs.
- **Shader-side state machine**: `iTime` never resets in the host renderer, so
  power/degauss events are signaled by *nonce* defines; the state pass
  stores the last-seen nonce in data pixels and restarts its sequence
  clock on change. First frame after load (blank history) is treated as
  a power-on — launching the terminal plays the warmup. The stored nonce
  lives in an RGBA16F texel, exact only up to 2048: past that the
  stored/live compare can never match and the sequence re-fires every
  frame — so the nonce params are bounded (nominal and hard max 2048; the
  bump wraps at the max, `crtctl` `_bump_nonce`).

### Data pixel protocol (state texture row 0)

| Pixel | R | G | B | A |
|---|---|---|---|---|
| (0,0) | seq clock (s since power event) | stored power nonce | stored degauss nonce | power state |
| (1,0) | warm clock (cathode thermal, s) | APL (IIR, τ=120 ms) | degauss clock | initialized flag |
| (2,0) *(DVST)* | erase clock (s since last erase) | stored erase nonce | stored↔live mismatch (IIR) | live ink coverage (256-probe fraction) |
| (5,0) *(DVST)* | write clock (s since the draw pass began) | — | — | — |

DVST P2.a (ink coverage) and P5.r (write clock) together drive the
progressive writing-beam sweep: `T_draw = (BASE + FULL·coverage)/write_rate`,
where `coverage` is the measured live ink fraction remapped to a 0..1 page
fullness (a full text page lights only ~5-15% of texels), so a full page
draws slower than a sparse one and content is revealed in top-to-bottom
scan order behind the advancing beam front. Display pass
reads these; never samples row 0 for content.

## Physics models and sources

Full research dossiers were compiled from: repairfaq.org (Goldwasser CRT
FAQs), EIA phosphor registrations (labguysworld / FH-Münster tables),
Randall & Wilkins 1945 (trap-emptying decay), Blur Busters CRT simulator,
libretro shader corpus (crt-geom, guest-advanced, Lottes, Megatron),
int10h monochrome guide, Sony Trinitron history, patents (spot killer
US5920339, degauss US6037716, AFC US3322894).

| Behavior | Model | Key numbers |
|---|---|---|
| Phosphor decay | Piecewise exponential, exact knee-crossing integration: τ_hi above knee, τ_lo tail below (approximates exp + power-law of sulfides) | P22R 1 ms (line emitter, no tail); P22G 0.4 ms + green tail (ZnS:Cu); P39 knee 0.25, tail 1.2 s; P4 "7% @ 33 ms" |
| P7 cascade | Blue layer beam-driven; yellow layer pumped by blue *light* → visible rise lag (τ≈120 ms), seconds-long tail | The one slow-rise phosphor |
| Gun/tone | Signal-domain brightness/contrast, gun gamma 2.35–2.55 relative to sRGB 2.2 | L ∝ V^γ, origin: triode drive |
| ABL | Drive compression above APL threshold via IIR-sensed average | full-white dims; sparse text doesn't |
| Beam spot | Gaussian scanline, σ grows with luminance (space charge), energy-normalized | crt-geom physics |
| Bandwidth | Horizontal Gaussian from TVL knob | composite ≈300, PVM ≈600–800 |
| Deconvergence | Per-channel weight-shifted taps, ~1.5× worse in corners | 0.2–2 px typical |
| Masks | Grille (continuous stripes + damper wires at 1/3 & 2/3), slot (staggered bricks), delta (hex-packed triads); output-pixel locked; zfast luminance-fade + gain compensation | mono phosphor ⇒ **no mask**, enforced at compile time and by preset test |
| Geometry | Quadratic warp: cylindrical (Trinitron, H-only) or spherical; radius in screen-heights (2–2.5 vintage, 3–5 FST) | pincushion/trapezoid/parallelogram/rotation pots |
| Power on (tube60s) | heater delay → undeflected dot → H opens (bright line) → V unfolds with sync roll-in and skew settle | dot only on scan-independent-HV designs — solid-state sets by construction cannot show it |
| Power on (ss80s) | degauss thunk (PTC decay τ≈0.45 s) + cathode fade-in + oversized raster settling | first light 5–20 s (scaled) |
| Power off | V collapse → bright line (energy concentration, phosphor-saturation capped) → dot → charge-bleed fade; modern era: spot killer = clean 120 ms fade | repairfaq tvcbspo |
| V-hold | Roll at beat frequency with AFC hesitation, VBI bar (7.5%) rides the seam, locks within ~±0.15 Hz | roll down = oscillator fast |
| H-hold | Per-line shear → venetian-blind diagonal tear + wrapping sync bar | AFC capture ±500 Hz |
| Hum bar | Dark band drifting up, period ≈8 s (59.94 vs 60 Hz beat) | 2–15% amplitude |
| HV breathing | Size ∝ 1/√V, sag ≈1 kV/mA → bright scenes grow/bloom | ≤1.5% healthy |
| Burn-in | Dose ∝ ∫luminance·dt (Coulomb aging), efficiency loss shows as darkening; stochastic rounding keeps sub-epsilon increments unbiased in fp16; optional pre-aged "vintage" ghost pattern | real: thousands of hours; knob compresses (documented) |
| Halation/diffusion | Wide desaturated ring + tight colored glow; golden-angle taps with per-pixel/per-frame phase jitter (sparse kernel integrates to a smooth halo instead of discrete ghost images around point sources) | faceplate internal reflection |
| White point | D65 identity (sRGB *is* codified P22) ↔ D93 Japanese consumer cold white | Trinitrons shipped cold |
| Glass | Transmission knob (0.27 dark / 0.42 std mono / ~0.65 color); contrast improves quadratically | emitted crosses once, ambient twice |
| Vector / XY | Random-scan class: beam mask from content (Sobel edge = outline, luma threshold = stroke) replaces the raster; pass-2 Gaussian core + wide golden-angle halo + endpoint/corner dwell dots; stroke-density feeds the APL slot → refresh-droop flicker; scanlines/interlace/sync/hum/retrace disabled, warp/glass/burn-in/collapse-to-dot kept; colour vector keeps shadow mask + deconvergence on the strokes | P4 white (Asteroids/Vectrex — *not* green), P31 scope, P22 shadow-mask colour (Tempest/Star Wars); woscope Gaussian beam profile; MAME vector bloom ≫ raster; DVG 16 intensity levels + dwell dots; slew-limited corners |
| DVST storage | Bistable P1-green willemite (Zn₂SiO₄:Mn, ~525 nm) storage mesh; written strokes latch forever at a fixed stored level, no decay; erase = full-screen green flash + collapse + lockout. **Progressive write**: the beam is a random-access vector store drawing point-to-point over time, so the page is laid down top-to-bottom (with a slight L→R tilt) behind an advancing front; `T_draw = (0.18 s + 2.30 s·page_fullness)/write_rate` (fullness = measured ink fraction / 0.09 full-page reference, clamped), i.e. a full page draws slower than a sparse one; freshly written strokes flash bright-white-green at the front and settle to stored (τ 180 ms) — the visible writing spot. Once the initial page finishes, latch is immediate (typing draws where you type). | Stored writing speed **1500–4000 vector-in/s** (Tek rating — *cm/ms*, not the cm/µs of variable-persistence scope tubes); dense full page **~1.8–5 s** ("several seconds for complex pictures"); erase pulse ~0.5 s real / lockout ~1 s (sim 0.75 s in-range). See research/dvst-writing-dossier.md |

## Honest approximations (the not-real list)

- **60 Hz panel**: true field-rate flicker and rolling-scan beam
  simulation need ≥120 Hz + frame queue (Blur Busters). The `flicker`
  param is a slow-beat cosmetic stand-in and is labeled as such.
- **Decay law**: the sulfide power-law tail is approximated by a second
  exponential below the knee (exact piecewise integration, but still an
  exponential). Constants tuned to the registered 10%-decay times.
- **Burn-in timescale** is compressed by `burnin_rate` (real damage
  takes thousands of hours); the dose→efficiency law is the real shape.
  Dose resets with the history texture (window resize / new window).
- **P7 yellow persistence** is perceptually compressed (τ 8 s vs real
  minutes) to stay useful on a terminal; scales with `persistence`.
- **Warmup times** default to 0.15× real (knob goes to 1.0 = real).
- **The tube is opaque** (alpha 1.0): `background-opacity` translucency
  is surrendered while the simulation is active — a CRT is not
  see-through. Disable custom shaders to get translucency back.
- Fork Metal path compiles but is untested (Linux project).
- **Plasma (pdp)** approximates subfield PWM artifacts with the cheap
  recipes from the research dossier (motion-gated posterization for
  false contouring, rotating ordered dither near black) rather than
  true bit-plane emission; phosphor lag, cell grid, black floor, and
  ABL follow the measured per-era numbers.
- **Temporal interlace and rolling scan** are validated on software GL
  (band geometry, comb structure, and duty-cycle photometry confirmed
  in screenshots); real >=120Hz hardware validation is still pending
  (protocol in ROADMAP.md).
- **Vector class — outline vs stroke**: a rasterised terminal frame carries
  no centre-line stroke information, and there is no honest way to recover
  true glyph skeletons in one pass with one feedback texture (thinning, JFA
  distance fields, and single-pass ridge detection all fail on moving
  content — see research/vector-rendering-dossier.md §2c/§3). So the beam
  path is *approximated*: `outline` mode uses the Sobel edge magnitude of the
  frame (robust for any font); `stroke` mode thresholds the luma (correct
  only for hairline fonts where the raster already IS the beam path). Both
  are labelled approximations, not recovered geometry.
- **Vector class — filled areas become outlines**: in outline mode a thick
  stem shows as two parallel strokes (they merge into one only when the stem
  is ≲2σ of the beam core, i.e. ~1px), and a filled block — the block
  cursor, `█`, powerline glyphs, a selection highlight — becomes an *outlined
  rectangle*. This is exactly what a real raster→display-list converter would
  do (a vector tube cannot fill an area), but it is stated plainly: the block
  cursor renders as a hollow box, and HiDPI doubles every stem into a clearly
  resolved double line (the Star-Wars-arcade-lettering look).
- **Vector refresh droop (`vector_flicker`)**: the mapping *stroke density ==
  average beam current == display-list length* into the APL sense line is
  physically correct (a busy vector screen really does draw more current and
  refresh slower). The resulting on-screen flicker, however, is the same
  slow-beat cosmetic stand-in class as the raster `flicker` knob — a 60Hz
  panel cannot reproduce true sub-60Hz field flicker — and is labelled as
  such. Lunar Lander's 41Hz beat is suggested, not reproduced.
- **DVST progressive write — scan order, not true vector order**: a real
  DVST draws the display list in the host's send order (arbitrary vectors,
  point-to-point). A rasterised terminal frame carries no draw order, so the
  reveal order is *approximated* as a top-to-bottom sweep with a slight
  left-to-right tilt (reading/writing order). The **timing law is honest in
  shape**: draw time scales with how full the page is, so a full page really
  does take longer than a sparse one, on the order of the real seconds. Three
  knowingly-approximated parts: (1) the reveal *order* (raster scan, not the
  host's vector sequence); (2) "how full" is the measured 256-probe ink
  fraction remapped to 0..1 against a fixed full-page reference (~0.09, since a
  full text page lights only ~5-15% of texels), not a true per-glyph
  stroke-length integral; (3) the absolute duration is scaled by the
  `dvst_write_rate` knob (1.0 ≈ real-ish: a full text page ~1.5 s, a solid
  graphic fill nearer the ~2.5 s cap, a sparse page a fraction of a second —
  matching the literature; the knob exists because the "real" number itself
  ranged from sub-second to ~12 s depending on beam vs comm-link limiting). The stored image, once written, is the unchanged
  bistable crisp green — progressive write only governs *how it appears*, never
  the final latched result, and the auto-erase detector is untouched.
- **DVST erase flash is shortened**: the sim's 12 ms page-flash vs the
  real ~0.5 s positive-erase pulse is a legibility choice (a half-second
  full-screen green flash on a terminal is jarring); the ~0.75 s lockout
  that follows is within the documented ~1 s.
- **what-if-crts-won-2026 is fiction** — a physics-plausible
  extrapolation, the only preset not modeled on real hardware, and it
  says so on the label.

## File layout

```
crt/
├── DESIGN.md            this document
├── params.json          single source of truth for all parameters
├── templates/           physics (do not edit generated shaders)
│   ├── phosphor-state.glsl.tmpl
│   └── crt-display.glsl.tmpl
├── presets/*.json       tube personalities (validated by tests)
├── tools/crtctl         the CLI + `panel` dispatch (README.md beside it)
├── tools/monoscope/     MONOSCOPE — the demoscene control surface (own README.md)
├── tests/
│   ├── test_presets.py        preset ↔ params.json validation
│   ├── test_crtctl.py         control tool unit tests
│   ├── test_monoscope.py      panel: headless (views as total frames, update logic)
│   ├── test_monoscope_pty.py  panel: real-pty proofs (hygiene, reload, bank)
│   ├── test_shader_compile.sh glslang+spirv-cross matrix (52 variants)
│   ├── feedback_proof.glsl    fork feedback proof shader
│   ├── test_feedback_runtime.sh   headless proof: iChannel1 persists
│   └── test_stack_runtime.sh      headless proof: full stack + tube-era
│                                  power-on choreography (burst-sampled)
└── state.json           current knob state (generated; gitignored)
```

## Requirements & deployment

The phosphor-state pass samples its own prior frame through `iChannel1`. A host must provide a floating-point feedback texture to support persistence, burn-in, and the shader-side state machine. The supplied exporters target WebGL2, RetroArch Slang, ReShade, and Metal; actual support depends on host capabilities. `tools/crtctl` currently includes integration-specific reload controls and is optional for other hosts.

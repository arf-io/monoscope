# Vector display class for ghostcrtty — rendering design dossier

Compiled 2026-07-16 for the vector CRT class (companion to
[vector-hardware-dossier.md](vector-hardware-dossier.md)). This is the
"how do we make terminal text look stroke-drawn" half; the hardware dossier
is the "what did the real machines do" half.

## 0. Verdict up front

A convincing "vector monitor" display class is achievable inside the
existing two-pass + one-feedback-texture architecture, with zero new host
capabilities and no transpile-target breakage. The honest shape of it:

- **The beam-physics layer (glow, endpoint dwell, phosphor trails,
  list-length flicker, no raster) is the easy 80%** — the codebase already
  has almost every ingredient (per-phosphor decay engine, APL IIR, warp
  geometry, a proven "different display class" carve-out in the DVST path
  of crt-display.glsl.tmpl).
- **True centerline stroke text from arbitrary rasterized glyphs is not
  honestly achievable** in 1–2 passes with one feedback texture. Outline
  (edge) mode is robust but shows double-lines on thick glyphs — quantified
  in §3.
- **The killer combo**: genuine single-stroke TTFs do not render correctly
  in FreeType-backed terminals, but *hairline-weight monospace outline
  fonts* (Iosevka Thin et al., all OFL) rasterize with 1–1.5 px stems at
  terminal sizes — at that width the raster effectively *is* the beam path
  and edge extraction degenerates into a single stroke. Preset-carried
  font overrides already exist (`TERMINAL_KEYS` in tools/crtctl); they
  need one new key (`font-style`).

## 1. What the codebase already provides (fit assessment)

| Need | Already present |
|---|---|
| Per-pass feedback for phosphor trails | Pass 1 self-feedback RGBA16F, exact piecewise-exponential decay |
| Vector-era phosphors | P31 (Vectrex-folklore/Tek scopes), P4 (the real arcade mono phosphor), P22 (Tempest/Star Wars color), P7, P11 — already in the decay tables. P15 (ZnO:Zn flying-spot, ~µs decay — sub-frame at 60 fps, i.e. "renders as zero persistence") is a trivial optional addition |
| Scene-complexity measure for flicker | APL IIR at data pixel P1.g (measureAPL, τ=120 ms) |
| "Different display class" precedent | CRT_DVST carve-out skips scanlines/mask/sync entirely in both passes — vector mode is structurally a sibling |
| Deflection geometry | warpToContent() — vector monitors had *worse* pincushion than raster (the Vectrex's is famous); keep it |
| Preset → terminal font override | presets carry `"terminal": {"font-family", "font-size"}`, applied by crtctl on preset apply |
| Transpile model | slang/WebGL2 transpilers bake structural params as #defines; a CRT_VECTOR_MODE enum used only in #if is exactly what they already handle (transpile_slang.py structural_keys) |

Free channel budget in vector mode (mono): R = beam excitation, **G =
dwell/endpoint energy (new)**, B = unused/scratch, A = burn-in. No
data-pixel protocol changes required.

## 2. Prior art survey

### 2a. Geometry-fed beam simulators (define the target look; not directly applicable)
- **woscope** (m1el) — the canonical writeup:
  https://m1el.github.io/woscope-how/ + https://github.com/m1el/woscope.
  Beam = Gaussian spot; pixel intensity = analytic integral of the Gaussian
  along the segment (erf-difference form), σ = beamsize/4, additive
  blending, saturation pushed toward white. Transferable facts: the line
  profile is a Gaussian in perpendicular distance, joints add correctly
  without seams, and **slow beam = bright, fast beam = dim**.
- **Nick Tasios, Simulating an XY oscilloscope on the GPU**
  (http://nicktasios.nl/posts/simulating-an-xy-oscilloscope-on-the-gpu.html)
  — same erf beam + phosphor afterglow as a feedback FBO multiplied by
  exp(−λ·Δt) each frame — literally the architecture ghostcrtty already
  has, with a cruder decay law than ours.
- Shadertoy XY-scope family (XttSzf, ttfyRM), XYScope for Processing
  (https://teddavis.org/xyscope/). All consume waveform/geometry inputs;
  none convert raster content. Their value is the **look**: thin brilliant
  core, wide soft halo, additive saturation to white, trails.
- **Trammell Hudson's V.st** (https://trmm.net/Category:Vector_display/) —
  real-hardware ground truth for strokes, endpoint dots, intensity ramps.

### 2b. Emulator practice
- **MAME**: HLSL docs (https://docs.mamedev.org/advanced/hlsl.html),
  ini/presets/vector.ini, hlsl/vector.fx. Knobs: `beam_width_min/max`
  (brightness-dependent beam width — same physics as our scan_bloom),
  `beam_intensity_weight`, `beam_dot_size` (**explicit endpoint-dot
  fake**), `vector_length_scale/ratio` (per-segment attenuation),
  `flicker`, phosphor ghosting; bloom levels set much higher for vector
  than raster. Load-bearing note: **"shadowmasks were only present on
  color vector games, and should not be used on monochrome vector games"**
  — mono vector must force mask none (existing enforcement), color vector
  legitimately keeps the mask.
- **e-basteln Asteroids monitor pages** + Computer Archeology's DVG doc:
  the DVG draws a display list of lines with 16 intensity levels; dots are
  drawn by *dwelling*; long lists → dropped refresh → flicker. Asteroids
  tubes are the canonical burn-in victims.
- Star Wars' outline lettering look: "arcadefont"
  (https://coolbutuseless.github.io/2020/05/04/introducing-arcadefont-...).

### 2c. Raster → stroke-look purely in fragment shaders
- **Edge → glow**: abundant, trivial, proven (Sobel + neon glow is a
  Shadertoy staple). One 3×3 neighborhood (8 extra taps) in pass 1. The
  only approach with deep, battle-tested prior art.
- **Skeletonization in-shader**: essentially no real-time prior art for
  *moving* content. Classical thinning removes one boundary layer per
  iteration → a w-px stem needs ~w/2 sequential passes. With one feedback
  texture you get one erosion step per frame: static text converges in 1–3
  frames, but every keystroke/scroll restarts convergence → strokes
  visibly pulse fat→thin. Also fights the feedback texture's primary job.
- **JFA distance fields** (Rong & Tan 2006): needs log₂(N) passes with
  specific step schedules — structurally incompatible with one pass per
  frame except as temporal amortization, which moving content breaks
  worse. **Rejected.**
- **Single-pass ridge detection** (the respectable centerline option):
  Steger-style curvilinear detection / Hessian-of-Gaussian ridge filters
  (Steger PAMI 1998; Frangi vesselness). 25–49 taps, one pass, no feedback
  needed; centerline = negative principal curvature + near-zero gradient.
  Works for stroke widths ≲ 2σ of the matched kernel; fails at junctions
  and where stroke width varies. Stage-3 experiment, not the product.

**60 fps feasibility**: pass-1 additions are 8 taps (Sobel) to ~49 taps
(ridge) at window resolution; pass-2 glow ~24–40 taps (glassGlow already
does 24). Trivial for real GPUs; llvmpipe will hurt at the ridge end —
keep Sobel as the default path.

## 3. The honest tradeoff space

### (a) Outline mode — glyph edges as the beam path
Sobel/DoG gradient magnitude on the linearized terminal frame → beam mask
→ beam physics. Robust, stateless, cheap, stable under motion.

**The double-line truth, quantified.** An edge detector puts strokes on
*both sides* of a stem of width w px. Two parallel Gaussians merge into a
single-peaked profile when separation ≲ 2σ. With a period-plausible beam
core σ ≈ 0.7–0.9 px:

| Glyph stem width | Where you see it | Result |
|---|---|---|
| 1 px | Regular mono at ~12–14 px, 1× DPI; any Thin font | Edges collapse — reads as a **single stroke** |
| 2 px | Regular mono at 16–21 px, 1× DPI | Merged single fat bright stroke; slightly inflated letterforms |
| 3–5 px | **Any HiDPI/2×**, bold, ≥24 px | Clearly resolved **double lines — outlined letterforms** (Star Wars-arcade-lettering look; period-authentic for vector *lettering*, wrong for "pen-stroke" text) |
| Filled areas (block cursor, `█`, powerline glyphs, selection highlights) | everywhere | **Outlined rectangles**. Actually what a real raster→display-list converter would do (vector monitors cannot fill), but must be stated |

HiDPI is the biggest gotcha: Ghostty renders at device pixels, so Retina
doubles every stem.

### (b) Centerline/skeleton mode
See §2c. Neither variant yields dependable glyph skeletons for arbitrary
fonts. Ship only as an experiment flag; never as the default.

### (c) Font cooperation — the recommended primary path
If the rasterized glyphs are already ~1 px strokes, the terminal frame IS
the beam path: threshold the luma (plus a light 3×3 max to bridge AA) and
hand it to the beam-physics layer. Endpoints really exist, dwell dots land
at real stroke ends.

**Font findings (verified real and downloadable):**

*True single-line fonts — mostly unusable in a terminal:* FreeType
requires filled closed contours; genuine single-line TTFs "are not
rendered properly by most graphics tools" (golanlevin/
p5-single-line-font-resources); Relief SingleLine renders as "triangular
surfaces" outside CAD. Hershey-Noailles (luuse.io, OFL 1.1, 31 styles) is
hairline closed outlines but NOT monospace — one experimental preset at
most. Monospace single-line fonts exist only in non-installable formats
(Consolines SVG, HP1345A/Tektronix 7000/Asteroids ROM SVG conversions,
KST32B, M+ Stroke) — great *reference*, unusable as terminal fonts.
CNC "stick fonts" (open-contour TTF): FreeType auto-closes → blobs.

*The practical answer — hairline-weight monospace outline fonts (all SIL
OFL, all render perfectly in Ghostty):*
- **Iosevka** (https://github.com/be5invis/Iosevka) — Thin (100) weight;
  Iosevka Term/Fixed purpose-built for terminals; buildable thinner via
  build plans. **First choice.**
- JetBrains Mono Thin, IBM Plex Mono Thin, Victor Mono Thin (all wght 100).
- At font-size 18–21 these rasterize ~1–1.5 px stems at 1× and ~2 px at 2×
  HiDPI — inside or near the merge regime at both densities. (Stem widths
  depend on hinting/DPI; verify with a screenshot during implementation.)

*Plumbing:* Ghostty supports `font-style = "Thin"` and
`font-variation = wght=100` (https://ghostty.org/docs/config/reference).
crtctl's TERMINAL_KEYS needs `font-style` (and optionally
`font-variation`) — small, contained change + preset validation updates.

## 4. Beam-physics layer (applies to any of a/b/c)

All extraction happens in **pass 1, in unwarped content space** (warp is a
pass-2 sampling concern — strokes stay geometrically stable under
warpToContent for free, exactly like DVST traces today).

**Pass 1 (state)** — vector branch:
1. Beam mask B(uv): Sobel magnitude (outline), thresholded luma (stroke),
   or ridge response (experimental). Modulate by content luma →
   per-stroke intensity levels (the DVG's 16 levels come free from font
   colors: dim comments, bright bold — a genuinely nice emergent property).
2. Endpoint/corner dwell: sample the mask on an 8-point ring (r ≈ 1.5–2
   px); lit-arm count 1 = endpoint, 2 adjacent arms = corner → write dwell
   energy into G with slightly longer effective decay. Reproduces MAME's
   beam_dot_size / DVG dwell dots physically enough. Fires meaningfully
   only when strokes are single lines (mode c, or thin stems in mode a) —
   closed outlines have no endpoints; corner detection covers mode a.
3. Excitation: newState.r = max(beamDrive, decayedHistory) through the
   existing decay engine — P4 for Asteroids white (per hardware dossier;
   P31 only for scope presets), P22 for color vector. Optional new p15
   enum entry (τ_hi ~3 µs → decays within one frame; honest and cheap).
4. Display-list length: redefine the APL measurement in vector mode to
   sample the beam mask (mean stroke density). Physically correct: on a
   vector monitor, average beam current IS stroke density. One IIR drives
   three consumers: ABL compression, HV-breathing bloom, and refresh
   droop → flicker (list longer than budget → simulated refresh below
   ~45 Hz → flicker amplitude rises). On a 60 Hz panel this is a
   beat-frequency cosmetic stand-in, same honesty-ledger entry as the
   existing flicker param. (A real ≥120 Hz mode could later gate beam
   injection at the simulated refresh phase via the P4 estHz machinery.)

**Pass 2 (display)** — vector carve-out, structurally parallel to CRT_DVST:
- Gaussian core (σ ≈ 0.6–0.9 px, 4–5-tap cross like the DVST spot) + wide
  halo (golden-angle taps, gain 3–10× a raster tube's halation — per
  MAME's vector bloom guidance) + additive saturation to white at high
  excitation (existing mono overdrive-whitening does this).
- Dwell dots: render G as bright saturated points with their own halo.
- **Disabled: scanlines, interlace, rolling scan, retrace lines, hum bar,
  V-hold/H-hold** (no timebase raster — sync errors are meaningless),
  smooth-scroll glide. Mask: forced off for mono, allowed for color vector
  presets (WG6100 shadow mask on strokes, delta type, modest strength).
  Deconvergence: color vector only.
- **Kept: warp geometry** (crank pincushion/spherical for Vectrex),
  bezel/corner/glass, burn-in (Asteroids ghosts!), power choreography
  (power-off collapse-to-dot is MORE authentic on a vector monitor — the
  spot killer existed precisely because of it), EMI wobble, degauss
  (color only).
- AA/stability under warp: bilinear on RGBA16F plus σ ≥ ~0.7 px core keeps
  1-px strokes from shimmering during scroll; the DVST path proves the
  sampling pattern.

## 5. What to avoid (and transpile constraints)

- No CPU-side geometry, no glyph metadata, no extra ping-pong passes.
- JFA/multi-step schedules: rejected.
- Every new toggle a **structural #define** (CRT_VECTOR_MODE enum {off,
  outline, stroke, ridge}) used only in #if — both transpilers handle it
  like CRT_DVST/CRT_PDP today. Numeric knobs (beam_core, beam_halo,
  halo_gain, dot_gain, edge_threshold, vector_budget, flicker mapping) as
  plain float params → free RetroArch sliders.
- WebGL2/slang gotchas already navigated: const globals must stay
  constant-expressions; constant loop bounds; ring/Sobel/glow taps are
  plain texture() with constant offsets — safe.
- Don't overload P1.g if content-APL is still consumed in vector mode —
  cleanest is measuring stroke density into the same slot in vector mode
  only (single consumer set, documented).

## 6. Staged implementation plan

**Stage 1 — outline beam mask + beam physics + presets (the product
core).** CRT_VECTOR_MODE structural enum; pass-1 Sobel mask + intensity +
corner/endpoint ring detect into G; vector-APL; pass-2 vector carve-out;
~8 new params (new `vector` group); presets: vectrex-1982 (white
P4-family, 9", heavy pincushion, 50 Hz), asteroids-dvg-1979 (P4, strong
dwell dots, high burn-in, 61.5 Hz), lunar-lander-1979 (41 Hz flicker),
tempest-wg6100-1981 and starwars-amplifone-1983 (P22 color + delta mask
on strokes, HV-sag bloom); preset/compile/runtime tests mirroring the
DVST ones. Effort: ~3–5 focused sessions. Risk: low — single-pass, proven
techniques; the visual risk is the §3 double-line reality on HiDPI, which
stage 2 fixes. DESIGN.md honesty-ledger entries: outline-vs-stroke,
flicker-as-beat, filled-areas-become-outlines.

**Stage 2 — single-stroke-look font presets (the killer combo).** Add
font-style (and optionally font-variation) to crtctl TERMINAL_KEYS +
validation + tests; ship font-cooperating preset variants (e.g.
vectrex-1982 carrying Iosevka Term Thin 20); switch those presets' mask
source to thresholded-luma (stroke mode) so dwell dots fire at true
stroke ends; document font install (OFL permits bundling with license
text). Effort: 1–2 sessions. Risks: stem-width-vs-DPI needs eyes-on
verification per platform; presets should degrade gracefully to outline
mode when the font is absent (crtctl can warn; the shader can't know).

**Stage 3 — centerline experiments (optional, flagged, honest).** ridge
mode (single-pass Hessian 5×5) behind the enum; possibly a
feedback-amortized thinning toy in channel B. Expected outcome:
"interesting, not shippable as default" — say so in DESIGN.md. Kill
criterion: junction dropouts breaking common glyphs (m, w, k) at preset
font sizes.

## Sources

woscope (https://m1el.github.io/woscope-how/ +
https://github.com/m1el/woscope); Tasios
(http://nicktasios.nl/posts/simulating-an-xy-oscilloscope-on-the-gpu.html);
Shadertoy XttSzf, ttfyRM, Mdf3zr, 4ss3Dr; XYScope
(https://teddavis.org/xyscope/); MAME HLSL docs + vector.ini + vector.fx
(github.com/mamedev/mame); e-basteln
(https://www.e-basteln.de/arcade/asteroids/monitor/); Computer Archeology
DVG (https://www.computerarcheology.com/Arcade/Asteroids/DVG.html);
Trammell Hudson (https://trmm.net/Category:Vector_display/); Wikipedia
Vector monitor / Vectrex; Amplifone (quarterarcade.com); arcadefont
(coolbutuseless.github.io); Rong & Tan JFA
(https://www.comp.nus.edu.sg/~tants/jfa/i3d06.pdf); HIPR2 thinning
(https://homepages.inf.ed.ac.uk/rbf/HIPR2/thin.htm); fonts:
golanlevin/p5-single-line-font-resources, isdat-type/Relief-SingleLine,
Hershey-Noailles (gitlab.com/Luuse), be5invis/Iosevka, Hershey Text
(evilmadscientist.com); Ghostty config reference
(https://ghostty.org/docs/config/reference); LabGuy's World phosphor data
(http://www.labguysworld.com/crt_phosphor_research.pdf).

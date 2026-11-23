# OPTICS ON A TUBE — a field guide to the glow around bright things

Every bright object on a CRT is dressed in light that did not come
straight from its phosphor dot to your eye. Glass scatters it, the beam
smears it, the electron optics misplace it, the chemistry remembers it,
and the screen itself slowly wears it in. This tutorial walks through
each of those effects: the real physics, the exact implementation in this repository
to model it (file, function, and the actual constants — checked against
the templates at writing time), the knob that controls it, and a lab to
isolate each one.

You are reading it through the pipeline it describes. Every figure below
is monospace text scanned by the simulated beam, so the figures exhibit
the effects they explain: the box-drawing lines bloom, their edges
fringe, and on the long-persistence presets they smear when you scroll.

A note on names: shader constants are `CRT_*` defines; the knob names in
`params.json` (what `crtctl set` takes) are lowercase. Both are given.
Model files: `templates/phosphor-state.glsl.tmpl` (pass 1: excitation,
decay, burn-in dose) and `templates/crt-display.glsl.tmpl` (pass 2:
beam, glass, mask). Constants quoted here were read from those files
fresh, not from memory.

---

## 1 · Case study: the ghost cursors of zenith-chromacolor-1971

The report: running the `zenith-chromacolor-1971` preset, the cursor
grows a constellation of faint copies of itself — beside it, above and
below it on diagonals, a couple of characters out. Not a smooth glow: a
series of distinct ghost cursors.

That observation was accurate, and it has two layers: the physics that
says there SHOULD be a halo there, and a sampling artifact that showed
the halo's skeleton instead of the halo. Both are documented here,
because the second one is how the simulation actually produced the
pixels on that screen (section 8 has the full confession and the fix
that now ships).

### 1.1 The physics: light trapped in the faceplate

A phosphor grain does not emit a ray at your eye; it emits into the
whole hemisphere, into glass with refractive index n ≈ 1.52. Snell's law
only lets light out of the outer surface if it arrives within the
critical angle:

    θc = asin(1/n) = asin(1/1.52) ≈ 41.1°

Everything steeper is totally internally reflected — the outer surface
of the faceplate is a perfect mirror for it. For a Lambertian emitter
only about 1/n² ≈ 43% of the light falls inside that escape cone; the
majority is trapped in the glass. A trapped ray crosses the faceplate
thickness t, mirrors off the outer surface, crosses back, and lands on
the phosphor/aluminization layer at a lateral distance 2·t·tanθ from
where it started — at minimum 2·t·tan 41.1° ≈ 1.75·t. There it
scatters; part of it re-escapes toward you, part hops outward again.

```
                            C · light steeper than 41.1° is trapped,
                            bounces once, lands 2·t·tanθ out, scatters
                            off the backing, and re-escapes here:
                            THE HALATION RING
            A · under 41.1°: refracts out
            (the direct image you see)
            ▲             ▲
            ┆             ┆
  ══════════╪══════╳══════╪═══════════════════════  OUTER SURFACE
            ┆     ╱ ╲     ┆    faceplate glass       (glass → air)
            ┆    ╱   ╲    ┆    n ≈ 1.52
            ┆   ╱ θ   ╲   ┆    thickness t ≈ 10 mm
            ┆  ╱       ╲  ┆    beyond θc the outer
            ┆ ╱         ╲ ┆    face is a perfect
            ┆╱           ╲┆    mirror (TIR)
  ══════════●═════════════●┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  PHOSPHOR GRAINS +
            P             L                         ALUMINIZED BACKING
            ├─ 2·t·tanθ ──┤
            emitting      lands ≥ 1.75·t from P;
            grain         scatter sends light back up (C)
                          and onward (rings #2, #3 … fainter)
```

FIG 1 · Faceplate cross-section. Ray A (under the critical angle)
refracts out and forms the image. Ray B (the ╱╲ path, θ > θc) is
trapped, hops 2·t·tanθ sideways, and re-emerges at L as ring light C.
Every trapped angle θ > 41.1° contributes, so the re-emergence is an
annulus starting at radius 1.75·t, with fainter concentric repeats from
multiple hops. This is halation, and it is documented hardware pain:
anti-halation faceplate patents US4633131 and US4884006 exist precisely
because of this ring (see `research/vector-hardware-dossier.md`, which
puts the first-ring radius at ≈1.75× glass thickness; the energy in the
ring is undocumented and remains this simulation's free parameter).

Scale check: a 21-inch consumer faceplate is roughly 10 mm thick, so
the first ring lands ~17 mm out — at terminal metrics, about two
character cells. "A couple of characters out" is exactly where the
physics puts the halation annulus. The observation matched the optics;
what it didn't match was a continuum. Twelve discrete ghosts is not an
optical phenomenon — it's a sampling one. Hold that thought for §8.

### 1.2 Why the cursor, of all things

The cursor is the perfect halation witness: it is small, isolated,
bright, and sits on dark background. On this fork it is often the
brightest thing on screen: pass 1 (`phosphor-state.glsl.tmpl`, cursor
strike overdrive) multiplies the drive inside a freshly moved cursor
cell by `1.0 + CRT_CURSOR_OVERDRIVE * exp(-age / 0.04)` for the first
0.25 s — with the default `cursor_overdrive = 0.7`, a 1.7× flash at
strike. The brighter and lonelier the source, the more visible the
skeleton of whatever kernel spreads its light.

---

## 2 · The glow zoo: six effects, one diagnostic table

Six different mechanisms put light (or darkness) where the content
didn't ask for it. They look superficially similar — "stuff around
bright stuff" — but each has a distinct signature, and you can learn to
read them apart at a glance:

| Effect | Shape and size | Color signature | Time behavior | Knobs (params.json) |
| --- | --- | --- | --- | --- |
| Halation | wide, ring-biased halo; inner radius ~1.1% of screen height, outer ~5.4% | desaturated — washed toward gray | static; tracks content instantly | `halation` |
| Diffusion | tight sheath hugging each stroke, ≤ ~1.2% of screen height | fully colored — the phosphor's own hue | static; tracks content instantly | `diffusion` |
| Deconvergence | directional fringes on vertical edges, ~1-2 px, worse in corners | red on one side, blue on the other | static; fixed offset | `misconvergence` |
| Bloom | bright scanlines fatten vertically and fill their gaps | same color, never brighter (energy-conserving) | instant, brightness-dependent | `scan_bloom`, `scan_min_width`, `focus` |
| Persistence | trails behind anything that moves or vanishes | tail drifts green/yellow on color tubes | temporal — decays over ms…s, moves WITH content | `persistence`, `trail_tint` |
| Burn-in | dark ghost etched where bright content LIVED | darkening, not glow | permanent-ish; fixed to the TUBE, not the content | `burnin_rate`, `burnin_visibility`, `burnin_vintage` |

The two hardest to distinguish in the wild: persistence trails move with
(actually: behind) the content and fade in real time; burn-in ghosts
stay put when you scroll, because they are damage to the screen, not
light in the image. If the ghost scrolls with the page, it's phosphor
chemistry. If it stays while the page moves, it's history.

---

## 3 · Halation, the model

Reality: the annular re-emergence of §1.1, plus multiple scatter (a ray
can hop several times, and scattered light re-enters the glass and hops
again). Multiple scatter mixes the three phosphor colors together and
spreads across triads, which is why real halation reads DESATURATED —
a grayish fog ring, not a colored one.

The model, `glassGlow()` in `templates/crt-display.glsl.tmpl`: the lit
phosphor (the pass-1 state texture) is averaged through a 12-tap disc
kernel at two scales and added back on top of the beam-sampled image:

- Kernel: 12 taps on a Vogel (golden-angle) spiral — tap i sits at
  angle `i * 2.39996` rad and radius `sqrt((i + 0.5) / 12)` of the
  kernel radius. The innermost tap is at 0.204 of the kernel radius,
  the outermost at 0.979 — so the kernel is genuinely ANNULAR: it has
  a hole in the middle, matching the ring physics.
- Halation scale: kernel radius `0.055 * res.y` — taps land between
  1.1% and 5.4% of screen height from the source.
- Desaturation: the wide average is mixed 60% toward its own luma
  (`mix(wide, vec3(wLum), 0.6)`) — the multiple-scatter gray.
- Contribution: `halo * CRT_HALATION`. The knob `halation` runs
  0-0.2 (default 0.06); `zenith-chromacolor-1971` ships 0.09 — the
  1971 black-matrix tube was BRIGHT, and bright tubes fog their glass.

What the model honestly is not: it does not trace rays through glass,
and the ring's energy fraction is a tuned constant, because no patent
or paper documents it (the dossier marks it "undocumented"). It is a
physically shaped kernel, not physical transport.

> TRY IT · THIS PAGE — switch PRESET to `zenith-chromacolor-1971` (the
> case-study tube) and look at the box-drawing figures: the wide gray
> fog around them is the halation term. Then reload with
> `?preset=zenith-chromacolor-1971&set=CRT_HALATION:0.2,CRT_DIFFUSION:0.0`
> in the URL to see halation alone at maximum, or `CRT_HALATION:0.0`
> to amputate it.

---

## 4 · Diffusion (GLASS GLOW), the model

Reality: before any of the ring drama, light is scattered at very short
range — by the phosphor grains themselves (they are a powder, not a
mirror), by the first glass surface, by the slight cloudiness of the
faceplate. This is a tight, single-scatter effect: it keeps the color
of the stroke that produced it. It is the difference between a glyph
that looks EMITTED and one that looks printed.

The model: the same 12-tap spiral in `glassGlow()`, second sampling at
kernel radius `0.012 * res.y` (taps between 0.24% and 1.17% of screen
height), NOT desaturated, contributed as `tight * CRT_DIFFUSION`. Knob
`diffusion`, range 0-0.3, default 0.08. A tidy detail: the tight
kernel's outer edge (1.17% H) meets the wide kernel's inner hole
(1.12% H) almost exactly — together they tile a continuous glow field
from 0.2% to 5.4% of screen height, colored at the center, gray fog
outside.

Telling it from halation: diffusion hugs the stroke and is colored;
halation stands off from it and is gray. Kill each in turn and compare:

> TRY IT · THIS PAGE — `?set=CRT_HALATION:0.0,CRT_DIFFUSION:0.3` (all
> sheath, no fog), then `?set=CRT_HALATION:0.2,CRT_DIFFUSION:0.0` (all
> fog, no sheath). The defaults for this page's default tube
> (`smartdark-creme`) are halation 0.035, diffusion 0.05.

---

## 5 · Deconvergence: the fringes that aren't glow

Reality: a color CRT has three electron guns that must land on the same
triad after being bent through the same yoke. They never perfectly do —
the residual landing error (misconvergence) puts the red and blue
images a fraction of a millimeter off the green one, and dynamic
convergence correction loses authority toward the corners, so the error
roughly doubles there. The result is not scatter at all, but it lives
in the same "why is this edge dirty" perceptual bucket: colored fringes
on contrast edges.

```
    content: one white stroke        painted (misconvergence = 1.4 px):

              ██                              B██R
              ██                              B██R
              ██              ───►            B██R
              ██                              B██R
              ██                              B██R
                                          blue┘  └red
                                        fringe      fringe
```

FIG 2 · Static R/B landing error. Red lands shifted one way, blue
mirrored the other; the white core stays where green is. On the real
delta-gun Zenith this was a point of pride for the era — and still
1-2 mm at the corners.

The model, `scanSample()` in `crt-display.glsl.tmpl`: the horizontal
gaussian filter is evaluated with per-channel shifted weights —
`convPx = CRT_MISCONVERGENCE * cornerSoft`, red weighted by
`exp(-0.5 * ((dx + convPx) / sigmaX)^2)` and blue by the mirror
`(dx - convPx)` — so the red image lands displaced +convPx pixels and
blue -convPx, folded into the same energy-normalized filter (no double
sampling). `cornerSoft = 1.0 + 0.5 * smoothstep(0.55, 1.25, rEdge)`
scales it up to 1.5× at the tube corners, and softens focus the same
way (off-axis astigmatism — the model is horizontal-only; vertical
misconvergence is not simulated). Knob `misconvergence`, 0-2 px,
default 0.3; `zenith-chromacolor-1971` ships 1.4, `trinitron-pvm` 0.15
(in-line guns), `wornout-office` 1.5.

How to tell it from everything else: it is DIRECTIONAL (left edge one
color, right edge the other), it does not extend beyond a couple of
pixels, and it never moves or decays.

> TRY IT · THIS PAGE — `?preset=trinitron-pvm&set=CRT_MISCONVERGENCE:2.0`
> then look at the ═ and │ rules: red/blue rails on opposite sides.
> Compare the corners of the screen against the center.

---

## 6 · Bloom: the beam getting fat

Reality: turn up the beam current and the spot grows — space-charge
repulsion inside the beam plus finite gun optics defocus the landing
spot as it gets hotter. Bright raster lines are visibly thicker than
dim ones; heavily driven text fills in the dark gap between scanlines.
Crucially, a wider spot is NOT extra light: the same electrons land
over more phosphor.

```
     dim row:      ·····▁▂▂▁·····      spot σ stays at SPOT SIZE
     bright row:   ··▂▄▆████▆▄▂··      σ grows with luminance —
                                       wider, gap-filling, and
                                       energy-normalized: never brighter
```

FIG 3 · Beam cross-sections. The gaussian profile IS the raster; the
gap between passes is dark because no beam went there.

The model, `scanSample()`: per scanline the vertical gaussian sigma is

    sigma = CRT_SCAN_MIN_WIDTH
          * (1.0 + CRT_SCAN_BLOOM * 1.4 * pow(lum, 0.62))
          * focusMul * cornerSoft

with `lum` the line's luma clamped to 1.5 (crt-geom lineage physics),
and the line weight divided by `sigma * 2.5066283` (σ·√2π) so the
integral is constant — blooming widens lines without brightening them.
Knobs: `scan_bloom` (0-1, default 0.55), `scan_min_width` (the σ floor
at black, in scanline heights, default 0.32), `focus` (global
multiplier; below 1.0 is sharper than electron optics allow).

Telling it from glow: bloom is a property of the LINES (vertical
fattening of the raster structure), not a skirt around shapes. It
appears the instant a row gets bright and vanishes with it.

> TRY IT · THIS PAGE — `?preset=bw-tv-p4&set=CRT_SCAN_BLOOM:1.0` vs
> `...:0.0`. Watch the headline rules and the status bar: at 1.0 the
> bright rows swell and their scanline gaps close; at 0.0 every row is
> uniformly thin (and looks wrong — LCD-flat).

---

## 7 · Persistence: trails, the memory of light

Reality: phosphorescence. After the beam leaves, a phosphor keeps
emitting: sulfide phosphors show a fast near-exponential drop followed
by a long power-law tail (Randall & Wilkins 1945). How long is
chemistry: P22-B&W-TV class decays in tens of milliseconds; the IBM
5151's P39 green takes on the order of a second (that is a feature:
flicker-free 50 Hz text); radar P7's yellow layer persists for many
seconds. On color tubes the deep tail is dominated by the
copper-activated green phosphor — old trails drift green-yellow.

The model, `decayPiecewise()` in `templates/phosphor-state.glsl.tmpl`:
excitation decays with time constant `tau_hi` above a knee level and
`tau_lo` below it, and the knee crossing is solved in closed form
inside the frame (`tKnee = tauHi * log(s / knee)`), so long or uneven
frame times integrate exactly instead of aliasing. Fresh beam energy
replaces decayed history via `max(drive, excited)`. Per-phosphor
constants (seconds), from the EIA registration data cited in the
template header:

| Phosphor (preset) | tau_hi | knee | tau_lo |
| --- | --- | --- | --- |
| P22 red gun (color presets) | 0.0010 | 0.10 | 0.003 |
| P22 green gun | 0.0004 | 0.10 | 0.045 × (0.5 + `trail_tint`) |
| P22 blue gun | 0.0003 | 0.08 | 0.012 |
| P39 (`ibm-5151-mda-1981`) | 0.040 | 0.25 | 1.20 |
| P134 amber (`vt-amber`) | 0.006 | 0.18 | 0.350 |
| P4 (`bw-tv-p4`) | 0.0124 | 0.07 | 0.080 |

The knob `persistence` (0-8, default 1.0) multiplies both taus: 1.0 is
the registration data, 0 disables decay (unphysical), 4× turns P39
into a radar hangover. `trail_tint` biases how green the color-tube
tail reads.

Telling it from everything else: persistence is the only TEMPORAL glow
— it exists only behind change. Static content has no trails. And
trails follow the content: scroll up, and the smear hangs below where
the text was.

> TRY IT · THIS PAGE — switch PRESET to `ibm-5151-mda-1981` and scroll
> with PgDn: the page smears exactly as a 5151 did, because this page
> IS content moving across a P39 feedback texture. Then try
> `?preset=ibm-5151-mda-1981&set=CRT_PERSISTENCE:4.0` for the
> exaggerated version. `vt-amber` gives the medium-tail amber feel.

---

## 8 · The sampling confession: twelve ghost cursors

Now the honest part. Sections 3-4 said "12-tap kernel" quickly; this
section slows down, because those 12 taps are exactly where the ghost
cursors came from.

`glassGlow()` GATHERS: for each output pixel it samples the lit
phosphor at 12 fixed offsets and averages. Equivalently (flip the
convolution around): every small bright source PAINTS a faint copy of
itself at each tap offset. A big lit area hides this — the shifted
copies overlap into a smooth wash. An isolated bright cursor does not:
you see the kernel itself, stamped 12 times around the cursor at radii
from 1.1% to 5.4% of screen height — beside, above and below on
diagonals, a couple of characters out. The kernel's skeleton.

The brightness math makes it worse than it sounds. Each wide tap
carries source/12 × `halation`; at the Zenith's 0.09 that is ~0.75% of
the cursor's luminance per ghost. Faint? No: the display encode is
`pow(x, 1/2.2)`, and 0.0075^(1/2.2) ≈ 0.11 — each ghost renders at
roughly 11% signal on a black background. Plainly visible, and flashing
1.7× brighter at every cursor strike (§1.2).

Why 12 taps at all? Real scatter is a continuum — the correct kernel
is an integral over the annulus. A shader approximates integrals with
samples, and 12 (at two scales, so 24 texture reads per pixel) is the
budget. The tap LAYOUT is a Vogel spiral — the sunflower pattern:

    angle_i  = i × 2.39996 rad            (the golden angle, ≈137.508°)
    radius_i = sqrt((i + 0.5) / 12)       (equal-area annuli)

The golden angle is the "most irrational" rotation: successive taps
never stack up in an angular pattern, so 12 of them cover the disc
about as uniformly as 12 points can. The sqrt spacing gives each tap
an equal share of disc area. It is the best fixed 12-tap kernel you
can build — and a fixed kernel is precisely the bug, because every
pixel, every frame, used the SAME 12 offsets. Coherent sampling error
does not look like noise; it looks like structure. Twelve structures.

### 8.1 The fix that ships: per-pixel, per-frame phase

The template now rotates the whole constellation by a hash of the
pixel coordinate AND the frame time. This is the actual shipped code
in `glassGlow()` (`templates/crt-display.glsl.tmpl`):

```
const int N = 12;
// Rotate the whole tap constellation per pixel and per frame.
// Real scatter is a continuum; with a fixed 12-tap kernel a small
// isolated source (the cursor) reads as 12 discrete ghost copies.
// Jittering the spiral's phase decorrelates neighboring pixels and
// successive frames, so the same 12 taps integrate — spatially and
// in the eye — into the smooth annular halo the physics predicts.
float rot = hash12(cuv * res + vec2(fract(iTime * 13.0) * 289.0,
                                    fract(iTime * 7.0) * 331.0))
            * 6.2831853;
for (int i = 0; i < N; i++) {
    float a = float(i) * 2.39996 + rot; // golden angle + jitter phase
    float r = sqrt((float(i) + 0.5) / float(N));
    vec2 d = vec2(cos(a), sin(a)) * r;
    vec3 sT = contentAt(cuv + d * (0.012 * res.y) / res);
    vec3 sW = contentAt(cuv + d * (0.055 * res.y) / res);
    tight += sT;
    wide += sW;
}
```

Each pixel gets a private random rotation of the spiral, redrawn every
frame. One pixel still takes only 12 samples — but its neighbors take
a differently rotated 12, and next frame everyone rotates again. The
ghost energy that used to pile up at 12 coherent points is spread
around each tap's radius ring; adjacent rings blur together as soon as
the source is bigger than the ring spacing (a cursor block always is),
and the eye's own integration averages the residue over frames. The
same 24 reads per pixel now buy an annular halo instead of a
constellation:

```
┌─ FIXED PHASE (rot = 0) ─────────┐  ┌─ JITTERED PHASE (shipped) ──────┐
│                                 │  │                                 │
│          ▒                      │  │            ░░░░░░░░░            │
│                      ▒          │  │         ░░░░░░░░░░░░░░░         │
│                                 │  │       ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░       │
│               ▒                 │  │      ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░     │
│       ▒                         │  │    ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░   │
│                          ▒      │  │   ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░  │
│             ▒  █                │  │  ░▒▒▒▒▒▒▒▒▒▒▒▒▒▓█▓▒▒▒▒▒▒▒▒▒▒░  │
│                                 │  │   ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░   │
│   ▒               ▒             │  │    ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░    │
│           ▒                 ▒   │  │      ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░      │
│                                 │  │       ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░        │
│                                 │  │         ░░░░░░░░░░░░░          │
│                   ▒             │  │            ░░░░░░░             │
│           ▒                     │  │                                 │
│                                 │  │                                 │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

FIG 4 · The wide-kernel tap constellation around an isolated bright
source █ (left: what every pixel sampled before the jitter — 12
coherent ghost positions) versus the integrated result with per-pixel,
per-frame phase (right: the taps' radius rings blur into a smooth
halo; ▓ marks where the tight diffusion kernel takes over near the
core). Left panel positions are computed from the actual spiral —
`angle = i·2.39996`, `radius = sqrt((i+0.5)/12)` — not sketched.

And at the terminal, what you actually see around a cursor:

```
┌─ BEFORE · fixed phase ──────────┐  ┌─ AFTER · jittered phase ────────┐
│                                 │  │                                 │
│                    ▒            │  │                                 │
│                  ▒    ▒         │  │                   ░░░░░░░       │
│                         ▒       │  │                 ░▒▒▒▒▒▒▒▒░      │
│  $ tail -f build.log █          │  │  $ tail -f build.log █▒▒░░      │
│                 ▒     ▒         │  │                 ░▒▒▒▒▒▒▒▒░      │
│                   ▒  ▒          │  │                   ░░░░░░░       │
│                     ▒           │  │                                 │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

FIG 5 · Side by side at the prompt. Before: a series of discrete ghost
cursors — sides, diagonals, a couple of characters out (two more hide
under the text to the left). After: one soft, slightly ring-biased
halo. Same 12 taps, same cost, honest energy in both cases — only the
COHERENCE of the sampling error changed. The price is a whisper of
high-frequency noise in the glow, which hides under the mask, the
`noise` knob, and your retina's temporal integration.

There is no knob for the old behavior: the jitter is unconditional in
the template, because coherent ghosting is a bug, not a look. To
convince yourself it is really doing something, you can still amputate
the whole glow stage (`?set=CRT_HALATION:0.0,CRT_DIFFUSION:0.0` — the
gate at the top of `glassGlow()` compiles it out) and compare.

A last honesty note: the tight and wide samples share the same 12
directions per pixel (`sT` and `sW` reuse `d`), so diffusion and
halation residues are correlated — invisible in practice because their
radii differ 4.6×. And the docs page you are reading has no hardware
cursor (its cursor uniforms are inert constants), so the live
demonstration here is any isolated bright glyph; in a live renderer, the cursor itself performs.

---

## 9 · Burn-in: the ghost that doesn't move

Reality: electron dose ages phosphor. Efficiency drops with accumulated
charge (hundreds of C/cm² territory), so wherever bright content sat
for years — status lines, menu bars, the prompt column — the screen
emits less today. That is a NEGATIVE ghost: dark, permanent, and glued
to the tube. Scroll the page and it stays put; that is the definitive
test against persistence (§2).

The model is split across both passes:

- Dose (pass 1, `phosphor-state.glsl.tmpl`): the state alpha channel
  integrates `emitLum * dt * 9.7e-5 * CRT_BURNIN_RATE` per frame, with
  stochastic rounding in quanta of 5e-4 so tiny increments survive the
  half-float accumulator. At `burnin_rate = 1.0` a static full-white
  region reaches dose ≈ 0.35 in about an hour — documented
  time-compression of thousands-of-hours physics; the dose→loss law is
  the real one. Dose survives knob changes (it lives in the feedback
  texture) and resets on resize.
- Visibility (pass 2, `burnEfficiency()` in `crt-display.glsl.tmpl`):
  emitted light is multiplied by
  `1.0 - 0.35 * CRT_BURNIN_VISIBILITY * wear` — a fully dosed spot on
  a `burnin_visibility = 1.0` tube is 35% down, heavily-worn-tube
  territory.
- Pre-aging (`burnin_vintage`): a procedural ghost of years of
  terminal work, composited into wear at strength
  `vintage * CRT_BURNIN_VINTAGE * 0.8`: 24 etched text rows, an extra-
  hot status line and title line, a worn left margin, and a broad
  center panel. `wornout-office` ships 0.65 of it.

> TRY IT · THIS PAGE — switch PRESET to `wornout-office`: the row
> ghosts and hot status line are visible immediately on flat areas
> (raise them with `?set=CRT_BURNIN_VINTAGE:1.0`). Then scroll: the
> etching stays fixed while the text moves — the opposite of the P39
> smear you saw in §7. This page also burns honestly: its status bar
> is reverse-video burn-in bait, and `ibm-5151-mda-1981` ships
> `burnin_rate = 0.24`, so a docs page left open all day on that
> preset will etch its own chrome.

---

## 10 · The lab: isolate every effect

The documentation renderer can be controlled with URL
parameters — the runtime honors `?preset=NAME`, `?set=CRT_X:V,...`
(compile-time define overrides, both passes), `?pattern=bars` (a
diagnostic test card of isolated bright bars), `?scroll=PX`,
`?advance=SECONDS` (pre-roll), and `?debug` (raw state texture).

Step 0 — snapshot, so nothing you do here is destructive:

```
crtctl save pre-lab          # full-state profile snapshot
crtctl status                # confirm target instance is reachable
crtctl preset zenith-chromacolor-1971
```

Step 1 — halation alone. Kill the tight glow, max the fog:

```
crtctl set diffusion 0
crtctl set halation 0.2
```

Expect: a wide, desaturated pool around bright text; around an
isolated cursor, a soft annulus — smooth, no discrete ghosts (§8).
Bench B: `?preset=zenith-chromacolor-1971&set=CRT_DIFFUSION:0.0,CRT_HALATION:0.2`

Step 2 — diffusion alone. Swap which term lives:

```
crtctl set halation 0
crtctl set diffusion 0.3
```

Expect: every stroke wears a tight colored sheath; the far field goes
clean black. Text looks emitted; no fog.
Bench B: `?set=CRT_HALATION:0.0,CRT_DIFFUSION:0.3`

Step 3 — deconvergence. Restore glow defaults first so you judge only
fringes:

```
crtctl set halation 0.09
crtctl set diffusion 0.08
crtctl set misconvergence 2.0
```

Expect: red rails on one side of vertical strokes, blue on the other,
visibly worse at the corners (×1.5). Set it back to 0 and the fringes
vanish; 1.4 is the Zenith's shipped value.
Bench B: `?preset=trinitron-pvm&set=CRT_MISCONVERGENCE:2.0`

Step 4 — bloom. Watch the raster, not the shapes:

```
crtctl set scan_bloom 1.0     # then compare: crtctl set scan_bloom 0
```

Expect: at 1.0 bright rows fatten and their scanline gaps close; at 0
all rows are equally thin. Average brightness does not change — the
model normalizes energy.
Bench B: `?preset=bw-tv-p4&set=CRT_SCAN_BLOOM:1.0` vs `...:0.0`

Step 5 — persistence. Chemistry needs a long-tail phosphor:

```
crtctl preset ibm-5151-mda-1981
crtctl set persistence 4.0
```

Then scroll something. Expect: second-scale green comets behind the
text, hanging where content WAS. Reset with `crtctl set persistence 1`
— the tail is still there (P39 at 1.0 is genuinely ~1 s), just honest.
Bench B: `?preset=ibm-5151-mda-1981&set=CRT_PERSISTENCE:4.0`, then PgDn.

Step 6 — burn-in. The slow one:

```
crtctl set burnin_rate 1.0
crtctl set burnin_visibility 1.0
```

Leave a static page up ~15-30 minutes, then scroll: its dark ghost
stays. For instant gratification, `crtctl set burnin_vintage 1.0`
ships the tube pre-ruined.
Bench B: `?preset=wornout-office&set=CRT_BURNIN_VINTAGE:1.0`

Step 7 — restore everything:

```
crtctl load pre-lab
```

---

## 11 · Sources and further reading

- `templates/crt-display.glsl.tmpl` — `glassGlow()` (halation +
  diffusion + the jittered spiral), `scanSample()` (bloom +
  deconvergence), `burnEfficiency()` (burn-in visibility + vintage
  pattern), `collapseLight()` (the power-off dot's own halation skirt).
- `templates/phosphor-state.glsl.tmpl` — `decayPiecewise()` (exact
  piecewise-exponential persistence), phosphor constant tables (EIA
  registration data via the labguysworld / FH-Muenster tables), the
  burn-in dose integrator, cursor strike overdrive.
- `params.json` — every knob named here, with ranges, defaults, and
  per-knob help text (`crtctl list artifacts`, `crtctl list scan`).
- `research/vector-hardware-dossier.md` — the halation entry: critical
  angle 41.1° for n = 1.52, first-ring radius ≈ 1.75× faceplate
  thickness, concentric ring sets, and the anti-halation patents
  US4633131 and US4884006; ring energy fraction documented as
  undocumented.
- Randall & Wilkins 1945 (phosphorescence decay law); the crt-geom
  shader lineage (brightness-dependent spot growth); DESIGN.md for the
  full physics citation set.

The rule this document lives by is the project's own: every glow has a
mechanism, every constant has a source or is declared a tuned guess,
and when the renderer's shortcut shows through — twelve ghost cursors
at golden angles — the fix is documented next to the physics it was
pretending to be.

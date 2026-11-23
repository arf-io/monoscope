# Vector / XY / Random-Scan / Calligraphic CRT Displays — research dossier

Compiled 2026-07-16/17 for the ghostcrtty vector display class (see ROADMAP /
task: vector CRT class). Confidence legend: **[D]** documented in primary or
primary-adjacent source · **[d]** derived arithmetic from documented numbers ·
**[E]** estimate/folklore — treat as tunable free parameter, not ground truth.

## (a) Taxonomy, and the "shared root components" question

### The answer, precisely

**For the arcade/consumer vector class: yes — same tube, same gun, same
envelope, same phosphor screen as raster; only the drive electronics differ.**
This is documented, not inferred. The Wells-Gardner 6100 FAQ (compiled from
Atari factory manuals): *"There is no inherent difference between the tubes
used in vector monitors and the tubes used in raster monitors; only the
control circuitry differs… you can replace a Wells-Gardner 6100 color vector
picture tube with any compatible 'off-the-shelf' 100-degree in-line picture
tube that is also used in raster-scan displays"* **[D]**
(https://gauck.com/arcade/wg6100/Wells-Gardner%206100%20Vector%20Monitor%20FAQ%20and%20Guide%20Version%201.1.pdf,
mirror https://www.vectorlist.org/Documents/6100_faq.pdf). Concretely:

- WG6100 color vector = stock **RCA 19VLUP22** 100° in-line shadow-mask color
  TV tube **[D]** (FAQ p.6). Amplifone = 90° **Rauland M48AAWOOX** **[D]**
  (FAQ p.6); Jed Margolin hedges his Star Wars unit as *"probably a
  19VJTP22"* **[D-hedged]** (https://www.jmargolin.com/xy/xymon.htm) — flag:
  three designations circulate, FAQ is the better source.
- Mono vector = ordinary B&W TV tubes: **19VARP4** (P4 = standard white TV
  phosphor) in the 19" G05/19V2000, Philips M47EAA7WS as drop-in; *"it is
  easy to use just about any B&W tube in X/Y games"* **[D]** (B&W Vector
  Monitor FAQ v1.2, https://www.crazykong.com/tech/bw_vector_monitor_faq.pdf,
  pp.22, 25). Cinematronics used a Sylvania 19VARP4 **[D]**
  (https://www.outerworldarcade.com/cinematronics/manuals/cine_faq_v096.pdf).
  Vectrex = **Samsung 240RB40**, *"an off-the-shelf picture tube manufactured
  for small black/white television sets"* **[D]**
  (https://en.wikipedia.org/wiki/Vectrex).
- Even the WG6100's HV transformer is *"identical"* to the one in Atari's
  Disco **raster** monitor **[D]** (FAQ p.18), and Electrohome built G05
  vector monitors on a line adjacent to its G07 raster lines in the same
  Kitchener plant **[D]**
  (https://forums.arcade-museum.com/threads/arcade-monitor-timeline.269589/).

**What is actually different** (the entire "vector-ness" lives here):

1. **Yoke windings**: low-inductance vector-specific windings on standard
   tube geometry (~1 mH per axis, 1.1/1.9 Ω, ~2 A full deflection on Star
   Wars **[D]** Margolin xymon.htm; 0.45 mH Vectrex vs 1.5–2 mH arcade
   **[D]** https://www.e-basteln.de/arcade/asteroids/monitor/). Replacement
   tubes shipped without yokes: *"save all that you have"* **[D]** (B&W FAQ
   p.22).
2. **Deflection drive**: DC-coupled linear class-AB/B amplifiers (*"the same
   kind of circuitry some audio amplifiers use"* **[D]** FAQ p.3) converting
   voltage to yoke current via feedback around a non-inductive sense resistor
   **[D]** (Margolin xymon.htm) — versus raster's fixed-frequency resonant
   flyback sweep. This is why vector monitors run hot and eat output
   transistors.
3. **No fixed timebase → separate HV generation**: raster steals HV from the
   line flyback; a vector monitor has no line rate, so it uses a free-running
   oscillator — Hartley at ~30 kHz (G05/19V2000) **[D]** (B&W FAQ pp.7–8),
   20 kHz timer-driven (WG6100; Margolin measured 19.2 kHz) **[D]** (FAQ
   p.59; xymon.htm). Margolin: in a TV the HV pulse "Big Zap" hides in
   H-sync; *"in XY there is no Horizontal Sync, so the Big Zap occurs
   randomly in the vectors"* **[D]**.
4. **Spot killer**: an RC activity detector on the deflection outputs that
   blanks the gun(s) when deflection stalls, because vector brightness *"is
   intentionally designed to be at a level high enough to burn or etch right
   into the picture tube face"* **[D]** (Omega Race manual, reprinted B&W FAQ
   p.3). Circuit detail: G05 samples rate-of-change via R500/501+C500/501,
   rectified onto C502/503 (B&W FAQ p.6); WG6100 uses voltage doublers
   D801–804 off the X/Y output sense resistors driving Q800 → cuts all three
   cathodes **[D]** (FAQ pp.58–59). Cinematronics adds a beam-on watchdog:
   any Z-on pulse ≥ **6.8 ms** is treated as a fault, plus a dedicated
   power-down spot killer **[D]** (Cinematronics repair guide).

### The taxonomy (two physically distinct families + hybrids)

| Class | Deflection | Tube | Phosphor | Examples |
|---|---|---|---|---|
| **TV-derived arcade/consumer vector** | Magnetic, linear DC amps, ~kHz–100s kHz bandwidth | Stock B&W or shadow-mask color TV tube | P4 white (mono), P22 triad (color) | Asteroids, Tempest, Star Wars, Vectrex |
| **Scope-derived XY** | Electrostatic plates, MHz bandwidth, small deflection angle → long narrow tube | Purpose-built scope CRT, mesh/PDA | P31 std, P11 photo, P7 long | Tek 602/606/608, oscilloscope music |
| **Calligraphic graphics workstation** | Magnetic (documented: E&S Picture System "Electromagnetic") | Large mono tube | P4 (E&S PS1, documented) | E&S LDS-1, Picture System, PS300 |
| **Shaped-beam military** | Magnetic, beam passes character stencil matrix | 19" Charactron (Convair), Typotron storage variant (Hughes) | Long-persistence (P14-class, see flag) | SAGE OA-1008 consoles |
| **Radial-scan radar PPI** | Magnetic; rotating yoke or fixed yoke with sin/cos-modulated sweeps | e.g. 7JP4 round tube | P7/P14 cascade, seconds-to-minute afterglow | ASR/marine/air-defense PPIs |
| **Beam-penetration ("penetron") color vector** | Magnetic/electrostatic; color selected by anode kV switching two stacked phosphor layers, no mask | special two-layer tube | red/green layers → R/O/Y/G | ATC/avionics displays **[D]** (patent US3188507). NOT used in any Atari monitor **[D — corrects a common claim]** |
| **Hybrid raster+calligraphic** | Raster scene + stroked light points in remaining frame time | — | — | E&S CT5/CT6 flight simulators **[D]** (https://history.siggraph.org/animation-video-pod/ct5-flight-simulator-by-evans-and-sutherland-computer-corporation/) |

Electrostatic-vs-magnetic physics: deflection rates in scopes ("10s of MHz")
are far too fast for yokes; electrostatic angle ∝ 1/Va vs magnetic ∝ 1/√Va,
so scope tubes stay long/narrow and lower-kV **[D]**
(https://en.wikipedia.org/wiki/Deflection_yoke,
https://en.wikipedia.org/wiki/Electrostatic_deflection).

## (b) Physics tables

### Phosphors (decay = time to 10% of peak; primary compilation: LabGuy's World JEDEC-derived chart http://www.labguysworld.com/crt_phosphor_research.pdf, cross-checked https://en.wikipedia.org/wiki/Phosphor)

| Phosphor | Color / peak λ | Decay to 10% | Where in the vector world |
|---|---|---|---|
| **P4** | white (ZnS:Ag + (Zn,Cd)S:Ag/Cu), 565/540 nm | **<7% after 33 ms** [D] | **All B&W arcade vector** (Asteroids, Battlezone-under-overlay, Cinematronics 19VARP4), E&S Picture System 21" [D]; Vectrex 240RB40 (P4-family white **[E]** — B&W TV tube, no P-number documented) |
| **P31** | yellowish-green ZnS:Cu, ~520 nm [E] | 0.01–1 ms class [D]; the oft-quoted "32–38 µs" is **unconfirmed [E]** | Oscilloscopes (standard from late 1950s), Tek 602/606/608 XY monitors [D] (https://w140.com/tekwiki/wiki/Phosphor). **NOT arcade vector — common misconception [D-corrected]** |
| **P11** | blue 460 nm | ~2 ms / 0.01–1 ms class [D] | Scope photography (writing-speed champion) |
| **P7** | cascade: blue flash 440 nm → yellow 558 nm | yellow **>1 minute** in low ambient [D] | Radar PPI, EKG, early scopes (https://tubetime.us/index.php/2015/10/31/crt-phosphor-video/) |
| **P19 / P26 / P33** | orange 590–595 nm | very long, P26/P33 **>1000 ms** [D] | Radar screens |
| **P14** | blue flash → orange, medium/long | seconds-class [D] | SAGE situation displays per Ulmann's FSQ-7 book **[D-secondhand, flag: seen via snippet]** |
| **P22 triad** | R 611 / G 530 / B 450 nm | medium (TV-standard) [D] | WG6100 / Amplifone color vector (stock shadow-mask tubes) |
| **P15** | UV 391 + green 504 nm | **~3 µs** [D] | Flying-spot scanners only — **not arcade [D-verified]** |

**Key phosphor corrections to folklore [all D]:** Asteroids drew **white** on
a P4-class tube, not green; Battlezone's green/red is a **plastic overlay**
on a white Amperex M50-120**W** tube (W = white per Pro-Electron code,
https://wiki.arcadeotaku.com/w/CRT_designation_systems,
https://forums.arcade-museum.com/threads/battlezone-monitor-overlays.537080/);
Vectrex glows blue-white, not P31 green; color vector = ordinary P22 shadow
mask, not beam penetration.

**How color-on-vector works [D]:** the shadow mask is *angle*-selective —
each of three converged guns can only ever reach its own triad dots
regardless of where the yoke throws the beams, so arbitrary trajectories keep
color separation. The costs: convergence must hold over the whole face
(mechanical rings + rubber wedges + paper magnetic shunts on WG6100; *"almost
impossible to align the edges without using the shunts"* [D] FAQ), the mask
caps resolution (the FAQ notes mono vector hit 768×1024 addressable in 1979
while *"the color mask… did not permit the same high resolution"*), and the
mask intercepts ~⅔+ of beam current. Mono needs no mask: one gun, one
continuous phosphor coat — this is why mono vectors look razor-continuous
and color vectors look grainy up close.

### Deflection / drive (arcade class)

| Monitor | Full-scale slew (measured, WG6100 FAQ App. E [D]) | Anode HV [D] | Notes |
|---|---|---|---|
| Electrohome G05 (mono) | 0.0975 in/µs (150 µs full 14.5") | **12.0 kV** (OVP 21 kV) | Asteroids ≤ s/n ~18.9k, Lunar Lander, Battlezone |
| WG 19V2000 (mono) | 0.12 in/µs (120 µs) | **14.5 kV ±500 V** (https://www.westnet.com/~chris/arcade/19V2000/page03.html) | later Asteroids |
| WG6100/19K6100 (color) | X 0.05 / Y 0.0375 in/µs (290/385 µs) — slowest of all | **19.5 kV** (R918 adjustment spec) | Tempest, Gravitar, Space Duel |
| WG6400 | X 0.1325 / Y 0.08 in/µs | — | Aztarac |
| Amplifone (color) | unmeasured; documented "faster drawing speed" than 6100 [D] | **19.5 kV** | Star Wars, Quantum, Major Havoc. The often-quoted "~25 kV" is **wrong** |
| Vectrex | ~100 µs full swing [D e-basteln]; yoke 0.45 mH | **5.8 kV ±150 V** [D] (service manual via https://mattpilz.com/vectrex-console-complete-screen-calibration-guide/) | |

Scope family: Tek **602** 1 MHz XY BW, −3.83 kV, trace width 14 mil (0.36 mm)
@0.5 µA; **606** 3 MHz, 5.6 kV, 5 mil spot; **608** 5 MHz XY / 10 MHz Z,
**22.5 kV**, 10 mil (0.25 mm) spot, **settles in 300 ns to within 0.5 mm**,
up to 75 fL [all D] (https://w140.com/tekwiki/wiki/602, /606, /608). E&S
Picture System (1974): magnetic deflection, spot **0.020"** (0.51 mm),
4096×4096 addressable, MAX DRAW TIME = **15.7·L + 3.0 µs** (L = fraction of
screen width), constant-rate drawing "maintaining constant line intensity…
independent of line length" [D]
(https://s3data.computerhistory.org/brochures/evanssutherland.3d.1974.102646288.pdf).

### Vector generator control laws (per architecture)

| | Atari DVG (1979) | Atari AVG (1980–85) | Cinematronics CCPU (1977) | Vectrex (1982) |
|---|---|---|---|---|
| Position generation | 12-bit counters + BRMs → **10-bit DAC**, S&H deglitch (blank during sample, unblank during hold) [D] | op-amp **integrators**, DAC sets ramp slope; caps discharged via LF13201 to cancel drift [D] | DAC step + **RC shaping network** into deflection driver [D, patent US4053740] | 8-bit DAC → analog integrators; **length = velocity × Timer-1 time** [D] |
| Clock | 1.5 MHz state PROM (12.096 MHz/8) [D] | same 1.5 MHz [D] | 5 MHz, ~600 ns/inst [D] | software on 1.5 MHz 6809 |
| Intensity | **16 levels** (4-bit Z per VCTR) [D] | **8 base levels** (3-bit Z) × STAT ZSTAT multiplier; Star Wars 8-bit path [D] | mostly **bi-level**; Sundance 16, Solar Quest 64 [D] | DAC $00–$7F via MUX ch.2 (+ **Vec_Dot_Dwell** dwell counter for dots) [D] |
| Speed normalization | binary-normalized at list-build; uniform *"within a worst case factor of almost two"* [D Margolin] | timer shift-normalized; `cycles = 0x8000 − timer` [D MAME avgdvg] | hardware NORMALIZE instruction loads shift count into line-length timer [D] | none — programmer's problem |
| Reposition/retrace | LABS jump while blanked | CNTR or **blank vector at max rate** [D] | initial-position switches | ZERO line recenters, integrators re-zeroed **every frame** (drift) [D] |
| Refresh | halt-poll + GO: Asteroids **61.5 Hz** (12.096 MHz/4096/12/4), Lunar Lander **41 Hz** [D MAME asteroid.cpp]; degrades when list > frame | Tempest/Quantum free-run *"endless loop… CPU updates vector RAM while the AVG is running"* [D avgdvg.c]; nominal 60 Hz | patent: 33 fps / FRAME waits 30 ms; MAME uses **38 Hz** — discrepancy flagged [D] | **50 Hz** by BIOS convention (30,000 cycles, Wait_Recal), deliberately EU-mains-locked; on 60 Hz mains vectors **wobble** [D] (https://vectorgaming.proboards.com/thread/2620/vectrex-works-outside-america-frequency) |

Beam speed anchor: Margolin's worked examples assume deflection amps move the
beam at *"a maximum speed of 1 screen unit/microsecond"* — an **illustrative
assumption, not a measured spec [D-as-teaching-example]**
(https://www.jmargolin.com/vgens/vgens.htm). Derived DVG timing: a divisor-1
VCTR runs ~1024 DVG clocks ≈ 677 µs **[d]** (from MAME's `fin` formula).

### The brightness law and endpoint physics [the core of the look]

- **Energy per unit length ∝ 1/beam speed** at fixed beam current. Margolin
  states it directly: a vector twice as long drawn in the same time *"will
  have its energy distributed over twice the distance… and will appear
  dimmer"* [D]. E&S engineered around it (constant-rate drawing [D]); the DVG
  only bounded it within ~2× [D].
- **Endpoints**: dwell = brightness. The Vectrex BIOS exposes it literally —
  `Vec_Dot_Dwell` is a delay loop with the beam parked to set dot brightness,
  with a documented burn-in warning [D]
  (https://www.playvectrex.com/designit/chrissalo/dotdrawing.htm). On AVGs,
  bright/blobby line ends come from **DAC-reference turn-on/turn-off
  mismatch**; by Star Wars speeds *"the vectors looked really bad"*, fixed in
  TomCat with fast LF13201 switches giving *"sharply defined end points"*
  [D Margolin]. The DVG conversely gated beam off **slightly early** to
  compensate monitor delay → slightly shortened lines [D]
  (https://www.e-basteln.de/arcade/asteroids/monitor/). Hudson: *"if the
  system pauses even for a few nanoseconds there is an appreciable change in
  the brightness of the line"* [D] (https://trmm.net/Vector_games_32c3/).
- **Overdrive bloom (documented, Star Wars)**: the game deliberately
  overdrives the color inputs → CRT draws excess current → **drags down HV →
  changes focus ratio → defocuses/blooms** — the Death Star explosion flash
  [D Margolin vgens.htm]. WG6100s visibly bloom on that scene where
  Amplifones don't [D]
  (https://www.vintagearcadegal.com/post/atari-s-star-wars-vector-s-shining-moment).
  Note: the "Asteroids shields flash" premise is **unsubstantiated** —
  Asteroids has hyperspace, no shield; Asteroids Deluxe's shield signals
  remaining power by *dimness*. Flag as folklore.
- **Corner rounding/ringing**: at 50 kHz deflection bandwidth corners visibly
  round; at 200 kHz only slightly [D]
  (https://allenwp.com/blog/2020/03/31/overshooting-oscillations-and-blanking-on-a-vector-display/,
  https://www.nycresistor.com/2012/09/03/vector-display/); overshoot
  oscillation before settling is real and hidden by ~36 µs blanking in that
  build [D]. Audio-rate XY at 44.1/48 kHz gives "rounded corners and often
  overshoots"; practitioners use 96–192 kHz [D]
  (https://github.com/macumbista/vectorsynthesis).
- **Halation**: total-internal-reflection ring around bright strokes; θc =
  41.1° for n=1.52 glass, lateral shift "on the order of the faceplate
  thickness (e.g. 10 mm)", concentric ring set [D] (patents US4633131,
  US4884006). First ring radius ≈ 2·t·tan θc ≈ **1.75× glass thickness
  [d]**. Ring energy fraction: **undocumented [E]**.
- **Spot size**: Tek 602 0.36 mm @0.5 µA is the only hard vector-class number
  found; ~500 µm typical direct-view beam spot per patent US4633131 [D];
  **no G05/WG6100 spot spec exists** — 0.5–1.5 mm FWHM for a 19" arcade tube
  is an **estimate [E]**. Spot profile Gaussian, σ = FWHM/2.355 [D/d].
- **Flicker**: Ferry–Porter CFF saturates ~80–100 Hz at high luminance and
  large field [D] (https://www.mdpi.com/2411-5150/7/1/26) → Cinematronics
  38 Hz and Lunar Lander 41 Hz flicker hard, Asteroids 61.5 Hz is marginal,
  worse peripherally **[d]**. Scene-load slowdown is real and documented
  qualitatively: Asteroids caps at 35 objects or "the game would visibly slow
  down" [D] (https://www.vecfever.com/faq/asteroids/); Vectrex "the more
  complex an image, the slower the refresh rate" [D]
  (https://vectrex.com/understanding-the-vector-display-of-the-vectrex/).
- **Burn-in**: Asteroids score digits/attract text burns are an acknowledged
  community problem (no-burn-in ROM sets exist) [D]
  (https://forums.arcade-museum.com/threads/asteroids-no-burn-in-rom-set.551284/);
  center-dot burns from parked beams [D]; Margolin recounts a runaway vector
  generator burning **through the shadow mask and into the glass** [D
  xymon.htm]. Tempest "well burn": plausible but **unsourced [E]**.
- **Visible retrace**: turn brightness up and *"you can see the full path of
  the electron beam as it flies around"* [D] (Woodcock,
  https://www.mikesarcade.com/cgi-bin/spies.cgi?action=url&type=info&page=gwoodcock_xyhelp.txt).
  On Z-less scopes (oscilloscope music) retrace is *always* visible →
  single-continuous-path composition [D].

## (c) Candidate preset table

| # | Preset | Year / maker | Price (if known) | Tube / phosphor | Refresh | HV | Signature artifacts |
|---|---|---|---|---|---|---|---|
| 1 | **Asteroids** (G05 / 19V2000 mono) | 1979, Atari; Electrohome (Canada) / Wells-Gardner (Chicago) | n/f | 19VARP4, **P4 white** | **61.5 Hz**, drops under 35-object load | 12 / 14.5 kV | Max-brightness shot dots (Z=15), rocks dim (Z=6–8), ~2× brightness nonuniformity, score-digit burn-in, slightly shortened line ends |
| 2 | **Lunar Lander** (G05) | 1979, Atari/Electrohome | n/f | P4 white | **41 Hz** — visibly flickery | 12 kV | Deep flicker; thrust-plume intensity play |
| 3 | **Battlezone** (G05 + overlay) | 1980, Atari | n/f | Amperex M50-120W white + green/red plastic overlay | ~60 Hz class | 12 kV | Overlay tint zones, horizon line, white-through-green bloom |
| 4 | **Tempest** (WG6100 "Quadrascan") | 1981, Atari/Wells-Gardner; 25,113 uprights [D] | n/f | RCA 19VLUP22, **P22 triad + shadow mask** | free-running ~60 Hz | 19.5 kV | Edge/corner RGB fringing (misconvergence), slowest slew (Y 0.0375 in/µs), no pincushion correction [D Margolin], weeks-scale MTBF folklore [D Play Meter 1983] |
| 5 | **Star Wars** (Amplifone) | 1983, Atari; 12,695 units [D] | n/f | Rauland M48AAWOOX ("probably 19VJTP22" per Margolin), P22 | ~60 Hz | 19.5 kV | Intentional HV-sag overdrive bloom (Death Star), blobby endpoints at high draw speed, HV-unit death as the era's failure icon |
| 6 | **Vectrex** | 1982, GCE/Milton Bradley, **$199 launch [D]** (https://en.wikipedia.org/wiki/Vectrex) | $199 | Samsung 240RB40 9", white P4-family **[E]** | **50 Hz** BIOS-locked; wobbles on 60 Hz mains [D] | **5.8 kV** | Dot-dwell brightness, integrator drift (per-frame re-zero), pattern-shifted BLANK dotted lines, per-game color overlays, small tube + low HV = fatter relative spot |
| 7 | **Star Castle / Cinematronics CCPU** | 1977–81, Cinematronics | n/f | Sylvania 19VARP4, P4 white | **38 Hz** (MAME) / 33 fps (patent) — flag | — | Bi-level intensity (wall states by brightness), RC-smoothed strokes, harsh flicker, 6.8 ms beam-on watchdog |
| 8 | **Oscilloscope XY (Tek 602/608 class)** | 1969–93, Tektronix | n/f | Scope CRT, **P31 green** (P7/P11 options) | n/a (continuous) | 3.8–22.5 kV | Tiny spot (0.25–0.36 mm), MHz bandwidth = crisp corners, center-dot burn risk, weak Z inputs (visible transit lines) |
| 9 | **Oscilloscope-music rig** (Tek D11/5103N @ 192 kHz audio) | 2013–, Jerobeam Fenderson | scope: used-market | P31 storage-family tube | continuous | — | No Z blanking → single-path drawing, sample-rate corner rounding (44.1 kHz visibly rounds), AC-coupling image drift, brightness ∝ 1/speed everywhere |
| 10 | **PPI radar scope** | 1940s–, various (e.g. 7JP4 tube) | n/f | **P7 cascade** (blue flash + yellow tail) or P19/P26 | one sweep per antenna rev: 12–15 RPM ASR, ~24/44 RPM marine, ~5–6 RPM long-range [D] | ~7 kV class [E] | Rotating radial trace, seconds-to-minute decaying echoes, blue leading edge on yellow afterglow |
| 11 | **SAGE OA-1008 situation display** | 1958, IBM/Convair (Charactron) | n/f | 19" **Charactron shaped-beam**, long-persistence (P14-class, flagged) | messages rewritten every **2.62 s** [D IBM manual, https://archive.org/stream/bitsavers_ibmsage362ug58_40521123/3-62-0_Display_System_Vol1_Aug58_djvu.txt] | — | Stencil-formed characters, slow fade-refresh cycle, light-gun interaction |
| 12 | **E&S Picture System / PS300** | 1974 / 1981, Evans & Sutherland | not documented (the "$50k–250k" bracket is **unverified [E]**) | 21" P4, 0.020" spot, magnetic deflection [D brochure] | 30 fps double-buffered; PS300 "up to 95,000 line segments at 30 fps" [D, OCR-noisy] | — | 256-level depth-cue intensity ramps, constant-rate drawing (no length dimming), 4096²–8192² addressability, endpoint matching 0.020" |

(n/f = not found; original arcade monitor unit prices are not documented
anywhere located — only 1995 WinTron HV-replacement pricing, $149.83–173.13
[D].)

## (d) Simulation notes — what matters from a rasterized input

Priority-ordered:

1. **Additive HDR beam deposition with Gaussian cross-section.** The proven
   math is the closed-form erf path integral (woscope:
   https://m1el.github.io/woscope-how/index.html; extended with in-segment
   phosphor decay by Tasios,
   http://nicktasios.nl/posts/simulating-an-xy-oscilloscope-on-the-gpu.html).
   The `1/(2l)` factor **is** the dwell-time law. Since ghostcrtty receives a
   rasterized image the shader can't integrate a true beam path — workable
   proxies: treat luminance as already-deposited energy, then (i) apply
   intensity-dependent spot growth, (ii) detect stroke terminals /
   high-curvature points and boost them as dwell hot-spots, (iii) modulate a
   per-frame "draw budget."
2. **Endpoint hot-dots and slight end-shortening.** Two documented,
   opposite-signed artifacts: AVG blobby bright ends (DAC on/off mismatch)
   vs DVG early-cutoff shortening. A per-preset endpoint-energy multiplier
   (>1 for AVG/Vectrex-dots, ≤1 with a gap for DVG) is physically honest.
3. **Refresh-vs-scene-load flicker.** Nobody in prior art renders this
   (MAME reduces it to stochastic per-vector dimming, `flicker=0.15`).
   Physically: total on-screen stroke length ∝ frame time; when it exceeds
   1/f_nominal, refresh slips. Bright-pixel count is a valid proxy for
   display-list length → drive global flicker depth (phosphor decays further
   between refreshes) + slight brightness drop. ghostcrtty's chance to beat
   MAME.
4. **Phosphor persistence per preset**: P4 <7% at 33 ms [D] (≈1–3% residual
   per 60 Hz frame [d]); P31 0.01–1 ms (effectively zero inter-frame trail);
   P7/P14 two-component (fast blue flash + seconds-to-minute colored tail —
   separate decay layer with different chromaticity). Long-persistence
   presets invert the aesthetic: the *trail* is the image.
5. **Bloom hierarchy**: (i) local intensity-dependent spot σ growth
   (mechanism documented, transfer function not — free parameter), (ii)
   halation ring at radius ≈1.75× faceplate thickness with a few-percent
   energy [E], (iii) wide Gaussian-cascade glow (MAME HLSL U-shaped level
   weights `1.0,0.48,0.32,0.24,0.16,0.24,0.32,0.48,0.64` are a documented
   starting point), (iv) **global HV-sag events**: total scene energy spikes
   → dim + defocus + slight size breathing everywhere — documented physics
   (Star Wars trick), never simulated in prior art.
6. **Color vector = raster tube truths**: keep shadow-mask/triad sampling
   from the existing raster path (same tube!), add edge-growing RGB
   misconvergence fringing (~0.5–2 mm [E]) and slight geometry error (no
   pincushion correction on Tempest [D]). Mono vector: **no mask at all** —
   this contrast is itself the most authentic detail.
7. **Deflection-bandwidth corner treatment**: preset-scaled corner
   rounding/overshoot (visible at 50 kHz BW, subtle at 200 kHz; audio-rate
   presets round hard). Probably only worth simulating for scope /
   oscilloscope-music presets where it dominates.
8. **Power/no-signal choreography**: spot-killer behavior (deflection
   collapse → beam blanked; a *failed* spot killer → burning center dot),
   power-down spot suppression, burn accumulation of static bright content
   (score digits). Ties into existing power choreography.
9. **Differentiators vs prior art**: refresh collapse under load, deflection
   slew/ringing as a visual, intensity-dependent defocus, HV-sag global
   breathing, halation rings distinct from bloom. Worth matching from prior
   art: VIDE's speed/dwell-coupled brightness and drift, MAME's
   intensity→width sigmoid (`beam_intensity_weight` 0.75, widths
   1.0–4.0/512 screen units), woscope/Tasios deposition math.

**Honest free-parameter list (undocumented, must be tuned):** arcade-tube
spot FWHM; halation energy fraction; convergence-error mm; bloom-vs-current
curve shape; Vectrex phosphor P-number; SAGE exact phosphor; burn-in
accumulation rate (time-to-burn "seconds" is never quantified).

## (e) Source list

**Primary / primary-adjacent:** Jed Margolin, "The Secret Life of Vector
Generators" (https://www.jmargolin.com/vgens/vgens.htm) and "The Secret Life
of XY Monitors" (https://www.jmargolin.com/xy/xymon.htm); Margolin's Star
Wars VG instruction sheet (https://www.jmargolin.com/vgens/vgcmd.pdf); WG6100
FAQ/Guide v1.1 (gauck.com / vectorlist.org mirrors above); B&W Vector Monitor
FAQ v1.2 (https://www.crazykong.com/tech/bw_vector_monitor_faq.pdf); WG
19V2000 manual scans (https://www.westnet.com/~chris/arcade/19V2000/page03.html);
Cinematronics Vector Monitor Repair Guide
(https://www.outerworldarcade.com/cinematronics/manuals/cine_faq_v096.pdf);
Rosenthal patent US4053740; Phil Pemberton DVG guide
(https://wiki.philpem.me.uk/_media/elec/vecgen/vecgen.pdf); IBM SAGE Display
System Vol.1 1958 (archive.org, id bitsavers_ibmsage362ug58_40521123); E&S
Picture System 1974 brochure
(https://s3data.computerhistory.org/brochures/evanssutherland.3d.1974.102646288.pdf);
E&S LDS-1 manual (bitsavers.org); PS300 brochure OCR (archive.org
TNM_PS_300); halation patents US4633131, US4884006; penetron patent
US3188507; Vectrex Programmer's Manual
(https://www.playvectrex.com/designit/fredtaft/vecprogman_v1.pdf),
INTERNAL.TXT (vectrexmuseum.com), dot-dwell doc
(https://www.playvectrex.com/designit/chrissalo/dotdrawing.htm).

**Measured/technical secondary:** TekWiki 602/604/606/608/D11/Phosphor pages
(https://w140.com/tekwiki/); LabGuy's World phosphor chart
(http://www.labguysworld.com/crt_phosphor_research.pdf); e-basteln
Asteroids-on-Vectrex monitor analysis
(https://www.e-basteln.de/arcade/asteroids/monitor/); Allen Pestaluky
overshoot/blanking (allenwp.com 2020-03-31); MAME sources vector.cpp /
avgdvg.cpp / asteroid.cpp / tempest.cpp / emuopts.cpp /
ini/presets/vector.ini / hlsl/vector.fx (github.com/mamedev/mame) + docs
(https://docs.mamedev.org/advanced/hlsl.html); computerarcheology.com
Asteroids DVG/Hardware/VectorROM; VecFever Asteroids FAQ
(https://www.vecfever.com/faq/asteroids/); vectorsynthesis README
(https://github.com/macumbista/vectorsynthesis); woscope
(https://m1el.github.io/woscope-how/index.html); Tasios GPU scope sim
(http://nicktasios.nl/posts/simulating-an-xy-oscilloscope-on-the-gpu.html);
V.st (https://trmm.net/V.st/, https://trmm.net/Vector_games_32c3/); Scopetrex
(https://github.com/schlae/scopetrex); VIDE analog emulation notes
(http://vide.malban.de/help/how-vectors-are-drawn); radartutorial.eu PPI
pages; TubeTime phosphor video (tubetime.us 2015-10-31); Ferry–Porter CFF
review (https://www.mdpi.com/2411-5150/7/1/26); Vectrex calibration guide w/
HV spec (https://mattpilz.com/vectrex-console-complete-screen-calibration-guide/).

**Community/tertiary (used with flags):** KLOV/arcade-museum forum threads
(monitor timeline, Battlezone overlays, shaky vectors, burn-in, Amplifone
HV); Woodcock XY repair guide (mikesarcade.com); repairfaq.org F_VAtari2/3;
vintagearcadegal Star Wars article; ed-thelen.org SAGE pages; Wikipedia
(Vectrex, Phosphor, Charactron, Vector monitor, Deflection yoke,
Electrostatic deflection); oscilloscopemusic.com; teddavis.org/xyscope.
**Rejected as unreliable:** Grokipedia claims (Battlezone green phosphor,
PS300 130k vectors/s), history-computer.com "48-inch SAGE CRT", the
Amplifone-25kV and Asteroids-shield-flash premises.

**Unresolved after search (do not assert):** original monitor unit prices;
E&S list prices; G05/WG6100 spot-size spec; SAGE exact P-number; Vectrex
phosphor P-number; E&S CT5/CT6 phosphor technology; per-frame vector counts
for Asteroids; zonn.com (Cinematronics primary tech notes) currently
unreachable.

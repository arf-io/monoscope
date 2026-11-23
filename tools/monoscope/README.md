# MONOSCOPE — the crtctl control surface

> A monoscope was a single vacuum tube that generated a station's test card —
> the pattern an engineer aligned the whole chain against.

MONOSCOPE is the interactive form of `crtctl`: the demoscene control surface
for the Ghostty CRT shader simulation. `crtctl` (no arguments on a tty) or
`crtctl panel` launches it; every `crtctl` CLI verb is unchanged and stays
stdlib-only.

```
crtctl                        # the panel
crtctl panel --motion off     # static frames (also MONOSCOPE_MOTION=off)
crtctl panel --no-splash      # skip the logon splash
crtctl panel --no-mouse       # keyboard only (M toggles it live)
crtctl panel --fps 6          # ambient frame rate (default 8; [ ] adjust live)
crtctl panel --flat-field     # §8.4 diagnostic: one flat colour on every cell
```

## What it is made of

`tools/monoscope/` is a self-contained Python 3 package (stdlib only, no
curses, no path dependency on any sibling repo):

| module | job |
|---|---|
| `term.py` | raw mode, alt screen, DEC 2026 synchronized frames, SGR mouse, bracketed paste, kitty keyboard flags (pushed blind, popped on exit), SIGWINCH, and a restore-no-matter-what teardown (atexit + SIGINT/SIGTERM/SIGHUP/SIGQUIT/SIGTSTP). It never touches the palette (no OSC 4/104). |
| `keys.py` | input decoder: legacy CSI/SS3, xterm modifiers, kitty CSI-u, SGR 1006 mouse, bracketed paste, Esc-timeout disambiguation. Stable `id` strings (`S-left`, `C-c`, `backtab`, …). |
| `canvas.py` | the cell grid (every cell has an explicit fg/bg) and the frame differ: emits only changed cells as truecolor SGR (xterm-256 quantised only when the terminal declares no truecolor). |
| `color.py` | the ground wave (`bg_wave`, `wave_phase`), colour math bit-conformant with the Scanhound spec (`hue_to_rgb`, `hsl_to_rgb`, plasma, breathing, hue stops — pinned by `tests/golden/scanhound_vectors.json`), the CRT-medium `crt_safe` saturation ceiling, and the **palette families**: the panel wears the tube — p22 colour, green (p1/p31/p39), amber (p3/p134), white (p4), paperwhite, blue (p11), radar (p7), storage (dvst), plasma (pdp). Each family has a Roy vertical face ramp for lettering (chrome / blue / fire / copper / magenta / green). |
| `blocks.py` | the block-shading vocabulary: dither gradients, fade runs, the half-block `PixelGrid`, bevel frames, rails, sparkles. |
| `tdf.py`, `banners.py`, `fonts/*.tdf` | a native TheDraw (.TDF) colour-font loader — the scene's own lettering — with five vendored fonts: 1911 (Razor 1911, splash), Blocktronics (7 rows), Cfh 3 (5), Silver (4), Nirvana (4). Titles are set at runtime and recoloured live. |
| `widgets.py` | band, glow-rail section bands, SMPTE group bar, the channel strip, bg-fill meters with a copper-bar gradient and a peg-over-range ▶, switches, chips, buttons, range ruler, status band, Roy hotkey rail, tube signature, banner block, noise field. |
| `model.py` | the state: rows, selection, filter/modified-only, undo, reload debounce, hit map, cached baseline. |
| `views.py`, `bankview.py`, `sheetview.py`, `helpview.py`, `splashview.py` | `render(model, canvas, tick)` — the whole frame, every tick, one pure function per mode. `views.apply_ground_wave` is the closing post-pass: the ground breathes, the instruments do not. |
| `app.py` | the loop: poll → update → render → diff → write; two clocks (ambient 8 fps, 30 fps for 400 ms after input); the debounced reload runs in a worker thread. |

## The ground wave

A slow vertical band travels up the panel, taking the background darker and
lighter — the tube's own hum bar, the mains ripple beating against the frame
rate on an unregulated supply.

The idea is lifted from the ARF-TUI's `line_bg`
(`AgentInterposer/crates/arf-cli/src/tui/theme.rs`): a per-row HSV wave whose
phase advances each tick. Three things are deliberately different here.

* **It wears the tube.** ARF anchors its wave on a fixed violet→cyan palette.
  Here it is a perturbation of the *active family's* ground, and the hue term
  only exists for families that have a hue ring at all — a P1 green tube
  breathes green, an amber P3 breathes amber, a paper-white ground moves only
  in brightness. It goes through `crt_safe` like every other colour on the
  panel.
* **It is a hum bar, not a light show.** Small amplitude, mostly value, and
  the trough is half as deep as the crest is tall — a symmetric swing on a
  ground this dark crushes to near-black and reads as a fault.
* **It is quantised** (`color.wave_phase`, `WAVE_STEPS`). This is the part
  that matters mechanically: a full-precision wave changes every row every
  tick, which defeats the renderer's row-level fast skip and turns every
  single frame into a full repaint — it would *cause* the tearing it is
  meant to decorate. Snapped to discrete levels, a row only changes when it
  crosses a step.

It follows the motion mode (`full` travels; `reduced` is static banding;
`off` is flat) and `MONOSCOPE_GRADIENT=off` disables it on its own for anyone
who wants the panel's colour motion without the breath.

Cost, measured on a 200x60 pty at 8 fps (`tests/measure_payload.py`): median
frame 9.7 kB → 13.0 kB with the wave on. Both are well under the 16.4 kB the
panel cost before the payload work in `canvas.py`.

## Layout ladder

| width | layout |
|---|---|
| < 100 | group bar (the SMPTE chips) on top · single bench column · detail band below |
| 100 … 149 | RAIL (groups) ▐ BENCH ▐ detail band below the bench |
| ≥ 150 | RAIL ▐ BENCH ▐ SCOPE (identity, prose, range strip, default/inherited/now, SAME KNOB OTHER TUBES, TUBE, RELOAD) |

Height buys a TheDraw title above the band (≥ 28 rows: 4-row font, ≥ 34: 5,
≥ 44 and ≥ 100 cols: Blocktronics 7).

## The channel strip

```
▐▶ BANDWIDTH     ████████████▒▒▒▒▒▒▒▒▒▒▒▒     260 TVL    ◂ 400
   cursor  label 13  meter 16…34 (elastic, never wider)  value 7  unit 5  delta
```

Fixed offsets, composed left to right; leftover width goes to the delta
column (the inherited tube's value when the knob differs, `⚠ cap N` when the
value is outside the nominal range) — never to a gap.

## Keys

See `?` inside the panel (the table is generated from `helpview.KEYMAP`, so
it can never drift). Highlights: `↵` types a value on a rotary — outside the
nominal range is allowed and asks once (Enter commits, Esc whoopsiedaisies);
`0` schema default; `⌫` revert to the inherited tube; `/` filter; `*`
modified-only; `p`/`P` tube bank / save tube; `L`/`S` profiles; `u`/`U`
undo/redo; `E` erase; `m` motion; `M` mouse; `^F` flat field.

## Tests

```
python3 -m unittest tests.test_monoscope       # headless: keys, canvas, colour parity, fonts, model, every view at 7 sizes, update logic
python3 -m unittest tests.test_monoscope_pty   # real ptys: draws, hygiene (2026, truecolor, no OSC 4), knob → state/shader/reload, bank, typing, help
```

## Design lineage

The layout and interaction doctrine follow the MONOSCOPE proposal
(`monoscope/docs/CRTCTL-UX-PROPOSAL.md`, 2026-07-28) and its Appendix A
(nominal vs hard ranges). The visual language is the BBS ANSI scene — the
Roy/SAC corpus and 16colo.rs: block-shading ramps, glow rails, TheDraw
lettering, dgry `░` noise fields, hotkey rails — carried by colour motion on
fixed glyphs (nothing drawn ever moves; only what is drawn changes colour).

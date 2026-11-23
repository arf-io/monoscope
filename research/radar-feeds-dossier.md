# crtradar feasibility dossier — REAL live radar on the P7 scopes

Compiled 2026-07-17 (feeds live-probed from this machine ~06:00Z). Companion
spike: [nexrad-l3-decode-spike.py](nexrad-l3-decode-spike.py) — ~60-line
pure-stdlib decode of actual NEXRAD Level III binary (verified against live
KTLX reflectivity 360×460 showing real 38.5 dBZ precipitation, velocity
360×1200, hydrometeor classification 360×1200).

**Verdict: fully feasible with public, keyless, live data — no fakes
required.** Items that CANNOT be made real are flagged in (e).

## (a) Weather feed — recommendation

**Primary: NEXRAD Level III super-res base reflectivity (N0B) from the
Unidata AWS bucket.** Anonymous plain-HTTPS, no AWS SDK:

- List newest:
  `https://unidata-nexrad-level3.s3.amazonaws.com/?list-type=2&prefix=TLX_N0B_2026_07_17`
  (3-letter site ID, key format `SSS_PPP_YYYY_MM_DD_HH_MM_SS`)
- GET the newest key → NIDS file, product 153, **720 radials × 1840 gates
  (0.5° × 0.25 km, 460 km)**, ~200 KB, landing **~40–70 s after scan valid
  time**, new volume every 4–7 min.
- Same bucket, live-verified current: N0G velocity (154), N0C correlation
  coefficient (161), **N0H hydrometeor classification (165)**, EET echo
  tops (135), NST storm tracking (58).
- Landscape facts: `noaa-nexrad-level2` is **dead** (403 anonymous; archive
  moved to `unidata-nexrad-level2` — Unidata notice
  https://www.unidata.ucar.edu/blogs/news/entry/important-changes-to-noaa-nexrad,
  registry https://registry.opendata.aws/noaa-nexrad/); N0Q/N0U retired
  from the broadcast feed in 2022 (IEM notice
  https://mesonet.agron.iastate.edu/onsite/news.phtml?id=1431) — use
  N0B/N0G there.

**Fallback 1 (zero-AWS, verified by fetch+decode): NWS tgftp** —
`https://tgftp.nws.noaa.gov/SL.us008001/DF.of/DC.radar/DS.p94r0/SI.ktlx/sn.last`
(N0Q, 360×460, 1°×1 km; ≤3 min stale, honors If-Modified-Since; 161 site
dirs). Velocity `DS.p99v0`, echo tops `DS.135et`, CC `DS.161c0`, hydro
class `DS.165h0` all live. File docs: https://www.weather.gov/tg/radfiles.

**Fallback 2 (near-zero code): IEM georeferenced PNG** —
`https://mesonet.agron.iastate.edu/data/gis/images/4326/ridge/TLX/N0B_0.png`
+ `.wld` (EPSG:4326 world file) + `.json` (valid time, VCP); ~30 s stale.
RIDGE docs: https://mesonet.agron.iastate.edu/GIS/ridge.phtml. Plus
**storm-cell attributes GeoJSON** (azimuth/range, TVS, meso, hail prob,
VIL, max dBZ, tops — perfect for scope data blocks):
`https://mesonet.agron.iastate.edu/geojson/nexrad_attr.geojson?radar=TLX`
(verified live).

**Format/decode**: NIDS = WMO header + 18 B message header + 102 B PDB +
symbology (packet 16 digital radial array; bzip2/zlib per product). **Pure
stdlib is proven** (struct+bz2+zlib, no numpy/metpy/pyart) — fits the
"self-contained, minimal deps" convention. MetPy Level3File is the
optional test-oracle.

**dBZ → scope intensity, honestly** (NOAA JetStream
https://www.noaa.gov/jetstream/reflectivity): N0B levels map linearly,
dBZ = (level−2)×0.5 − 32 (matches in-file thresholds, verified). Display
via the six historical **VIP levels**: 1: 18–30 (light), 2: 30–41,
3: 41–46, 4: 46–50, 5: 50–57, 6: ≥57 dBZ; snow ~5–20 dBZ; clear-air
biologicals below ~20.

**Rain/snow/airborne particles/geologic features — all REAL via N0H
(product 165)**: per-gate classes include rain (60/70), big drops (80),
graupel (90), hail (100), dry/wet snow (40/50), ice crystals (30),
**biological = airborne particles (10)**, **ground clutter/AP = geologic
returns (20)**; cross-check with CC < ~0.8 for non-meteorological (NWS
dual-pol https://www.weather.gov/jan/dualpolupgrade-applications).
**Flag**: there is no public *unfiltered* base reflectivity (clutter is
filtered at the RDA) — a permanent terrain ring would require DEM
synthesis and must be labeled "simulated terrain" if offered.

**International**: RainViewer public tiles, keyless, attribution required
(https://www.rainviewer.com/api.html, verified live); DWD
`opendata.dwd.de/weather/radar/` (open, keyless); Environment Canada
GeoMet WMS `RADAR_1KM_RRAI` (anonymous,
https://eccc-msc.github.io/open-data/msc-geomet/readme_en/). All are
gridded-image-shaped, not polar — phase 2.

**ToS**: NOAA data is public domain, attribution requested (NODD registry
entry, awslabs/open-data-registry noaa-nexrad.yaml); IEM public domain,
attribution appreciated, "don't build for thousands of simultaneous users"
(https://mesonet.agron.iastate.edu/disclaimer.php); api.weather.gov
(metadata only — serves no imagery) requires a User-Agent string. One
desktop app polling every 60–120 s with conditional GETs is well inside
all of these.

## (b) ADS-B feed — recommendation

All three top aggregators verified live, keyless; identical readsb/tar1090
JSON shape; positions **0.1–0.5 s fresh**.

1. **airplanes.live** (primary):
   `https://api.airplanes.live/v2/point/{lat}/{lon}/{radius≤250nm}` —
   1 req/s documented limit, non-commercial, richest enrichment (`desc`,
   `ownOp`); hard 403 above 250 nm (https://airplanes.live/api-guide/).
2. **adsb.lol** (fallback A):
   `https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}`, plus `/v2/mil`,
   `/v2/sqk/{code}`, `/v2/closest`; openly-licensed stance, dynamic rate
   limits; keys *may* come later (https://api.adsb.lol/docs,
   https://github.com/adsblol/api).
3. **adsb.fi** (fallback B):
   `https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{d≤250}`
   (v3 — v2 form deprecated); 1 req/s; personal non-commercial only,
   **attribution + homepage link required**
   (https://github.com/adsbfi/opendata).

Ruled out: **OpenSky** (anonymous = 400 credits/day ≈ one poll per
3.6 min; ToS restricts to non-profit research, written license for
operational/live-product use); **ADSB.One** (docs archived, Cloudflare
challenge); **ADSBexchange** (paid only).

**Fields for the beacon** (all observed live): `squawk` = the real 4-digit
Mode A code — the beacon tag; `emergency` (general/nordo/unlawful ⇒
7700/7600/7500 handling free); `hex` (ICAO 24-bit, `~` prefix = TIS-B);
`flight`, `alt_baro` (feet or "ground"), `gs`, `track`, `category`
(A1 light … A5 heavy, A7 rotorcraft, B2 balloon, B6 UAV), `dbFlags&1` =
military, `type` (adsb_icao/mlat/tisb_*), and `dst`/`dir` = range/bearing
from query point — the API literally hands you polar scope coordinates.

## (c) Authentic-scope reference (numbers, sourced)

**Sweep rates** — terminal **ASR-8/9/11: 12.5 RPM = 4.8 s/rev, 60 NM**
(https://www.radartutorial.eu/19.kartei/03.atc/karte003.en.html); en-route
ARSR/CARSR: 5–6 RPM = 10–12 s/rev, 200–250 NM. Weather: WSR-57 era ~3 RPM
PPI at 5–250 NM ranges; **WSR-88D bottom tilt: 21.15°/s in VCP 12
(~3.5 RPM), volume every 4.3 min; VCP 212 4.6 min; clear-air VCP 31
≈ 0.84 RPM, 10 min** (ROC VCP Info Sheet
https://www.roc.noaa.gov/public-documents/operations-branch/VCP_Info_Sheet.pdf,
FMH-11 Part C https://www.icams-portal.gov/resources/ofcm/fmh/FMH11/fmh11partC.pdf).
**Honesty note**: no operational WSR-88D display ever showed a rotating
sweep — modern consoles render completed sweeps
(https://training.weather.gov/nwstc/NEXRAD/RADAR/Section1-2.html); the
rotating wedge is authentic to the WSR-57/74 analog PPI era and to the
antenna itself. crtradar presents it as the analog-era presentation —
precisely this project's aesthetic.

**ATC symbology, cell-drawable** (AIM FIG 4-5-2/4-5-3 legends, mirror
https://www.airresearch.com/Pilots/AIM-08/Chap4/aim0405.html; FAA JO
7110.65 §5-5
https://www.faa.gov/air_traffic/publications/atpubs/atc_html/chap5_section_5.html;
CRC/STARS docs https://docs.virtualnas.net/crc/stars/ — secondary but
precise):
- Primary target: `+` uncorrelated, `×` correlated (arc/"banana" blob in
  broadband era, long-axis range-oriented).
- Beacon reply: **`/` slash just beyond the primary at the same azimuth**
  (`\` when correlated); the 7110.65 still measures separation "between
  the ends of beacon control slashes."
- Position symbols: controller letter for owned tracks; STARS `*` beacon,
  `V` = 1200 VFR, `◇` primary-only, `#` coast.
- **Data block**: line 1 callsign (≤7 chars); line 2 altitude in hundreds
  (3 digits) + ground speed in tens (2 digits) — `AAL231` / `080 22` =
  8,000 ft, 220 kt; `H` = heavy; leader line; flashing LOW ALT/7700;
  untracked targets get squawk + Mode C only. History trails stream
  behind the motion while blip/slash stay range-oriented — the authentic
  double geometry.
- Weather on the ATC scope: 6-level NWS-calibrated channel, **two levels
  displayed at once** as patterned/stippled fills (MIT LL ATC-270
  https://archive.ll.mit.edu/mission/aviation/publications/publication-files/atc-reports/Crowe_1999_ATC-270_WW-15318.pdf).
- Range rings: 10/15-mile marks on the ARTS III figure; video-map runway
  centerlines dashed so mark+space = 1 mile.

**Phosphor**: P7 = blue ZnS:Ag flash + yellow (Zn,Cd)S:Cu layer pumped by
the *light* of the first (MIT RLE TR-56, 1948,
https://dspace.mit.edu/bitstream/handle/1721.1/4992/RLE-TR-056-04706923.pdf)
— exactly what phosphor-state.glsl.tmpl already implements
(CRT_P7_CASCADE, rise tau 120 ms, yellow decay 8 s × persistence). Real P7
decays inverse-power-law with >1 min visibility; the shader's exponential
is the documented "perceptually compressed" approximation. Orange
P19/P26/P33 = the later long-persistence radar family, low burn resistance
(burned-in range rings are authentic). Which tube sat in which FAA console
is veteran-lore, flagged.

**Artifact menu** (each physically real, for optional app-side rendering):
STC quiet zone near center; center "main bang" blob; ground clutter near
site; MTI tangential fade; second-trip echoes; FRUIT speckle; beacon
ring-around arcs; ident "blossom"; iso-echo "doughnut" (blanked cores) for
the WSR-57 mode; CP rain-knockdown; phosphor burn of static overlays.

## (d) Architecture sketch

**Boundary**: the app draws characters; the shader owns ALL persistence
physics. phosphor-state computes newState = max(drive, excited) with
piecewise-exponential decay; P7's yellow layer holds ~16 s at the mil-ppi
preset's persistence 2.0 — an erased character keeps glowing and fades.
Therefore:

- **Flash-and-erase sweep**: the app lights only a narrow wedge (~4–10°)
  behind the beam azimuth θ(t) = 360°·t/T and erases cells as they leave
  the wedge. The P7 cascade then does exactly what the real tube did. At
  T = 4.8 s (ATC) the mil-ppi preset leaves targets ~74% bright at
  repaint; the weather scope (T ≈ 17 s, VCP-12-authentic) wants a
  crtradar-wx preset variant with persistence ≈ 3–4 (yellow tau 24–32 s).
  Ship one or two new preset JSONs (can carry terminal.font-size
  overrides per convention).
- **Shader sweep-gating: rejected, with reasons** — crtctl bakes params
  into regenerated GLSL and reloads via D-Bus/SIGUSR2, so there is no
  live channel to phase-sync shader iTime with the app's beam; a reload
  resets nothing cleanly; and angular gating would also gate non-scope
  text (status bar, data blocks — which on real ARTS were
  continuously-refreshed alphanumerics and correctly stay solid).
  App-side beam is both simpler and more authentic.
- **Buffer-and-reveal (the latency-hiding trick that is also the truth)**:
  keep displayed[az][rng] and pending[az][rng] polar buffers. Feed polls
  fill pending; as the beam crosses azimuth bin a, displayed[a] ←
  pending[a] and that radial is painted. A real scope reveals data exactly
  one beam-passage at a time, so 40 s–4 min feed staleness is invisible
  and *honest* — the screen never claims data it doesn't have (status
  line shows product valid time; that's the real timestamp).
- **Cadences**: Level III poll = S3 prefix list or tgftp sn.last
  conditional GET every 60–120 s (new volumes every 4–7 min). ADS-B = one
  point query per antenna revolution (4.8 s ATC / 12 s en-route) — 5–12×
  under the 1 req/s limits. Aircraft revealed at beam crossing of their
  `dir` bearing; between reveals the track coasts (extrapolate along
  track/gs, exactly what ARTS trackers did; label coast `#` after 30 s,
  drop per STARS at 5 min).
- **Rendering**: monochrome preset (CRT_MONO) → intensity = glyph
  coverage × foreground gray ramp. Weather: `░▒▓█` (or braille dithering)
  quantized to VIP 1–6 per gate, polar→cell resampled with aspect
  correction from TIOCGWINSZ ws_xpixel/ws_ypixel (Ghostty populates
  these; fallback 1:2). At font-size 20 in a 1080p window (~190×44 cells)
  the scope rim resolves ~1.3° azimuth — same order as the 1° NIDS
  radials; nothing is faked by upscaling. Aircraft: `+`/`×` primary
  stylization, `/` beacon slash, two-line data block with real
  callsign/altitude-hundreds/speed-tens, real squawk for untracked
  targets, emergency field driving flashing 7500/7600/7700, dbFlags&1
  military marking. Frame loop ~20–30 fps redrawing only wedge-delta
  cells (hundreds of cells/frame — trivial for Python + raw ANSI; stdlib
  only, urllib for feeds, threads/asyncio for polling).
- **Modes/UX**: `crtradar wx KTLX` (weather PPI: N0B + N0H classes +
  storm-attr data blocks + EET), `crtradar atc --lat --lon --range 60`
  (ASR scope: ADS-B + two-level weather stipple underlay from the same
  N0B), site picker from a bundled NEXRAD list (refreshable via
  api.weather.gov/radar/stations, UA required), --range presets
  60/124/248 nm with authentic ring spacing.

## (e) Risks and honesty flags

1. **Feed drift**: AWS bucket rename (2025) and N0Q retirement (2022) are
   precedents — pin current names, implement tgftp + IEM fallbacks from
   day one (all three verified working today).
2. **Aggregator longevity**: adsb.lol may require feeder keys "in the
   future"; airplanes.live access "might change." Mitigation: identical
   JSON shape across all three → one backend interface, three drivers.
3. **What cannot be real with public keyless data**: (i) true
   primary-radar skin paint — ADS-B *is* beacon data, so the slash+data
   block is genuinely real, but any primary blip is stylization and
   non-transponder aircraft are invisible; (ii) unfiltered ground/terrain
   reflectivity — only N0H class-20/CC-flagged clutter is real; a DEM
   terrain ring would be labeled simulation; (iii) a rotating sweep on a
   WSR-88D — authentic only to the WSR-57/analog era presentation.
4. **Coverage**: NEXRAD is US+territories; ADS-B thins outside US/EU/AU
   (measured: Nairobi ~5–7 aircraft vs Sydney ~45); MLAT effectively
   US/EU-only. International weather = RainViewer/DWD/GeoMet, phase 2.
5. **ToS obligations**: adsb.fi requires attribution+link; RainViewer
   requires attribution; NOAA/IEM attribution requested — put all in
   --about and the README. OpenSky must NOT be used as a polling backend.
6. **P7 exponential vs real power-law decay** — existing, documented sim
   approximation; no action needed for feasibility.

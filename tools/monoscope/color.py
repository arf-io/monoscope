"""monoscope.color — color math and the panel's palette families.

The conversion core (``hsl_to_rgb``, ``hue_to_rgb``, ``hsv_to_rgb``,
``rgb_to_hsv``, ``lerp_rgb``, ``sample_hue_stops``, ``plasma_*``,
``breathing``) reproduces the Scanhound design-system spec
(``~/Augments/Scanhound/docs/spec/01-color-and-motion.md``) exactly — same
truncation/rounding rules — so MONOSCOPE speaks the same color language as
the rest of the operator's TUIs. Additions on top are the CRT-medium policy
(``crt_safe``: saturation ceiling, so the shadow mask does not chop a pure
primary into stripes) and the phosphor-derived palette families.

All colors are ``(r, g, b)`` int tuples 0..255.
"""

from __future__ import annotations

import math

__all__ = [
    "hsl_to_rgb", "hue_to_rgb", "hsv_to_rgb", "rgb_to_hsv", "lerp_rgb", "dim",
    "mix", "scale", "lighten", "darken", "luma", "crt_safe", "set_sat_ceiling", "SAT_CEILING", "sample_hue_stops",
    "plasma_hue", "plasma_color", "breathing", "gradient", "stepped",
    "Family", "FAMILIES", "family_for_phosphor", "GROUP_HUES",
]

_TAU = math.tau
_SWEEP_CACHE = {}


def _trunc_u8(x):
    if x <= 0.0:
        return 0
    if x >= 255.0:
        return 255
    return int(x)


def _round_half_away(x):
    f = math.floor(x)
    r = x - f
    if r > 0.5:
        return f + 1
    if r < 0.5:
        return f
    return f + 1 if x > 0.0 else f


def _round_u8(x):
    v = _round_half_away(x)
    return 0 if v < 0 else 255 if v > 255 else v


def _sector(h, c, x):
    s = int(h / 60.0)
    if s == 0:
        return (c, x, 0.0)
    if s == 1:
        return (x, c, 0.0)
    if s == 2:
        return (0.0, c, x)
    if s == 3:
        return (0.0, x, c)
    if s == 4:
        return (x, 0.0, c)
    return (c, 0.0, x)


def hsl_to_rgb(h, s, l):
    """HSL → RGB, channels truncated (Scanhound §1.1)."""
    h = h % 360.0
    c = (1.0 - abs(2.0 * l - 1.0)) * s
    x = c * (1.0 - abs(((h / 60.0) % 2.0) - 1.0))
    m = l - c / 2.0
    r1, g1, b1 = _sector(h, c, x)
    return (_trunc_u8((r1 + m) * 255.0), _trunc_u8((g1 + m) * 255.0), _trunc_u8((b1 + m) * 255.0))


def hue_to_rgb(hue_degrees):
    """The canonical rainbow: HSV s=1, v=0.88, rounded (Scanhound §1.2)."""
    h = hue_degrees % 360.0
    c = 0.88
    x = c * (1.0 - abs(((h / 60.0) % 2.0) - 1.0))
    r1, g1, b1 = _sector(h, c, x)
    return (_round_u8(r1 * 255.0), _round_u8(g1 * 255.0), _round_u8(b1 * 255.0))


def hsv_to_rgb(h, s, v):
    h = h % 360.0
    c = v * s
    x = c * (1.0 - abs(((h / 60.0) % 2.0) - 1.0))
    m = v - c
    r1, g1, b1 = _sector(h, c, x)
    return (_round_u8((r1 + m) * 255.0), _round_u8((g1 + m) * 255.0), _round_u8((b1 + m) * 255.0))


def rgb_to_hsv(c):
    rf, gf, bf = c[0] / 255.0, c[1] / 255.0, c[2] / 255.0
    cmax, cmin = max(rf, gf, bf), min(rf, gf, bf)
    delta = cmax - cmin
    if delta < 1e-10:
        h = 0.0
    elif abs(cmax - rf) < 1e-10:
        h = 60.0 * (((gf - bf) / delta) % 6.0)
    elif abs(cmax - gf) < 1e-10:
        h = 60.0 * ((bf - rf) / delta + 2.0)
    else:
        h = 60.0 * ((rf - gf) / delta + 4.0)
    s = 0.0 if cmax < 1e-10 else delta / cmax
    return (h, s, cmax)


def lerp_rgb(a, b, t):
    """Linear interpolation, truncated (Scanhound §1.5)."""
    if t <= 0.0:
        return a
    if t >= 1.0:
        return b
    return (_trunc_u8(a[0] + (b[0] - a[0]) * t),
            _trunc_u8(a[1] + (b[1] - a[1]) * t),
            _trunc_u8(a[2] + (b[2] - a[2]) * t))


def dim(c, pct=45):
    """Scanhound dim: scale to pct percent (integer math)."""
    return (c[0] * pct // 100, c[1] * pct // 100, c[2] * pct // 100)


def mix(a, b, t):
    return lerp_rgb(a, b, t)


def scale(c, k):
    return (_trunc_u8(c[0] * k), _trunc_u8(c[1] * k), _trunc_u8(c[2] * k))


def darken(c, amount):
    """Toward black by `amount` in [0,1]."""
    return scale(c, 1.0 - amount)


def lighten(c, amount):
    """Toward white by `amount` in [0,1]."""
    return lerp_rgb(c, (255, 255, 255), amount)


def luma(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


#: Saturation ceiling for the CRT medium. Tube-aware: the app sets it from the
#: active tube (1.0 with no mask — "full colour" is real when the tube can
#: show it; ~0.78 under a shadow mask / grille where a pure primary lands on
#: one phosphor set and gets chopped into stripes).
SAT_CEILING = 0.78


def set_sat_ceiling(mask_type=None, mask_strength=None):
    """Derive SAT_CEILING from the tube: no mask → 1.0; masked → 0.72..0.85
    depending on mask depth (weak masks chop less)."""
    global SAT_CEILING
    if not mask_type or str(mask_type).lower() == "none":
        SAT_CEILING = 1.0
    else:
        try:
            k = max(0.0, min(1.0, float(mask_strength if mask_strength is not None else 0.45)))
        except (TypeError, ValueError):
            k = 0.45
        SAT_CEILING = 0.86 - 0.14 * k
    _SWEEP_CACHE.clear()
    return SAT_CEILING


def crt_safe(c, max_sat=None, min_val=0.0):
    """The CRT-medium color policy: pull saturation to <= the ceiling so a
    shadow mask / aperture grille cannot chop a pure primary into a single
    phosphor stripe. Named and documented on purpose — this is where
    MONOSCOPE deliberately leaves Scanhound golden conformance."""
    if max_sat is None:
        max_sat = SAT_CEILING
    h, s, v = rgb_to_hsv(c)
    if s <= max_sat and v >= min_val:
        return c
    return hsv_to_rgb(h, min(s, max_sat), max(v, min_val))


def sample_hue_stops(stops, t):
    """Piecewise-linear hue lerp with shortest-arc wraparound (Scanhound §6)."""
    n = len(stops)
    if n == 0:
        return 0.0
    if n == 1:
        return stops[0]
    tc = min(max(t, 0.0), 1.0)
    scaled = tc * (n - 1)
    lo = int(math.floor(scaled))
    hi = min(lo + 1, n - 1)
    frac = scaled - lo
    h0, h1 = stops[lo], stops[hi]
    diff = h1 - h0
    if diff > 180.0:
        diff -= 360.0
    elif diff < -180.0:
        diff += 360.0
    return (h0 + frac * diff) % 360.0


def plasma_hue(pos, total, tick):
    """1-D three-sine plasma hue (Scanhound §3.1)."""
    t = float(tick)
    frac = pos / (total - 1) if total > 1 else 0.0
    v = math.sin(frac * _TAU + t / 20.0) + math.sin(frac * _TAU * 2.0 + t / 15.0) + math.sin(t / 10.0)
    return (((v / 3.0 + 1.0) / 2.0) * 360.0) % 360.0


def plasma_color(x, y, tick):
    """2-D RGB-channel plasma (Scanhound §3.2)."""
    phase = tick * 0.05
    return (int(math.sin(x * 0.1 + phase) * 127.0 + 128.0),
            int(math.sin(y * 0.1 + phase * 0.7) * 127.0 + 128.0),
            int(math.sin((x + y) * 0.1 + phase * 1.3) * 127.0 + 128.0))


# ---------------------------------------------------------------------------
# the ground wave — the panel's slow vertical breath
# ---------------------------------------------------------------------------
#
# Lineage: the ARF-TUI's `line_bg` (AgentInterposer,
# crates/arf-cli/src/tui/theme.rs) — a per-row HSV wave whose phase advances
# each tick, so the background travels up the screen getting darker and
# lighter. Three things are different here, and each is because this panel is
# a CRT instrument rather than a synthwave dashboard:
#
# 1. **It wears the tube.** ARF's wave is anchored on a fixed violet→cyan
#    palette. Here the wave is a perturbation of the *active family's* ground,
#    and the hue term only exists for families that have a hue ring at all —
#    a P1 green tube breathes green, an amber P3 breathes amber, and a
#    paper-white ground stays neutral and only changes in brightness. It also
#    goes through `crt_safe`, so the ceiling that governs every other colour
#    on the panel governs this one too.
#
# 2. **It is a hum bar, not a rainbow.** A real tube on an unregulated supply
#    shows exactly this: a slow bright band travelling vertically as mains
#    ripple beats against the frame rate. So the amplitude is small and mostly
#    in *value* — the effect is meant to read as the tube being alive, not as
#    a light show behind the instrument.
#
# 3. **It is quantised.** This is the part that matters mechanically. A wave
#    that recomputes every row's background to full precision every tick makes
#    every row differ from the last frame, which defeats the renderer's
#    row-level fast skip and turns every single frame into a full repaint —
#    i.e. it would undo the payload work in canvas.py and *cause* the tearing
#    it is supposed to decorate. Snapping the wave to WAVE_STEPS discrete
#    levels means a given row only changes when it crosses a step, so a few
#    rows change per frame instead of all of them, and the banding is finer
#    than the 8-bit ground can show anyway.

WAVE_STEPS = 12          # quantisation levels across the wave's amplitude
WAVE_PERIOD_ROWS = 2.2   # full cycle = this many screen heights
WAVE_SPEED = 0.42        # rows per tick the wave travels
WAVE_VALUE = 0.055       # ±V, in HSV units
WAVE_SAT = 0.06          # ±S, colour families only
WAVE_HUE = 7.0           # ±degrees, colour families only


def wave_phase(row, rows, tick, speed=WAVE_SPEED, period_rows=WAVE_PERIOD_ROWS):
    """Quantised sine of the ground wave at `row`, in [-1, 1].

    Quantised, not raw: see the note above — full-precision output here costs
    a whole-screen repaint every frame.
    """
    period = max(1.0, period_rows * max(1, rows))
    v = math.sin(((row + tick * speed) / period) * _TAU)
    return round(v * WAVE_STEPS) / WAVE_STEPS


def bg_wave(base, row, rows, tick, motion="full", hues=True):
    """`base` shifted by the ground wave for this row and tick.

    ``motion='off'`` returns `base` untouched. ``'reduced'`` gives a static
    brightness banding with no travel and no hue movement — the same contract
    the rest of the panel honours for reduced motion.
    """
    if motion == "off":
        return base
    if motion == "reduced":
        q = wave_phase(row, rows, 0, speed=0.0)
        dv, ds, dh = q * WAVE_VALUE * 0.5, 0.0, 0.0
    else:
        q = wave_phase(row, rows, tick)
        # Asymmetric on purpose: the trough is half as deep as the crest is
        # tall. A symmetric swing on a ground this dark crushes the bottom of
        # the wave to near-black, which reads as a fault rather than a breath.
        dv = q * WAVE_VALUE if q >= 0.0 else q * WAVE_VALUE * 0.5
        ds = q * WAVE_SAT if hues else 0.0
        dh = q * WAVE_HUE if hues else 0.0
    if dv == 0.0 and ds == 0.0 and dh == 0.0:
        return base
    h, sat, val = rgb_to_hsv(base)
    h = (h + dh) % 360.0
    sat = min(1.0, max(0.0, sat + ds))
    # The ground is very dark, so a linear V offset would swamp it. Lift from
    # a floor instead: the band brightens the tube, it does not wash it out.
    val = min(1.0, max(0.0, val + dv))
    return crt_safe(hsv_to_rgb(h, sat, val))


def breathing(tick, rate=0.08):
    """0.65 + 0.35*sin(tick*rate) — range [0.3, 1.0] (Scanhound §4)."""
    return 0.65 + 0.35 * math.sin(tick * rate)


def gradient(colors, n):
    """n colors interpolated smoothly across the given stops (>=1 stop)."""
    if n <= 0:
        return []
    if len(colors) == 1:
        return [colors[0]] * n
    out = []
    segs = len(colors) - 1
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0.0
        pos = t * segs
        k = min(int(pos), segs - 1)
        out.append(lerp_rgb(colors[k], colors[k + 1], pos - k))
    return out


def stepped(colors, n, steps=6):
    """The demoscene take on a gradient: `steps` hard bands rather than an
    airbrush — the ANSI-scene look is 16 colors and dither, not a smear."""
    if n <= 0:
        return []
    ramp = gradient(colors, max(2, steps))
    return [ramp[min(steps - 1, int(i * steps / max(1, n)))] for i in range(n)]


# ---------------------------------------------------------------------------
# Palette families — the panel wears the tube.
# ---------------------------------------------------------------------------

class Family:
    """A color family the whole panel is drawn from.

    ``ink``      body text
    ``dim``      recessive text / unlit meter runs
    ``hot``      the active/selection accent
    ``glow``     the brightest highlight (bevel tops, cursor)
    ``ground``   the panel background (dark)
    ``ground2``  a second ground for banding
    ``ramp``     4+ stops dark→bright used for block-shading bevels
    ``hues``     hue ring for rainbow/plasma sweeps (None = monochrome family:
                 sweeps become luminance sweeps of ``ramp``)
    """

    __slots__ = ("name", "ink", "dim", "hot", "glow", "ground", "ground2", "ramp", "hues", "warn", "bad", "ok", "face", "noise")

    def __init__(self, name, ink, dim_, hot, glow, ground, ground2, ramp, hues, warn=(255, 190, 70), bad=(255, 90, 90), ok=(120, 230, 140), face=None, noise=None):
        self.name = name
        self.ink, self.dim, self.hot, self.glow = ink, dim_, hot, glow
        self.ground, self.ground2 = ground, ground2
        self.ramp = tuple(ramp)
        self.hues = tuple(hues) if hues else None
        self.warn, self.bad, self.ok = warn, bad, ok
        # face: the letter-face ramp, TOP → BOTTOM (bright highlight → body → dark → cool foot),
        # in the Roy vertical-ramp idiom (chrome / blue / fire / copper / magenta / green).
        self.face = tuple(face) if face else tuple(reversed(self.ramp))
        # noise: the dark negative-space texture colour (dgry ░ field)
        self.noise = noise or lerp_rgb(ground2, dim_, 0.45)

    def face_at(self, t):
        """Face ramp sample: t=0 top highlight → t=1 foot. Discrete steps
        (no airbrush): quantised to the ramp's stops."""
        f = self.face
        n = len(f)
        return f[min(n - 1, max(0, int(t * n)))]

    def sweep(self, t):
        """Color at t∈[0,1] along the family's sweep (hue ring or ramp).
        Quantised to 1/720 and memoised — the sweep is sampled thousands of
        times per frame."""
        q = int((t % 1.0) * 720)
        cache = _SWEEP_CACHE.setdefault(id(self), {})
        c = cache.get(q)
        if c is None:
            if self.hues:
                c = crt_safe(hue_to_rgb(sample_hue_stops(self.hues, q / 720.0)))
            else:
                r = self.ramp
                c = r[min(len(r) - 1, int((q / 720.0) * len(r)))]
            cache[q] = c
        return c

    def shade(self, t):
        """Ramp sample at t∈[0,1] (dark→bright), interpolated."""
        r = self.ramp
        if t <= 0:
            return r[0]
        if t >= 1:
            return r[-1]
        pos = t * (len(r) - 1)
        k = int(pos)
        return lerp_rgb(r[k], r[min(k + 1, len(r) - 1)], pos - k)


def _ramp_from(hue, sat=0.75, n=6, lo=0.10, hi=0.98):
    return [crt_safe(hsv_to_rgb(hue, sat, lo + (hi - lo) * i / (n - 1))) for i in range(n)]


# P22 colour: the full nine-hue SMPTE-card family. Ink is warm white; hot is
# the electric cyan-blue of a Trinitron test card; ramp is a blue-steel bevel.
P22 = Family(
    "p22",
    ink=(226, 222, 214), dim_=(112, 108, 124), hot=(105, 205, 255), glow=(240, 248, 255),
    ground=(8, 6, 14), ground2=(14, 11, 24),
    ramp=[(18, 22, 60), (34, 48, 120), (60, 96, 190), (105, 160, 240), (170, 210, 255), (240, 248, 255)],
    hues=(200.0, 275.0, 320.0, 15.0, 45.0, 120.0, 175.0, 200.0),
    # Roy's blue face: white → chrome → lblu → blu → deep foot
    face=[(255, 255, 255), (200, 200, 208), (184, 192, 255), (88, 96, 255), (24, 32, 192), (10, 14, 96)],
)
GREEN = Family(
    "p1", ink=(160, 240, 160), dim_=(60, 110, 60), hot=(180, 255, 180), glow=(230, 255, 230),
    ground=(3, 12, 5), ground2=(6, 20, 8), ramp=_ramp_from(120, sat=0.7), hues=None,
    warn=(230, 255, 140), bad=(255, 200, 120), ok=(180, 255, 180),
    # green: spark → lgrn → grn → dark
    face=[(232, 255, 96), (125, 255, 125), (16, 192, 16), (8, 120, 8), (4, 60, 6)],
)
AMBER = Family(
    "p3", ink=(255, 200, 110), dim_=(120, 85, 40), hot=(255, 225, 150), glow=(255, 245, 210),
    ground=(14, 8, 2), ground2=(22, 13, 4), ramp=_ramp_from(38, sat=0.78), hues=None,
    warn=(255, 240, 160), bad=(255, 120, 60), ok=(255, 225, 150),
    # copper (Roy's own): white sparkle → lred → copper → brown → purple foot
    face=[(255, 255, 255), (255, 110, 90), (200, 106, 30), (138, 58, 8), (100, 24, 60)],
)
WHITE = Family(
    "p4", ink=(232, 232, 232), dim_=(110, 110, 110), hot=(255, 255, 255), glow=(255, 255, 255),
    ground=(8, 8, 9), ground2=(15, 15, 17),
    ramp=[(30, 30, 32), (70, 70, 74), (120, 120, 126), (170, 170, 176), (215, 215, 220), (255, 255, 255)],
    hues=None, warn=(255, 255, 255), bad=(255, 255, 255), ok=(255, 255, 255),
    # chrome: wht → lgry → dgry → dark
    face=[(255, 255, 255), (200, 200, 208), (160, 160, 168), (88, 88, 96), (48, 48, 56)],
)
DVST = Family(
    "dvst", ink=(150, 240, 190), dim_=(50, 100, 80), hot=(190, 255, 220), glow=(230, 255, 240),
    ground=(2, 14, 12), ground2=(4, 22, 20), ramp=_ramp_from(160, sat=0.7), hues=None,
    warn=(230, 255, 160), bad=(255, 200, 120), ok=(190, 255, 220),
    face=[(230, 255, 240), (150, 240, 190), (40, 190, 130), (16, 110, 80), (6, 50, 40)],
)
RADAR = Family(
    "p7", ink=(170, 220, 255), dim_=(60, 90, 130), hot=(120, 190, 255), glow=(220, 240, 255),
    ground=(3, 8, 20), ground2=(6, 14, 30),
    ramp=[(10, 20, 60), (25, 60, 130), (60, 120, 200), (120, 190, 255), (200, 240, 200), (230, 255, 170)],
    hues=(215.0, 200.0, 95.0, 75.0), warn=(230, 255, 170), bad=(255, 120, 120), ok=(120, 190, 255),
    face=[(235, 255, 200), (120, 190, 255), (60, 120, 200), (25, 60, 130), (10, 20, 60)],
)
PLASMA = Family(
    "pdp", ink=(236, 226, 220), dim_=(120, 100, 110), hot=(255, 130, 90), glow=(255, 240, 220),
    ground=(10, 6, 8), ground2=(18, 10, 14),
    ramp=[(50, 12, 30), (120, 30, 60), (200, 70, 60), (255, 130, 90), (255, 190, 130), (255, 240, 220)],
    hues=(350.0, 20.0, 45.0, 320.0, 350.0),
    # fire: yellow → orange → red → dark red → purple foot
    face=[(255, 240, 106), (255, 140, 60), (224, 32, 32), (122, 10, 10), (58, 10, 40)],
)

BLUE = Family(
    "p11", ink=(190, 215, 255), dim_=(70, 90, 140), hot=(150, 200, 255), glow=(235, 245, 255),
    ground=(4, 6, 20), ground2=(8, 12, 32), ramp=_ramp_from(222, sat=0.7), hues=None,
    warn=(220, 235, 255), bad=(255, 160, 160), ok=(150, 200, 255),
    face=[(255, 255, 255), (184, 192, 255), (88, 96, 255), (24, 32, 192), (10, 14, 96)],
)
PAPER = Family(
    "paperwhite", ink=(240, 232, 216), dim_=(120, 112, 100), hot=(255, 250, 235), glow=(255, 255, 250),
    ground=(12, 10, 8), ground2=(20, 17, 13),
    ramp=[(40, 36, 30), (90, 82, 70), (140, 130, 112), (190, 178, 158), (225, 215, 195), (255, 250, 235)],
    hues=None, warn=(255, 250, 235), bad=(255, 200, 180), ok=(255, 250, 235),
    face=[(255, 250, 235), (225, 215, 195), (170, 158, 138), (110, 100, 86), (60, 54, 46)],
)

# phosphor enum member → family (params.json 'phosphor' values)
FAMILIES = {
    "p22": P22, "p22_d93": P22, "p1": GREEN, "p31": GREEN, "p39": GREEN,
    "p3": AMBER, "p134": AMBER, "p4": WHITE, "paperwhite": PAPER,
    "p7": RADAR, "p11": BLUE, "dvst": DVST, "pdp": PLASMA,
}

# Permanent hue identity per parameter group (degrees) — "MASK is always the
# fifth hue". Order matches params.json's groups map.
GROUP_HUES = {
    "video": 200.0, "geometry": 275.0, "scan": 320.0, "vector": 15.0, "mask": 45.0,
    "phosphor": 120.0, "artifacts": 175.0, "burnin": 30.0, "system": 0.0,
}


def family_for_phosphor(name):
    """Map a phosphor enum member (p22, p22_d93, p1, p31, p3, dvst_p1, ...) to
    a Family. Unknown → P22 (colour)."""
    if not name:
        return P22
    n = str(name).lower()
    if n in FAMILIES:
        return FAMILIES[n]
    for key in sorted(FAMILIES, key=len, reverse=True):
        if n.startswith(key + "_"):
            return FAMILIES[key]
    if "dvst" in n or "storage" in n:
        return DVST
    if "amber" in n:
        return AMBER
    if "green" in n:
        return GREEN
    if "white" in n:
        return WHITE
    return P22

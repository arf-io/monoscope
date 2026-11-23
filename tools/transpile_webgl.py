#!/usr/bin/env python3
# transpile_webgl.py — generate "docs on a tube": a single self-contained
# HTML page that renders the Monoscope documentation (README + DESIGN +
# ROADMAP) THROUGH a WebGL2 port of the two-pass CRT simulation.
#
# Usage:
#   transpile_webgl.py [--out FILE] [--preset NAME ...]
#
# Output (default): <crt>/docs/Monoscope-docs.html
#   - no network dependencies, works from file://
#   - requires WebGL2 + EXT_color_buffer_float at runtime; shows an honest
#     fallback (the flat rendered document + a banner) without them.
#
# Mapping model (vs transpile_slang.py):
#   - v1 bakes ALL params as #defines per preset (like crtctl itself does),
#     so no const-demotion is needed: every global `const` initializer is a
#     constant expression once the defines are literals. The template GLSL
#     bodies are embedded ONCE; per-preset #define blocks are embedded per
#     preset; the page's JS concatenates prelude + defines + body into the
#     final GLSL ES 3.00 fragment sources.
#   - power_on / power_nonce / degauss_nonce / erase_nonce are NOT baked by
#     this script: the page appends them at shader-build time so the POWER /
#     DEGAUSS / ERASE buttons can bump a nonce and rebuild the program pair
#     (feedback textures persist across rebuilds — same semantics as crtctl
#     regenerating shaders + host renderer hot reload).
#   - warmup_time_scale is capped (WARMUP_CAP) so a fresh page lights fast
#     enough for a single headless screenshot; documented in the page intro.
#   - host renderer uniforms: iResolution/iTime/iTimeDelta/iFrame are fed from
#     requestAnimationFrame wall-clock timestamps; cursor uniforms are inert
#     constants (a document has no hardware cursor).
#   - y-convention: WebGL is GL (bottom-left origin) like host renderer, so no
#     flips anywhere EXCEPT the content-canvas upload, because a 2D canvas
#     is top-left origin. The flip is done as a 2D drawImage(scale(1,-1))
#     blit into a staging canvas rather than UNPACK_FLIP_Y_WEBGL: the
#     latter was observed to CORRUPT SRGB8_ALPHA8 canvas uploads on
#     Chromium's ANGLE/Vulkan path (half-row-shifted mixed orientations).
#     The state pass's data-pixel row 0 stays at the framebuffer bottom,
#     untouched by the content flip.
#   - sRGB: the content canvas uploads as SRGB8_ALPHA8 (WebGL2 core), so
#     sampling linearizes exactly like host renderer's sRGB sampler did; the
#     display pass appends an explicit linear->sRGB encode (pow 1/2.2, the
#     same convention the slang port uses) because the WebGL2 default
#     framebuffer does not gamma-encode on write.
#
# Python 3 stdlib only.

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CRT = os.path.dirname(HERE)

DEFAULT_PRESETS = [
    "smartdark-creme",
    "ibm-5151-mda-1981",
    "vt-amber",
    "bw-tv-p4",
    "vectrex-1982",
    "zenith-chromacolor-1971",
    "tek4010-storage",
    "pioneer-kuro-2008",
    "trinitron-pvm",
    "wornout-office",
]
DEFAULT_ACTIVE = "smartdark-creme"
DOC_FILES = ["README.md", "OPTICS-TUTORIAL.md", "DESIGN.md"]

# Cap warm-up pacing so a fresh page (and a single headless screenshot at
# defaults) shows a lit screen within ~2 s while keeping the choreography.
WARMUP_CAP = 0.04

# Params owned by the page's runtime (appended by JS at shader-build time).
RUNTIME_KEYS = {"power_on", "power_nonce", "degauss_nonce", "erase_nonce"}

TEMPLATES = {
    "state": "phosphor-state.glsl.tmpl",
    "display": "crt-display.glsl.tmpl",
}


def load_params():
    with open(os.path.join(CRT, "params.json")) as f:
        return json.load(f)["params"]


def load_template(name):
    with open(os.path.join(CRT, "templates", TEMPLATES[name])) as f:
        return f.read()


def fmt_value(spec, value):
    t = spec["type"]
    if t == "float":
        s = "%.6g" % float(value)
        return s if ("." in s or "e" in s) else s + ".0"
    if t == "int":
        return str(int(value))
    if t == "bool":
        return "1" if value in (True, "true", 1) else "0"
    if t == "enum":
        return str(spec["values"][value] if isinstance(value, str) else int(value))
    raise ValueError(t)


def define_block(params, preset_vals):
    lines = []
    for key in sorted(params):
        if key in RUNTIME_KEYS:
            continue
        spec = params[key]
        val = preset_vals.get(key, spec["default"])
        if key == "warmup_time_scale":
            val = min(float(val), WARMUP_CAP)
        lines.append("#define %s %s" % (spec["define"], fmt_value(spec, val)))
    return "\n".join(lines) + "\n"


def adapt_body(body):
    """Template GLSL -> GLSL ES 3.00 body. texture()/const arrays/structs
    are all valid ES 3.00 as-is; only the injection marker needs handling
    (the page's prelude defines CRT_PARAMS_INJECTED and the #define block
    is prepended before the body)."""
    return body.replace(
        "//@CRT_PARAMS@",
        "// (parameters baked by transpile_webgl.py; injected before this body)")


def build_docs():
    intro = """# GHOSTCRTTY — DOCS ON A TUBE

You are reading the Monoscope documentation THROUGH the simulation it
documents. A WebGL2 port of the two host renderer shader passes renders this
page: pass 1 (phosphor-state) turns the text into phosphor excitation in
an RGBA16F framebuffer fed back to itself (the fork's iChannel1), pass 2
(crt-display) pushes that through deflection, mask and glass. One preset
= one baked parameter set, exactly like crtctl's generated shaders.

Controls: mouse wheel / PgUp / PgDn / arrow keys / Home / End scroll the
page inside the tube. PRESET swaps tubes (fresh phosphor, replayed
warm-up). POWER replays the era-correct off/on choreography on the live
state — try it on bw-tv-p4. DEGAUSS fires the coil (color tubes wobble
and purity-swim). ERASE is the DVST page flash on tek4010-storage, and a
tube-swap excitation clear everywhere else.

Honest notes for this port: warm-up pacing is compressed (WARMUP RATE is
baked at 0.04 so the page lights fast); cursor strike overdrive and the
DVST hold-mode idle dimmer are inert (a document has no hardware
cursor); DECSCLM smooth-scroll and rolling scan are compiled but off in
these presets; scrolling this page is content moving, not terminal
scrolling, so long-persistence phosphors (ibm-5151-mda-1981) smear it
exactly as they would. The URL accepts ?preset=NAME&advance=SECONDS
(and &erasetest=SECONDS) for reproducible screenshots, and
?set=CRT_NAME:VALUE,... overrides any compiled shader define — the
OPTICS-TUTORIAL below uses that for its TRY IT experiments. Without
WebGL2 + EXT_color_buffer_float you get the flat page and an honest
banner, not a fake CRT.
"""
    parts = [intro]
    for name in DOC_FILES:
        with open(os.path.join(CRT, name)) as f:
            content = f.read()
        fences = sum(1 for ln in content.split("\n")
                     if ln.lstrip().startswith("```"))
        if fences % 2:
            # An unclosed fence would swallow every following file as one
            # giant code block (this actually happened: a stray ``` at the
            # end of DESIGN.md). Close it and say so.
            print("WARNING: %s has an unbalanced ``` fence; auto-closing"
                  % name, file=sys.stderr)
            content += "\n```\n"
        parts.append("\n\n---\n\n# ░░ FILE: %s ░░\n\n---\n\n" % name)
        parts.append(content)
    return "".join(parts)


def js_str_payload(obj):
    # `</` must not appear verbatim inside a <script> block.
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monoscope — docs on a tube</title>
<style>
  html, body { margin:0; height:100%; background:#08080a; color:#9a938c;
    font:13px/1.45 system-ui, sans-serif; overflow:hidden; }
  body { display:flex; flex-direction:column; }
  header { display:flex; gap:10px; align-items:center; padding:7px 12px;
    border-bottom:1px solid #1c1c20; flex:none; user-select:none; }
  .brand { color:#d8d2ca; font-weight:600; letter-spacing:.05em; }
  .brand small { color:#6d6862; font-weight:400; margin-left:6px; }
  select, button { background:#141417; color:#cfc9c0; border:1px solid #2a2a30;
    border-radius:4px; padding:4px 10px; font:inherit; cursor:pointer; }
  select:hover, button:hover { border-color:#4a4a52; }
  button.off { color:#e08080; border-color:#5a2a2a; }
  #hint { margin-left:auto; color:#5f5a54; font-size:12px; }
  #fallback { padding:12px 16px; background:#241a10; color:#e8b96a;
    border-bottom:1px solid #3a2c18; flex:none; white-space:pre-wrap; }
  #stage { flex:1; min-height:0; position:relative; background:#000; }
  #stage canvas { position:absolute; inset:0; width:100%; height:100%;
    display:block; }
  #err { position:absolute; inset:0; overflow:auto; margin:0; padding:14px;
    background:#180b0b; color:#e89090; font:12px/1.5 monospace; z-index:9; }
</style>
</head>
<body>
<header>
  <span class="brand">Monoscope<small>docs on a tube</small></span>
  <select id="preset" title="Tube preset (fresh phosphor, replayed warm-up)"></select>
  <button id="power" title="Era-correct power off/on choreography (shader rebuild, state preserved)">POWER</button>
  <button id="degauss" title="Degauss coil: raster shimmy + purity swim (~2 s PTC decay)">DEGAUSS</button>
  <button id="erase" title="DVST page flash / tube-swap excitation clear">ERASE</button>
  <span id="hint">wheel · PgUp/PgDn · arrows scroll the page inside the tube</span>
</header>
<div id="fallback" hidden></div>
<div id="stage"><canvas id="tube"></canvas></div>
<script>const CRT = @@DATA@@;</script>
<script>
'use strict';
/* Monoscope docs-on-a-tube runtime. Generated by transpile_webgl.py — do
   not edit the HTML; edit the generator. */
const Q = new URLSearchParams(location.search);

/* ---------------- theme (the "terminal" the tube scans) ---------------- */
const TH = {
  bg: '#0d0805', fg: '#eae3df', bright: '#fff6ea', dim: '#8d857c',
  h1: '#ffd9a0', h2: '#f0b868', h3: '#e0a860', code: '#9fe8a8',
  codeBg: '#181009', link: '#a8d8ff', rule: '#6a625a', bullet: '#f0b868',
  bar: '#c9bfae', barText: '#171006',
};
const COLORS = { '': TH.fg, b: TH.bright, i: TH.fg, c: TH.code, a: TH.link,
  h1: TH.h1, h2: TH.h2, h3: TH.h3, rule: TH.rule, bl: TH.bullet, dim: TH.dim };
const MONO = "ui-monospace, 'DejaVu Sans Mono', 'Cascadia Mono', Consolas, Menlo, monospace";

/* ---------------- DOM ---------------- */
const stage = document.getElementById('stage');
const tube = document.getElementById('tube');
const selPreset = document.getElementById('preset');
const btnPower = document.getElementById('power');
const btnDegauss = document.getElementById('degauss');
const btnErase = document.getElementById('erase');
const fbBanner = document.getElementById('fallback');

const doc = document.createElement('canvas');   // the offscreen "terminal"
const dctx = doc.getContext('2d');
const flipC = document.createElement('canvas'); // y-flip staging for GL upload
const fctx = flipC.getContext('2d');

/* ---------------- state ---------------- */
let W = 0, H = 0;
let active = (Q.get('preset') && CRT.presets[Q.get('preset')])
  ? Q.get('preset') : CRT.default;
let power = true, nPower = 1, nDegauss = 0, nErase = 0;
let gl = null, glOK = false;
let contentTex = null, stateTex = [null, null], fbos = [null, null], cur = 0;
let progState = null, progDisplay = null, vsShader = null;
let simTime = 0, frameIdx = 0, lastTs = null, docDirty = true;
let fontPx = 21, cw = 8, LH = 30, padX = 18, padTop = 8, cols = 80;
// The tube framebuffer works in DEVICE pixels: scale the type by
// devicePixelRatio so it reads ~15-16pt regardless of HiDPI (a bare
// px value looked half-size on 2x panels). ?fontsize=N is in CSS px.
{ const q = new URLSearchParams(location.search).get('fontsize');
  const cssPx = q ? Math.max(10, Math.min(40, parseInt(q, 10) || 21)) : 21;
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  fontPx = Math.round(cssPx * dpr);
  LH = Math.round(fontPx * 1.42); }
let lines = [], scrollY = 0, maxScroll = 0;
let preWarm = 2.0;

function setStatus(s) { document.documentElement.dataset.crtStatus = s; }
setStatus('booting');

/* ======================================================================
   Minimal markdown -> monospace line model.
   A line = { segs: [{t, st}], indent, bg }.  st in
   ''|b|i|c|a|h1|h2|h3|rule|bl|dim ; bg 'code' draws the fence background.
   ====================================================================== */
function plainLen(segs) { let n = 0; for (const s of segs) n += s.t.length; return n; }

const RE_INLINE = /(`+)(.+?)\1|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]*)\)|\*([^*\n]+)\*/g;
function inline(s) {
  const out = []; let last = 0; let m;
  RE_INLINE.lastIndex = 0;
  while ((m = RE_INLINE.exec(s))) {
    if (m.index > last) out.push({ t: s.slice(last, m.index), st: '' });
    if (m[2] !== undefined) out.push({ t: m[2], st: 'c' });
    else if (m[3] !== undefined) out.push({ t: m[3], st: 'b' });
    else if (m[4] !== undefined) out.push({ t: m[4], st: 'a' });
    else out.push({ t: m[6], st: 'i' });
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push({ t: s.slice(last), st: '' });
  return out;
}

function wrapSegs(segs, width, first, hang, bg, styleOverride) {
  width = Math.max(8, width);
  const words = [];
  for (const g of segs) {
    for (const p of g.t.split(/(\s+)/)) {
      if (p === '') continue;
      words.push({ t: p, st: styleOverride || g.st, sp: /^\s+$/.test(p) });
    }
  }
  const out = []; let curSegs = [], len = 0, indent = first;
  const flush = () => {
    while (curSegs.length && curSegs[curSegs.length - 1].sp) {
      len -= curSegs.pop().t.length;
    }
    out.push({ segs: curSegs, indent, bg: bg || null });
    curSegs = []; len = 0; indent = hang;
  };
  for (const w of words) {
    if (w.sp) {
      if (len > 0 && len + 1 <= width - indent) { curSegs.push({ t: ' ', st: '' }); len++; }
      continue;
    }
    let t = w.t;
    if (len > 0 && len + t.length > width - indent) flush();
    while (t.length > 0) {
      const room = width - indent - len;
      if (t.length <= room) { curSegs.push({ t, st: w.st }); len += t.length; t = ''; }
      else {
        const chunk = Math.max(1, room);
        curSegs.push({ t: t.slice(0, chunk), st: w.st });
        t = t.slice(chunk);
        flush();
      }
    }
  }
  if (curSegs.length || out.length === 0) flush();
  return out;
}

function build(md) {
  lines = [];
  const push = (segs, indent, bg) =>
    lines.push({ segs, indent: indent || 0, bg: bg || null });
  const blank = () => {
    const last = lines[lines.length - 1];
    if (last && plainLen(last.segs) === 0 && !last.bg) return;
    push([]);
  };
  const src = md.split('\n');
  let i = 0, para = [];
  const flushPara = () => {
    if (!para.length) return;
    for (const L of wrapSegs(inline(para.join(' ')), cols, 0, 0)) lines.push(L);
    para = [];
  };
  while (i < src.length) {
    const ln = src[i];
    if (/^\s*```/.test(ln)) {                            // fenced code
      flushPara(); blank(); i++;
      while (i < src.length && !/^\s*```/.test(src[i])) {
        let t = src[i]; const w = cols - 2;
        if (t.length === 0) push([{ t: '', st: 'c' }], 1, 'code');
        while (t.length > 0) {
          push([{ t: t.slice(0, w), st: 'c' }], 1, 'code');
          t = t.slice(w);
        }
        i++;
      }
      i++; blank(); continue;
    }
    if (/^\s*$/.test(ln)) { flushPara(); blank(); i++; continue; }
    const h = ln.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      flushPara(); blank();
      const lvl = h[1].length;
      const st = lvl === 1 ? 'h1' : lvl === 2 ? 'h2' : 'h3';
      const segs = inline(h[2].replace(/\s*#+\s*$/, ''));
      for (const L of wrapSegs(segs, cols, 0, 0, null, st)) lines.push(L);
      const n = Math.min(cols, Math.max(plainLen(segs), lvl === 1 ? 24 : 16));
      if (lvl === 1) push([{ t: '═'.repeat(n), st: 'h1' }]);
      else if (lvl === 2) push([{ t: '─'.repeat(n), st: 'rule' }]);
      blank(); i++; continue;
    }
    if (/^ {0,3}([-*_])( *\1){2,} *$/.test(ln)) {        // hr
      flushPara(); blank();
      push([{ t: '─'.repeat(cols), st: 'rule' }]);
      blank(); i++; continue;
    }
    if (ln.trim().startsWith('|')) {                      // table
      flushPara();
      const block = [];
      while (i < src.length && src[i].trim().startsWith('|')) {
        block.push(src[i].trim()); i++;
      }
      emitTable(block); continue;
    }
    const lm = ln.match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/);
    if (lm) {                                             // list item
      flushPara();
      let item = lm[3]; i++;
      while (i < src.length && /^\s{2,}\S/.test(src[i])
             && !/^\s*([-*+]|\d+\.)\s+/.test(src[i])
             && !src[i].trim().startsWith('|') && !/^\s*```/.test(src[i])) {
        item += ' ' + src[i].trim(); i++;
      }
      const marker = /^\d+\.$/.test(lm[2]) ? lm[2] + ' ' : '• ';
      const ind = 1 + Math.floor(lm[1].length / 2) * 2;
      const segs = [{ t: marker, st: 'bl' }].concat(inline(item));
      for (const L of wrapSegs(segs, cols, ind, ind + marker.length)) lines.push(L);
      continue;
    }
    const qm = ln.match(/^\s*>\s?(.*)$/);
    if (qm) {                                             // blockquote
      flushPara();
      const segs = [{ t: '▎ ', st: 'rule' }].concat(inline(qm[1]));
      for (const L of wrapSegs(segs, cols, 1, 3, null, 'dim')) lines.push(L);
      i++; continue;
    }
    para.push(ln.trim()); i++;
  }
  flushPara();
}

function emitTable(block) {
  const rows = block.map(r =>
    r.replace(/^\|/, '').replace(/\|\s*$/, '').split('|').map(c => c.trim()));
  let header = null, body = rows;
  if (rows.length > 1 && rows[1].length &&
      rows[1].every(c => /^:?-{2,}:?$/.test(c))) {
    header = rows[0]; body = rows.slice(2);
  }
  const all = (header ? [header] : []).concat(body);
  if (!all.length) return;
  const n = Math.max.apply(null, all.map(r => r.length));
  for (const r of all) while (r.length < n) r.push('');
  const cellSegs = all.map(r => r.map(c => inline(c)));
  const nat = new Array(n).fill(3);
  for (const r of cellSegs) r.forEach((c, j) => { nat[j] = Math.max(nat[j], plainLen(c)); });
  const usable = cols - 2 - 3 * (n - 1);
  const widths = nat.slice();
  let total = widths.reduce((a, b) => a + b, 0);
  while (total > usable) {
    let j = 0;
    for (let k = 1; k < n; k++) if (widths[k] > widths[j]) j = k;
    if (widths[j] <= 6) break;
    widths[j]--; total--;
  }
  const blankLine = () => lines.push({ segs: [], indent: 0, bg: null });
  const emitRow = (segsRow, isHead) => {
    const wrapped = segsRow.map((c, j) =>
      wrapSegs(c, widths[j], 0, 0, null, isHead ? 'b' : null));
    const hh = Math.max.apply(null, wrapped.map(w => w.length));
    for (let k = 0; k < hh; k++) {
      const segs = [];
      for (let j = 0; j < n; j++) {
        const L = (wrapped[j][k] && wrapped[j][k].segs) || [];
        let len = 0;
        for (const s of L) { segs.push(s); len += s.t.length; }
        if (len < widths[j]) segs.push({ t: ' '.repeat(widths[j] - len), st: '' });
        if (j < n - 1) segs.push({ t: ' │ ', st: 'rule' });
      }
      lines.push({ segs, indent: 1, bg: null });
    }
  };
  blankLine();
  if (header) {
    emitRow(cellSegs[0], true);
    const segs = [];
    for (let j = 0; j < n; j++) {
      segs.push({ t: '─'.repeat(widths[j]), st: 'rule' });
      if (j < n - 1) segs.push({ t: '─┼─', st: 'rule' });
    }
    lines.push({ segs, indent: 1, bg: null });
    for (let r = 1; r < cellSegs.length; r++) emitRow(cellSegs[r], false);
  } else {
    for (const r of cellSegs) emitRow(r, false);
  }
  blankLine();
}

/* ---------------- drawing the terminal page ---------------- */
function fontFor(st) {
  const bold = st === 'b' || st === 'h1' || st === 'h2' || st === 'h3' || st === 'bl';
  const italic = st === 'i';
  return (italic ? 'italic ' : '') + (bold ? 'bold ' : '') + fontPx + 'px ' + MONO;
}

function drawDoc() {
  dctx.fillStyle = TH.bg;
  dctx.fillRect(0, 0, W, H);
  dctx.textBaseline = 'top';
  const visH = H - LH;                       // status bar eats the last row
  const first = Math.max(0, Math.floor(scrollY / LH));
  const frac = scrollY - first * LH;
  const rows = Math.ceil(visH / LH) + 1;
  for (let r = 0; r < rows; r++) {
    const li = first + r;
    if (li >= lines.length) break;
    const y = padTop + r * LH - frac;
    if (y > visH) break;
    const line = lines[li];
    if (line.bg === 'code') {
      dctx.fillStyle = TH.codeBg;
      dctx.fillRect(padX - 8, y - Math.ceil((LH - fontPx) / 2) + 1, W - 2 * padX + 16, LH);
    }
    let col = line.indent;
    for (const s of line.segs) {
      if (!s.t) continue;
      dctx.font = fontFor(s.st);
      dctx.fillStyle = COLORS[s.st] || TH.fg;
      dctx.fillText(s.t, padX + col * cw, y);
      col += s.t.length;
    }
  }
  /* status bar (reverse video, like a real terminal — burn-in bait) */
  const sy = H - LH;
  dctx.fillStyle = TH.bar;
  dctx.fillRect(0, sy, W, LH);
  dctx.fillStyle = TH.barText;
  dctx.font = 'bold ' + fontPx + 'px ' + MONO;
  const pct = maxScroll > 0 ? Math.round(100 * scrollY / maxScroll) : 100;
  const label = ' GHOSTCRTTY DOCS · ' + active.toUpperCase() +
    (power ? '' : ' · [POWER OFF]');
  const right = 'L' + (first + 1) + '/' + lines.length + ' · ' + pct + '% ';
  dctx.fillText(label, 8, sy + Math.round((LH - fontPx) / 2));
  dctx.fillText(right, W - 8 - right.length * cw, sy + Math.round((LH - fontPx) / 2));
  /* scrollbar */
  if (maxScroll > 0) {
    const trackH = sy - padTop;
    const thumbH = Math.max(24, trackH * (sy / (maxScroll + sy)));
    const thumbY = padTop + (trackH - thumbH) * (scrollY / maxScroll);
    dctx.fillStyle = TH.dim;
    dctx.fillRect(W - 5, thumbY, 3, thumbH);
  }
  docDirty = true;
}

function relayout() {
  // Type size: preset base (CSS px) scaled by devicePixelRatio, because
  // the framebuffer is device-pixel-space — 21 CSS px reads ~15.7pt on
  // every display. ?fontsize=N (CSS px) overrides the preset base.
  { const q = new URLSearchParams(location.search).get('fontsize');
    const base = q ? Math.max(10, Math.min(40, parseInt(q, 10) || 21))
                   : Math.max(21, CRT.presets[active].font || 21);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    fontPx = Math.round(base * dpr); }
  dctx.font = fontPx + 'px ' + MONO;
  cw = dctx.measureText('M').width;
  LH = Math.round(fontPx * 1.45);
  padX = Math.round(cw * 2);
  cols = Math.max(40, Math.floor((W - 2 * padX - 8) / cw));
  const keep = maxScroll > 0 ? scrollY / maxScroll : 0;
  build(CRT.docs);
  const visH = H - LH - padTop;
  maxScroll = Math.max(0, lines.length * LH - visH + LH);
  scrollY = Math.min(maxScroll, Math.round(keep * maxScroll));
  drawDoc();
}

function scrollBy(dy) {
  const y = Math.max(0, Math.min(maxScroll, scrollY + dy));
  if (y !== scrollY) { scrollY = y; drawDoc(); }
}

/* ======================================================================
   WebGL2 pipeline: content canvas -> [pass A: phosphor-state, RGBA16F
   ping-pong self-feedback] -> [pass B: crt-display -> default FB].
   ====================================================================== */
const VS = '#version 300 es\n' +
  'void main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));' +
  'gl_Position=vec4(p*2.0-1.0,0.0,1.0);}';

const PRELUDE = [
  '#version 300 es',
  'precision highp float;',
  'precision highp int;',
  'uniform highp sampler2D iChannel0;',
  'uniform highp sampler2D iChannel1;',
  'uniform vec3 iResolution;',
  'uniform float iTime;',
  'uniform float iTimeDelta;',
  'uniform int iFrame;',
  'out vec4 _gc_FragColor;',
  '// host renderer cursor uniforms: inert in the browser (no hardware cursor).',
  'const vec4 iCurrentCursor = vec4(-1e6, -1e6, 0.0, 0.0);',
  'const vec4 iCurrentCursorColor = vec4(0.0);',
  '#define iTimeCursorChange iTime',
  '#define CRT_PARAMS_INJECTED 1',
  '',
].join('\n');

const MAIN_STATE =
  '\nvoid main(){ mainImage(_gc_FragColor, gl_FragCoord.xy); }\n';
const MAIN_DISPLAY =
  '\nvoid main(){ mainImage(_gc_FragColor, gl_FragCoord.xy);\n' +
  '  // host renderer encoded via GL_FRAMEBUFFER_SRGB on write; WebGL2 default\n' +
  '  // framebuffer wants encoded values explicitly (same as slang port).\n' +
  '  _gc_FragColor.rgb = pow(clamp(_gc_FragColor.rgb, 0.0, 1.0), vec3(1.0/2.2));\n' +
  '  _gc_FragColor.a = 1.0; }\n';

function fail(msg) {
  fbBanner.hidden = false;
  fbBanner.textContent = '⚠ ' + msg;
  setStatus('fallback');
}

function showError(msg) {
  const pre = document.createElement('pre');
  pre.id = 'err';
  pre.textContent = msg;
  stage.appendChild(pre);
  setStatus('error');
}

function compile(type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(sh);
    gl.deleteShader(sh);
    throw new Error('shader compile failed:\n' + log);
  }
  return sh;
}

function makeProgram(fsSrc) {
  const fs = compile(gl.FRAGMENT_SHADER, fsSrc);
  const p = gl.createProgram();
  gl.attachShader(p, vsShader);
  gl.attachShader(p, fs);
  gl.linkProgram(p);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(p);
    gl.deleteProgram(p);
    throw new Error('program link failed:\n' + log);
  }
  return {
    p,
    u: {
      iResolution: gl.getUniformLocation(p, 'iResolution'),
      iTime: gl.getUniformLocation(p, 'iTime'),
      iTimeDelta: gl.getUniformLocation(p, 'iTimeDelta'),
      iFrame: gl.getUniformLocation(p, 'iFrame'),
      iChannel0: gl.getUniformLocation(p, 'iChannel0'),
      iChannel1: gl.getUniformLocation(p, 'iChannel1'),
    },
  };
}

function nonceDefines() {
  return '#define CRT_POWER_ON ' + (power ? 1 : 0) + '\n' +
         '#define CRT_POWER_NONCE ' + nPower + '\n' +
         '#define CRT_DEGAUSS_NONCE ' + nDegauss + '\n' +
         '#define CRT_ERASE_NONCE ' + nErase + '\n';
}

function fragSource(pass) {
  const pv = CRT.presets[active];
  let extra = '';
  if (Q.has('debug')) {
    /* view the raw phosphor-state texture (pass B passthrough) */
    extra = '#undef CRT_DEBUG_STATE\n#define CRT_DEBUG_STATE 1\n';
  }
  if (Q.has('set')) {
    /* diagnostic define overrides: ?set=CRT_HALATION:0.0,CRT_MASK_TYPE:0 */
    for (const kv of Q.get('set').split(',')) {
      const m = kv.match(/^(CRT_\w+):(.+)$/);
      if (m) extra += '#undef ' + m[1] + '\n#define ' + m[1] + ' ' + m[2] + '\n';
    }
  }
  return PRELUDE + pv.defines + nonceDefines() + extra +
    (pass === 'state' ? CRT.bodyState + MAIN_STATE
                      : CRT.bodyDisplay + MAIN_DISPLAY);
}

function buildShaders() {
  if (progState) gl.deleteProgram(progState.p);
  if (progDisplay) gl.deleteProgram(progDisplay.p);
  progState = makeProgram(fragSource('state'));
  progDisplay = makeProgram(fragSource('display'));
}

function initGL() {
  gl = tube.getContext('webgl2', { alpha: false, antialias: false,
    depth: false, stencil: false, preserveDrawingBuffer: true });
  if (!gl) {
    fail('WebGL2 is not available — showing the flat document instead of the CRT pipeline.');
    return false;
  }
  if (!gl.getExtension('EXT_color_buffer_float')) {
    fail('EXT_color_buffer_float is missing: the phosphor-state pass needs an RGBA16F feedback framebuffer (the capability the host renderer fork provides natively). Showing the flat document instead.');
    return false;
  }
  gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
  gl.disable(gl.DEPTH_TEST);
  gl.disable(gl.BLEND);
  vsShader = compile(gl.VERTEX_SHADER, VS);
  return true;
}

function texParams() {
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
}

function alloc() {
  gl.activeTexture(gl.TEXTURE0);
  if (!contentTex) contentTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, contentTex);
  texParams();
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.SRGB8_ALPHA8, W, H, 0,
    gl.RGBA, gl.UNSIGNED_BYTE, null);
  for (let k = 0; k < 2; k++) {
    if (!stateTex[k]) stateTex[k] = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, stateTex[k]);
    texParams();
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, W, H, 0,
      gl.RGBA, gl.HALF_FLOAT, null);
    if (!fbos[k]) fbos[k] = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbos[k]);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0,
      gl.TEXTURE_2D, stateTex[k], 0);
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      throw new Error('RGBA16F framebuffer incomplete');
    }
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  cur = 0;
  docDirty = true;
}

function zeroState() {
  for (let k = 0; k < 2; k++) {
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, stateTex[k]);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, W, H, 0,
      gl.RGBA, gl.HALF_FLOAT, null);
  }
  cur = 0;
}

function uploadDoc() {
  /* 2D canvas is top-left origin; GL textures are bottom-left. Flip via a
     2D raster blit (UNPACK_FLIP_Y_WEBGL corrupts SRGB8_ALPHA8 canvas
     uploads on Chromium's ANGLE/Vulkan path — verified with a probe).
     This affects ONLY the content upload — the state pass's data-pixel
     row stays at the bottom of its own framebuffer, exactly like
     host renderer/GL. */
  fctx.setTransform(1, 0, 0, -1, 0, H);
  fctx.drawImage(doc, 0, 0);
  fctx.setTransform(1, 0, 0, 1, 0, 0);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, contentTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.SRGB8_ALPHA8,
    gl.RGBA, gl.UNSIGNED_BYTE, flipC);
  docDirty = false;
}

function setUniforms(pr, dt) {
  gl.uniform3f(pr.u.iResolution, W, H, 1.0);
  gl.uniform1f(pr.u.iTime, simTime);
  gl.uniform1f(pr.u.iTimeDelta, dt);
  gl.uniform1i(pr.u.iFrame, frameIdx);
  if (pr.u.iChannel0) gl.uniform1i(pr.u.iChannel0, 0);
  if (pr.u.iChannel1) gl.uniform1i(pr.u.iChannel1, 1);
}

function bindTex(unit, tex) {
  gl.activeTexture(gl.TEXTURE0 + unit);
  gl.bindTexture(gl.TEXTURE_2D, tex);
}

function stepSim(dt, present) {
  if (docDirty) uploadDoc();
  simTime += dt;
  /* pass A: phosphor state (self-feedback ping-pong) */
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbos[cur]);
  gl.viewport(0, 0, W, H);
  gl.useProgram(progState.p);
  bindTex(0, contentTex);
  bindTex(1, stateTex[1 - cur]);
  setUniforms(progState, dt);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  /* pass B: display (pure function of pass A -> safe to skip off-screen) */
  if (present) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, W, H);
    gl.useProgram(progDisplay.p);
    bindTex(0, stateTex[cur]);
    setUniforms(progDisplay, dt);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  cur = 1 - cur;
  frameIdx++;
}

/* deterministic pre-roll: same physics, coarser dt (the state pass
   integrates decay in closed form, so large steps stay exact) */
function advanceSim(sec) {
  if (!(sec > 0)) return;
  const dt = 0.05, n = Math.round(sec / dt);
  for (let i = 0; i < n; i++) stepSim(dt, i === n - 1);
}

function sizeChanged() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = stage.getBoundingClientRect();
  const w = Math.max(320, Math.min(3200, Math.round(r.width * dpr)));
  const h = Math.max(240, Math.min(2000, Math.round(r.height * dpr)));
  return w !== W || h !== H;
}

function handleResize() {
  sizeCanvas();
  relayout();
  if (Q.has('pattern')) testPattern();
  if (glOK) {
    alloc();
    zeroState();
    /* a resize is a mode change: fresh feedback replays the warm-up;
       re-run the pre-roll so the screen is not dark for warm-up seconds */
    preRoll();
  }
}

function preRoll() {
  advanceSim(preWarm);
  if (Q.has('erasetest')) {
    doErase();
    advanceSim(parseFloat(Q.get('erasetest')) || 0.35);
  }
  if (Q.has('poweroff')) {
    doPower();
    advanceSim(parseFloat(Q.get('poweroff')) || 0.25);
  }
}

function frame(ts) {
  /* headless/booting layouts can settle after load: track the real size
     (the CSS-stretched canvas would otherwise silently distort) */
  if (sizeChanged()) handleResize();
  const dt = lastTs === null ? 1 / 60
    : Math.min(Math.max((ts - lastTs) / 1000, 0.0001), 0.1);
  lastTs = ts;
  stepSim(dt, true);
  requestAnimationFrame(frame);
}

/* ---------------- controls ---------------- */
function doPower() {
  power = !power; nPower++;
  buildShaders();
  btnPower.classList.toggle('off', !power);
  drawDoc();
}
function doDegauss() { nDegauss++; buildShaders(); }
function doErase() { nErase++; buildShaders(); }

function switchPreset(name) {
  if (!CRT.presets[name]) return;
  active = name; power = true;
  btnPower.classList.remove('off');
  relayout();
  if (glOK) { zeroState(); buildShaders(); }
}

function fallbackMode() {
  tube.remove();
  doc.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block;';
  stage.appendChild(doc);
  btnPower.disabled = btnDegauss.disabled = btnErase.disabled = true;
}

/* ---------------- input ---------------- */
stage.addEventListener('wheel', (e) => {
  e.preventDefault();
  const dy = e.deltaMode === 1 ? e.deltaY * LH : e.deltaY;
  scrollBy(dy);
}, { passive: false });

window.addEventListener('keydown', (e) => {
  const page = H - 2 * LH;
  let dy = null;
  if (e.key === 'PageDown' || (e.key === ' ' && !e.shiftKey)) dy = page;
  else if (e.key === 'PageUp' || (e.key === ' ' && e.shiftKey)) dy = -page;
  else if (e.key === 'ArrowDown') dy = LH;
  else if (e.key === 'ArrowUp') dy = -LH;
  else if (e.key === 'Home') { scrollBy(-scrollY); e.preventDefault(); return; }
  else if (e.key === 'End') { scrollBy(maxScroll); e.preventDefault(); return; }
  if (dy !== null) { e.preventDefault(); scrollBy(dy); }
});

selPreset.addEventListener('change', () => switchPreset(selPreset.value));
btnPower.addEventListener('click', doPower);
btnDegauss.addEventListener('click', doDegauss);
btnErase.addEventListener('click', doErase);

let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (sizeChanged()) handleResize(); }, 150);
});

/* ---------------- boot ---------------- */
function sizeCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = stage.getBoundingClientRect();
  W = Math.max(320, Math.min(3200, Math.round(r.width * dpr)));
  H = Math.max(240, Math.min(2000, Math.round(r.height * dpr)));
  tube.width = W; tube.height = H;
  doc.width = W; doc.height = H;
  flipC.width = W; flipC.height = H;
}

function testPattern() {
  /* diagnostic content (?pattern=bars): isolated bars make any sampling
     displacement directly measurable in a screenshot */
  dctx.fillStyle = '#000'; dctx.fillRect(0, 0, W, H);
  dctx.fillStyle = '#fff';
  for (const x of [100, 400, 800, 1100]) if (x < W - 3) dctx.fillRect(x, 0, 3, H);
  for (const y of [100, 400, 700]) if (y < H - 3) dctx.fillRect(0, y, W, 3);
  dctx.fillRect(20, 20, 60, 60);
  docDirty = true;
}

function boot() {
  for (const name of CRT.order) {
    const o = document.createElement('option');
    o.value = name;
    o.textContent = name;
    o.title = CRT.presets[name].desc;
    selPreset.appendChild(o);
  }
  selPreset.value = active;
  sizeCanvas();
  relayout();
  if (Q.has('scroll')) scrollBy(parseFloat(Q.get('scroll')) || 0);
  if (Q.has('pattern')) testPattern();
  if (!initGL()) { fallbackMode(); drawDoc(); return; }
  try {
    alloc();
    buildShaders();
    glOK = true;
    if (Q.has('advance')) preWarm = parseFloat(Q.get('advance')) || 0;
    preRoll();
    setStatus('running');
    requestAnimationFrame(frame);
  } catch (err) {
    showError('Monoscope pipeline failed honestly:\n\n' + err.message);
    console.error(err);
  }
}

boot();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(CRT, "docs", "monoscope-docs.html"))
    ap.add_argument("--preset", action="append",
                    help="preset name (repeatable); default: the curated set")
    args = ap.parse_args()

    params = load_params()
    names = args.preset or DEFAULT_PRESETS

    presets = {}
    for name in names:
        path = os.path.join(CRT, "presets", name + ".json")
        with open(path) as f:
            pj = json.load(f)
        pv = pj.get("params", {})
        font_pt = pj.get("terminal", {}).get("font-size")
        presets[name] = {
            "defines": define_block(params, pv),
            "desc": pj.get("description", ""),
            "font": round(font_pt * 4 / 3) if font_pt else None,
        }

    default = DEFAULT_ACTIVE if DEFAULT_ACTIVE in presets else names[0]
    data = {
        "bodyState": adapt_body(load_template("state")),
        "bodyDisplay": adapt_body(load_template("display")),
        "presets": presets,
        "order": names,
        "default": default,
        "docs": build_docs(),
    }

    html = TEMPLATE.replace("@@DATA@@", js_str_payload(data))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(html)
    print("wrote %s (%d bytes, %d presets: %s)"
          % (args.out, len(html), len(names), ", ".join(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

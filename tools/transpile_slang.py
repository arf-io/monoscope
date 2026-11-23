#!/usr/bin/env python3
# transpile_slang.py — generate the libretro/RetroArch slang port of the
# monoscope CRT simulation from the single source of truth (params.json +
# the two Ghostty shader templates).
#
# Usage:
#   transpile_slang.py [--out DIR] [--preset NAME ...] [--validate]
#
# Output layout (default DIR = <crt>/slang):
#   DIR/monoscope.slangp              -> the default preset (smartdark-creme)
#   DIR/presets/<name>.slangp          one per preset
#   DIR/generated/<name>/phosphor-state.slang
#   DIR/generated/<name>/crt-display.slang
#
# Mapping model:
#   - Params used in preprocessor conditionals (#if/#elif) are STRUCTURAL:
#     baked as #defines per preset variant (matches how slang shader packs
#     ship families of compiled variants).
#   - All other params become runtime `#pragma parameter` knobs (RetroArch
#     menu sliders), with the preset's value as the default.
#   - Ghostty uniforms are provided by a compatibility prelude:
#     iResolution/iTime/iTimeDelta/iFrame from slang semantics, cursor
#     uniforms as inert constants (no hardware cursor in an emulator),
#     y-flipped sampling + fragCoord so the templates' GL y-up convention
#     is preserved end to end (data pixel row stays at the bottom).
#   - Pass 0 (PhosphorState) renders to a float framebuffer and reads its
#     own previous frame via the slang feedback alias; pass 1 reads pass 0
#     as Source. The final pass gamma-encodes explicitly (Ghostty relied
#     on GL_FRAMEBUFFER_SRGB).
#   - scan_lines gains emulator superpowers: 0 = auto (use the core's
#     native vertical resolution, OriginalSize.y).
#
# Python 3 stdlib only. Validate with --validate (splits stages and runs
# glslangValidator --target-env vulkan1.1 on each, exactly the front end
# RetroArch itself uses).

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRT = os.path.dirname(HERE)

# ---------------------------------------------------------------------------
# Slang spec knobs (verified against libretro/slang-shaders README and
# working feedback shaders; adjust here if the spec check finds drift).
# ---------------------------------------------------------------------------
SPEC = {
    "feedback_suffix": "Feedback",   # alias "PhosphorState" -> sampler
                                     # "PhosphorStateFeedback"
    "builtins_ubo": ["MVP", "OutputSize", "OriginalSize", "SourceSize",
                     "FrameCount"],
    "float_format_pragma": "R16G16B16A16_SFLOAT",
}

TEMPLATES = {
    "phosphor-state": "phosphor-state.glsl.tmpl",
    "crt-display": "crt-display.glsl.tmpl",
}

VERTEX_STAGE = """#pragma stage vertex
layout(location = 0) in vec4 Position;
layout(location = 1) in vec2 TexCoord;
layout(location = 0) out vec2 vTexCoord;

void main()
{
   gl_Position = global.MVP * Position;
   vTexCoord = TexCoord;
}
"""


def load_params():
    with open(os.path.join(CRT, "params.json")) as f:
        return json.load(f)["params"]


def load_template(name):
    with open(os.path.join(CRT, "templates", TEMPLATES[name])) as f:
        return f.read()


def structural_keys(params, bodies):
    """Params whose define appears in a preprocessor conditional in either
    template are structural (compile-time)."""
    cond_lines = []
    for body in bodies.values():
        for line in body.split("\n"):
            s = line.strip()
            if s.startswith(("#if", "#elif")):
                cond_lines.append(s)
    blob = "\n".join(cond_lines)
    out = set()
    for key, spec in params.items():
        if re.search(r"\b%s\b" % re.escape(spec["define"]), blob):
            out.add(key)
    # Nonces/system triggers make no sense as menu sliders either.
    for key, spec in params.items():
        if spec.get("group") == "system":
            out.add(key)
    return out


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


def runtime_param_lines(params, runtime_keys, preset_vals):
    """#pragma parameter lines + UBO members + defines for runtime knobs."""
    pragmas, members, defines = [], [], []
    for key in runtime_keys:
        spec = params[key]
        t = spec["type"]
        default = preset_vals.get(key, spec["default"])
        if t == "enum":
            dflt = spec["values"][default] if isinstance(default, str) else int(default)
            lo, hi, step = 0, max(spec["values"].values()), 1
        elif t == "bool":
            dflt = 1 if default in (True, "true", 1) else 0
            lo, hi, step = 0, 1, 1
        else:
            dflt = default
            lo, hi, step = spec["min"], spec["max"], spec.get("step", 0.01)
        label = spec.get("label", key)
        pragmas.append(
            '#pragma parameter crt_%s "%s" %s %s %s %s'
            % (key, label.replace('"', "'"),
               fmt_value({"type": "float"}, dflt),
               fmt_value({"type": "float"}, lo),
               fmt_value({"type": "float"}, hi),
               fmt_value({"type": "float"}, step)))
        members.append("    float crt_%s;" % key)
        if t == "float":
            if key == "scan_lines_placeholder":
                pass
            defines.append("#define %s params.crt_%s" % (spec["define"], key))
        elif t == "int":
            if key == "scan_lines":
                # 0 = auto: use the core's native line count.
                defines.append(
                    "#define %s int(params.crt_%s < 1.0 ? "
                    "params.OriginalSize.y : params.crt_%s)"
                    % (spec["define"], key, key))
            else:
                defines.append("#define %s int(params.crt_%s)"
                               % (spec["define"], key))
        else:  # bool / enum -> integer semantics
            defines.append("#define %s int(params.crt_%s)"
                           % (spec["define"], key))
    return pragmas, members, defines


def structural_defines(params, struct_keys, preset_vals):
    out = ["#define CRT_PARAMS_INJECTED 1"]
    for key in sorted(struct_keys):
        spec = params[key]
        val = preset_vals.get(key, spec["default"])
        out.append("#define %s %s" % (spec["define"], fmt_value(spec, val)))
    return out


def compat_prelude(pass_name, self_alias):
    """Ghostty-uniform compatibility layer for the slang host."""
    feedback = self_alias + SPEC["feedback_suffix"]
    lines = [
        "// ---- monoscope slang host compatibility layer ----",
        "#define HOST_RETROARCH 1",
        "#define iResolution vec3(params.OutputSize.xy, 1.0)",
        "// Wall-clock pacing: FrameTimeDelta (microseconds, RetroArch",
        "// 1.16+) keeps the physics real-time even when the core",
        "// ticks slowly (image viewer, pause, fast-forward). Zero",
        "// (unsupported runtime / first frame) falls back to 1/60.",
        "#define iTimeDelta (params.FrameTimeDelta == 0u ? (1.0/60.0) "
        ": clamp(float(params.FrameTimeDelta) * 1e-6, 1e-4, 0.1))",
        "#define iTime (float(params.FrameCount) * (1.0 / 60.0))",
        "#define iFrame int(params.FrameCount)",
        "// No hardware cursor in an emulator: inert values (dead code",
        "// folds; hold-mode idle never triggers).",
        "const vec4 iCurrentCursor = vec4(-1e6, -1e6, 0.0, 0.0);",
        "const vec4 iCurrentCursorColor = vec4(0.0);",
        "#define iTimeCursorChange iTime",
        "const int iCursorVisible = 0;",
        "// y-up convention bridge: the templates use GL bottom-left",
        "// origin; slang vTexCoord is top-left. Flip at every boundary.",
        "vec4 crtTexA(sampler2D t, vec2 uv) {",
        "    return texture(t, vec2(uv.x, 1.0 - uv.y));",
        "}",
        "#define _CRT_CH0(uv) crtTexA(Source, uv)",
    ]
    if pass_name == "phosphor-state":
        lines.append("#define _CRT_CH1(uv) crtTexA(%s, uv)" % feedback)
    else:
        lines.append("#define _CRT_CH1(uv) vec4(0.0)")
    return "\n".join(lines)


def demote_runtime_consts(body, runtime_defines):
    """Vulkan GLSL: global const initializers must be constant expressions.
    Any template global const whose initializer references a runtime
    parameter define becomes a #define instead."""
    names = set(runtime_defines)
    pat = re.compile(
        r"^(\s*const\s+(?:float|vec2|vec3|vec4|int)\s+(\w+)\s*=\s*)"
        r"([^;]+);", re.M | re.S)
    def sub(m):
        init = m.group(3)
        if any(re.search(r"\b%s\b" % re.escape(n), init) for n in names):
            one_line = " ".join(init.split())
            return "#define %s (%s)" % (m.group(2), one_line)
        return m.group(0)
    return pat.sub(sub, body)


def rewrite_body(body, pass_name):
    """Template GLSL -> slang-host GLSL."""
    # texture(iChannelN, X) -> boundary-flipped host samplers.
    body = re.sub(r"texture\s*\(\s*iChannel0\s*,\s*", "_CRT_CH0(", body)
    body = re.sub(r"texture\s*\(\s*iChannel1\s*,\s*", "_CRT_CH1(", body)
    # Strip the template's marker/guards (structural defines are injected
    # by us, before the body).
    body = body.replace("//@CRT_PARAMS@", "")
    body = body.replace(
        '#ifndef CRT_PARAMS_INJECTED\n#error "This is a template. '
        'Run crtctl to generate the shader with parameters."\n#endif', "")
    return body


def emit_pass(pass_name, params, struct_keys, runtime_keys, preset_vals,
              alias):
    body = rewrite_body(load_template(pass_name), pass_name)
    pragmas, members, run_defines = runtime_param_lines(
        params, runtime_keys, preset_vals)
    body = demote_runtime_consts(
        body, [params[k]['define'] for k in runtime_keys])
    sdefs = structural_defines(params, struct_keys, preset_vals)

    ubo = [
        "layout(std140, set = 0, binding = 0) uniform UBO",
        "{",
        "    mat4 MVP;",
        "    vec4 OutputSize;",
        "    vec4 OriginalSize;",
        "    vec4 SourceSize;",
        "    uint FrameCount;",
        "    uint FrameTimeDelta;",
    ] + members + ["} params;", "#define global params"]

    frag_head = [
        "#pragma stage fragment",
        "layout(location = 0) in vec2 vTexCoord;",
        "layout(location = 0) out vec4 FragColor;",
        "layout(set = 0, binding = 2) uniform sampler2D Source;",
    ]
    if pass_name == "phosphor-state":
        frag_head.append(
            "layout(set = 0, binding = 3) uniform sampler2D %s%s;"
            % (alias, SPEC["feedback_suffix"]))

    tail = [
        "void main()",
        "{",
        "    vec2 _fc = vec2(vTexCoord.x, 1.0 - vTexCoord.y)",
        "             * params.OutputSize.xy;",
        "    mainImage(FragColor, _fc);",
    ]
    if pass_name == "crt-display":
        tail += [
            "    // Ghostty's GL pipeline gamma-encoded on write",
            "    // (FRAMEBUFFER_SRGB); RetroArch expects encoded output.",
            "    FragColor.rgb = pow(clamp(FragColor.rgb, 0.0, 1.0),",
            "                        vec3(1.0 / 2.2));",
        ]
    else:
        tail += [
            "    // Pass 0 must ALSO linearize its content input: Ghostty",
            "    // sampled an sRGB texture (auto-linearized); RetroArch",
            "    // hands us raw encoded values. Handled inside",
            "    // fetchContent via HOST_RETROARCH.",
        ]
    tail.append("}")

    parts = [
        "#version 450",
        "// Generated by transpile_slang.py — DO NOT EDIT.",
        '#pragma name %s' % alias,
    ]
    if pass_name == "phosphor-state":
        parts.append("#pragma format %s" % SPEC["float_format_pragma"])
    parts += pragmas
    parts += sdefs
    parts += ubo
    parts += run_defines
    parts.append(VERTEX_STAGE)
    parts += frag_head
    parts.append(compat_prelude(pass_name, alias))
    parts.append(body)
    parts += tail
    return "\n".join(parts) + "\n"


def linearize_patch(src):
    """fetchContent linearizes under HOST_RETROARCH (raw encoded input)."""
    return src.replace(
        "vec3 fetchContent(vec2 uv) {\n"
        "    vec4 t = _CRT_CH0(uv);\n"
        "    return t.rgb / max(t.a, 1e-3);\n"
        "}",
        "vec3 fetchContent(vec2 uv) {\n"
        "    vec4 t = _CRT_CH0(uv);\n"
        "#ifdef HOST_RETROARCH\n"
        "    // Emulator frames arrive gamma-encoded; the physics runs in\n"
        "    // linear light (Ghostty's sRGB sampler did this for us).\n"
        "    return pow(max(t.rgb, 0.0), vec3(2.2));\n"
        "#else\n"
        "    return t.rgb / max(t.a, 1e-3);\n"
        "#endif\n"
        "}")


def emit_slangp(preset_name, runtime_keys, params, preset_vals, rel):
    lines = [
        "shaders = 2",
        "",
        'shader0 = "%sgenerated/%s/phosphor-state.slang"' % (rel, preset_name),
        'alias0 = "PhosphorState"',
        "filter_linear0 = true",
        "scale_type0 = viewport",
        "scale0 = 1.0",
        "float_framebuffer0 = true",
        "",
        'shader1 = "%sgenerated/%s/crt-display.slang"' % (rel, preset_name),
        "filter_linear1 = true",
        "scale_type1 = viewport",
        "scale1 = 1.0",
    ]
    return "\n".join(lines) + "\n"


def split_stages(slang_src):
    """Split a .slang into (vertex, fragment) GLSL for validation, the way
    RetroArch's front end does."""
    lines = slang_src.split("\n")
    common, vertex, fragment = [], [], []
    cur = common
    for ln in lines:
        s = ln.strip()
        if s.startswith("#pragma stage vertex"):
            cur = vertex
            continue
        if s.startswith("#pragma stage fragment"):
            cur = fragment
            continue
        if s.startswith("#pragma name") or s.startswith("#pragma format") \
           or s.startswith("#pragma parameter"):
            continue
        cur.append(ln)
    head = "\n".join(common)
    return (head + "\n" + "\n".join(vertex),
            head + "\n" + "\n".join(fragment))


def validate(slang_path):
    with open(slang_path) as f:
        src = f.read()
    vtx, frg = split_stages(src)
    ok = True
    with tempfile.TemporaryDirectory() as td:
        for suffix, text in (("vert", vtx), ("frag", frg)):
            p = os.path.join(td, "s." + suffix)
            with open(p, "w") as f:
                f.write(text)
            # Explicit -o: with --target-env glslang otherwise writes
            # <stage>.spv into the CURRENT directory (that is how a stale
            # frag.spv/vert.spv once ended up in the repo).
            r = subprocess.run(
                ["glslangValidator", "--target-env", "vulkan1.1", "-S",
                 suffix, p, "-o", p + ".spv"],
                capture_output=True, text=True)
            if r.returncode != 0:
                ok = False
                print("FAIL %s [%s]" % (slang_path, suffix))
                print("\n".join((r.stdout + r.stderr).splitlines()[:8]))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(CRT, "slang"))
    ap.add_argument("--preset", action="append")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    params = load_params()
    bodies = {n: load_template(n) for n in TEMPLATES}
    struct = structural_keys(params, bodies)
    runtime = [k for k in params if k not in struct]

    pdir = os.path.join(CRT, "presets")
    names = args.preset or sorted(
        fn[:-5] for fn in os.listdir(pdir) if fn.endswith(".json"))

    os.makedirs(os.path.join(args.out, "presets"), exist_ok=True)
    fails = 0
    for name in names:
        with open(os.path.join(pdir, name + ".json")) as f:
            pv = json.load(f).get("params", {})
        gdir = os.path.join(args.out, "generated", name)
        os.makedirs(gdir, exist_ok=True)
        for pass_name, alias in (("phosphor-state", "PhosphorState"),
                                 ("crt-display", "CrtDisplay")):
            src = emit_pass(pass_name, params, struct, runtime, pv, alias)
            src = linearize_patch(src)
            path = os.path.join(gdir, pass_name + ".slang")
            with open(path, "w") as f:
                f.write(src)
            if args.validate and not validate(path):
                fails += 1
        with open(os.path.join(args.out, "presets", name + ".slangp"),
                  "w") as f:
            f.write(emit_slangp(name, runtime, params, pv, "../"))
    # Default entry point.
    if "smartdark-creme" in names or not args.preset:
        with open(os.path.join(args.out, "monoscope.slangp"), "w") as f:
            f.write(emit_slangp("smartdark-creme", runtime, params,
                                {}, ""))
    print("generated %d presets -> %s%s" % (
        len(names), args.out,
        "" if not args.validate else
        (" | validation: %s" % ("ALL PASS" if fails == 0
                                else "%d FAILURES" % fails))))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

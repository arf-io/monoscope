#!/usr/bin/env python3
# transpile_metal.py - generate the Metal Shading Language port of the
# ghostcrtty two-pass CRT simulation from params.json and the GLSL templates.
#
# Pipeline:
#   template GLSL + injected defines/uniforms
#     -> glslangValidator -V --target-env vulkan1.2
#     -> spirv-cross --msl --msl-version 20400
#
# Output layout (default DIR = <crt>/metal):
#   DIR/<preset>/phosphor-state.metal
#   DIR/<preset>/crt-display.metal
#   DIR/runtime/phosphor-state.metal       when --runtime is passed
#   DIR/runtime/crt-display.metal          when --runtime is passed
#   DIR/ABI.md

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

TEMPLATES = {
    "phosphor-state": "phosphor-state.glsl.tmpl",
    "crt-display": "crt-display.glsl.tmpl",
}

FUNCTION_NAMES = {
    "phosphor-state": "ghostcrtty_phosphor_state",
    "crt-display": "ghostcrtty_crt_display",
}


class TranspileError(Exception):
    pass


def load_params():
    with open(os.path.join(CRT, "params.json")) as f:
        return json.load(f)["params"]


def load_template(name):
    with open(os.path.join(CRT, "templates", TEMPLATES[name])) as f:
        return f.read()


def load_preset(name):
    with open(os.path.join(CRT, "presets", name + ".json")) as f:
        return json.load(f).get("params", {})


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


def preprocessor_keys(params, bodies):
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
    return out


def runtime_key_sets(params, pp_keys, all_numeric):
    if not all_numeric:
        baked = set(pp_keys)
    else:
        # A fully runtime Metal variant can only lift params out of the
        # preprocessor when GLSL syntax still allows it. Numeric params used
        # inside normal code are uniforms; bool/enum preprocessor selectors
        # remain compiled from params.json defaults.
        baked = {
            k for k in pp_keys
            if params[k]["type"] in ("bool", "enum")
        }
    runtime = [k for k in params if k not in baked]
    return baked, runtime


def uniform_block(params):
    lines = [
        "layout(set = 0, binding = 0, std140) uniform GhostCrtUniforms",
        "{",
        "    vec4 iResolution;",
        "    float iTime;",
        "    float iTimeDelta;",
        "    int iFrame;",
        "    float _pad0;",
    ]
    for key in params:
        lines.append("    float crt_%s;" % key)
    lines += ["} gcu;"]
    return lines


def define_for_uniform(key, spec):
    name = spec["define"]
    expr = "gcu.crt_%s" % key
    if spec["type"] == "float":
        return "#define %s %s" % (name, expr)
    return "#define %s int(%s)" % (name, expr)


def parameter_defines(params, baked_keys, runtime_keys, preset_vals):
    lines = ["#define CRT_PARAMS_INJECTED 1"]
    for key in params:
        spec = params[key]
        if key in baked_keys:
            val = preset_vals.get(key, spec["default"])
            lines.append("#define %s %s" % (spec["define"], fmt_value(spec, val)))
        elif key in runtime_keys:
            lines.append(define_for_uniform(key, spec))
    return lines


def demote_runtime_consts(body, runtime_define_names):
    pat = re.compile(
        r"^(\s*const\s+(?:float|vec2|vec3|vec4|int)\s+(\w+)\s*=\s*)"
        r"([^;]+);",
        re.M | re.S)

    def sub(m):
        init = m.group(3)
        if any(re.search(r"\b%s\b" % re.escape(n), init)
               for n in runtime_define_names):
            return "#define %s (%s)" % (m.group(2), " ".join(init.split()))
        return m.group(0)

    return pat.sub(sub, body)


def adapt_body(body, pass_name):
    body = re.sub(r"texture\s*\(\s*iChannel0\s*,\s*", "_CRT_CH0(", body)
    body = re.sub(r"texture\s*\(\s*iChannel1\s*,\s*", "_CRT_CH1(", body)
    body = body.replace("//@CRT_PARAMS@", "")
    body = body.replace(
        '#ifndef CRT_PARAMS_INJECTED\n#error "This is a template. '
        'Run crtctl to generate the shader with parameters."\n#endif',
        "")
    return body


def compat_prelude(pass_name):
    lines = [
        "// ---- ghostcrtty Metal host compatibility layer ----",
        "#define HOST_METAL 1",
        "#define iResolution gcu.iResolution",
        "#define iTime gcu.iTime",
        "#define iTimeDelta gcu.iTimeDelta",
        "#define iFrame gcu.iFrame",
        "const vec4 iCurrentCursor = vec4(-1e6, -1e6, 0.0, 0.0);",
        "const vec4 iCurrentCursorColor = vec4(0.0);",
        "#define iTimeCursorChange iTime",
        "const int iCursorVisible = 0;",
        "// Metal textures are addressed top-left. The templates are GL-style",
        "// bottom-left, so every texture boundary is sampled through this flip.",
    ]
    if pass_name == "phosphor-state":
        lines += [
            "layout(set = 0, binding = 0) uniform sampler2D contentTexture;",
            "layout(set = 0, binding = 1) uniform sampler2D historyTexture;",
            "vec4 _CRT_SAMPLE(sampler2D t, vec2 uv) {",
            "    return texture(t, vec2(uv.x, 1.0 - uv.y));",
            "}",
            "#define _CRT_CH0(uv) _CRT_SAMPLE(contentTexture, uv)",
            "#define _CRT_CH1(uv) _CRT_SAMPLE(historyTexture, uv)",
        ]
    else:
        lines += [
            "layout(set = 0, binding = 2) uniform sampler2D previousPassTexture;",
            "vec4 _CRT_SAMPLE(sampler2D t, vec2 uv) {",
            "    return texture(t, vec2(uv.x, 1.0 - uv.y));",
            "}",
            "#define _CRT_CH0(uv) _CRT_SAMPLE(previousPassTexture, uv)",
            "#define _CRT_CH1(uv) vec4(0.0)",
        ]
    return lines


def emit_glsl(pass_name, params, baked_keys, runtime_keys, preset_vals):
    body = adapt_body(load_template(pass_name), pass_name)
    body = demote_runtime_consts(
        body, [params[k]["define"] for k in runtime_keys])

    tail = [
        "void main()",
        "{",
        "    vec2 _crtFragCoord = vec2(gl_FragCoord.x,",
        "        iResolution.y - gl_FragCoord.y);",
        "    mainImage(FragColor, _crtFragCoord);",
    ]
    if pass_name == "crt-display":
        tail += [
            "    // Match the slang/WebGL ports: final display output is",
            "    // explicitly encoded from linear light to sRGB.",
            "    FragColor.rgb = pow(clamp(FragColor.rgb, 0.0, 1.0),",
            "                        vec3(1.0 / 2.2));",
            "    FragColor.a = 1.0;",
        ]
    tail.append("}")

    parts = [
        "#version 450",
        "// Generated by transpile_metal.py - DO NOT EDIT.",
        "layout(location = 0) out vec4 FragColor;",
    ]
    parts += uniform_block(params)
    parts += parameter_defines(params, baked_keys, runtime_keys, preset_vals)
    parts += compat_prelude(pass_name)
    parts.append(body)
    parts += tail
    return "\n".join(parts) + "\n"


def run_checked(cmd, label):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        msg = "\n".join((r.stdout + r.stderr).splitlines()[:12])
        raise TranspileError("%s failed:\n%s" % (label, msg))
    return r


def compile_msl(glsl_src, pass_name, out_path):
    with tempfile.TemporaryDirectory() as td:
        frag = os.path.join(td, pass_name + ".frag")
        spv = os.path.join(td, pass_name + ".spv")
        with open(frag, "w") as f:
            f.write(glsl_src)
        run_checked([
            "glslangValidator", "-V", "--target-env", "vulkan1.2",
            "-S", "frag", frag, "-o", spv,
        ], "glslangValidator %s" % pass_name)
        r = run_checked([
            "spirv-cross", spv,
            "--msl",
            "--msl-version", "20400",
            "--msl-decoration-binding",
            "--msl-pad-fragment-output",
            "--rename-entry-point", "main", FUNCTION_NAMES[pass_name], "frag",
        ], "spirv-cross %s" % pass_name)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(r.stdout)


def variant_to_metal(label, out_dir, params, pp_keys, preset_vals, all_numeric):
    baked, runtime = runtime_key_sets(params, pp_keys, all_numeric)
    count = 0
    for pass_name in ("phosphor-state", "crt-display"):
        glsl = emit_glsl(pass_name, params, baked, runtime, preset_vals)
        compile_msl(glsl, pass_name,
                    os.path.join(out_dir, label, pass_name + ".metal"))
        count += 1
    return count


def uniform_offsets(params):
    rows = [
        (0, "float4", "iResolution", "xy = drawable pixels, z = 1, w reserved"),
        (16, "float", "iTime", "seconds"),
        (20, "float", "iTimeDelta", "seconds"),
        (24, "int32", "iFrame", "zero-based frame counter"),
        (28, "float", "_pad0", "reserved, write 0"),
    ]
    off = 32
    for key, spec in params.items():
        rows.append((
            off,
            "float",
            "crt_%s" % key,
            "%s param, pass enum/bool/int values as numeric codes" % spec["type"],
        ))
        off += 4
    return rows


def emit_abi(params, out_dir, preset_count):
    rows = uniform_offsets(params)
    lines = [
        "# ghostcrtty Metal ABI",
        "",
        "Generated by `tools/transpile_metal.py`. This file is the stable",
        "contract consumed by the Swift overlay app.",
        "",
        "## Fragment Functions",
        "",
        "| Pass | Function | Output |",
        "| --- | --- | --- |",
        "| phosphor-state | `ghostcrtty_phosphor_state` | RGBA16Float phosphor state; logical data row 0 is stored at the physical bottom row. |",
        "| crt-display | `ghostcrtty_crt_display` | sRGB-encoded display color. Use a non-sRGB color target unless the host intentionally removes the shader-side encode. |",
        "",
        "## Resource Bindings",
        "",
        "Metal resource namespaces are independent. Uniforms always use",
        "`[[buffer(0)]]`; textures and samplers use the matching numeric slot.",
        "",
        "| Pass | Resource | Metal binding | Notes |",
        "| --- | --- | --- | --- |",
        "| phosphor-state | `GhostCrtUniforms` | `buffer(0)` | Single uniform struct below. |",
        "| phosphor-state | `contentTexture` | `texture(0)` | Terminal/content frame. Prefer an sRGB Metal pixel format for encoded content so sampling returns linear light. |",
        "| phosphor-state | `contentTextureSmplr` | `sampler(0)` | Linear filtering is expected. |",
        "| phosphor-state | `historyTexture` | `texture(1)` | Previous frame of this pass, RGBA16Float. |",
        "| phosphor-state | `historyTextureSmplr` | `sampler(1)` | Linear filtering is expected. |",
        "| crt-display | `GhostCrtUniforms` | `buffer(0)` | Same bytes as pass 0. |",
        "| crt-display | `previousPassTexture` | `texture(2)` | Current phosphor-state output, RGBA16Float. |",
        "| crt-display | `previousPassTextureSmplr` | `sampler(2)` | Linear filtering is expected. |",
        "",
        "## Coordinate Convention",
        "",
        "The GLSL templates use the OpenGL/Shadertoy logical coordinate system:",
        "`fragCoord.y == 0` is the bottom row, and the phosphor state machine",
        "stores data pixels in logical row 0. Metal fragment positions and",
        "texture sampling are top-left oriented, so the transpiler handles this",
        "inside the generated shader: `gl_FragCoord.y` is converted to",
        "`iResolution.y - gl_FragCoord.y`, and every `iChannel` sample flips",
        "`uv.y` at the texture boundary. The host should bind ordinary top-left",
        "Metal textures; do not add another y flip in Swift.",
        "",
        "## Uniform Struct Layout",
        "",
        "Use std140-compatible packing. The runtime knob block follows",
        "`params.json` order exactly. All `crt_*` fields are 32-bit floats;",
        "for int, bool, and enum params, write the numeric code as a float.",
        "Preset variants compile preprocessor-selected params into the",
        "shader, but the fields remain present for one stable struct.",
        "The `runtime/` variant keeps every float/int param as a live uniform;",
        "bool/enum preprocessor selectors are still compiled from defaults.",
        "",
        "| Offset | Type | Field | Notes |",
        "| ---: | --- | --- | --- |",
    ]
    for off, typ, name, note in rows:
        lines.append("| %d | `%s` | `%s` | %s |" % (off, typ, name, note))
    lines += [
        "",
        "## Generated Matrix",
        "",
        "- Preset variants: %d" % preset_count,
        "- Passes per preset: 2",
        "- Runtime variant path: `metal/runtime/` when generated with `--runtime`",
    ]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ABI.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def require_tools():
    missing = [t for t in ("glslangValidator", "spirv-cross")
               if shutil.which(t) is None]
    if missing:
        raise TranspileError("missing required tool(s): %s" % ", ".join(missing))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(CRT, "metal"))
    ap.add_argument("--preset", action="append")
    ap.add_argument("--runtime", action="store_true",
                    help="also generate metal/runtime with all numeric params as uniforms")
    ap.add_argument("--validate", action="store_true",
                    help="print compile-matrix status; generation always uses glslang + spirv-cross")
    args = ap.parse_args()

    require_tools()
    params = load_params()
    bodies = {n: load_template(n) for n in TEMPLATES}
    pp_keys = preprocessor_keys(params, bodies)
    pdir = os.path.join(CRT, "presets")
    names = args.preset or sorted(
        fn[:-5] for fn in os.listdir(pdir) if fn.endswith(".json"))

    failures = []
    passed = 0
    for name in names:
        try:
            passed += variant_to_metal(
                name, args.out, params, pp_keys, load_preset(name), False)
        except TranspileError as e:
            failures.append("%s: %s" % (name, e))

    runtime_passed = 0
    if args.runtime:
        try:
            runtime_passed = variant_to_metal(
                "runtime", args.out, params, pp_keys, {}, True)
        except TranspileError as e:
            failures.append("runtime: %s" % e)

    emit_abi(params, args.out, len(names))

    total = len(names) * 2
    print("METAL MATRIX: %d/%d preset passes compiled clean" %
          (passed, total))
    if args.runtime:
        print("METAL RUNTIME: %d/2 passes compiled clean" % runtime_passed)
    print("generated %d presets%s -> %s" %
          (len(names), " + runtime" if args.runtime else "", args.out))
    if failures:
        for f in failures:
            print("FAIL %s" % f, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

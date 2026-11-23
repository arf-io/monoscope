# Shader exporters and control utility

The shader exporters consume the root `params.json`, presets, and GLSL templates. Python 3 is sufficient for the WebGL2, Slang, and ReShade exporters. The Metal exporter also requires `glslangValidator` and `spirv-cross`.

```sh
python3 tools/transpile_webgl.py --out /tmp/monoscope-docs.html
python3 tools/transpile_slang.py --out /tmp/monoscope-slang --validate
python3 tools/transpile_reshade.py --out /tmp/monoscope-reshade
python3 tools/transpile_metal.py --out /tmp/monoscope-metal
```

Use `--preset NAME` to select one or more presets where supported. The web exporter creates a demonstration document that renders the project documentation through WebGL2. Slang and ReShade exporters create host-specific shader files. The two GLSL passes require a host that supports floating point feedback textures for phosphor persistence.

`tools/crtctl` and `tools/monoscope/` provide a terminal control interface for a Ghostty integration. They are optional and are not required to generate or use the shader packs.

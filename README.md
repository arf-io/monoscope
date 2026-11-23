# Monoscope

Monoscope is a CRT and phosphor display simulation engine. It models the electrical signal and phosphor persistence in one GLSL pass, then tube geometry, mask, and glass in a second pass. The project includes parameter definitions, tube presets, shader exporters, generated shader packs, tests, and research notes.

## Install and first run

Clone the public repository and generate the self-contained Monoscope demo page. Python 3 is the only requirement for this command; it uses the standard library.

```sh
git clone https://github.com/arf-io/monoscope.git
cd monoscope
mkdir -p build
python3 tools/transpile_webgl.py --out build/monoscope-demo.html
```

Open `build/monoscope-demo.html` in a WebGL2-capable browser. It renders the project documentation through the CRT effect. The display simulation uses WebGL2 and `EXT_color_buffer_float`; without those capabilities the page shows its fallback view. The embedded renderer demonstrates this pipeline and is not a general-purpose web page wrapper.

## Install and use with RetroArch

Generate and validate the Slang shader pack, copy it under RetroArch's configured `shaders/shaders_slang/` directory, then select `monoscope/monoscope.slangp` from Quick Menu → Shaders → Load Preset. The pack requires a Slang renderer with floating-point framebuffers.

```sh
python3 tools/transpile_slang.py --out /tmp/monoscope-slang --validate
mkdir -p "$HOME/.config/retroarch/shaders/shaders_slang/monoscope"
cp -R /tmp/monoscope-slang/. "$HOME/.config/retroarch/shaders/shaders_slang/monoscope/"
```

Replace the example directory with RetroArch's configured Slang shader folder on other platforms.

## Generate shader packs

The exporters use Python 3 and the standard library, except the Metal exporter, which also needs `glslangValidator` and `spirv-cross`.

```sh
python3 tools/transpile_webgl.py --out /tmp/monoscope-docs.html
python3 tools/transpile_slang.py --out /tmp/monoscope-slang --validate
python3 tools/transpile_reshade.py --out /tmp/monoscope-reshade
python3 tools/transpile_metal.py --out /tmp/monoscope-metal --validate
```

Use `--preset NAME` to select presets where supported. The complete persistence model requires a two-pass renderer with floating-point feedback textures. Host capabilities and GPU performance vary. The Metal exporter and source are provided as an integration starting point; they were compiled through the exporter matrix but have not been validated in a native Metal host.

## Project layout

- `templates/`: canonical two-pass GLSL source.
- `params.json`: parameter schema used by the exporters.
- `presets/`: curated display profiles.
- `research/`, `DESIGN.md`, `OPTICS-TUTORIAL.md`: source notes, model details, and disclosed approximations.
- `slang/`, `reshade/`, `metal/`: generated or host-specific shader assets.
- `tools/`: shader exporters and the optional Ghostty control utility.
- `tests/`: preset, command-line, and shader validation.

## Validation

Portable Python checks verified on macOS:

```sh
python3 -m unittest tests.test_presets tests.test_monoscope
```

`test_crtctl.py` and `test_monoscope_pty.py` include Linux D-Bus integration assertions and need Linux, `gdbus`, and a session bus. The graphics runtime scripts also need their documented graphics tools and a compatible display environment. Shader exporters for Slang (62 presets), ReShade (62 presets), Metal (124 passes), and the WebGL2 documentation demo were run successfully during release preparation.

## License

The simulation source, presets, tools, and documentation are MIT licensed, as stated in the original project README. See [LICENSE](LICENSE). Referenced hardware specifications and research remain the property of their respective authors and publishers; citations are included in the research notes.

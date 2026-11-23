#!/usr/bin/env python3
"""Run OBS headless with a stack of shader filters and capture the result.

Everything lives under a throwaway XDG_CONFIG_HOME so the operator's real OBS
configuration is never touched.
"""
import json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 320, 180


def build(root, filters, fmt="RGBA", secs=6):
    cfg = os.path.join(root, "obs-studio")
    rec = os.path.join(root, "rec")
    for d in (os.path.join(cfg, "basic", "profiles", "t"),
              os.path.join(cfg, "basic", "scenes"), rec):
        os.makedirs(d, exist_ok=True)

    with open(os.path.join(cfg, "global.ini"), "w") as f:
        # FirstRun=false matters: left true, OBS opens the auto-configuration
        # wizard, which is a modal dialog that never gets dismissed under Xvfb
        # and hangs AppInit forever.
        ini = ("[General]\nPre19Defaults=false\nPre21Defaults=false\n"
               "Pre23Defaults=false\nPre24.1Defaults=false\n"
               "FirstRun=false\nLastVersion=537001985\n"
               "InstallGUID=00000000-0000-0000-0000-000000000000\n"
               "EnableAutoUpdates=false\nConfirmOnExit=false\n"
               "[Basic]\nProfile=t\nProfileDir=t\nSceneCollection=t\n"
               "SceneCollectionFile=t\n")
        f.write(ini)
    with open(os.path.join(cfg, "user.ini"), "w") as f:
        f.write(ini)

    with open(os.path.join(cfg, "basic", "profiles", "t", "basic.ini"), "w") as f:
        f.write("[General]\nName=t\n"
                "[Video]\nBaseCX=%d\nBaseCY=%d\nOutputCX=%d\nOutputCY=%d\n"
                "FPSType=1\nFPSInt=30\nColorFormat=%s\nColorSpace=%s\nColorRange=Full\n"
                "[Output]\nMode=Advanced\n"
                "[AdvOut]\nRecType=Standard\nRecEncoder=obs_x264\nRecFilePath=%s\n"
                "RecFormat2=mkv\nRecRB=false\n"
                "RecEncoderSettings=\n"
                "[SimpleOutput]\nFilePath=%s\nRecFormat2=mkv\nRecQuality=Lossless\n"
                % (W, H, W, H, fmt, "Rec. 2100 (PQ)" if os.environ.get("SG_HDR") else "sRGB", rec, rec))
    # lossless x264 so the capture itself never quantises what we measure
    with open(os.path.join(cfg, "basic", "profiles", "t", "recordEncoder.json"), "w") as f:
        json.dump({"bitrate": 2500, "crf": 0, "keyint_sec": 1, "preset": "ultrafast",
                   "profile": "high444", "rate_control": "CRF",
                   "x264opts": "qp=0"}, f)

    scene = {
        "current_scene": "S", "current_program_scene": "S", "name": "t",
        "scene_order": [{"name": "S"}],
        "sources": [
            {"id": "color_source_v3", "name": "col", "versioned_id": "color_source_v3",
             "settings": {"color": 4278190080, "width": W, "height": H},
             "enabled": True, "filters": filters,
             "mixers": 0, "sync": 0, "flags": 0, "volume": 1.0},
            {"id": "scene", "name": "S", "versioned_id": "scene",
             "settings": {"custom_size": False, "id_counter": 1, "items": [
                 {"name": "col", "id": 1, "visible": True, "pos": {"x": 0, "y": 0},
                  "scale": {"x": 1.0, "y": 1.0}, "align": 5, "bounds_type": 0,
                  "scale_filter": "disable", "blend_method": "default",
                  "blend_type": "normal"}]},
             "enabled": True, "mixers": 0, "sync": 0, "flags": 0, "volume": 1.0},
        ],
    }
    with open(os.path.join(cfg, "basic", "scenes", "t.json"), "w") as f:
        json.dump(scene, f, indent=1)
    return cfg, rec


def sfilter(name, path, settings=None):
    s = {"shader_file_name": path, "from_file": True}
    s.update(settings or {})
    return {"id": "shader_filter", "name": name, "versioned_id": "shader_filter",
            "enabled": True, "settings": s}


def run(root, secs=6):
    env = dict(os.environ, XDG_CONFIG_HOME=root, QT_QPA_PLATFORM="xcb")
    env.pop("WAYLAND_DISPLAY", None)
    p = subprocess.Popen(
        ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24",
         "obs", "--multi", "--minimize-to-tray", "--startrecording",
         "--collection", "t", "--profile", "t", "--scene", "S",
         "--disable-updater", "--disable-missing-files-check"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(secs)
    p.terminate()
    try:
        out = p.communicate(timeout=20)[0]
    except subprocess.TimeoutExpired:
        p.kill(); out = p.communicate()[0]
    return out.decode("utf8", "replace")

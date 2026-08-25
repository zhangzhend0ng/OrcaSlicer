# profile.py — seed an ISOLATED app data dir ("sandbox profile") for a
# black-box vision test run.
#
# Why not ORCA_GUI_TEST_MODE: that env var HIDES the main window
# (GUI_App.cpp: mainframe->Show(true) is skipped when gui_test_mode()) — a
# vision driver has nothing to screenshot. Instead we pre-seed the datadir so
# a NORMAL, VISIBLE startup skips every modal side path:
#
#   wizard     : needs conf to exist AND printers to be non-default AND
#                privacy flag non-empty (GUI_App::config_wizard_startup).
#                -> we copy installed system presets + write a conf with
#                   privacy_policy_isagree=true and firstguide.finish=true.
#   splash     : app.show_splash_screen = false
#   language   : app.language = "en_US" (template byte-stability; NOT the OS
#                locale, which a fresh dir would otherwise pick and persist)
#   start page : app.default_page = "1" (3D editor; "0" is the WebView2 Home)
#   restore    : app.backup_switch = false + no last_backup_path (Plater would
#                otherwise pop the modal "restore previous project?" dialog)
#   geometry   : drop window_mainframe/main_frame_pos keys -> default size
#
# Config format (this fork, USE_JSON_CONFIG): a single JSON object followed by
# "\n# MD5 checksum <32 hex>\n". The MD5 is only an informational check on
# load (a mismatch logs an info line); the JSON must simply parse.

import hashlib
import json
import os
import shutil
from pathlib import Path

# Keys dropped from the source conf: recent files leak paths and can trigger
# UI affordances; window geometry keys force a deterministic default layout.
_DROP_APP_KEYS = [
    "main_frame_pos", "main_frame_size", "last_backup_path",
    "object_settings_maximized", "object_settings_pos", "object_settings_size",
]
_DROP_SECTIONS = ["recent", "recent_projects"]


def default_source_conf() -> Path:
    return Path(os.environ["APPDATA"]) / "Snapmaker_Orca" / "Snapmaker_Orca.conf"


def default_source_presets() -> Path:
    return Path(os.environ["APPDATA"]) / "Snapmaker_Orca" / "system"


def load_conf(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    left = raw[: raw.rfind("}") + 1]  # strip the trailing checksum comment
    return json.loads(left)


def write_conf(path: Path, conf: dict) -> None:
    body = json.dumps(conf, indent=4, ensure_ascii=False)
    digest = hashlib.md5((body + "\n").encode("utf-8")).hexdigest().upper()
    path.write_text(body + "\n# MD5 checksum " + digest + "\n", encoding="utf-8")


def overrides_for(conf: dict) -> dict:
    """Apply sandbox defaults, keeping each key's existing JSON type (bool vs
    string) so the app's typed getters (get vs get_bool) keep working."""
    app = conf.setdefault("app", {})
    ov = {
        "language": "en_US",            # string in real conf
        "show_splash_screen": False,    # bool in real conf
        "single_instance": False,       # bool in real conf
        "default_page": "1",            # string "1" = 3D editor (Prepare)
        "privacy_policy_isagree": True,  # bool in real conf
        "backup_switch": False,         # bool: kill the restore-project modal
    }
    for k, v in ov.items():
        app[k] = v
    # Wizard finish flag: bool True, exactly as the guide dialog persists it.
    conf.setdefault("firstguide", {})["finish"] = True
    return ov


def seed_profile(dest: Path,
                 source_conf: Path | None = None,
                 source_presets: Path | None = None,
                 fresh: bool = False) -> Path:
    """Create/refresh `dest` as a runnable sandbox datadir; returns it."""
    dest = Path(dest)
    source_conf = Path(source_conf) if source_conf else default_source_conf()
    source_presets = Path(source_presets) if source_presets else default_source_presets()

    if fresh and dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # 1) system presets: makes printers.only_default_printers() false so the
    #    startup wizard does not run. Copied from the user's installed set
    #    (matches the exe the user runs; ~3MB). For CI-grade determinism point
    #    --presets-from at the exe's own resources/profiles instead.
    dst_system = dest / "system"
    if not dst_system.exists():
        if not source_presets.exists():
            raise FileNotFoundError(f"preset source not found: {source_presets}")
        shutil.copytree(source_presets, dst_system)

    # 2) app conf: start from the user's real config (keeps ssl/update/
    #    preset-selection state realistic), then sandbox-override.
    if not source_conf.exists():
        raise FileNotFoundError(f"source conf not found: {source_conf}")
    conf = load_conf(source_conf)
    for sec in _DROP_SECTIONS:
        conf.pop(sec, None)
    for k in _DROP_APP_KEYS:
        conf.get("app", {}).pop(k, None)
    applied = overrides_for(conf)
    write_conf(dest / "Snapmaker_Orca.conf", conf)
    print(f"[profile] seeded {dest}")
    print(f"[profile] overrides: {json.dumps(applied)}")
    return dest


if __name__ == "__main__":
    import sys
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("vision_profile")
    seed_profile(dest)

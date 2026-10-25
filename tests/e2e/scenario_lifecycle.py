"""Lifecycle scenario: the full plugin software cycle against the real executable,
in an isolated datadir (user data is never touched).

Legs (each asserts; the first failure aborts with a nonzero exit):
  1  clean boot                  -- app up, no probe row, no probe tab
  2  dir-install + refresh       -- hot discovery: row present, inactive
  3  enable                      -- row activated, is_loaded, tab present
  4  disable                     -- row inactive, tab torn down
  5  re-enable                   -- tab returns (plugin-level load re-registration)
  6  uninstall + native confirm  -- row/dir/tab all cleared
  7  restart                     -- zero residue
  8  restore + refresh + enable  -- rediscovery and tab return (restore leg)
  9  restart                     -- tab persists at boot (boot-registration paths)

Leg 5 and legs 8/9 are the regression surface of the Pages registration race fixed in
df6a5fdd40 (replay_plugin_pages_registration): pre-fix, legs 8/9 lost the tab forever.
"""

import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2elib import (AppSession, check, click_native_confirm, find_window,
                    install_plugin_dir, sidecar_of, wait_until)

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "e2e_probe")


def leg(session, n, desc, cond, detail=""):
    check(cond, "leg %d failed (%s): %s" % (n, desc, detail))
    print("  leg %2d ok -- %s" % (n, desc))


def run(exe, workdir, seed_conf):
    plugins_dir = os.path.join(workdir, "datadir", "orca_plugins")
    fixture_backup = os.path.join(workdir, "fixture_backup")

    # -- legs 1-7: first session -------------------------------------------
    session = AppSession(exe, workdir, seed_conf=seed_conf, cdp_port=9222)
    session.launch()
    session.wait_up()
    try:
        session.open_plugins_dialog()
        rows = session.dialog_rows()
        leg(session, 1, "clean boot: no probe row", session.row("E2E Probe") is None, str(rows))
        leg(session, 1, "clean boot: no probe tab", "E2E Probe" not in session.tabs(),
            str(session.tabs()))

        install_plugin_dir(plugins_dir, "e2e-probe", FIXTURE, enabled=False,
                           capabilities=("E2E Probe",))
        # Pristine copy taken before any toggle, so the restore leg replays a real
        # "reinstall from a saved copy" (discovered disabled, then enabled).
        shutil.copytree(os.path.join(plugins_dir, "e2e-probe"), fixture_backup)
        session.refresh_plugins()
        row = session.row("E2E Probe")
        leg(session, 2, "hot discovery row present", row is not None, str(session.dialog_rows()))
        leg(session, 2, "discovered row inactive", row is not None and row["checked"] is False, str(row))

        session.toggle_plugin("E2E Probe")
        payload = wait_until(lambda: (lambda p: p and p[0]["is_loaded"] is True and p[0]["status"] == "Activated"
                                      and p or None)(session.plugin_payload("E2E Probe")),
                             timeout=25, what="enabled+loaded")
        leg(session, 3, "enabled: activated+loaded",
            bool(payload) and payload[0]["is_loaded"] is True, str(payload))
        tabs = wait_until(lambda: "E2E Probe" in session.tabs() and session.tabs() or None,
                          timeout=25, what="tab present")
        leg(session, 3, "enabled: tab present", "E2E Probe" in tabs, str(tabs))

        session.toggle_plugin("E2E Probe")
        payload = wait_until(lambda: (lambda p: p and p[0]["is_loaded"] is False and p or None)(session.plugin_payload("E2E Probe")),
                             timeout=25, what="unloaded")
        leg(session, 4, "disabled: inactive", bool(payload) and payload[0]["is_loaded"] is False, str(payload))
        wait_until(lambda: "E2E Probe" not in session.tabs() or None, timeout=25, what="tab torn down")
        leg(session, 4, "disabled: tab torn down", "E2E Probe" not in session.tabs(), str(session.tabs()))

        session.toggle_plugin("E2E Probe")
        payload = wait_until(lambda: (lambda p: p and p[0]["is_loaded"] is True and p or None)(session.plugin_payload("E2E Probe")),
                             timeout=25, what="re-loaded")
        leg(session, 5, "re-enabled: loaded", bool(payload) and payload[0]["is_loaded"] is True, str(payload))
        tabs = wait_until(lambda: "E2E Probe" in session.tabs() and session.tabs() or None,
                          timeout=25, what="tab returned")
        leg(session, 5, "re-enabled: tab returned", "E2E Probe" in tabs, str(tabs))

        key = payload_key(session)
        session.send_command({"command": "plugin_menu_action", "plugin_key": key, "action": "delete_plugin"})
        click_native_confirm(session.proc.pid, "Delete Plugin", "Yes")
        wait_until(lambda: session.row("E2E Probe") is None and True or None, timeout=25, what="row gone")
        leg(session, 6, "uninstalled: row gone", session.row("E2E Probe") is None, str(session.dialog_rows()))
        leg(session, 6, "uninstalled: dir gone",
            wait_until(lambda: not os.path.exists(os.path.join(plugins_dir, "e2e-probe")) and True or None,
                       timeout=25, what="dir gone"))
        wait_until(lambda: "E2E Probe" not in session.tabs() or None, timeout=25, what="tab gone")
        leg(session, 6, "uninstalled: tab gone", "E2E Probe" not in session.tabs(), str(session.tabs()))
        session.close_plugins_dialog()
    finally:
        session.terminate()

    # -- leg 7: restart, zero residue ----------------------------------------
    session = AppSession(exe, workdir, seed_conf=seed_conf, cdp_port=9222)
    session.launch()
    session.wait_up()
    try:
        leg(session, 7, "restart: dir still gone", not os.path.exists(os.path.join(plugins_dir, "e2e-probe")))
        leg(session, 7, "restart: no probe tab", "E2E Probe" not in session.tabs(), str(session.tabs()))
        session.open_plugins_dialog()
        leg(session, 7, "restart: no probe row", session.row("E2E Probe") is None, str(session.dialog_rows()))
        session.close_plugins_dialog()
    finally:
        session.terminate()

    # -- legs 8-9: restore, rediscover, enable, persist ----------------------
    shutil.copytree(fixture_backup, os.path.join(plugins_dir, "e2e-probe"))
    sidecar = sidecar_of(plugins_dir, "e2e-probe")
    leg(session, 8, "restored sidecar enabled=false", sidecar["enabled"] is False, str(sidecar))

    session = AppSession(exe, workdir, seed_conf=seed_conf, cdp_port=9222)
    session.launch()
    session.wait_up()
    try:
        session.open_plugins_dialog()
        session.refresh_plugins()
        leg(session, 8, "restore: rediscovered", session.row("E2E Probe") is not None, str(session.dialog_rows()))
        session.toggle_plugin("E2E Probe")
        payload = wait_until(lambda: (lambda p: p and p[0]["is_loaded"] is True and p or None)(session.plugin_payload("E2E Probe")),
                             timeout=25, what="restore loaded")
        leg(session, 8, "restore: enabled+loaded", bool(payload) and payload[0]["is_loaded"] is True, str(payload))
        tabs = wait_until(lambda: "E2E Probe" in session.tabs() and session.tabs() or None,
                          timeout=25, what="restore tab returned")
        leg(session, 8, "restore: tab returned", "E2E Probe" in tabs, str(tabs))
        session.close_plugins_dialog()
    finally:
        session.terminate()

    session = AppSession(exe, workdir, seed_conf=seed_conf, cdp_port=9222)
    session.launch()
    session.wait_up()
    try:
        tabs = session.tabs()
        leg(session, 9, "restart after enable: tab persists", "E2E Probe" in tabs, str(tabs))
        sidecar = sidecar_of(plugins_dir, "e2e-probe")
        leg(session, 9, "sidecar persisted enabled=true", sidecar["enabled"] is True, str(sidecar))
    finally:
        session.terminate()

    print("lifecycle scenario: ALL LEGS PASSED")


def payload_key(session):
    payload = session.plugin_payload("E2E Probe")
    # plugin_key is not in the trimmed payload view; read it from the full store.
    key = session.cdp.eval("PluginsDialog", """
        (function(){for (var v of pluginsById.values()){ if (String(v.name||'').indexOf('E2E Probe')>=0) return v.plugin_key; } return ''; })()
    """)
    check(key, "could not read plugin_key for E2E Probe")
    return key


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--seed-conf", required=True)
    args = ap.parse_args()
    run(args.exe, args.work, os.path.abspath(args.seed_conf))

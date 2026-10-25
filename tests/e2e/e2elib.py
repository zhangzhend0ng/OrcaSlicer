"""Reusable driver for application-level E2E scenarios (Windows, desktop session required).

Why this exists: the unit suites cover libraries, not the software cycle -- first run,
plugin install/enable/use, restart persistence, uninstall residue and CLI slicing are only
observable against the real executable. Every probe in this library was first proven in a
manual forensic round (2026-10-24/25, see docs/reviews/port-python-plugins-absorption-ledger.md
"三方复查轮") and is productized here so the cycle can be re-run by anyone, machine-driven.

Driving model (all proved in the forensic round):
  - The app is launched with an ISOLATED --datadir (user data is never touched) and
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<port>, which exposes
    every embedded webview (home, Plugins dialog, plugin pages) to CDP.
  - The Plugins dialog is opened through the top-bar hamburger menu (window-relative
    coordinates; the window is maximized first so the layout is deterministic).
  - The dialog's DOM is driven via CDP (SendWXMessage is the page->native command bridge).
  - Tab-strip state is read through UI Automation (PowerShell UIAutomationClient); wx
    owner-drawn menus expose nothing to UIA, which is why menus are clicked by position.
  - Native wxMessageBox confirmations accept only a synchronous SendMessage(BM_CLICK);
    PostMessage variants are ignored (ledger, lifecycle acceptance entry).

Requires: python (websocket-client), powershell (in-box), an interactive desktop session.
NOT wired into ctest on purpose: it drives the real GUI and needs a desktop.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import websocket

CDP_POLL_INTERVAL = 0.5


class E2EError(AssertionError):
    pass


def check(cond, msg):
    if not cond:
        raise E2EError(msg)


def wait_until(fn, timeout=20, interval=1.0, what="condition"):
    """Poll fn() until truthy or timeout; returns the last value. Post-action state
    changes (async deletes, worker loads) settle at machine-dependent speed, so legs
    poll instead of sleeping a fixed guess."""
    deadline = time.time() + timeout
    value = None
    while time.time() < deadline:
        try:
            value = fn()
        except Exception:
            value = None
        if value:
            return value
        time.sleep(interval)
    return value


def sweep_stale_webviews(cdp_port):
    """Kill WebView2 browser processes still carrying this harness's debugging-port flag.

    The flag is injected only through WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS in
    AppSession.launch(), so the filter cannot touch another application's webviews."""
    marker = "--remote-debugging-port=%d" % cdp_port
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedgewebview2.exe'\" | "
          "Where-Object { $_.CommandLine -like '*%s*' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" % marker)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------------------------------------------------------------------- #
# Native window helpers (ctypes)
# --------------------------------------------------------------------------- #
import ctypes
from ctypes import wintypes as w

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)


def _windows_of_pid(pid, visible_only=True):
    out = []

    @_WNDENUMPROC
    def cb(hwnd, _):
        p = w.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and (not visible_only or _user32.IsWindowVisible(hwnd)):
            t = ctypes.create_unicode_buffer(256)
            _user32.GetWindowTextW(hwnd, t, 256)
            c = ctypes.create_unicode_buffer(128)
            _user32.GetClassNameW(hwnd, c, 128)
            rc = w.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(rc))
            out.append({"hwnd": hwnd, "title": t.value, "class": c.value,
                        "rect": (rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)})
        return True

    _user32.EnumWindows(cb, 0)
    return out


def find_window(pid, title_contains=None, cls=None):
    for win in _windows_of_pid(pid):
        if title_contains is not None and title_contains not in win["title"]:
            continue
        if cls is not None and win["class"] != cls:
            continue
        return win
    return None


def wait_main_window(pid, timeout=90):
    """Wait for the wx main frame (class wxWindowNR) to exist and be visible."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        win = find_window(pid, cls="wxWindowNR")
        if win:
            return win
        time.sleep(CDP_POLL_INTERVAL)
    raise E2EError("main window did not appear within %ss (pid %s)" % (timeout, pid))


def maximize_window(hwnd):
    _user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    time.sleep(0.6)


def click_screen(x, y, settle=0.35):
    _user32.SetCursorPos(x, y)
    time.sleep(settle)
    _user32.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.09)
    _user32.mouse_event(4, 0, 0, 0, 0)


def close_window(hwnd):
    _user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE


def click_native_confirm(pid, title_contains, button_text="Yes", timeout=15):
    """Synchronous BM_CLICK on a wxMessageBox-style task dialog button (PostMessage never
    works on this dialog form -- see the ledger's lifecycle acceptance notes)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        box = find_window(pid, title_contains=title_contains, cls="#32770")
        if box:
            buttons = []

            @_WNDENUMPROC
            def cb(child, _):
                c = ctypes.create_unicode_buffer(128)
                _user32.GetClassNameW(child, c, 128)
                t = ctypes.create_unicode_buffer(256)
                _user32.GetWindowTextW(child, t, 256)
                buttons.append((c.value, t.value, child))
                return True

            _user32.EnumChildWindows(box["hwnd"], cb, 0)
            for cls_name, text, child_hwnd in buttons:
                if cls_name == "Button" and button_text in text:
                    _user32.SendMessageW(child_hwnd, 0x00F5, 0, 0)  # BM_CLICK, synchronous
                    return True
            # Task-dialog (DirectUI) fallback: WM_COMMAND IDYES to the dialog itself.
            _user32.SendMessageW(box["hwnd"], 0x0111, 6, 0)
            return True
        time.sleep(CDP_POLL_INTERVAL)
    raise E2EError("confirm dialog '%s' never appeared" % title_contains)


# --------------------------------------------------------------------------- #
# Tab strip probe (UI Automation via PowerShell; wx exposes the tab panes there)
# --------------------------------------------------------------------------- #
_TABS_PS1 = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$target = [int]$env:E2E_PID
$root = [System.Windows.Automation.AutomationElement]::RootElement
$app = $root.FindFirst([System.Windows.Automation.TreeScope]::Children,
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $target)))
if (-not $app) { Write-Output "[]"; exit }
$all = $app.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$names = @("Prepare","Preview","Device","Project")
$out = @()
foreach ($e in $all) {
  $n = $e.Current.Name
  $r = $e.Current.BoundingRectangle
  if ($r.Height -gt 0 -and $r.Height -le 60 -and $r.Width -gt 50 -and $r.Y -ge 0 -and $r.Y -lt 120) {
    $out += $n
  }
}
Write-Output ($out -join "`n")
"""


def read_tab_strip(pid, timeout=30):
    """Return the list of tab names rendered in the main window's tab strip (y<120 band)."""
    env = dict(os.environ, E2E_PID=str(pid))
    deadline = time.time() + timeout
    while time.time() < deadline:
        p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _TABS_PS1],
                           capture_output=True, text=True, env=env, timeout=60)
        names = [n for n in (p.stdout or "").splitlines() if n.strip()]
        if names:
            return names
        time.sleep(CDP_POLL_INTERVAL)
    return []


# --------------------------------------------------------------------------- #
# CDP client
# --------------------------------------------------------------------------- #
class Cdp:
    def __init__(self, port):
        self.port = port
        self._n = 0

    def pages(self):
        try:
            return json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % self.port, timeout=5))
        except Exception:
            return []

    def find_page(self, url_contains):
        for page in self.pages():
            if url_contains in page.get("url", ""):
                return page
        return None

    def eval(self, url_contains, expr, timeout=15):
        page = self.find_page(url_contains)
        check(page is not None, "no CDP page matching %r" % url_contains)
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=timeout, suppress_origin=True)
        try:
            self._n += 1
            ws.send(json.dumps({"id": self._n, "method": "Runtime.evaluate",
                                "params": {"expression": expr, "returnByValue": True}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == self._n:
                    result = msg.get("result", {})
                    if "exceptionDetails" in result:
                        raise E2EError("CDP eval failed: " + json.dumps(result["exceptionDetails"])[:300])
                    return result.get("result", {}).get("value")
        finally:
            ws.close()

    def wait_page(self, url_contains, timeout=60, present=True):
        deadline = time.time() + timeout
        while time.time() < deadline:
            here = self.find_page(url_contains) is not None
            if here == present:
                return
            time.sleep(CDP_POLL_INTERVAL)
        raise E2EError("CDP page %r did not become present=%s" % (url_contains, present))


# --------------------------------------------------------------------------- #
# Application session
# --------------------------------------------------------------------------- #
class AppSession:
    """A launched app instance with an isolated data dir and a CDP port."""

    def __init__(self, exe, workdir, seed_conf=None, cdp_port=9222, extra_args=()):
        self.exe = exe
        self.workdir = workdir
        self.datadir = os.path.join(workdir, "datadir")
        self.plugins_dir = os.path.join(self.datadir, "orca_plugins")
        self.cdp_port = cdp_port
        os.makedirs(self.plugins_dir, exist_ok=True)
        if seed_conf and not os.path.exists(os.path.join(self.datadir, "Snapmaker_Orca.conf")):
            os.makedirs(self.datadir, exist_ok=True)
            shutil.copyfile(seed_conf, os.path.join(self.datadir, "Snapmaker_Orca.conf"))
        self.proc = None
        self.extra_args = list(extra_args)
        self.cdp = Cdp(cdp_port)

    def launch(self, extra_args=()):
        check(self.proc is None or self.proc.poll() is not None, "session already running")
        # A scenario that aborted earlier (exception before terminate()) can leave WebView2
        # browser processes behind; app exit does not always reap them (the fork's zombie
        # webview issue). A leftover browser holding the CDP port makes every later
        # session's webview targets invisible (pages never enumerate), which surfaced as
        # deterministic "PluginsDialog did not become present" failures when several runs
        # share a machine. Sweep only processes this harness created: the debugging-port
        # flag comes from WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS below and never appears on
        # another application's webview.
        sweep_stale_webviews(self.cdp_port)
        env = dict(os.environ)
        env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--remote-debugging-port=%d" % self.cdp_port
        args = [self.exe, "--datadir", self.datadir] + self.extra_args + list(extra_args)
        self.proc = subprocess.Popen(args, cwd=os.path.dirname(self.exe), env=env)
        return self.proc

    def wait_up(self, timeout=120):
        win = wait_main_window(self.proc.pid, timeout=timeout)
        maximize_window(win["hwnd"])
        # Give plugin discovery + autoload a generous settle window before asserting state.
        time.sleep(12)
        return win

    def terminate(self, force_after=15):
        if self.proc is None:
            return
        win = find_window(self.proc.pid, cls="wxWindowNR")
        if win:
            close_window(win["hwnd"])
        try:
            self.proc.wait(timeout=force_after)
            return
        except subprocess.TimeoutExpired:
            pass
        self.proc.kill()
        self.proc.wait(timeout=30)

    # -- plugins dialog driving ------------------------------------------------
    def open_plugins_dialog(self):
        win = find_window(self.proc.pid, cls="wxWindowNR")
        check(win is not None, "main window gone")
        # Menu clicks are ignored while the frame is in the background (foreground lock):
        # raise it first. Plain SetForegroundWindow is denied for background processes, so
        # borrow the foreground thread's input queue for the call.
        fg = _user32.GetForegroundWindow()
        fg_tid = w.DWORD()
        _user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_tid))
        our_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        _user32.AttachThreadInput(our_tid, fg_tid.value, True)
        _user32.SetForegroundWindow(win["hwnd"])
        _user32.AttachThreadInput(our_tid, fg_tid.value, False)
        time.sleep(0.8)
        # Top-bar hamburger then the Plugins entry. These are absolute screen coordinates:
        # the window is maximized on the primary monitor, so its visible content origin is
        # the screen origin (the frame rect (-8,-31) includes off-screen borders -- adding
        # window-relative offsets would click off-screen). Established in the 2026-10-23/25
        # acceptance rounds.
        click_screen(70, 20)
        time.sleep(1.3)
        click_screen(79, 127)
        time.sleep(3.0)
        self.cdp.wait_page("PluginsDialog", timeout=20)

    def close_plugins_dialog(self):
        box = find_window(self.proc.pid, title_contains="Plugins", cls="#32770")
        if box:
            close_window(box["hwnd"])
            time.sleep(1.5)

    def dialog_rows(self):
        rows = self.cdp.eval("PluginsDialog", """
            (function(){var out=[];document.querySelectorAll('#pluginList .plugin-row').forEach(function(r){
              var cb=r.querySelector('input[type=checkbox]');
              out.push({name:(r.innerText||'').split('\\n')[0], checked:cb?cb.checked:null});});
              return JSON.stringify(out);})()
        """)
        return json.loads(rows) if rows else []

    def row(self, name):
        for r in self.dialog_rows():
            if name in r["name"]:
                return r
        return None

    def send_command(self, payload):
        return self.cdp.eval("PluginsDialog", "SendWXMessage(JSON.stringify(%s)); 'sent'" % json.dumps(payload))

    def toggle_plugin(self, name):
        check(self.row(name) is not None, "no row %r to toggle" % name)
        self.cdp.eval("PluginsDialog", """
            (function(name){
              var rows=document.querySelectorAll('#pluginList .plugin-row');
              for (var r of rows){ if ((r.innerText||'').indexOf(name)>=0){
                var cb=r.querySelector('input[type=checkbox]'); if(cb){cb.click(); return 'toggled';} }}
              return 'not-found';})("%s")
        """ % name)

    def refresh_plugins(self):
        self.send_command({"command": "refresh_plugins"})
        time.sleep(3.0)

    # -- plugin payloads / state ------------------------------------------------
    def plugin_payload(self, name_contains):
        data = self.cdp.eval("PluginsDialog", """
            JSON.stringify(Array.from(pluginsById.values())
              .filter(function(p){return String(p.name||'').indexOf("%s")>=0;})
              .map(function(p){return {name:p.name, is_loaded:p.is_loaded, status:p.status, error:p.error,
                                        caps:(p.capabilities||[]).map(function(c){return c.type+':'+c.name+':'+c.enabled;})};}))
        """ % name_contains)
        return json.loads(data) if data else []

    def tabs(self):
        return read_tab_strip(self.proc.pid)


# --------------------------------------------------------------------------- #
# Plugin fixture install (local-directory discovery shape)
# --------------------------------------------------------------------------- #
def install_plugin_dir(plugins_dir, name, source_dir, enabled=False, capabilities=()):
    """Drop a plugin directory + install-state sidecar into the isolated orca_plugins root."""
    dest = os.path.join(plugins_dir, name)
    check(not os.path.exists(dest), "fixture %s already installed" % name)
    shutil.copytree(source_dir, dest)
    state = {
        "capabilities": [{cap: True} for cap in capabilities],
        "enabled": enabled,
        "installed_from": "local",
        "installed_version": "1.0.0",
        "permissions": {"events": [], "fs_read": [], "fs_readwrite": [], "network_http": [],
                        "network_socket": [], "process": [], "threading": []},
        "plugin_name": name,
    }
    with open(os.path.join(dest, ".install_state.json"), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    return dest


def sidecar_of(plugins_dir, name):
    path = os.path.join(plugins_dir, name, ".install_state.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

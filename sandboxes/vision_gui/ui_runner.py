#!/usr/bin/env python3
# ui_runner.py — thin CustomTkinter shell over the vision_gui driver scripts.
#
# One small dependency (customtkinter) on top of the stdlib; the driver
# scripts keep all the real logic (seed/launch/vision), so this is purely a
# launcher UI: pick model file(s) -> run m1/m2/batch -> streamed log pane.
#
# Usage: .venv/Scripts/python ui_runner.py

import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness import winutil  # noqa: E402

SCRIPTS = {
    "m1": HERE / "m1_minimal_loop.py",
    "m2": HERE / "m2_slice_chain.py",
}

# Convenience defaults (replaceable via the file picker).
COMMON_MODELS = [
    r"C:\Users\snapmaker\Downloads\混色级联删除测试.3mf",
    r"C:\Users\snapmaker\Downloads\四料混色.3mf",
    r"C:\Users\snapmaker\Downloads\立方体.3mf",
]

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                                ctypes.c_wchar_p,
                                                ctypes.POINTER(ctypes.c_uint32)]
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


def find_app_window():
    """Largest visible window owned by a snapmaker-orca.exe process (any PID
    — the drivers run it as their child, so this shell cannot know the PID).
    """
    best = None
    best_area = -1
    for hwnd, pid in winutil.enum_windows():
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            continue
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = ctypes.c_uint32(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                if buf.value.lower().endswith("snapmaker-orca.exe"):
                    l, t, r, b = winutil.window_rect(hwnd)
                    if (r - l) * (b - t) > best_area:
                        best, best_area = hwnd, (r - l) * (b - t)
        finally:
            kernel32.CloseHandle(h)
    return best


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


class Runner(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("vision_gui runner — black-box GUI test sandbox")
        self.geometry("1280x680")
        self.minsize(720, 480)
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.proc: subprocess.Popen | None = None
        self.batch_pending: list[str] = []

        # ---- model input row ----
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(top, text="Model(s):").pack(side="left", padx=(6, 4))
        self.models = ctk.CTkTextbox(top, height=64, width=520, wrap="none",
                                     font=("Consolas", 12))
        self.models.pack(side="left", padx=4)
        self.models.insert("1.0", COMMON_MODELS[0])
        col = ctk.CTkFrame(top, fg_color="transparent")
        col.pack(side="left", padx=4)
        ctk.CTkButton(col, text="Browse…", width=110, command=self._browse).pack(pady=2)
        ctk.CTkButton(col, text="Common", width=110, command=self._common).pack(pady=2)

        # ---- run buttons ----
        btns = ctk.CTkFrame(self)
        btns.pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(btns, text="M1 minimal loop", command=lambda: self._run_m("m1")).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="M2 slice chain", command=self._run_m2).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Batch M2 (all models)", command=self._run_batch).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Stop", fg_color="#b00020", hover_color="#8f001a",
                      command=self._stop).pack(side="left", padx=4)
        self.status = ctk.CTkLabel(btns, text="idle", text_color="#888888")
        self.status.pack(side="right", padx=8)

        # ---- log + live-view panes ----
        mid = ctk.CTkFrame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log = ctk.CTkTextbox(mid, wrap="none", font=("Consolas", 11),
                                  activate_scrollbars=True)
        self.log.pack(side="left", fill="both", expand=True)
        self.log.tag_config("ok", foreground="#3ddc84")
        self.log.tag_config("err", foreground="#ff6b6b")
        self.log.tag_config("sys", foreground="#8a8a8a")

        side = ctk.CTkFrame(mid, width=400, corner_radius=8)
        side.pack(side="right", fill="y", padx=(8, 0))
        side.pack_propagate(False)
        ctk.CTkLabel(side, text="live view (PrintWindow, 1s poll)",
                     font=("Segoe UI", 11, "bold")).pack(pady=(6, 2))
        self.view = ctk.CTkLabel(side, text="no app session", text_color="#666666")
        self.view.pack(fill="both", expand=True, padx=6, pady=6)
        self._last_img = None

        self.after(100, self._poll)
        threading.Thread(target=self._shot_loop, daemon=True).start()

    # ---- helpers ---------------------------------------------------------

    def _models(self) -> list[str]:
        return [l.strip() for l in self.models.get("1.0", "end").splitlines() if l.strip()]

    def _browse(self):
        files = filedialog.askopenfilenames(
            title="Pick model file(s)", filetypes=[("Models", "*.3mf *.stl"), ("All", "*.*")])
        if files:
            self.models.delete("1.0", "end")
            self.models.insert("1.0", "\n".join(files))

    def _common(self):
        self.models.delete("1.0", "end")
        self.models.insert("1.0", "\n".join(COMMON_MODELS))

    def _log(self, text: str, tag: str = "log"):
        self.log.insert("end", text, tag)
        self.log.see("end")

    def _poll(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item[0] == "__STATUS__":
                    self.status.configure(text=item[1], text_color=item[2])
                elif item[0] == "__NEXT__":
                    self._next_batch()
                elif item[0] == "__IMG__":
                    _, img, size = item
                    self._last_img = img  # keep a reference (CTkImage GC)
                    self.view.configure(image=img, text=f"{size[0]}x{size[1]}")
                elif item[0] == "__NOAPP__":
                    if self._last_img is not None:
                        self._last_img = None
                        self.view.configure(image=None, text="no app session")
                else:
                    text, tag = item
                    self._log(text, tag)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _shot_loop(self):
        """Live-view thread: find the app window by process name, capture it
        with PrintWindow and push a CTkImage to the UI queue (1s poll)."""
        while True:
            try:
                hwnd = find_app_window()
                if hwnd:
                    cap = winutil.capture_window(hwnd)
                    arr = np.frombuffer(cap[2], np.uint8).reshape(cap[1], cap[0], 4)
                    rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
                    img = Image.fromarray(rgb)
                    img.thumbnail((380, 420))
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                           size=img.size)
                    self.queue.put(("__IMG__", ctk_img, (cap[0], cap[1])))
                else:
                    self.queue.put(("__NOAPP__",))
            except Exception:
                pass
            time.sleep(1.0)

    # ---- run -------------------------------------------------------------

    def _run(self, script: Path, args: list[str], label: str):
        if self.proc and self.proc.poll() is None:
            self._log("(a run is already active)\n", "err")
            return
        cmd = [sys.executable, str(script), *args]
        env = {k: v for k, v in os.environ.items() if k.upper() != "ORCA_GUI_TEST_MODE"}
        self._log(f"$ {script.name} {' '.join(args)}\n", "sys")
        self.status.configure(text=f"running {label}…", text_color="#888888")
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace",
                                     env=env, cwd=str(HERE))
        threading.Thread(target=self._reader, args=(label,), daemon=True).start()

    def _reader(self, label: str):
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            if any(k in line for k in ("GREEN", "PASS", "TOOK")):
                tag = "ok"
            elif any(k in line for k in ("RED", "FAIL", "Error", "Traceback")):
                tag = "err"
            else:
                tag = "log"
            self.queue.put((line, tag))
        rc = self.proc.wait()
        verdict = "GREEN" if rc == 0 else f"RED (exit {rc})"
        color = "#3ddc84" if rc == 0 else "#ff6b6b"
        self.queue.put((f"\n===== {label}: {verdict} =====\n", "ok" if rc == 0 else "err"))
        self.queue.put(("__STATUS__", f"done — {verdict}", color))
        if self.batch_pending:
            self.queue.put(("__NEXT__", None))

    def _run_m(self, key: str):
        self._run(SCRIPTS[key], [], key)

    def _run_m2(self):
        models = self._models()
        if not models:
            self._log("(no model given)\n", "err")
            return
        self._run(SCRIPTS["m2"], ["--model", models[0]], "m2")

    def _run_batch(self):
        models = self._models()
        if not models:
            self._log("(no model given)\n", "err")
            return
        self.batch_pending = list(models)
        self._log(f"(batch of {len(models)} model(s))\n", "sys")
        self._next_batch()

    def _next_batch(self):
        if not self.batch_pending:
            self._log("(batch finished)\n", "sys")
            return
        m = self.batch_pending.pop(0)
        self._run(SCRIPTS["m2"], ["--model", m], f"m2 {Path(m).name}")

    def _stop(self):
        if not (self.proc and self.proc.poll() is None):
            return
        if messagebox.askyesno("Stop run",
                               "Hard-kill the current run?\n\n"
                               "WARNING: killing the driver can leave the app orphaned and "
                               "corrupt the shared Sentry crashpad DB (README pitfall #11) — "
                               "if later launches crash, start the app once manually to "
                               "rebuild it."):
            self.batch_pending = []
            self.proc.kill()
            self._log("(stopped by user — driver killed; check for orphaned app/Sentry state)\n", "sys")


if __name__ == "__main__":
    Runner().mainloop()

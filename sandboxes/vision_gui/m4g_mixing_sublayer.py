#!/usr/bin/env python3
# m4g_mixing_sublayer.py — 'Subdivide Mix Layer' (config dithering_local_z_mode):
# the sidebar Process panel exposes the checkbox on the Multimaterial page in
# Advanced mode; toggling it at layer height 0.4 (>0.1) pops NO warning, at
# layer height 0.1 (<=0.1) pops the 'Configuration Conflict' advisory while
# still applying the check, and slicing completes with the option enabled
# (表1 #36/#37, 表2 #40/#41).
#
# White-box refs:
#   - PrintConfig.cpp:4343-4348 — 'dithering_local_z_mode' label 'Subdivide
#     Mix Layer', def->mode = comAdvanced (hidden until the Process panel's
#     'Advanced' switch flips the app mode).
#   - Tab.cpp:2625-2629 — the option lives in the 'Color Mixing
#     (Experimental)' group, LAST group of the Multimaterial page
#     (TabPrint::build, Multimaterial page starts with 'Prime tower').
#   - Tab.cpp:1566-1575 — enabling with layer_height <= 0.1+EPSILON pops a
#     RichMessageDialog titled 'Configuration Conflict' ('The current layer
#     height is 0.1 mm or below. Enabling Subdivide Mixing Layers may
#     cause...', wxOK) AFTER the config change is applied.
#   - Tab.cpp:1815-1826 — the mirrored advisory when SETTING a layer height
#     <= 0.1 while the option is enabled (not hit here: we go 0.4 -> 0.1
#     while OFF, then 0.1 -> 0.4 while ON, both advisories silent for the
#     value that lands).
#   - Tab.cpp:1781-1813 — ANY layer-height commit is range-checked against
#     the nozzle limits (fdm_U1.json: min 0.08 / max 0.32): typing 0.1 is in
#     range (silent), typing 0.4 back pops the 'Layer height exceeds the
#     limit...' Adjust/Ignore dialog — 'Ignore' keeps the preset value.
#   - OptionsGroup.cpp:248 activate_line — labels are PAINTED by OG_CustomCtrl
#     (no label windows); a checkbox option renders as an ~18px empty-text
#     wxBitmapToggleButton (Widgets/CheckBox.hpp) at the row's value column.
#
# Black-box path: boot standard fixture -> real-click the 'Advanced'
# SwitchButton on the Process title row -> real-click the 'Multimaterial' tab
# (self-drawn ButtonsListCtrl item, located by its window text) -> wheel the
# options viewport until OCR shows 'Subdivide' -> real-click the 18px checkbox
# Button on that row, state read from the frame capture (teal fraction):
#   #41a at lh 0.4: check ON -> no new #32770 within 3s + checked; uncheck.
#   #37/#41b set lh 0.1 (Quality page topmost Edit, real typing) -> check ON ->
#   'Configuration Conflict' #32770 ('0.1 mm or below') -> OK -> stays checked.
#   #36 lh back to 0.4 (no warning) -> slice completes (done badge) -> uncheck,
#   app alive.
#
# Scope note (表1 #36 numeric half): the subdivided sub-layer height itself is
# solver-dependent; the gcode local-Z parse is documented OUT of black-box
# scope — the automated assertion is the option applying + a completed slice.
# Stale-table notes: none — #37/#40/#41 match the current build dialogs.

import ctypes
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded, wait_slicing_done  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       click_slice_start, verdict)

user32 = ctypes.WinDLL("user32")
LOG = "[m4g]"
SB_W = 424
VIEW_Y0, VIEW_Y1 = 700, 800  # fallback options band; the real band is read
                             # from the viewport panel (view_band) — it
                             # stretches with the window (73px windowed,
                             # 313px maximized)


def client(session, x, y):
    return winutil.client_to_screen(session.hwnd, x, y)


def frect(session):
    return winutil.window_rect(session.hwnd)


def to_local(session, r):
    f = frect(session)
    return (r[0] - f[0], r[1] - f[1], r[2] - f[0], r[3] - f[1])


def kids(session):
    out = []
    for t, c, r, h in mixing_util.children(session.hwnd):
        lx, ly = r[0] - frect(session)[0], r[1] - frect(session)[1]
        out.append((t, c, r, h, lx, ly))
    return out


def real_click(rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)
    time.sleep(0.8)


def view_band(session):
    """Visible options viewport band (client y0, y1), read from the panel's
    own rect so it tracks the window height. Recalibrated 08-31: with the
    fixed 700..800 band the maximized run wheeled the LAST group ('Color
    Mixing') fully into view (title resting at ty1~970 at max scroll) and
    still rejected it — the title could never enter [702,776]."""
    vp = options_viewport(session)
    if not vp:
        return VIEW_Y0, VIEW_Y1
    x0, y0, x1, y1 = to_local(session, vp[0])
    return y0, y1


def ocr_band(session, y0=None, y1=None):
    """OCR words of the sidebar options band, client coords."""
    if y0 is None or y1 is None:
        y0, y1 = view_band(session)
    img = capture_bgr(session)
    words = mdu.ocr_words_img(img[y0:y1, 0:SB_W], scale=3)
    return [(w, x, y + y0, w_w, w_h) for w, x, y, w_w, w_h in words]


def advanced_switch(session):
    """The 'Advanced' SwitchButton right of its label on the Process title
    row (empty-text wxBitmapToggleButton; icons sit further right at
    x > 365, the Global/Objects pills left at x < 220)."""
    label = None
    for t, c, r, h, lx, ly in kids(session):
        if c == "Static" and t.strip() == "Advanced" \
                and user32.IsWindowVisible(h) and 590 <= ly <= 640:
            label = (lx, ly, r)
            break
    if not label:
        return None
    cands = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "Button" or t.strip() or not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (16 <= w <= 56 and 10 <= hh <= 28):
            continue
        if 590 <= ly <= 640 and label[0] + 20 <= lx <= label[0] + 130:
            cands.append((r, h))
    cands.sort(key=lambda rh: rh[0][0])
    return cands[0] if cands else None


def advanced_on(session):
    """Switch knob position from the frame capture: ON paints the knob at the
    RIGHT half of the switch (teal). Returns (on_frac_left_half, diff_hint)."""
    sw = advanced_switch(session)
    if not sw:
        return None
    r = to_local(session, sw[0])
    img = capture_bgr(session)
    sub = img[r[1] + 2:r[3] - 2, r[0] + 2:r[2] - 2].astype(int)
    if sub.size == 0:
        return None
    mid = sub.shape[1] // 2
    def chroma(part):
        spread = part.max(axis=2) - part.min(axis=2)
        return float((spread > 40).mean())
    return chroma(sub[:, :mid]), chroma(sub[:, mid:])


def tab_button(session, name):
    """The self-drawn process tab item: wxWindowNR child whose text is the
    tab name, ~22px tall, in the tab row band (client y 680-702)."""
    for t, c, r, h, lx, ly in kids(session):
        if c == "wxWindowNR" and t.strip() == name \
                and user32.IsWindowVisible(h) \
                and 14 <= r[3] - r[1] <= 30 and 30 <= r[2] - r[0] <= 130 \
                and 675 <= ly <= 705 and lx > 5:
            return r, h
    return None


TAB_STRATEGY = [0]  # remembered across calls: 0 real, 1 message, 2 down/up
RESET_WHEEL_NOTCHES = 40  # tab switch: force the options viewport back to
                          # top. Recalibrated 08-31: the scroll offset is
                          # SHARED across pages, so arriving from a
                          # max-scrolled Multimaterial page left Quality
                          # mid-content and 15 notches (~400-600px) could
                          # not recover the top (measured: Layer height
                          # unreachable on the 0.4-restore visit).


def _click_tab_item(session, rect, strategy):
    if strategy == 0:
        real_click(rect)
        return
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    if strategy == 1:
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.15)
        winutil.msg_click_screen(cx, cy, session.hwnd)
        time.sleep(0.8)
        return
    # strategy 2: split down / dwell / up
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.2)
    sw = winutil.user32.GetSystemMetrics(0)
    sh = winutil.user32.GetSystemMetrics(1)
    absx, absy = int(cx * 65535 / sw), int(cy * 65535 / sh)
    ev = winutil._INPUT()
    ev.type = 0
    ev.value.dx, ev.value.dy = absx, absy
    ev.value.dwFlags = winutil.MOUSEEVENTF_MOVE | winutil.MOUSEEVENTF_LEFTDOWN \
        | winutil.MOUSEEVENTF_ABSOLUTE
    winutil.user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(winutil._INPUT))
    time.sleep(0.25)
    ev2 = winutil._INPUT()
    ev2.type = 0
    ev2.value.dx, ev2.value.dy = absx, absy
    ev2.value.dwFlags = winutil.MOUSEEVENTF_LEFTUP | winutil.MOUSEEVENTF_ABSOLUTE
    winutil.user32.SendInput(1, ctypes.byref(ev2),
                             ctypes.sizeof(winutil._INPUT))
    time.sleep(0.8)


def click_tab(session, name, expect_word, timeout_s=75.0):
    """Switch the process page by clicking the tab item, VERIFY via a
    page-unique OCR word at the top of the options viewport (Quality ->
    'height', Multimaterial -> 'tower'), and wait out the sizer settle.
    After a field edit the tab strip may ignore plain real clicks
    (measured 08-30), so strategies rotate: real click -> message-level
    click (m1's ButtonsListCtrl path) -> split down/up."""
    strategies = [TAB_STRATEGY[0]] + [s for s in (0, 1, 2) if s != TAB_STRATEGY[0]]
    deadline = time.monotonic() + timeout_s
    clicked = False
    n_poll = 0
    si = 0
    while time.monotonic() < deadline:
        hit = tab_button(session, name)
        if hit:
            strategy = strategies[min(si // 2, len(strategies) - 1)]
            _click_tab_item(session, hit[0], strategy)
            clicked = True
            time.sleep(1.5)
        else:
            print(f"{LOG} click_tab({name}): tab item NOT FOUND")
        vp = options_viewport(session)
        if vp:
            wheel_viewport(session, vp, RESET_WHEEL_NOTCHES, delta=120)
        joined = " ".join(w.lower() for w, *_ in ocr_band(session))
        print(f"{LOG} click_tab({name}) poll{n_poll} strat{strategy}: "
              f"{joined[:70]!r}")
        if expect_word in joined:
            TAB_STRATEGY[0] = strategy
            time.sleep(3.0)  # sizer/fixup_items_positions settle
            return clicked
        if n_poll == 2:
            import cv2
            img = capture_bgr(session)
            cv2.imwrite(str(HERE / "artifacts" / "m4g_tab_stuck.png"), img)
        n_poll += 1
        si += 1
        time.sleep(0.5)
    return False


def options_viewport(session):
    """The Multimaterial/Quality page viewport: a wide 'panel' wxWindowNR
    filling the band under the tab row. Size-adaptive (recalibrated 08-31
    on the maximized window): the panel TOP is anchored at local y ~719-725,
    but its HEIGHT stretches with the window (73px at the 800-tall window,
    313px maximized) — the old 50..120 height cap matched only the windowed
    era and made every wheel a silent no-op (measured via diag_m4g_max)."""
    best = None
    for t, c, r, h, lx, ly in kids(session):
        if c != "wxWindowNR" or t.strip() != "panel":
            continue
        if not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if 380 <= w <= 440 and hh >= 50 and 700 <= ly <= 740:
            if best is None or hh > best[0][3] - best[0][1]:
                best = (r, h)
    return best


MOUSEEVENTF_WHEEL = 0x0800


def real_wheel(session, x_client, y_client, notches, delta=-120):
    """Real wheel input at a client point (SetCursorPos + SendInput wheel).
    Real input goes through the OS routing (focused window -> wx forwards
    to the window under the cursor), unlike SendMessage'd WM_MOUSEWHEEL."""
    sx, sy = client(session, x_client, y_client)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.15)
    for _ in range(abs(notches)):
        ev = winutil._INPUT()
        ev.type = 0
        ev.value.dx = 0
        ev.value.dy = 0
        ev.value.mouseData = delta & 0xFFFFFFFF
        ev.value.dwFlags = MOUSEEVENTF_WHEEL
        winutil.user32.SendInput(1, ctypes.byref(ev),
                                 ctypes.sizeof(winutil._INPUT))
        time.sleep(0.08)
    time.sleep(0.4)


def wheel_viewport(session, viewport, notches, delta=-120):
    r, h = viewport
    cx = (r[0] + r[2]) // 2 - frect(session)[0]
    cy = (r[1] + r[3]) // 2 - frect(session)[1]
    real_wheel(session, cx, cy, notches, delta=delta)


def scroll_to_word(session, substr, max_notches=160, notches_per_round=5):
    """Wheel the options viewport (real input) until `substr` OCRs inside
    it. Returns the word's client rect or None."""
    seen = 0
    last_join = ""
    while seen <= max_notches:
        words = ocr_band(session)
        for w, x, y, ww, hh in words:
            if substr.lower() in w.lower():
                if seen:
                    print(f"{LOG} scrolled {seen} notches to reach {substr!r}")
                return (x, y, x + ww, y + hh)
        join = " ".join(w for w, *_ in words)
        if join != last_join:
            print(f"{LOG} scroll@{seen}: {join[:90]!r}")
            last_join = join
        vp = options_viewport(session)
        if not vp:
            print(f"{LOG} scroll: viewport lost at {seen}")
            return None
        wheel_viewport(session, vp, notches_per_round)
        seen += notches_per_round
    print(f"{LOG} scroll: {substr!r} NOT reached in {seen} notches; "
          f"last={last_join[:90]!r}")
    return None


def row_checkboxes(session, y_client, y_tol=12, x_lo=200, x_hi=330):
    """Empty-text ~18px Buttons (option checkboxes) on an option row band;
    candidates that horizontally overlap a same-band Edit are spin/undo
    artifacts and dropped."""
    band = [k for k in kids(session)
            if k[1] == "Button" and not k[0].strip()
            and user32.IsWindowVisible(k[3])]
    sq = [(r, h) for t, c, r, h, lx, ly in band
          if 12 <= r[2] - r[0] <= 26 and 12 <= r[3] - r[1] <= 26
          and abs((r[1] + r[3]) // 2 - frect(session)[1] - y_client) <= y_tol
          and x_lo <= lx <= x_hi]
    edits = [(r, h) for t, c, r, h, lx, ly in kids(session)
             if c == "Edit" and user32.IsWindowVisible(h)
             and abs((r[1] + r[3]) // 2 - frect(session)[1] - y_client) <= y_tol]
    out = []
    for r, h in sq:
        cx = (r[0] + r[2]) // 2
        if any(abs((er[0] + er[2]) // 2 - cx) < 60 for er, _eh in edits):
            continue
        out.append((r, h))
    out.sort(key=lambda rh: rh[0][0])
    return out


def checked_state(session, rect):
    """Teal fraction of the checkbox rect in the FRAME capture (the real
    render; PrintWindow washes the alpha bitmaps). Checked box paints the
    teal checkmark (#009688), unchecked is a plain gray/white box."""
    x0, y0, x1, y1 = to_local(session, rect)
    img = capture_bgr(session)
    sub = img[y0 + 2:y1 - 2, x0 + 2:x1 - 2].astype(int)
    if sub.size == 0:
        return 0.0
    spread = sub.max(axis=2) - sub.min(axis=2)
    return float((spread > 50).mean())


def find_conflict_dialog(session, known, timeout_s=8.0):
    """hwnd of a NEW small #32770 (RichMessageDialog) of the app, or None."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and h not in known \
                    and (r[3] - r[1]) < 300:
                return h
        time.sleep(0.25)
    return None


def dialog_body(pid, dlg):
    body = " ".join(t for t, c, r, h in mixing_util.children(dlg)
                    if t.strip() and c == "Static")
    if not body:
        from harness import ocr_util
        try:
            body = ocr_util.ocr_hwnd(dlg)
        except Exception:
            pass
    return body


def dismiss_conflict(session, dlg):
    """Click the dialog's OK (RichMessageDialog wxOK)."""
    hit = mixing_util.child_by_text(dlg, "OK")
    if not hit:
        return False
    r = hit[2]
    winutil.real_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    time.sleep(1.2)
    return True


def top_dialog_set(session):
    return set(h for _c, _t, _r, h in mixing_util.toplevel(session.pid))


def float_edits_in_view(session):
    """Visible Edit children inside the options viewport band with a float
    value, topmost first (the Quality page's 'Layer height' is the first
    option row; the label is painted, so disambiguation is positional)."""
    y0, y1 = view_band(session)
    out = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "Edit" or not user32.IsWindowVisible(h):
            continue
        if not (y0 <= ly <= y1 and 220 <= lx <= 340):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (50 <= w <= 140 and 12 <= hh <= 26):
            continue
        val = mdu.edit_value(h)
        try:
            float(val)
        except ValueError:
            continue
        out.append((r, h, val))
    out.sort(key=lambda x: x[0][1])
    return out


def wait_layer_height_edit(session, timeout_s=180.0):
    """Topmost float Edit on the (Quality) page = the 'Layer height' option
    (first option row; the label is painted by OG_CustomCtrl). If nothing
    is found, periodically force the viewport back to top — the scroll
    offset persists across tab switches (RESET_WHEEL_NOTCHES note)."""
    deadline = time.monotonic() + timeout_s
    n = 0
    while time.monotonic() < deadline:
        eds = float_edits_in_view(session)
        if eds:
            return eds[0]
        n += 1
        if n % 3 == 0:
            vp = options_viewport(session)
            if vp:
                wheel_viewport(session, vp, RESET_WHEEL_NOTCHES, delta=120)
        time.sleep(1.0)
    return None


GUITHREADINFO = mdu.GUITHREADINFO


def focus_hwnd(hwnd):
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    user32.GetGUIThreadInfo(tid, ctypes.byref(info))
    return info.hwndFocus


def real_edit_set(session, rect, hwnd, text):
    """Real-click focus an Edit, Ctrl+A + Del, unicode-type `text`, Enter.
    Returns the live text (mdu.edit_value) or None when focus failed."""
    VK_CONTROL, VK_A, VK_DELETE, VK_RETURN = 0x11, 0x41, 0x2E, 0x0D
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    ok_focus = False
    for _ in range(4):
        winutil.force_set_foreground(session.hwnd)
        time.sleep(0.4)
        winutil.user32.SetCursorPos(x, y)
        time.sleep(0.15)
        winutil.real_click_screen(x, y)
        time.sleep(0.5)
        if focus_hwnd(hwnd) == hwnd:
            ok_focus = True
            break
    if not ok_focus:
        return None
    mdu._send_keys([(VK_CONTROL, False), (VK_A, False), (VK_A, True),
                    (VK_CONTROL, True)])
    time.sleep(0.15)
    mdu._send_keys([(VK_DELETE, False), (VK_DELETE, True)])
    time.sleep(0.2)
    mdu._send_chars(text)
    time.sleep(0.3)
    mdu._send_keys([(VK_RETURN, False), (VK_RETURN, True)])
    time.sleep(0.6)
    return mdu.edit_value(hwnd)


def group_title(session, substr):
    """An options-group title (':StaticLine' = wxWindowNR with the group
    name, full width). Its rect tracks the scroll offset exactly, so it is
    usable for positioning even when scrolled out of view (the 20x20
    same-text icon overlays are filtered by width)."""
    f = frect(session)
    for t, c, r, h, lx, ly in kids(session):
        if c == "wxWindowNR" and substr.lower() in t.lower() \
                and user32.IsWindowVisible(h) \
                and (r[2] - r[0]) > 100 and lx < 424 and ly > 400:
            return r, h
    return None


def neutralize_focus(session):
    """After real typing the keyboard focus sits in the option Edit; with
    that focus the real wheel no longer scrolls the options viewport and
    real clicks on the tab strip are ignored (measured 08-30). ESC + a
    harmless click on the 'Process' title Static returns focus to the
    panel."""
    mdu._send_keys([(0x1B, False), (0x1B, True)])
    time.sleep(0.3)
    for t, c, r, h, lx, ly in kids(session):
        if c == "Static" and t.strip() == "Process" \
                and user32.IsWindowVisible(h) and 595 <= ly <= 635:
            real_click(r)
            return True
    return False


def scroll_group_into_view(session, substr, timeout_s=420.0):
    """Wheel the options viewport until the group title `substr` sits high
    enough in the VISIBLE band that its FIRST OPTION ROW is also fully
    visible (title bottom within [band_top+2, band_bottom-24], band from
    view_band()). 1-notch steps with position read from the title's own
    rect (a multi-notch wheel can jump whole groups between OCRs).
    Self-heals a wheel stuck on the Edit focus via neutralize_focus().
    Returns (rect, hwnd) or None."""
    deadline = time.monotonic() + timeout_s
    f = frect(session)
    last_y = None
    stuck = 0
    while time.monotonic() < deadline:
        hit = group_title(session, substr)
        vp = options_viewport(session)
        if not vp:
            time.sleep(0.5)
            continue
        if hit:
            ty1 = hit[0][3] - f[1]
            y0, y1 = view_band(session)
            if y0 + 2 <= ty1 <= y1 - 24:
                return hit
            wheel_viewport(session, vp, 1,
                           delta=-120 if ty1 > y1 - 24 else 120)
            if last_y == ty1:
                stuck += 1
                if stuck >= 3:
                    print(f"{LOG} wheel stuck at ty1={ty1} -> neutralize "
                          f"focus")
                    neutralize_focus(session)
                    stuck = 0
            else:
                stuck = 0
            last_y = ty1
        else:
            wheel_viewport(session, vp, 4, delta=-120)
        time.sleep(0.12)
    return None


def find_subdivide_row(session):
    """Scroll the 'Color Mixing (Experimental)' group into view and locate
    the Subdivide Mix Layer row: OCR confirm + the 18px checkbox candidate
    on the first option row under the group title. If the row is still cut
    off, wheel one more notch and retry."""
    for _ in range(6):
        hit = scroll_group_into_view(session, "Color Mixing")
        if not hit:
            return None, []
        tr = hit[0]
        ty1 = tr[3] - frect(session)[1]
        word = None
        for w, x, y, ww, hh in ocr_band(session):
            if "subdivi" in w.lower() \
                    and abs((y + hh // 2) - (ty1 + 14)) <= 40:
                word = (x, y, x + ww, y + hh)
                break
        y_row = (word[1] + word[3]) // 2 if word else ty1 + 16
        cands = row_checkboxes(session, y_row, y_tol=14)
        if word and cands:
            return word, cands
        vp = options_viewport(session)
        if vp:
            wheel_viewport(session, vp, 1, delta=-120)
        time.sleep(0.4)
    return None, []


def toggle_subdivide(session, want_checked, tries=4):
    """Click the Subdivide checkbox until the frame-capture state reads
    `want_checked`. Rotates real -> message-level click on retries. Returns
    (final_state, clicked_btn_rect) or (None, None)."""
    for attempt in range(tries):
        word, cands = find_subdivide_row(session)
        if not word or not cands:
            return None, None
        for rect, h in cands[:3]:
            before = checked_state(session, rect)
            if attempt < 2:
                real_click(rect)
            else:
                cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
                winutil.user32.SetCursorPos(cx, cy)
                time.sleep(0.15)
                winutil.msg_click_screen(cx, cy, session.hwnd)
                time.sleep(1.0)
            time.sleep(0.8)
            after = checked_state(session, rect)
            print(f"{LOG} subdivide click(att{attempt}): before={before:.2f} "
                  f"after={after:.2f}")
            # Checked reads ~0.21 teal fraction on this build/layout, an
            # unchecked box ~0.00-0.06 (measured 08-31 on the maximized
            # window; the windowed-era 0.25 threshold misclassified every
            # checked state and made the toggle rounds flail).
            now_on = after > 0.13
            if now_on == want_checked and abs(after - before) > 0.05:
                return now_on, rect
            if now_on == want_checked:
                return now_on, rect
        time.sleep(0.8)
    word, cands = find_subdivide_row(session)
    if word and cands:
        st = checked_state(session, cands[0][0])
        if (st > 0.13) == want_checked:
            return st > 0.13, cands[0][0]
    return None, None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model loaded: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            return verdict(results)
        time.sleep(2.0)

        # --- flip the Process panel 'Advanced' switch (comSimple hides the
        #     comAdvanced option, PrintConfig.cpp:4347) ---
        sw = advanced_switch(session)
        print(f"{LOG} advanced switch: {sw}")
        results["advanced switch located"] = "PASS" if sw else "FAIL"
        if not sw:
            return verdict(results)
        st0 = advanced_on(session)
        real_click(sw[0])
        time.sleep(2.0)
        st1 = advanced_on(session)
        print(f"{LOG} advanced knob chroma L/R: before={st0} after={st1}")
        flipped = (st0 is not None and st1 is not None
                   and abs(st0[0] - st1[0]) + abs(st0[1] - st1[1]) > 0.05)
        results["advanced mode toggles"] = "PASS" if flipped else "FAIL"

        # --- Multimaterial tab (ButtonsListCtrl item with window text) ---
        tab_ok = click_tab(session, "Multimaterial", "tower")
        print(f"{LOG} multimaterial tab switched: {tab_ok}")
        results["multimaterial tab switches"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            return verdict(results)

        # --- scroll until 'Subdivide' paints, locate its checkbox ---
        word, cands = find_subdivide_row(session)
        print(f"{LOG} subdivide word: {word} candidates: "
              f"{[to_local(session, r) for r, _h in cands]}")
        located = bool(word and cands)
        results["Subdivide Mix Layer reachable in Advanced mode"] = (
            "PASS" if located else "FAIL")
        if not located:
            return verdict(results)

        # --- #41a: toggle ON at lh 0.4 -> NO warning ---
        known = top_dialog_set(session)
        st, rect = toggle_subdivide(session, want_checked=True)
        print(f"{LOG} #41a toggle on: state={st} rect={rect}")
        late = find_conflict_dialog(session, known, timeout_s=3.0)
        popped_txt = dialog_body(session.pid, late) if late else ""
        if late:
            print(f"{LOG} UNEXPECTED dialog: {popped_txt[:120]!r}")
            dismiss_conflict(session, late)
        results["#41a at 0.4mm: no warning + checks on"] = (
            "PASS" if (st is True and late is None) else "FAIL")

        # --- uncheck (still no warning) ---
        known = top_dialog_set(session)
        st_off, _r = toggle_subdivide(session, want_checked=False)
        late2 = find_conflict_dialog(session, known, timeout_s=2.0)
        if late2:
            dismiss_conflict(session, late2)
        results["#41a uncheck silent at 0.4mm"] = (
            "PASS" if (st_off is False and late2 is None) else "FAIL")

        # --- Quality tab: set layer height to 0.1 (real typing) ---
        qtab = click_tab(session, "Quality", "height")
        print(f"{LOG} quality tab switched: {qtab}")
        hit = wait_layer_height_edit(session) if qtab else None
        lh_ok = False
        lh_rect = None
        if hit:
            lh_rect, lh_h, lh_val = hit
            new_val = real_edit_set(session, lh_rect, lh_h, "0.1")
            print(f"{LOG} layer height edit: {lh_val!r} -> {new_val!r}")
            neutralize_focus(session)  # wheel/clicks die while the Edit holds focus
            lh_ok = bool(new_val and new_val.startswith("0.1"))
        results["layer height sets to 0.1"] = "PASS" if lh_ok else "FAIL"
        if not lh_ok:
            results["#37/#41b conflict dialog at 0.1mm"] = "FAIL"
            results["#36 slice with Subdivide enabled"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- Multimaterial again: toggle ON at 0.1 -> 'Configuration
        #     Conflict' advisory, then the checkbox STAYS checked ---
        click_tab(session, "Multimaterial", "tower")
        word, cands = find_subdivide_row(session)
        if not (word and cands):
            results["#37/#41b conflict dialog at 0.1mm"] = "FAIL"
            results["#36 slice with Subdivide enabled"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)
        known = top_dialog_set(session)
        st_on, rect = toggle_subdivide(session, want_checked=True)
        warn = find_conflict_dialog(session, known, timeout_s=6.0)
        wtitle = wbody = ""
        if warn:
            for cls, txt, r, h in mixing_util.toplevel(session.pid):
                if h == warn:
                    wtitle = txt
            wbody = dialog_body(session.pid, warn)
            print(f"{LOG} conflict dialog: title={wtitle!r} "
                  f"body={wbody[:140]!r}")
        dismissed = dismiss_conflict(session, warn) if warn else False
        time.sleep(1.0)
        st_after = checked_state(session, rect) if rect else 0.0
        print(f"{LOG} #41b state after dismiss: {st_after:.2f} "
              f"st_on={st_on}")
        results["#37/#41b conflict dialog at 0.1mm"] = (
            "PASS" if (warn is not None and dismissed
                       and "0.1 mm or below" in wbody) else "FAIL")

        # --- back to 0.4 for slicing. NOTE: the U1 0.8 nozzle caps
        #     max_layer_height at 0.32 (fdm_U1.json), so committing 0.4 pops
        #     the 'Layer height exceeds the limit...' Adjust/Ignore dialog
        #     (Tab.cpp:1794-1812) — 'Ignore' keeps the preset value. ---
        click_tab(session, "Quality", "height")
        hit2 = wait_layer_height_edit(session)
        lh_ok2 = False
        if hit2:
            r2, h2, v2 = hit2
            known = top_dialog_set(session)
            new2 = real_edit_set(session, r2, h2, "0.4")
            print(f"{LOG} layer height back: {v2!r} -> {new2!r}")
            neutralize_focus(session)
            lh_ok2 = bool(new2 and new2.startswith("0.4"))
            rng = find_conflict_dialog(session, known, timeout_s=6.0)
            if rng:
                hit_ign = mixing_util.child_by_text(rng, "Ignore")
                btn = "Ignore" if hit_ign else "No"
                print(f"{LOG} range dialog popped -> click {btn!r}")
                mixing_util.click_button(rng, btn)
                time.sleep(1.2)
        results["layer height back to 0.4"] = "PASS" if lh_ok2 else "FAIL"

        # --- #36: slice with Subdivide enabled ---
        if not lh_ok2:
            results["#36 slice with Subdivide enabled"] = "FAIL"
            results["state restored + app alive"] = "FAIL"
            return verdict(results)
        started = click_slice_start(session)
        done, done_score = (False, 0.0)
        if started:
            done, done_score = wait_slicing_done(session, timeout_s=1500)
        print(f"{LOG} #36 slice started={started} done={done} "
              f"(score {done_score:.3f})")
        results["#36 slice with Subdivide enabled"] = (
            "PASS" if (started and done) else "FAIL")

        # --- restore: uncheck, confirm ---
        click_tab(session, "Multimaterial", "tower")
        st_end, _r = toggle_subdivide(session, want_checked=False)
        print(f"{LOG} final uncheck: {st_end}")
        results["subdivide off after slice + app alive"] = (
            "PASS" if (st_end is False and session.alive()) else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())

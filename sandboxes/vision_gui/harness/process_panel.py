#!/usr/bin/env python3
# process_panel.py — generic driver for the RIGHT-SIDEBAR Process panel
# (settings sidebar), extracted from m4g_mixing_sublayer (which remains the
# Color-Mixing-specific consumer). Everything here is calibrated for the
# MAXIMIZED window (08-31 recalibration) and window-size-adaptive:
#   - the sidebar is TOP-anchored (Process title row ~y616, tab row ~y697
#     at any window height); the options viewport under the tab row
#     STRETCHES with the window — never assume a fixed band, read it from
#     the panel rect (view_band).
#   - the scroll offset is SHARED across pages: force the viewport back to
#     top when arriving from a deep-scrolled page (RESET_WHEEL_NOTCHES).
#   - option labels are PAINTED by OG_CustomCtrl (no label HWNDs): rows are
#     located positionally (group title rect + OCR), values via the row's
#     Edit/checkbox controls.
#   - committing an Edit keeps keyboard focus and blocks wheel/clicks:
#     neutralize_focus() after every real_edit_set.
#
# All clicks are REAL (SendInput) or message-level per the m4g strategies.

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402

user32 = ctypes.WinDLL("user32")
# 64-bit-safe prototype: CB_SELECTSTRING passes a string POINTER in lParam
user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_ulonglong, ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_longlong

SB_W = 424
VIEW_Y0, VIEW_Y1 = 700, 800  # fallback options band; the real band is read
                             # from the viewport panel (view_band) — it
                             # stretches with the window (73px windowed,
                             # 313px maximized)
RESET_WHEEL_NOTCHES = 40  # tab switch: force the options viewport back to
                          # top. Recalibrated 08-31: the scroll offset is
                          # SHARED across pages, so arriving from a
                          # max-scrolled Multimaterial page left Quality
                          # mid-content and 15 notches (~400-600px) could
                          # not recover the top (measured: Layer height
                          # unreachable on the 0.4-restore visit).


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


def ocr_band(session, y0=None, y1=None, psm=3):
    """OCR words of the sidebar options band, client coords. psm 6 helps
    when rows sit half-cut at the band edge (psm 3 drops them — measured
    09-02 on the Ironing group)."""
    if y0 is None or y1 is None:
        y0, y1 = view_band(session)
    img = capture_bgr(session)
    words = mdu.ocr_words_img(img[y0:y1, 0:SB_W], scale=3, psm=psm)
    return [(w, x, y + y0, w_w, w_h) for w, x, y, w_w, w_h in words]


def process_row_y(session):
    """Local y of the 'Process' title Static — the sidebar's ANCHOR row.
    The panel layout shifts with what the boot loaded (the mixed-fixture
    boot puts it at ~614, an empty boot at ~462 — no Color Mixing section),
    so every Process-panel y band anchors here instead of absolute px."""
    for t, c, r, h, lx, ly in kids(session):
        if c == "Static" and t.strip() == "Process" \
                and user32.IsWindowVisible(h) and lx < 100:
            return ly
    return None


def close_setup_wizard(session, attempts=4, log="[panel]"):
    """Close the first-run 'Setup Wizard' (#32770, HTML) that pops OVER the
    main frame and swallows every real click / WindowFromPoint in its area
    (measured 09-01; user-spotted in the evidence video)."""
    gone = 0
    for i in range(attempts):
        hit = None
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and "wizard" in txt.lower():
                hit = h
                break
        if not hit:
            gone += 1
            if gone >= 2:
                return True
            time.sleep(0.5)
            continue
        print(f"{log} closing wizard hwnd 0x{hit:x}")
        winutil.close_window(hit)
        time.sleep(1.2)
    return not any(cls == "#32770" and "wizard" in txt.lower()
                   for cls, txt, r, h in mixing_util.toplevel(session.pid))


def relocate_wizard(session, attempts=3, log="[panel]"):
    """The 'Setup Wizard' overlays the window centre and swallows clicks;
    WM_CLOSE on it may cancel the whole setup and EXIT the app (measured
    09-01). Instead of closing, MOVE it far off-screen: the app is
    untouched and the covered interactions keep working."""
    moved = 0
    for _ in range(attempts):
        hit = None
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and "wizard" in txt.lower():
                hit = h
                break
        if not hit:
            return True
        winutil.user32.SetWindowPos(hit, 0, -32000, -32000, 0, 0,
                                    0x0001 | 0x0002 | 0x0010)  # NOSIZE|NOZORDER|NOACTIVATE
        moved += 1
        time.sleep(0.6)
    if moved:
        print(f"{log} relocated wizard x{moved}")
    return True


def advanced_switch(session):
    """The 'Advanced' SwitchButton right of its label on the Process title
    row (empty-text wxBitmapToggleButton; icons sit further right)."""
    py = process_row_y(session)
    if py is None:
        return None
    label = None
    for t, c, r, h, lx, ly in kids(session):
        if c == "Static" and t.strip() == "Advanced" \
                and user32.IsWindowVisible(h) and abs(ly - py) <= 20:
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
        if abs(ly - py) <= 20 and label[0] + 20 <= lx <= label[0] + 130:
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


def ensure_advanced(session, want=True, timeout_s=30.0):
    """Flip the Advanced switch only when its state differs from `want`.
    Returns True when the knob reading agrees with `want` afterwards."""
    st = advanced_on(session)
    if st is None:
        return False
    on_now = st[1] > st[0]
    if on_now == want:
        return True
    sw = advanced_switch(session)
    if not sw:
        return False
    real_click(sw[0])
    time.sleep(2.0)
    st2 = advanced_on(session)
    return st2 is not None and (st2[1] > st2[0]) == want


def tab_button(session, name):
    """The self-drawn process tab item: wxWindowNR child whose text is the
    tab name, ~22px tall, in the tab row band (~50-110px below the
    'Process' anchor row — layout-shift safe)."""
    py = process_row_y(session)
    if py is None:
        return None
    for t, c, r, h, lx, ly in kids(session):
        if c == "wxWindowNR" and t.strip() == name \
                and user32.IsWindowVisible(h) \
                and 14 <= r[3] - r[1] <= 30 and 30 <= r[2] - r[0] <= 130 \
                and py + 50 <= ly <= py + 110 and lx > 5:
            return r, h
    return None


TAB_STRATEGY = [0]  # remembered across calls: 0 real, 1 message, 2 down/up


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
    strategy = strategies[0]
    while time.monotonic() < deadline:
        hit = tab_button(session, name)
        if hit:
            strategy = strategies[min(si // 2, len(strategies) - 1)]
            _click_tab_item(session, hit[0], strategy)
            clicked = True
            time.sleep(1.5)
        else:
            print(f"[panel] click_tab({name}): tab item NOT FOUND")
        vp = options_viewport(session)
        if vp:
            wheel_viewport(session, vp, RESET_WHEEL_NOTCHES, delta=120)
        joined = " ".join(w.lower() for w, *_ in ocr_band(session))
        print(f"[panel] click_tab({name}) poll{n_poll} strat{strategy}: "
              f"{joined[:70]!r}")
        if expect_word in joined:
            TAB_STRATEGY[0] = strategy
            time.sleep(3.0)  # sizer/fixup_items_positions settle
            return clicked
        n_poll += 1
        si += 1
        time.sleep(0.5)
    return False


def options_viewport(session):
    """The Multimaterial/Quality page viewport: a wide 'panel' wxWindowNR
    filling the band under the tab row. Size-adaptive (recalibrated 08-31
    on the maximized window): the panel TOP is anchored just below the tab
    row (which itself sits ~50-110px below the 'Process' anchor — the
    empty-boot layout sits ~150px higher than the fixture boot), and its
    HEIGHT stretches with the window (73px at the 800-tall window, 313px
    maximized) — the old 50..120 height cap matched only the windowed era
    and made every wheel a silent no-op (measured via diag_m4g_max)."""
    py = process_row_y(session)
    if py is None:
        return None
    best = None
    cands = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "wxWindowNR" or t.strip() != "panel":
            continue
        if not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if w >= 300 and hh >= 40:
            cands.append((lx, ly, w, hh))
        if 380 <= w <= 440 and hh >= 50 and py + 70 <= ly <= py + 130:
            if best is None or hh > best[0][3] - best[0][1]:
                best = (r, h)
    if best is None:
        print(f"[panel] options_viewport None; panel candidates "
              f"(lx,ly,w,h): {cands[:10]}")
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


def group_title(session, substr):
    """An options-group title (':StaticLine' = wxWindowNR with the group
    name, full width). Its rect tracks the scroll offset exactly, so it is
    usable for positioning even when scrolled out of view (the 20x20
    same-text icon overlays are filtered by width)."""
    py = process_row_y(session)
    if py is None:
        return None
    f = frect(session)
    for t, c, r, h, lx, ly in kids(session):
        if c == "wxWindowNR" and substr.lower() in t.lower() \
                and user32.IsWindowVisible(h) \
                and (r[2] - r[0]) > 100 and lx < 424 and ly > py:
            return r, h
    return None


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
                    print(f"[panel] wheel stuck at ty1={ty1} -> neutralize "
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


def neutralize_focus(session):
    """After real typing the keyboard focus sits in the option Edit; with
    that focus the real wheel no longer scrolls the options viewport and
    real clicks on the tab strip are ignored (measured 08-30). ESC + a
    harmless click on the 'Process' title Static returns focus to the
    panel."""
    mdu._send_keys([(0x1B, False), (0x1B, True)])
    time.sleep(0.3)
    py = process_row_y(session)
    for t, c, r, h, lx, ly in kids(session):
        if c == "Static" and t.strip() == "Process" \
                and user32.IsWindowVisible(h) \
                and (py is None or abs(ly - py) <= 25):
            real_click(r)
            return True
    return False


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


def top_dialog_set(session):
    return set(h for _c, _t, _r, h in mixing_util.toplevel(session.pid))


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


def wait_float_edit(session, timeout_s=180.0):
    """Topmost float Edit on the (Quality) page = the first option row
    ('Layer height'; the label is painted by OG_CustomCtrl). If nothing is
    found, periodically force the viewport back to top — the scroll offset
    persists across tab switches (RESET_WHEEL_NOTCHES note)."""
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
                    print(f"[panel] scrolled {seen} notches to reach {substr!r}")
                return (x, y, x + ww, y + hh)
        join = " ".join(w for w, *_ in words)
        if join != last_join:
            print(f"[panel] scroll@{seen}: {join[:90]!r}")
            last_join = join
        vp = options_viewport(session)
        if not vp:
            print(f"[panel] scroll: viewport lost at {seen}")
            return None
        wheel_viewport(session, vp, notches_per_round)
        seen += notches_per_round
    print(f"[panel] scroll: {substr!r} NOT reached in {seen} notches; "
          f"last={last_join[:90]!r}")
    return None


def find_process_preset_combo(session):
    """The print/process preset selector on the Process title row — the row
    just below the 'Process' anchor. Text varies by boot:
      - fixture boot: '0.40 Standard @Snapmaker U1 (0.8 nozzle)'
      - empty boot:   'Default Setting' (no preset embedded)
    Returns (rect, hwnd, text), or (None, None, None) with a sidebar
    diagnostic dump when nothing matches."""
    py = process_row_y(session)
    if py is None:
        return (None, None, None)
    fallback = None
    for t, c, r, h, lx, ly in kids(session):
        if not user32.IsWindowVisible(h) or not t.strip():
            continue
        if not (py + 10 <= ly <= py + 70) or not (10 <= lx <= 60):
            continue
        w = r[2] - r[0]
        if "@Snapmaker" in t and w >= 100:
            return (r, h, t.strip())
        if t.strip() == "Default Setting" and w >= 100:
            fallback = (r, h, t.strip())
    if fallback:
        return fallback
    probe = []
    for t, c, r, h, lx, ly in kids(session):
        if t.strip() and len(t.strip()) > 3 and user32.IsWindowVisible(h) \
                and lx < 440 and py <= ly <= py + 90:
            probe.append((t.strip()[:44], c, lx, ly))
        if len(probe) >= 20:
            break
    print(f"[panel] preset NOT found; sidebar texts near Process row: "
          f"{probe}")
    return (None, None, None)


def switch_process_preset(session, target_substr, tries=6):
    """Switch the process preset to the popup row containing
    `target_substr`. The row popup is a self-drawn 'panel' top-level; rows
    are OCR-located first, probed at the measured 28px pitch as fallback;
    every click selects + closes the popup, so the loop reopens until the
    combo text confirms (m3e mechanics, text re-anchored)."""
    r, ch, txt = find_process_preset_combo(session)
    if not ch:
        return False
    if target_substr in txt:
        return True
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    for attempt in range(tries):
        winutil.msg_click_screen(cx, cy, session.hwnd)
        popup = None
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and not popup:
            time.sleep(0.2)
            for t, ptxt, pr, h in mixing_util.toplevel(session.pid):
                if t == "wxWindowNR" and ptxt == "panel":
                    popup = (pr, h)
        if not popup:
            print(f"[panel] preset popup did not open (attempt {attempt})")
            return False
        pr, ph = popup
        # diagnostic: ALL panel toplevels right now (wrong-panel risk)
        allp = [(r2, h2) for t2, pt2, r2, h2 in mixing_util.toplevel(session.pid)
                if t2 == "wxWindowNR" and pt2 == "panel"]
        print(f"[panel] panel toplevels: {allp}")
        clicked = False
        # OCR-locate the row inside the popup (its own pixels)
        w, hgt, bgra = winutil.capture_window(ph)
        import numpy as np
        img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
        try:
            import cv2
            cv2.imwrite(str(HERE / "artifacts" / "m5a_popup.png"),
                        img[:, :, ::-1])
        except Exception:
            pass
        words = mdu.ocr_words_img(img, scale=3)
        print(f"[panel] preset popup {pr} ocr: "
              f"{' | '.join(t for t, *_ in words)[:160]!r}")
        for t_w, x, y, w_w, w_h in words:
            if target_substr in t_w:
                sx = pr[0] + x + w_w // 2
                sy = pr[1] + y + w_h // 2
                winutil.msg_click_screen(sx, sy)  # popup: no root piercing
                clicked = True
                break
        if not clicked:
            py = pr[1] + 14 + attempt * 28
            winutil.msg_click_screen((pr[0] + pr[2]) // 2, py)
        time.sleep(0.8)
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(ch, buf, 256)
        if target_substr in buf.value:
            return True
    return False


def set_option_float(session, label_substr, text, group_substr=None):
    """Locate the option row `label_substr` and type `text` into its Edit.
    Returns (ok, old_value, new_value). Neutralizes focus afterwards (a
    focused Edit blocks wheel/clicks)."""
    r, h, old = find_option_edit(session, label_substr, group_substr)
    if not h:
        return False, old, None
    new = real_edit_set(session, r, h, text)
    neutralize_focus(session)
    ok = bool(new and new.startswith(text))
    return ok, old, new


def find_option_row(session, label_substr, group_substr=None,
                    timeout_s=420.0, psm=3):
    """Locate an OPTION ROW by its painted label: scroll `group_substr`'s
    group into view, then OCR the visible band for `label_substr`.
    Returns (word_rect_client, y_row_center) or (None, None). Labels are
    PAINTED by OG_CustomCtrl (no HWNDs) — OCR is the only handle."""
    if group_substr:
        hit = scroll_group_into_view(session, group_substr, timeout_s)
        print(f"[panel] scroll_group({group_substr!r}) -> "
              f"{'hit' if hit else 'NOT FOUND'}")
        if not hit:
            return None, None
    for _ in range(6):
        words = ocr_band(session, psm=psm)
        print(f"[panel] find_option_row({label_substr!r}) band: "
              f"{' '.join(w for w, *_ in words)[:120]!r}")
        for w, x, y, ww, hh in words:
            if label_substr.lower() in w.lower():
                return (x, y, x + ww, y + hh), y + hh // 2
        vp = options_viewport(session)
        if vp:
            wheel_viewport(session, vp, 1, delta=-120)
        time.sleep(0.4)
    return None, None


def option_edit_at(session, y_row, y_tol=14, x_lo=220, x_hi=340):
    """The Edit control on the option row at client y `y_row` (the value
    column sits at x 220..340; m4g's float_edits_in_view calibration)."""
    f = frect(session)
    out = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "Edit" or not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (40 <= w <= 140 and 12 <= hh <= 26):
            continue
        if abs((r[1] + r[3]) // 2 - f[1] - y_row) <= y_tol                 and x_lo <= lx <= x_hi:
            out.append((r, h))
    out.sort(key=lambda rh: rh[0][0])
    return out[0] if out else None


def option_combo_at(session, y_row, y_tol=14):
    """The ComboBox control on the option row at client y `y_row`."""
    f = frect(session)
    out = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "ComboBox" or not user32.IsWindowVisible(h) or not t.strip():
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (80 <= w <= 180 and 16 <= hh <= 30):
            continue
        if abs((r[1] + r[3]) // 2 - f[1] - y_row) <= y_tol                 and 180 <= lx <= 380:
            out.append((r, h, t.strip()))
    out.sort(key=lambda rh: rh[0][0])
    return out[0] if out else None


def find_option_edit(session, label_substr, group_substr=None):
    """(rect, hwnd, current_text) of the Edit on the option row labeled
    `label_substr`, or (None, None, None)."""
    word, y_row = find_option_row(session, label_substr, group_substr)
    if not word:
        return None, None, None
    hit = option_edit_at(session, y_row)
    if not hit:
        return None, None, None
    r, h = hit
    return r, h, mdu.edit_value(h)


def set_option_combo(session, current_value, target):
    """Switch an options-panel combo currently showing `current_value` to
    `target` via keyboard cycling (cycle_combo_to)."""
    r, h, _cur = find_option_combo(session, current_value)
    if not h:
        return False
    return cycle_combo_to(session, r, h, target)


def find_option_combo(session, current_value, psm=3):
    """Locate an options-panel combo by its PAINTED value text (the value is
    painted by OG_CustomCtrl like the label; the control exposes no window
    text). OCR finds the word, WindowFromPoint resolves the real hwnd.
    Returns (rect, hwnd, text)."""
    word, y_row = find_option_row(session, current_value, psm=psm)
    if not word:
        return (None, None, None)
    f = frect(session)
    sx, sy = f[0] + (word[0] + word[2]) // 2, f[1] + y_row
    hwnd = winutil.window_from_screen_point(sx, sy)
    if not hwnd or hwnd == session.hwnd:
        return (None, None, None)
    rc = winutil.window_rect(hwnd)
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return (rc, hwnd, buf.value)


def set_combo_native(session, word_text, target_prefix, log="[panel]"):
    """Select an options-panel combo option by NATIVE CB_ messages: locate
    the combo GEOMETRICALLY (the smallest control whose rect contains the
    painted value word), CB_FINDSTRING the option, CB_SETCURSEL it, then
    notify the parent with CBN_SELCHANGE so wx records the change."""
    word, y_row = find_option_row(session, word_text)
    if not word:
        print(f"{log} set_combo_native: word {word_text!r} not found")
        return False
    f = frect(session)
    wxp, wyp = f[0] + (word[0] + word[2]) // 2, f[1] + y_row
    best = None
    for t, c, r, h, lx, ly in kids(session):
        if not user32.IsWindowVisible(h):
            continue
        if r[0] <= wxp < r[2] and r[1] <= wyp < r[3]:
            area = (r[2] - r[0]) * (r[3] - r[1])
            if best is None or area < best[0]:
                best = (area, r, h, c, t)
    if not best:
        print(f"{log} set_combo_native: no control at the word")
        return False
    ch = best[2]
    buf = ctypes.create_unicode_buffer(target_prefix)
    lparam = ctypes.cast(buf, ctypes.c_void_p)
    idx = user32.SendMessageW(ch, 0x014C, 0xFFFFFFFF, lparam)  # CB_FINDSTRING
    print(f"{log} combo hwnd=0x{ch:x} class={best[3]} find={idx}")
    if idx < 0:
        return False
    user32.SendMessageW(ch, 0x014E, idx, None)                 # CB_SETCURSEL
    time.sleep(0.4)
    parent = user32.GetParent(ch)
    cid = user32.GetDlgCtrlID(ch)
    if parent and cid:
        user32.SendMessageW(parent, 0x0111,
                            ((cid & 0xFFFF) << 16) | 1, ch)    # CBN_SELCHANGE
    time.sleep(0.8)
    text = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ch, text, 256)
    ok = target_prefix.lower() in text.value.lower()
    print(f"{log} combo text after select: {text.value!r} ok={ok}")
    return ok


def cycle_combo_to(session, rect, hwnd, target_word, max_steps=4):
    """Switch an options-panel combo to the option whose text contains
    `target_word`. The combo has real window text but the popup is NOT a
    dialog 'panel' — so: 1) CB_SELECTSTRING + CBN_SELCHANGE notification
    (native, deterministic); 2) fallback: keyboard DOWN/ENTER cycling with
    OCR verification of the painted value."""
    WM_COMMAND = 0x0111
    CB_SELECTSTRING = 0x014D
    CBN_SELCHANGE = 1

    def combo_text():
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    def notify_parent():
        parent = user32.GetParent(hwnd)
        cid = user32.GetDlgCtrlID(hwnd)
        if parent and cid:
            user32.SendMessageW(parent, WM_COMMAND,
                                ((cid & 0xFFFF) << 16) | CBN_SELCHANGE, hwnd)

    def try_selectstring():
        buf = ctypes.create_unicode_buffer(target_word)
        lparam = ctypes.cast(buf, ctypes.c_void_p).value or 0
        user32.SendMessageW(hwnd, CB_SELECTSTRING, 0xFFFFFFFF, lparam)
        time.sleep(0.4)
        ok = target_word.lower() in combo_text().lower()
        if ok:
            notify_parent()
            time.sleep(0.4)
        print(f"[panel] cycle CB_SELECTSTRING -> text={combo_text()!r} "
              f"ok={ok}")
        return ok

    def committed():
        for w, *_ in ocr_band(session):
            if target_word.lower() in w.lower():
                return True
        return False

    def focus():
        # clicks route by position, but the keyboard only reaches the app
        # when it holds focus (it is demoted/NOACTIVATE). A click on the
        # combo OPENS the dropdown, so the focused hwnd becomes the combo's
        # list — accept ANY focus inside the app thread (measured 09-01)
        for _ in range(4):
            relocate_wizard(session)
            winutil.force_set_foreground(session.hwnd)
            cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.15)
            winutil.real_click_screen(cx, cy)
            time.sleep(0.6)
            fh = focus_hwnd(session.hwnd)
            if fh:
                return True
            time.sleep(0.4)
        return False

    print(f"[panel] cycle combo start: text={combo_text()!r} "
          f"target={target_word!r}")
    if try_selectstring() and committed():
        return True
    VK_DOWN, VK_UP, VK_RETURN = 0x28, 0x26, 0x0D
    for vk in (VK_DOWN, VK_UP):
        for _step in range(max_steps):
            if not focus():
                print("[panel] cycle: combo focus FAILED")
                continue
            mdu._send_keys([(vk, False), (vk, True)])
            time.sleep(0.3)
            mdu._send_keys([(VK_RETURN, False), (VK_RETURN, True)])
            time.sleep(0.8)
            print(f"[panel] cycle vk={vk:#x} step={_step}: "
                  f"text={combo_text()!r} ocr_committed={committed()}")
            if committed():
                return True
        mdu._send_keys([(0x1B, False), (0x1B, True)])
        time.sleep(0.3)
    return False


def find_option_checkbox(session, label_substr, group_substr=None):
    """[(rect, hwnd)] checkbox candidates on the option row labeled
    `label_substr` (m4g's find_subdivide_row, generalized)."""
    word, y_row = find_option_row(session, label_substr, group_substr)
    if not word:
        return []
    return row_checkboxes(session, y_row, y_tol=14)


def find_option_row_seq(session, seq, group_substr=None,
                        timeout_s=420.0, psm=3):
    """find_option_row for a consecutive OCR word SEQUENCE: single-word
    matching is ambiguous when the value starts with a common token
    ('No ironing' and 'Nozzle' both match 'no' — measured 09-02). Scrolls
    `group_substr` into view first, then hunts +-1 notch around it.
    Returns (rect_of_word_run_client, run_center_y) or (None, None)."""
    if group_substr:
        hit = scroll_group_into_view(session, group_substr, timeout_s)
        print(f"[panel] scroll_group({group_substr!r}) -> "
              f"{'hit' if hit else 'NOT FOUND'}")
        if not hit:
            return None, None
    seq_l = [s.lower() for s in seq]
    n = len(seq_l)
    last_join = ""
    for _round in range(10):  # 5 notches down, then 5 back up
        words = ocr_band(session, psm=psm)
        for i in range(len(words) - n + 1):
            got = [w.lower() for w, *_ in words[i:i + n]]
            if got == seq_l:
                x0, y0 = words[i][1], words[i][2]
                x1 = words[i + n - 1][1] + words[i + n - 1][3]
                y1 = words[i + n - 1][2] + words[i + n - 1][4]
                return (x0, y0, x1, y1), (y0 + y1) // 2
        join = " ".join(w for w, *_ in words)
        if join != last_join:
            print(f"[panel] row_seq{seq!r} band: {join[:110]!r}")
            last_join = join
        vp = options_viewport(session)
        if not vp:
            return None, None
        wheel_viewport(session, vp, 1, delta=-120 if _round < 5 else 120)
        time.sleep(0.3)
    return None, None


def find_option_combo_seq(session, seq, group_substr=None, psm=3):
    """find_option_combo keyed by a word SEQUENCE (see find_option_row_seq):
    resolve the combo control under the matched value run via
    WindowFromPoint. Returns (rect, hwnd, text)."""
    word, y_row = find_option_row_seq(session, seq, group_substr, psm=psm)
    if not word:
        return (None, None, None)
    f = frect(session)
    sx, sy = f[0] + (word[0] + word[2]) // 2, f[1] + y_row
    hwnd = winutil.window_from_screen_point(sx, sy)
    if not hwnd or hwnd == session.hwnd:
        return (None, None, None)
    rc = winutil.window_rect(hwnd)
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return (rc, hwnd, buf.value)


def set_combo_by_popup(session, locate, target_substr, log="[panel]",
                       verify_seq=None, group_substr=None, psm=3):
    """m5d's Support-Type mechanic, generalized: open the options-panel
    combo whose painted value matches `locate` (a word substring, or a word
    SEQUENCE tuple for ambiguous tokens), then click the popup row whose
    text contains `target_substr` (OCR-located first, blind 28px-pitch row
    fallback with re-open). Returns (ok, target_confirmed) where
    target_confirmed is True once `target_substr` is the painted value.

    verify_seq + group_substr: MEASURED 09-02 — a combo commit REBUILDS the
    page and the scroll lands elsewhere, so the painted-value OCR verify
    can hunt forever with the row off-band. When given, re-scroll
    `group_substr` into view, re-resolve the combo by the NEW value's word
    SEQUENCE `verify_seq`, and check the combo's REAL window text (the
    control exposes it even though the popup painting is OCR-hostile)."""
    import numpy as np
    from harness import export_util
    relocate_wizard(session)
    if isinstance(locate, (tuple, list)):
        r, h, cur = find_option_combo_seq(session, locate, group_substr,
                                          psm=psm)
    else:
        r, h, cur = find_option_combo(session, locate, psm=psm)
    print(f"{log} set_combo_by_popup({locate!r} -> {target_substr!r}): "
          f"combo text={cur!r}")
    if not h:
        return False, False
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    winutil.msg_click_screen(cx, cy, session.hwnd)
    popup = None
    for _ in range(20):
        popup = export_util.wait_popup(session.pid, timeout_s=0.5)
        if popup:
            break
    print(f"{log} popup: {popup}")
    if popup:
        pr, ph = popup[2], popup[3]
        time.sleep(0.8)  # self-drawn rows lag the popup creation
        words = []
        for _attempt in range(3):
            w, hgt, bgra = winutil.capture_window(ph)
            img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
            words = mdu.ocr_words_img(img, scale=3)
            if words:
                break
            time.sleep(0.6)
        print(f"{log} popup rows: "
              f"{' | '.join(t for t, *_ in words)[:140]!r}")
        clicked = False
        for t_w, x, y, w_w, w_h in words:
            if target_substr.lower() in t_w.lower():
                winutil.msg_click_screen(pr[0] + x + w_w // 2,
                                         pr[1] + y + w_h // 2)
                clicked = True
                break
        if not clicked:
            # blind fallback: 28px row pitch; verify by re-locating the
            # combo by its new value after each click, reopen when missed
            for row in range(5):
                winutil.msg_click_screen((pr[0] + pr[2]) // 2,
                                         pr[1] + 14 + row * 28)
                time.sleep(1.0)
                if find_option_combo(session, target_substr)[1]:
                    clicked = True
                    print(f"{log} blind row {row} hit {target_substr!r}")
                    break
                winutil.msg_click_screen(cx, cy, session.hwnd)
                time.sleep(1.0)
                popup2 = None
                for _ in range(10):
                    popup2 = export_util.wait_popup(session.pid,
                                                    timeout_s=0.5)
                    if popup2:
                        break
                    time.sleep(0.2)
                if not popup2:
                    break
                pr = popup2[2]
        time.sleep(1.5)
    ok = find_option_combo(session, target_substr, psm=psm)[1] is not None
    if not ok and verify_seq:
        if group_substr:
            scroll_group_into_view(session, group_substr)
        _r2, _h2, txt2 = find_option_combo_seq(session, verify_seq,
                                               psm=psm)
        ok = bool(_h2 and target_substr.lower() in (txt2 or "").lower())
        print(f"{log} verify by combo text: {txt2!r} ok={ok}")
    else:
        print(f"{log} combo now paints target: {ok}")
    return h is not None, ok


def set_option_checkbox(session, label_substr, want_checked,
                        group_substr=None, tries=4):
    """Toggle the checkbox on the option row `label_substr` until the frame
    state reads `want_checked` (checked ~0.21 teal fraction, unchecked
    ~0.00-0.06; measured 08-31). Returns (state, rect) or (None, None)."""
    cands = find_option_checkbox(session, label_substr, group_substr)
    for attempt in range(tries):
        if not cands:
            cands = find_option_checkbox(session, label_substr, group_substr)
            if not cands:
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
            print(f"[panel] checkbox {label_substr!r} att{attempt}: "
                  f"{before:.2f} -> {after:.2f}")
            now_on = after > 0.13
            if now_on == want_checked:
                return now_on, rect
        time.sleep(0.8)
    return None, None

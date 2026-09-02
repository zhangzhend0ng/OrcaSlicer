#!/usr/bin/env python3
# mix_dialog_util.py — primitives for the per-filament "Add Mix"/"Edit Mix"
# dialog (MixedFilamentDialog) and the sidebar "Color Mixing" panel.
#
# UI facts (source-verified on the 08-26 build, MixedFilamentDialog.cpp):
#   - the dialog is a native modal #32770 titled 'Add Mix' (ctor :137) or
#     'Edit Mix' (:151); Confirm/Cancel are self-drawn Buttons with REAL
#     text labels 'OK'/'Cancel' (:1172/:1180).
#   - the four mode tabs are CUSTOM painted Button widgets (labels
#     Ratio/Cycle/Match/Gradient, :270) — GetWindowText is EMPTY, so tabs
#     are located by OCR word positions (pytesseract image_to_data) with an
#     even-slot fallback.
#   - card titles / legends are wxStaticText ('Static' class): 'Mixing
#     Ratio' (:636), 'Preview' (:694), 'Mix Effect' (:704), 'Filament %d'
#     (:1695), per-filament '%d%%' legends (:1545) — readable via
#     GetWindowText.
#   - the Cycle pattern input and the Match hex input are the dialog's only
#     'Edit' windows; wxTextCtrl accepts WM_CHAR typing and Enter
#     (wxEVT_TEXT_ENTER, :1047) triggers validation.
#   - validation/warning banners are inline wxStaticText bands — error red
#     (:2218/:2220) disables OK; advisory orange (:2226/:2229/:2346) keeps
#     OK enabled. All texts readable via GetWindowText.
#   - sidebar: the 'Color Mixing' panel title bar (:6474) hosts the add
#     button at its right end (probed like mixing_util.open_mixing_dialog);
#     mixed entries render a 'MixedFilamentBadge' + a Static label
#     ('F1 50%+F2 50%', 'F1->F2' or cycle summary, :6673-6711) + a
#     'menu_filament' Options button (:6809) that opens a NATIVE wxMenu
#     (#32768) with Edit / Merge with / Delete (:6817-6942).

import ctypes
import re
import time

import numpy as np
import pytesseract

from . import mixing_util, ocr_util, topbar_util, winutil  # noqa: F401  (ocr_util configures pytesseract)

user32 = ctypes.WinDLL("user32")

GWL_STYLE = -16
WS_DISABLED = 0x08000000

DIALOG_TITLES = ("Add Mix", "Edit Mix")

TAB_LABELS = ("Ratio", "Cycle", "Match", "Gradient")


# --- dialog discovery ---------------------------------------------------------

def find_mix_dialog(pid: int, timeout_s: float = 10.0,
                    titles=DIALOG_TITLES):
    """The Add/Edit Mix dialog: a tall #32770 whose title is one of
    `titles` (the batch dialog 'Color Mixing Match' is excluded)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, rect, hwnd in mixing_util.toplevel(pid):
            if cls == "#32770" and any(t in txt for t in titles) \
                    and rect[3] - rect[1] > 400:
                return hwnd
        time.sleep(0.3)
    return None


def dialog_rect(pid: int, dlg: int):
    for cls, txt, rect, hwnd in mixing_util.toplevel(pid):
        if hwnd == dlg:
            return rect
    return None


def dialog_title(pid: int, dlg: int):
    for cls, txt, rect, hwnd in mixing_util.toplevel(pid):
        if hwnd == dlg:
            return txt
    return None


# --- child lookups -------------------------------------------------------------

def static_texts(dlg: int):
    """[(text, rect, hwnd, visible)] of Static-class children."""
    out = []
    for t, c, r, h in mixing_util.children(dlg):
        if c == "Static" and t.strip():
            out.append((t, r, h, bool(user32.IsWindowVisible(h))))
    return out


def find_static(dlg: int, substr: str, visible_only=True):
    """(text, rect, hwnd) of the first Static whose text contains
    `substr` (case-insensitive)."""
    for t, r, h, vis in static_texts(dlg):
        if substr.lower() in t.lower() and (vis or not visible_only):
            return t, r, h
    return None


def edit_boxes(dlg: int):
    """Visible Edit-class children (pattern input / hex input)."""
    return [(r, h) for t, c, r, h in mixing_util.children(dlg)
            if c == "Edit" and user32.IsWindowVisible(h)]


def button_state(dlg: int, substr: str):
    """(rect, hwnd, enabled) of the child whose TEXT contains `substr`
    (any class — OK/Cancel are custom wxWindowNR buttons with real text),
    or None."""
    for t, c, r, h in mixing_util.children(dlg):
        if t.strip() and substr in t:
            enabled = not bool(user32.GetWindowLongW(h, GWL_STYLE)
                               & WS_DISABLED)
            return r, h, enabled
    return None


def banner_texts(dlg: int):
    """Visible Static texts that look like error/advisory banners."""
    markers = ("cannot be mixed", "not recognized", "invalid characters",
               "leading or trailing", "ratio is too high",
               "excessive filaments", "same filament colors",
               "please enter a valid", "different filament types")
    out = []
    for t, r, h, vis in static_texts(dlg):
        low = t.lower()
        if vis and any(m in low for m in markers):
            out.append(t)
    return out


def legend_pcts(dlg: int):
    """Per-filament legend percentages ('%d%%' Statics), as ints."""
    out = []
    for t, r, h, vis in static_texts(dlg):
        if vis:
            m = re.fullmatch(r"\s*(\d{1,3})%\s*", t)
            if m:
                out.append(int(m.group(1)))
    return out


def ok_enabled(dlg: int) -> bool:
    hit = button_state(dlg, "OK")
    return bool(hit and hit[2])


# --- tabs / buttons / combos (all expose REAL window text) ---------------------

TAB_SIZE = (81, 28)


def find_tab(dlg: int, name: str):
    """(rect, hwnd, active) of a mode tab. The four custom tab Buttons
    expose their labels ('Ratio'/'Cycle'/'Match'/'Gradient') as window
    text (81x28 each, measured); the ACTIVE tab paints #009688 teal."""
    for t, c, r, h in mixing_util.children(dlg):
        if t.strip() == name and abs((r[2] - r[0]) - TAB_SIZE[0]) <= 6 \
                and abs((r[3] - r[1]) - TAB_SIZE[1]) <= 6:
            return r, h, tab_active(r)
    return None


def tab_active(rect: tuple) -> bool:
    """Sample the SCREEN pixel at the tab center: the active tab bg is
    teal #009688 (GetPixel COLORREF 0x889600 = RGB(0,150,136), measured);
    inactive tabs are light gray."""
    gdi = ctypes.WinDLL("gdi32")
    sdc = user32.GetDC(0)
    x0, y0, x1, y1 = rect
    pts = [(x0 + 5, y0 + 5), (x1 - 5, y0 + 5), (x0 + 5, y1 - 5),
           (x1 - 5, y1 - 5), (x0 + 8, (y0 + y1) // 2),
           (x1 - 8, (y0 + y1) // 2)]
    teal = 0
    for px, py in pts:
        v = gdi.GetPixel(sdc, px, py) & 0xFFFFFFFF
        if v == 0xFFFFFFFF:  # CLR_INVALID — pixel not on screen
            continue
        r, g, b = v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF
        if r < 70 and 100 < g < 180 and 100 < b < 170:
            teal += 1
    user32.ReleaseDC(0, sdc)
    return teal >= 2  # label glyphs occupy the center; corners stay teal


def active_tab(dlg: int):
    """Name of the active mode tab (or None)."""
    for name in TAB_LABELS:
        hit = find_tab(dlg, name)
        if hit and hit[2]:
            return name
    return None


def click_tab(session, dlg, name) -> bool:
    """Switch a mode tab by its window text and confirm via the teal
    active-state pixel."""
    hit = find_tab(dlg, name)
    if not hit:
        return False
    rect = hit[0]
    for _ in range(3):
        if hit[2]:
            return True
        x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        winutil.user32.SetCursorPos(x, y)
        time.sleep(0.15)
        winutil.real_click_screen(x, y)
        time.sleep(0.8)
        hit = find_tab(dlg, name)
        if not hit:
            return False
        rect = hit[0]
    return bool(hit and hit[2])


def filament_combos(dlg: int):
    """The rowComboBoxes: wxWindowNR children ~231x30 whose text is the
    selected preset label (measured 'Generic PETG')."""
    out = []
    for t, c, r, h in mixing_util.children(dlg):
        if c == "wxWindowNR" and t.strip() \
                and 180 <= r[2] - r[0] <= 280 and 24 <= r[3] - r[1] <= 38 \
                and user32.IsWindowVisible(h):
            out.append((t, r, h))
    out.sort(key=lambda x: x[1][1])
    return out


def card_button(dlg: int, anchor_substr: str, idx: int = 0):
    """A small icon Button in the card whose title contains
    `anchor_substr` (e.g. the row add/remove 'Button' 16x25 right of the
    'Filament Selection' title). Returns (rect, hwnd) or None."""
    hit = find_static(dlg, anchor_substr)
    if not hit:
        return None
    _t, (_ax0, ay0, _ax1, ay1), _h = hit
    cands = []
    for t, c, r, h in mixing_util.children(dlg):
        if c != "Button" or not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (10 <= w <= 30 and 18 <= hh <= 32):
            continue
        if ay0 - 6 <= r[1] <= ay1 + 40:
            cands.append((r, h))
    cands.sort(key=lambda rh: rh[0][0])
    return cands[idx] if len(cands) > idx else None


def ratio_selector(dlg: int):
    """(rect, hwnd) of the 2-filament ratio selector bar: the wide short
    panel between the 'Mixing Ratio' title and the '%d%%' legends
    (measured 293x24 at 34px under the title)."""
    title = find_static(dlg, "Mixing Ratio")
    if not title:
        return None
    ty1 = title[1][3]
    cands = []
    for t, c, r, h in mixing_util.children(dlg):
        if c != "wxWindowNR" or not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if w > 250 and 18 <= hh <= 30 and ty1 < r[1] < ty1 + 60:
            cands.append((r, h))
    cands.sort(key=lambda rh: rh[0][1])
    return cands[0] if cands else None


def click_selector_frac(session, dlg, rect, fx: float):
    """Click at a horizontal fraction of the selector bar (real input)."""
    x = int(rect[0] + (rect[2] - rect[0]) * fx)
    y = (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.15)
    winutil.real_click_screen(x, y)
    time.sleep(0.6)


def panel_below(dlg: int, anchor_substr: str, w_lo=100, w_hi=200):
    """(rect, hwnd) of the panel below a label (e.g. the 140x128 preview
    under 'Preview')."""
    hit = find_static(dlg, anchor_substr)
    if not hit:
        return None
    _t, (_ax0, ay1, _ax2, _ay3), _h = hit
    cands = []
    for t, c, r, h in mixing_util.children(dlg):
        if c != "wxWindowNR" or not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if w_lo <= w <= w_hi and 90 <= hh <= 160 and ay1 - 4 <= r[1] <= ay1 + 30:
            cands.append((r, h))
    cands.sort(key=lambda rh: rh[0][0])
    return cands[0] if cands else None


def hwnd_pixels(hwnd: int):
    """BGR numpy array of a window's own pixels."""
    w, h, bgra = winutil.capture_window(hwnd)
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    return img.copy()


def footer_top(dlg: int):
    """Screen y of the fixed OK/Cancel footer band (the dialog's scrolled
    content slides UNDER it — children report 'visible' even when covered,
    measured 08-30)."""
    hit = button_state(dlg, "OK")
    return hit[0][1] if hit else None


def content_panel(dlg: int):
    """(rect, hwnd) of the big wxScrolledWindow content panel."""
    cands = []
    for t, c, r, h in mixing_util.children(dlg):
        if c == "wxWindowNR" and 370 <= r[2] - r[0] <= 390                 and (r[3] - r[1]) > 300 and user32.IsWindowVisible(h):
            cands.append((r, h))
    cands.sort(key=lambda rh: -rh[0][3])
    return cands[0] if cands else None


def scroll_content_to(session, dlg, anchor_substr: str,
                      swatch: tuple = (22, 26), max_clicks: int = 10):
    """Wheel the content down until a swatch panel (default 24x24) below
    `anchor_substr` clears the footer band. Returns True once uncovered."""
    for _ in range(max_clicks):
        ft = footer_top(dlg)
        hit = find_static(dlg, anchor_substr)
        if not hit or not ft:
            return False
        ty1 = hit[1][3]
        sw = [r for t, c, r, h in mixing_util.children(dlg)
              if c == "wxWindowNR" and swatch[0] <= r[2] - r[0] <= swatch[1]
              and swatch[0] <= r[3] - r[1] <= swatch[1]
              and ty1 - 4 <= r[1] <= ty1 + 150
              and user32.IsWindowVisible(h)]
        if sw:
            y1 = min(r[3] for r in sw)
            if y1 < ft - 6:
                return True
        panel = content_panel(dlg)
        if not panel:
            return False
        r, h = panel
        cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
        lparam = (cy << 16) | (cx & 0xFFFF)
        user32.SendMessageW(h, 0x020A, (-120) << 16, lparam)  # WM_MOUSEWHEEL
        time.sleep(0.4)
    return False


def toplevel_snapshot(session):
    return set(h for _c, _t, _r, h in mixing_util.toplevel(session.pid))


def popup_any(session, known, timeout_s: float = 3.0):
    """First NEW 'panel' top-level (any width) after `known` was taken."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "wxWindowNR" and txt == "panel" and h not in known:
                return r
        time.sleep(0.15)
    return None


def popup_panel(session, width: int, timeout_s: float = 3.0):
    """The owner-drawn combo popup: a top-level wxWindowNR 'panel' of the
    combo's width (measured 231 px)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "wxWindowNR" and txt == "panel" \
                    and abs((r[2] - r[0]) - width) <= 4:
                return r
        time.sleep(0.2)
    return None


def popup_pick(session, popup_rect: tuple, row: int):
    """Click popup row `row` (28px pitch, first row at top+14, measured)."""
    px = (popup_rect[0] + popup_rect[2]) // 2
    py = popup_rect[1] + 14 + row * 28
    winutil.user32.SetCursorPos(px, py)
    time.sleep(0.2)
    winutil.real_click_screen(px, py)
    time.sleep(0.8)


def popup_cancel(session):
    """Close a stuck owner-drawn combo popup (WM_CANCELMODE to every open
    'panel' popup top-level)."""
    closed = False
    for cls, txt, r, h in mixing_util.toplevel(session.pid):
        if cls == "wxWindowNR" and txt == "panel":
            user32.SendMessageW(h, 0x001F, 0, 0)  # WM_CANCELMODE
            closed = True
    time.sleep(0.3)
    return closed


# --- OCR word map ---------------------------------------------------------------

def ocr_words_img(img: np.ndarray, scale: int = 3, psm: int = 3):
    """[(text, x, y, w, h)] in ORIGINAL image coords (conf>40).
    psm: tesseract page-segmentation mode. The default 3 (auto) silently
    DROPS rows next to '-----' divider art — the preset popup's section
    headers made it lose the user-preset rows (measured 09-02); pass
    psm=6 (uniform block) for list-like captures."""
    if scale != 1:
        big = cv2_resize(img, scale)
    else:
        big = img
    data = pytesseract.image_to_data(
        big, config=f"-l eng --psm {psm}",
        output_type=pytesseract.Output.DICT)
    words = []
    for i, txt in enumerate(data["text"]):
        t = txt.strip()
        if not t or int(data["conf"][i]) < 40:
            continue
        words.append((t, data["left"][i] // scale, data["top"][i] // scale,
                      data["width"][i] // scale, data["height"][i] // scale))
    return words


def cv2_resize(img, scale):
    import cv2
    return cv2.resize(img, None, fx=scale, fy=scale,
                      interpolation=cv2.INTER_CUBIC)


def ocr_words(dlg: int, scale: int = 3):
    return ocr_words_img(mixing_util.dialog_bgr(dlg), scale=scale)


def word_rect(words, substr, y_max=None):
    """First OCR word containing `substr` (ci) as (x, y, w, h) or None."""
    for t, x, y, w, h in words:
        if substr.lower() in t.lower() and (y_max is None or y <= y_max):
            return (x, y, w, h)
    return None


# --- clicking -------------------------------------------------------------------

def real_click_frac(session, dlg, fx: float, fy: float):
    """Real click at a fraction of the dialog rect."""
    rect = dialog_rect(session.pid, dlg)
    if not rect:
        return False
    x = int(rect[0] + (rect[2] - rect[0]) * fx)
    y = int(rect[1] + (rect[3] - rect[1]) * fy)
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.15)
    winutil.real_click_screen(x, y)
    time.sleep(0.5)
    return True


def click_word(session, dlg, substr, y_max=None) -> bool:
    """OCR the dialog, real-click the center of the first matching word."""
    rect = dialog_rect(session.pid, dlg)
    wr = word_rect(ocr_words(dlg), substr, y_max=y_max)
    if not wr or not rect:
        return False
    x, y, w, h = wr
    sx = rect[0] + x + w // 2
    sy = rect[1] + y + h // 2
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.15)
    winutil.real_click_screen(sx, sy)
    time.sleep(0.6)
    return True


def click_button(session, dlg, substr) -> bool:
    return mixing_util.click_button(dlg, substr)


# --- text input -----------------------------------------------------------------

def set_edit_text(session, edit_hwnd: int, text: str, enter=True):
    """Replace an Edit control's content and optionally press Enter
    (the Cycle pattern validates on ENTER / KILL_FOCUS)."""
    winutil.select_all(edit_hwnd)
    winutil.msg_key(edit_hwnd, 0x2E)  # VK_DELETE clears the selection
    time.sleep(0.2)
    winutil.msg_text(edit_hwnd, text)
    time.sleep(0.2)
    if enter:
        winutil.press_enter(edit_hwnd)
    time.sleep(0.4)


WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E


def edit_value(edit_hwnd: int) -> str:
    """Real-time text of an Edit control. NOTE: GetWindowText returns a
    STALE cached string for other-process EDIT controls (measured: it
    kept returning the initial '12' after WM_SETTEXT / typing); WM_GETTEXT
    reads the live text."""
    ln = user32.SendMessageW(edit_hwnd, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(ln + 2)
    user32.SendMessageW(edit_hwnd, WM_GETTEXT, ln + 1,
                        ctypes.c_void_p(ctypes.addressof(buf)))
    return buf.value


# --- real keyboard input (SendInput) --------------------------------------------
# Message-injected WM_CHAR/WM_KEYDOWN reach the control but the app's
# validation only fires on REAL input edge cases; measured 08-30: real
# typing + real Enter run the full validate path (banner + OK state).

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("flags", ctypes.c_uint),
                ("hwndActive", ctypes.c_void_p), ("hwndFocus", ctypes.c_void_p),
                ("hwndCapture", ctypes.c_void_p), ("hwndMenuOwner", ctypes.c_void_p),
                ("hwndMoveSize", ctypes.c_void_p), ("hwndCaret", ctypes.c_void_p),
                ("rcCaret", ctypes.wintypes.RECT)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint), ("time", ctypes.c_uint),
                ("dwExtraInfo", ctypes.c_void_p)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("padding", ctypes.c_ubyte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint), ("union", _INPUTUNION)]


def _send_keys(keys):
    """keys: iterable of (vk_or_unicode, is_up). vk 0 => unicode char in
    wScan."""
    arr = (_INPUT * len(keys))()
    for i, (vk, up) in enumerate(keys):
        arr[i].type = INPUT_KEYBOARD
        if vk == 0 or vk > 0xFFFF:
            continue
        arr[i].union.ki = _KEYBDINPUT(
            vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
    user32.SendInput(len(keys), arr, ctypes.sizeof(_INPUT))


def _send_chars(text, chunk: int = 40):
    """Unicode typing in SendInput batches (a single 1000-event call gets
    dropped by the input queue — measured 08-30)."""
    for start in range(0, len(text), chunk):
        piece = text[start:start + chunk]
        arr = (_INPUT * (len(piece) * 2))()
        for i, c in enumerate(piece):
            arr[2 * i].type = INPUT_KEYBOARD
            arr[2 * i].union.ki = _KEYBDINPUT(
                0, ord(c), KEYEVENTF_UNICODE, 0, None)
            arr[2 * i + 1].type = INPUT_KEYBOARD
            arr[2 * i + 1].union.ki = _KEYBDINPUT(
                0, ord(c), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)
        user32.SendInput(len(arr), arr, ctypes.sizeof(_INPUT))
        time.sleep(0.05)


VK_CONTROL = 0x11
VK_A = 0x41
VK_DELETE = 0x2E
VK_RETURN = 0x0D


def real_edit_text(session, dlg, text, clear=True, enter=True,
                   max_chars=None):
    """Drive the dialog's visible Edit with REAL input: focus by real
    click, Ctrl+A + Delete clear, unicode typing, real Enter (validation
    runs on TEXT_ENTER). Re-locates the Edit first — the banner band
    expands/collapses and shifts the layout. Returns the live text."""
    hit = None
    for _ in range(3):
        eds = edit_boxes(dlg)
        if eds:
            hit = eds[0]
            break
        time.sleep(0.4)
    if not hit:
        return None
    rect, eh = hit

    def focused() -> bool:
        # the edit must be BOTH in the foreground frame and have keyboard
        # focus — after many operations the foreground may silently fall
        # back to another window and the keystrokes would land there
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        tid = user32.GetWindowThreadProcessId(eh, None)
        user32.GetGUIThreadInfo(tid, ctypes.byref(info))
        return bool(info.hwndFocus) and info.hwndFocus == eh

    for attempt in range(4):
        # re-locate EVERY attempt: the banner band expands/collapses after
        # each validation and shifts the Edit vertically (measured 45px)
        eds = edit_boxes(dlg)
        if eds:
            rect, eh = eds[0]
        x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
        winutil.force_set_foreground(dlg)
        time.sleep(0.4)
        winutil.user32.SetCursorPos(x, y)
        time.sleep(0.15)
        winutil.real_click_screen(x, y)
        time.sleep(0.5)
        if focused():
            break
    if not focused():
        return edit_value(eh)
    if clear:
        _send_keys([(VK_CONTROL, False), (VK_A, False), (VK_A, True),
                    (VK_CONTROL, True)])
        time.sleep(0.15)
        _send_keys([(VK_DELETE, False), (VK_DELETE, True)])
        time.sleep(0.2)
        if edit_value(eh) != "" :
            # the ^A+Del did not land — retry once
            _send_keys([(VK_CONTROL, False), (VK_A, False), (VK_A, True),
                        (VK_CONTROL, True)])
            time.sleep(0.15)
            _send_keys([(VK_DELETE, False), (VK_DELETE, True)])
            time.sleep(0.2)
    payload = text if max_chars is None else text[:max_chars]
    if payload:
        _send_chars(payload)
    time.sleep(0.3)
    if enter:
        _send_keys([(VK_RETURN, False), (VK_RETURN, True)])
        time.sleep(0.5)
    return edit_value(eh)


# --- pixel observation ------------------------------------------------------------

def region_img(dlg, rect_local):
    """Dialog pixels of a LOCAL (x0,y0,x1,y1) rect."""
    return mixing_util.dialog_bgr(dlg)[rect_local[1]:rect_local[3],
                                       rect_local[0]:rect_local[2]]


def region_changed(dlg, rect_local, capture0, tol=1.0) -> bool:
    img1 = region_img(dlg, rect_local)
    if capture0 is None or capture0.shape != img1.shape:
        return False
    diff = float(np.abs(capture0.astype(int) - img1.astype(int)).mean())
    return diff > tol


def label_region(dlg, substr, dx=(0, 160), dy=(-8, 72)):
    """A local rect anchored at a Static label (for preview panels)."""
    hit = find_static(dlg, substr)
    if not hit:
        return None
    _t, (x0, y0, x1, y1), _h, _v = hit
    return (x0 + dx[0], y0 + dy[0], x0 + dx[1], y0 + dy[1])


# --- sidebar panel ----------------------------------------------------------------

def _sidebar_title_row(session, title: str):
    """(label_rect, [button rects left->right]) of a sidebar title-bar row
    (measured: the 'Color Mixing' row panel spans the sidebar width and
    hosts small icon Buttons at its right end — del(-) then add(+))."""
    frect = winutil.window_rect(session.hwnd)
    label = None
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c == "Static" and t == title and (r[3] - r[1]) < 40 \
                and frect[1] < r[3] < frect[3] \
                and r[0] < frect[0] + (frect[2] - frect[0]) * 0.4 \
                and user32.IsWindowVisible(h):
            label = r
            break
    if not label:
        return None
    row_top, row_bot = label[1] - 8, label[3] + 8
    btns = []
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c != "Button" or not user32.IsWindowVisible(h):
            continue
        if min(r[3], row_bot) - max(r[1], row_top) > 10 \
                and label[2] < r[0] < label[0] + 500:
            btns.append((r, h))
    btns.sort(key=lambda bh: bh[0][0])
    return label, btns


def color_mix_bar(session):
    """Rect of the sidebar 'Color Mixing' row label, or None."""
    hit = _sidebar_title_row(session, "Color Mixing")
    return hit[0] if hit else None


def open_add_mix_dialog(session, timeout_s: float = 12.0):
    """Click the add (+) button — the RIGHT-most icon button of the
    'Color Mixing' row; returns the Add Mix dialog hwnd or None."""
    row = _sidebar_title_row(session, "Color Mixing")
    if not row or not row[1]:
        return None
    r, _h = row[1][-1]
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    for _ in range(3):
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        winutil.msg_click_screen(cx, cy, session.hwnd)
        dlg = find_mix_dialog(session.pid, timeout_s=3.0)
        if dlg:
            return dlg
    return None


def mix_entry_labels(session):
    """Sidebar mixing-entry Static labels ('F1 50%+F2 50%', 'F1->F2',
    cycle summaries) as (text, rect, hwnd)."""
    out = []
    pat = re.compile(r"^F\d[\dF %,+>\-\[\]]*$")
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c == "Static" and t.strip() and pat.match(t.strip()) \
                and user32.IsWindowVisible(h):
            out.append((t.strip(), r, h))
    return out


def entry_menu_button(session, label_rect):
    """The Options ('menu_filament') Button on the same row as a mixing
    label (right of it, y-overlapping)."""
    ly0, ly1 = label_rect[1], label_rect[3]
    best = None
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c != "Button" or not user32.IsWindowVisible(h):
            continue
        if r[0] < label_rect[2] - 4:
            continue
        overlap = min(r[3], ly1) - max(r[1], ly0)
        if overlap > (ly1 - ly0) * 0.4:
            if best is None or r[0] < best[0][0]:
                best = (r, h)
    return best


def physical_filament_count(session) -> int:
    """Number of visible numbered filament color chips ('1'..'N' Statics
    inside the Filaments area) — counts distinct digits."""
    nums = set()
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c == "Static" and t.strip().isdigit() \
                and user32.IsWindowVisible(h):
            nums.add(int(t.strip()))
    return len(nums)


def filament_row_buttons(session):
    """Icon buttons of the sidebar 'Filaments' row, left->right (the
    right-most is the add (+) button; the trash 'Remove last filament'
    is among them)."""
    row = _sidebar_title_row(session, "Filaments")
    return row[1] if row else []


# --- physical filament rows (measured 08-30 on the left sidebar) -----------
# Each 2-column slot = a digit 'Button' chip + a material-name combo
# (wxWindowNR, GetWindowText = preset material 'Snapmaker PLA Silk' /
# 'Generic PETG' — NO '@' suffix). The rows live in a scrolled band
# between the 'Filaments' title bar and the 'Color Mixing' title bar.

def sidebar_rows_band(session):
    """(top, bottom, x0) of the sidebar physical-filament rows band; the
    bottom falls back to top+180 when the 'Color Mixing' row is hidden
    (1 filament, Plater.cpp:6585)."""
    frow = _sidebar_title_row(session, "Filaments")
    if not frow:
        return None
    top = frow[0][3] + 2
    x0 = frow[0][0] - 20
    crow = _sidebar_title_row(session, "Color Mixing")
    bottom = (crow[0][1] - 2) if crow else top + 180
    return top, bottom, x0


def filament_material_combos(session):
    """(text, rect, hwnd) of the visible material-name combos in the
    rows band — one per physical filament slot."""
    band = sidebar_rows_band(session)
    if not band:
        return []
    top, bottom, x0 = band
    out = []
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c != "wxWindowNR" or not t.strip() or "@" in t \
                or t.strip() == "panel":
            continue
        if not user32.IsWindowVisible(h):
            continue
        if top <= r[1] <= bottom and x0 <= r[0] <= x0 + 400 \
                and 100 <= r[2] - r[0] <= 200:
            out.append((t.strip(), r, h))
    out.sort(key=lambda x: (x[1][1], x[1][0]))
    return out


def physical_filament_count_ex(session):
    """Robust physical-slot count: material combos, falling back to the
    digit chips, then to the trash-button state (the trash is HIDDEN at
    <= 1 filament, Plater.cpp:4102-4108, which pins the 1-filament state
    while the rows rebuild)."""
    n = len(filament_material_combos(session))
    if n:
        return n
    band = sidebar_rows_band(session)
    if band:
        top, bottom, x0 = band
        nums = set()
        for t, c, r, h in mixing_util.children(session.hwnd):
            if c == "Button" and t.strip().isdigit() \
                    and user32.IsWindowVisible(h) \
                    and top <= r[1] <= bottom and x0 <= r[0] <= x0 + 400:
                nums.add(int(t.strip()))
        if nums:
            return len(nums)
    if len(filament_row_buttons(session)) == 2:
        return 1
    return 0


# --- sidebar entry Options-menu primitives (added 08-30 for m4d/m4f/m4j) ---

def pick_popup_index(session, dlg: int, combo_idx: int, pop_idx: int) -> bool:
    """Open the owner-drawn popup of the Add-Mix row combo `combo_idx` and
    real-click row `pop_idx` (28px pitch, first row at popup_top+14).
    Returns True when a popup was found and a pick click was made — the
    CALLER must verify the effect (combo text / registered sidebar label):
    when several filaments share a preset label the popup rows carry no
    distinguishing text (measured on the all-PLA fixtures)."""
    combos = filament_combos(dlg)
    if len(combos) <= combo_idx:
        return False
    crect = combos[combo_idx][1]
    known = toplevel_snapshot(session)
    cx, cy = (crect[0] + crect[2]) // 2, (crect[1] + crect[3]) // 2
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.2)
    winutil.real_click_screen(cx, cy)
    time.sleep(1.0)
    pop = popup_any(session, known)
    if not pop:
        popup_cancel(session)
        return False
    popup_pick(session, pop, pop_idx)
    return True


def entry_options_menu(session, label_rect, timeout_s: float = 5.0):
    """Real-click a mixing entry's Options ('...') button and read the
    native #32768 popup menu. Returns (menu_rect, menu_hwnd, hmenu, items)
    or None; dismiss with close_entry_menu(). A previous menu's #32768
    window can linger for a moment after WM_CANCELMODE — stale windows are
    drained first and an EMPTY menu read (GetMenuItemCount 0 on a dying
    window, measured) is retried."""
    btn = entry_menu_button(session, label_rect)
    if not btn:
        return None
    r = btn[0]
    x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    for _attempt in range(3):
        close_entry_menu(session)
        if topbar_util.wait_menu_popup(session.pid, timeout_s=1.5):
            # a stale menu is still around — dismiss again and let it die
            close_entry_menu(session)
            time.sleep(1.0)
        winutil.user32.SetCursorPos(x, y)
        time.sleep(0.2)
        winutil.real_click_screen(x, y)
        menus = topbar_util.wait_menu_popup(session.pid, timeout_s=timeout_s)
        if not menus:
            continue
        hwnd = menus[0][4]
        hmenu = topbar_util.menu_hmenu(hwnd)
        items = topbar_util.menu_items(hmenu)
        if items:
            return menus[0][:4], hwnd, hmenu, items
        close_entry_menu(session)
        time.sleep(0.8)
    return None


def close_entry_menu(session):
    """Dismiss any open popup menus of the app."""
    topbar_util.close_menu_windows(session.pid)


def menu_delete_entry(session, label_rect, max_attempts: int = 4) -> bool:
    """Options menu -> 'Delete' for the mixing entry whose label sits at
    `label_rect` (top-level menu row y-candidate probe, rows sit ~12px
    lower than the naive formula; observable = no entry label at that y
    anymore). A probe click landing on 'Edit' opens Edit Mix — it is
    cancelled and the menu reopened (m4c pattern)."""
    def gone():
        return not any(abs(r[1] - label_rect[1]) < 6
                       for _t, r, _h in mix_entry_labels(session))

    for _attempt in range(max_attempts):
        menu = entry_options_menu(session, label_rect)
        if not menu:
            continue
        rect, _hwnd, hmenu, items = menu
        idx = topbar_util.find_item(hmenu, "Delete")
        if idx is None:
            close_entry_menu(session)
            return False
        left, top, right, bottom = rect
        pitch = (bottom - top - 4) / max(len(items), 1)
        base = top + 2 + int((idx + 0.5) * pitch)
        cands = [base + k * 6 for k in range(0, 6)] + \
                [base - k * 6 for k in (1, 2, 3)]
        cx = (left + right) // 2
        opened_edit = None
        for yy in cands:
            winutil.user32.SetCursorPos(cx, yy)
            time.sleep(0.15)
            winutil.real_click_screen(cx, yy)
            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline:
                if gone():
                    close_entry_menu(session)
                    return True
                edlg = find_mix_dialog(session.pid, timeout_s=0.3)
                if edlg:
                    opened_edit = edlg
                    break
                time.sleep(0.3)
            if opened_edit:
                break
            if gone():
                close_entry_menu(session)
                return True
        close_entry_menu(session)
        if opened_edit:
            click_button(session, opened_edit, "Cancel")
            time.sleep(1.2)
        time.sleep(0.8)
    return gone()


def title_panel_buttons(session, title):
    """Visible icon Buttons that are DIRECT children of the sidebar title
    panel hosting the `title` Static ('Filaments' / 'Color Mixing'),
    sorted left->right. Immune to the slot-chip Buttons (and an unrelated
    overlapping button) that leak into the title-row band when the
    physical list scrolls — the 64-slot fixture makes the y-overlap scan
    filament_row_buttons() unreliable there. Measured children:
    Filaments panel = [icon, sync, del, add]; Color Mixing panel =
    [icon, (del only with a non-empty mixing list), add]."""
    label_h = None
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c == "Static" and t == title:
            label_h = h
            break
    if not label_h:
        return []
    panel = user32.GetParent(label_h)
    out = [(r, h) for t, c, r, h in mixing_util.children(panel)
           if c == "Button" and user32.IsWindowVisible(h)]
    out.sort(key=lambda bh: bh[0][0])
    return out

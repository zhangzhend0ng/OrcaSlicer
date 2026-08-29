#!/usr/bin/env python3
# ocr_util.py — Tesseract-based text observation for black-box cases.
#
# WHY: some content exists only as PIXELS (self-drawn tooltips, html
# dialogs, swatch lists) — invisible to window text, UIA and GetWindowText.
# Tesseract (eng) measured clearly better than the local Windows OCR on
# this machine (the system only ships a zh-CN language pack, which mangles
# English UI text). See BLACKBOX_CASES.md 'OCR' notes.
#
# Purity: this reads the SAME screenshots the rest of the harness captures
# (PrintWindow) — it only upgrades the interpretation, not the channel.
# Measured: 'Color Difference: Good (AE=0.0)' recognized verbatim from a
# hover tooltip window.

import os
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from . import winutil

TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = r"C:\Program Files\Tesseract-OCR\tessdata"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
if "TESSDATA_PREFIX" not in os.environ:
    os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR


def ocr_image(img: np.ndarray, scale: int = 3) -> str:
    """OCR a BGR image, upscaling small UI text first."""
    if scale != 1:
        img = cv2.resize(img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)
    return pytesseract.image_to_string(img, config="-l eng").strip()


def ocr_hwnd(hwnd: int, scale: int = 3) -> str:
    """PrintWindow-capture a window (tooltip, dialog) and OCR it."""
    w, h, bgra = winutil.capture_window(hwnd)
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    return ocr_image(img[:, :, ::-1].copy(), scale=scale)


def assert_keywords(text: str, keywords: list) -> bool:
    """All keywords present in the OCR text (case-insensitive)."""
    low = text.lower()
    return all(k.lower() in low for k in keywords)

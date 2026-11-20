"""Digitize ARTA spectrum plots (PNG) into numeric curves.

ARTA draws with a flat palette (no anti-aliasing):
    red    (255,0,0)     -> measured magnitude ("Magn")
    black  (0,0,0)       -> overlay curve ("Over"), not used for the analysis
    yellow (192,192,0)   -> cursor line (hides the red curve in its column)
    grey   (192/128)     -> grid
The plot frame is detected automatically, axis ranges are taken from settings
(default: 20 Hz .. 20 kHz log, -20 .. 50 dB lin).
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

RED = (255, 0, 0)
YELLOW = (192, 192, 0)


@dataclass
class Trace:
    """Per pixel column representation of the red curve."""
    file: Path
    f: np.ndarray            # column centre frequency [Hz]
    df: np.ndarray           # column frequency width [Hz]
    top: np.ndarray          # highest red pixel [dB]  (NaN = no data)
    med: np.ndarray          # median of red pixels [dB] (centre of the noise band)
    bottom: np.ndarray       # lowest red pixel [dB]
    frame: tuple             # (x0, x1, y0, y1) in pixels
    db_per_px: float
    oct_per_px: float
    cursor: dict = field(default_factory=dict)   # {'x','f_px','f_txt','L_txt'}
    rms_a_txt: float | None = None               # ARTA "RMS = .. dB(A)" if shown
    title_txt: str = ""


def _mask(a: np.ndarray, rgb) -> np.ndarray:
    return (a[..., 0] == rgb[0]) & (a[..., 1] == rgb[1]) & (a[..., 2] == rgb[2])


def detect_frame(a: np.ndarray) -> tuple[int, int, int, int]:
    """Return plot frame (x0, x1, y0, y1) from long dark/grey lines."""
    dark = (a[..., 0] < 140) & (a[..., 1] < 140) & (a[..., 2] < 140) & ~_mask(a, RED)
    H, W = dark.shape
    xs = np.where(dark.sum(0) > 0.6 * H * 0.8)[0]
    ys = np.where(dark.sum(1) > 0.6 * W * 0.8)[0]
    if len(xs) < 2 or len(ys) < 2:
        raise ValueError("plot frame not found")
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def _ocr(img: Image.Image) -> str:
    """OCR via tesseract CLI (optional; returns '' if unavailable)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png") as tf:
            img.save(tf.name)
            out = subprocess.run(["tesseract", tf.name, "-", "--psm", "6"],
                                 capture_output=True, text=True, timeout=30)
        return out.stdout
    except Exception:
        return ""


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def digitize(path: Path, f_lo=20.0, f_hi=20000.0, db_top=50.0, db_bot=-20.0,
             use_ocr=True) -> Trace:
    im = Image.open(path).convert("RGB")
    a = np.asarray(im)
    x0, x1, y0, y1 = detect_frame(a)
    red = _mask(a, RED)
    yel = _mask(a, YELLOW)

    lf0, lf1 = np.log10(f_lo), np.log10(f_hi)
    n = x1 - x0 - 1                      # interior columns
    xs = np.arange(x0 + 1, x1)
    # frequency at column centre and column edges (log axis)
    fx = lambda x: 10 ** (lf0 + (x - x0) / (x1 - x0) * (lf1 - lf0))
    f = fx(xs.astype(float))
    df = fx(xs + 0.5) - fx(xs - 0.5)
    ydb = lambda y: db_top - (y - y0) / (y1 - y0) * (db_top - db_bot)

    top = np.full(n, np.nan); med = np.full(n, np.nan); bot = np.full(n, np.nan)
    sub = red[y0 + 1:y1, x0 + 1:x1]
    for i in range(n):
        ys = np.nonzero(sub[:, i])[0]
        if ys.size:
            yy = ys + y0 + 1
            top[i] = ydb(yy.min()); bot[i] = ydb(yy.max()); med[i] = ydb(np.median(yy))

    tr = Trace(path, f, df, top, med, bot, (x0, x1, y0, y1),
               (db_top - db_bot) / (y1 - y0), (lf1 - lf0) * np.log2(10) / (x1 - x0))

    # --- text below the plot: cursor read-out, RMS(A), title (OCR) -------------
    if use_ocr:
        H, W = a.shape[:2]
        txt_img = im.crop((x0 - 40, y1 + 30, min(W, x0 + 1300), H))
        txt_img = txt_img.resize((txt_img.width * 2, txt_img.height * 2))
        txt = _ocr(txt_img)
        m = re.search(r"Cursor:\s*([\d.,]+)\s*Hz,\s*(-?[\d.,]+)\s*dB", txt)
        if m:
            tr.cursor["f_txt"] = _num(m.group(1)); tr.cursor["L_txt"] = _num(m.group(2))
        m = re.search(r"RMS\s*=\s*([+-]?[\d.,]+)\s*dB", txt)
        if m:
            tr.rms_a_txt = _num(m.group(1))
        lines = [l for l in txt.splitlines() if l.strip().startswith("#")]
        tr.title_txt = lines[0].strip() if lines else ""

    # --- cursor column(s): red is hidden there -> repair -----------------------
    ycols = np.where(yel[y0 + 1:y1, x0 + 1:x1].sum(0) > 0.5 * (y1 - y0))[0]
    for i in ycols:
        nb = [j for j in (i - 2, i - 1, i + 1, i + 2) if 0 <= j < n]
        tr.top[i] = np.nanmax(top[nb]); tr.med[i] = np.nanmedian(med[nb])
        tr.bottom[i] = np.nanmin(bot[nb])
        tr.cursor["x"] = int(i); tr.cursor["f_px"] = float(f[i])
        Lc = tr.cursor.get("L_txt"); fc = tr.cursor.get("f_txt")
        # the cursor read-out is an exact bin value at the cursor position
        if Lc is not None and fc is not None and abs(np.log2(fc / f[i])) < 3 * tr.oct_per_px:
            tr.top[i] = max(tr.top[i], Lc)

    # fill isolated empty columns by interpolation (should be rare)
    for arr in (tr.top, tr.med, tr.bottom):
        bad = np.isnan(arr)
        if bad.any() and (~bad).sum() > 2:
            arr[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), arr[~bad])
    return tr

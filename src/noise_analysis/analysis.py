"""Measurement grouping, background-noise fit, line detection and metrics."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter

from .digitize import Trace, digitize
from . import psycho as ps

FNAME_RE = re.compile(r"^(?P<nr>\d+)_(?P<rest>.+?)(?:_(?P<min>\d+)\s*min(?:ute)?_later)?\.png$",
                      re.IGNORECASE)


# ----------------------------------------------------------------------------- file grouping

@dataclass
class Measurement:
    path: Path
    minutes: int                  # 0 = first measurement
    mtime: datetime
    trace: Trace | None = None
    peaks: list = field(default_factory=list)
    bands: np.ndarray | None = None      # level per common band [dB]
    metrics: dict = field(default_factory=dict)
    duplicate_of: str | None = None

    @property
    def label(self):
        return f"{self.minutes} min"


@dataclass
class Device:
    nr: int
    name: str                     # e.g. "TestDevice_01  541400-I06"
    measurements: list

    @property
    def tab(self):
        return f"{self.nr:02d}"


def _device_name(rest: str) -> str:
    # strip fixed suffixes of the naming scheme, keep device id + serial info
    s = re.sub(r"__5cm.*$", "", rest)
    return re.sub(r"_{2,}", "  ", s).strip("_ ")


def scan_folder(folder: Path, mtimes: dict | None = None) -> list[Device]:
    devs: dict[int, Device] = {}
    for p in sorted(folder.glob("*.png")):
        m = FNAME_RE.match(p.name)
        if not m:
            continue
        nr = int(m.group("nr"))
        mins = int(m.group("min") or 0)
        ts = (mtimes or {}).get(p.name) or datetime.fromtimestamp(p.stat().st_mtime)
        d = devs.setdefault(nr, Device(nr, _device_name(m.group("rest")), []))
        d.measurements.append(Measurement(p, mins, ts))
    for d in devs.values():
        d.measurements.sort(key=lambda x: x.minutes)
    return [devs[k] for k in sorted(devs)]


# ----------------------------------------------------------------------------- band axis

def band_axis(f_lo: float, f_hi: float, bpo: int):
    """Base-10 fractional-octave mid-band frequencies (IEC 61260-1)."""
    G = 10 ** 0.3
    x0 = int(np.ceil(bpo * np.log10(f_lo / 1000) / 0.3))
    x1 = int(np.floor(bpo * np.log10(f_hi / 1000) / 0.3))
    x = np.arange(x0, x1 + 1)
    fm = 1000 * G ** (x / bpo)
    return fm, fm * G ** (-0.5 / bpo), fm * G ** (0.5 / bpo)


# ----------------------------------------------------------------------------- background fit

def _poly_eval(coef, f):
    u = np.log10(np.asarray(f, float) / 1000.0)
    return np.polyval(coef[::-1], u)          # coef[0] + coef[1]*u + ...


def robust_polyfit(f, L, degree=3, iters=30, c=4.685):
    """IRLS with Tukey bisquare weights, polynomial in u = lg(f/1 kHz).
    Returns coefficients c0..cn (ascending)."""
    u = np.log10(f / 1000.0)
    w = np.ones_like(L)
    coef = None
    for _ in range(iters):
        coef_d = np.polyfit(u, L, degree, w=np.sqrt(w))
        r = L - np.polyval(coef_d, u)
        s = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-9
        z = r / (c * s)
        w_new = np.where(np.abs(z) < 1, (1 - z**2) ** 2, 0.0)
        if coef is not None and np.allclose(coef_d, coef, atol=1e-6):
            break
        coef, w = coef_d, w_new
    return coef[::-1], float(1.4826 * np.median(np.abs(L - np.polyval(coef, u))))


def peak_mask(tr: Trace, win_px=31, prom=2.0):
    """Columns that stick out of the local noise envelope (used to exclude lines)."""
    env = median_filter(tr.top, size=win_px, mode="nearest")
    m = (tr.top - env) >= prom
    # widen by 2 px
    mm = m.copy()
    for k in (1, 2):
        mm[k:] |= m[:-k]; mm[:-k] |= m[k:]
    return mm, env


# ----------------------------------------------------------------------------- per measurement

def detect_peaks(tr: Trace, floor_coef, s):
    """Tonal lines: local maxima > floor + thr AND > local envelope + prom."""
    fmin, fmax = s["f_min"], s["f_max"]
    valid = (tr.f >= fmin) & (tr.f <= fmax)
    floor = _poly_eval(floor_coef, tr.f)
    m, env = peak_mask(tr, s["peak_window_px"], s["peak_prominence_db"])
    cand = valid & m & ((tr.top - floor) > s["line_threshold_db"])
    peaks = []
    idx = np.flatnonzero(cand)
    if idx.size:
        groups = np.split(idx, np.flatnonzero(np.diff(idx) > 2) + 1)
        for g in groups:
            i = g[np.argmax(tr.top[g])]
            if tr.top[i] - env[i] < s["peak_prominence_db"]:
                continue
            peaks.append(dict(i=int(i), f=float(tr.f[i]), L=float(tr.top[i]),
                              floor=float(floor[i]), above_floor=float(tr.top[i] - floor[i])))
    return peaks


def noise_level(tr: Trace, peaks):
    """Median trace with line columns replaced by interpolation from neighbours."""
    L = tr.med.copy()
    bad = np.zeros_like(L, bool)
    for p in peaks:
        bad[max(0, p["i"] - 3):p["i"] + 4] = True
    m, _ = peak_mask(tr)
    bad |= m
    good = ~bad
    L[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(good), L[good])
    return L


def band_values(tr: Trace, peaks, lo, hi):
    """Level per common band: noise centre, or the line level if a line lies in the band."""
    Ln = noise_level(tr, peaks)
    out = np.full(lo.size, np.nan)
    pf = np.array([p["f"] for p in peaks]); pl = np.array([p["L"] for p in peaks])
    for k in range(lo.size):
        sel = (tr.f >= lo[k]) & (tr.f < hi[k])
        if not sel.any():                       # band narrower than a pixel column
            out[k] = float(np.interp(np.sqrt(lo[k] * hi[k]), tr.f, Ln))
        else:
            out[k] = float(ps.db(np.mean(10 ** (Ln[sel] / 10))))
        if pf.size:
            inb = (pf >= lo[k]) & (pf < hi[k])
            if inb.any():
                out[k] = max(out[k], float(pl[inb].max()))
    return out


def spectrum_model(tr: Trace, peaks, s, f_from=None):
    """Noise PSD + tones from the digitized narrow-band FFT (ARTA, amplitude-correct)."""
    enbw_hz = s["enbw_bins"] * s["fs"] / s["fft_len"]
    Ln = noise_level(tr, peaks)
    # empirical calibration against ARTA's own RMS(A) read-out (see settings)
    psd = 10 ** ((Ln + s.get("cal_noise_db", 0.0)) / 10) / enbw_hz
    sel = np.ones_like(tr.f, bool) if f_from is None else tr.f >= f_from
    tones = []
    for p in peaks:
        if f_from is not None and p["f"] < f_from:
            continue
        pt = 10 ** (p["L"] / 10) - 10 ** (Ln[p["i"]] / 10)
        if pt > 0:
            tones.append((p["f"], pt * 10 ** (s.get("cal_tone_db", 0.0) / 10)))
    return ps.SpectrumModel(tr.f[sel], tr.df[sel], psd[sel], tones)


def metrics(tr: Trace, peaks, s):
    mdl = spectrum_model(tr, peaks, s, f_from=s["f_min"])
    full = spectrum_model(tr, peaks, s)                     # 20 Hz..20 kHz (validation)
    fm, lt = mdl.third_octaves(fmin_valid=s["f_min"])
    N, ns, zg = ps.loudness_zwicker(lt, field=s["field_type"])
    out = dict(LA=float(mdl.level_a(s["f_min"], s["f_max"])),
               LZ=float(mdl.level_z(s["f_min"], s["f_max"])),
               LA_full=float(full.level_a()),
               N=float(N), LN=float(ps.loudness_level_phon(N)),
               S=float(ps.sharpness_din45692(ns, zg)),
               third_oct=lt, ns=ns)
    # tonality per line (only lines above the limit-detection threshold)
    tl = []
    for p in peaks:
        pt = 10 ** (p["L"] / 10)
        t = ps.tonality(mdl, p["f"], pt)
        p.update(t)
        tl.append(t)
    if tl:
        k = int(np.argmax([t["PR"] for t in tl]))
        out.update(PR_max=tl[k]["PR"], PR_f=peaks[k]["f"], TNR_max=max(t["TNR"] for t in tl),
                   KT_max=max(t["KT"] for t in tl),
                   n_prominent=int(sum(t["PR_prominent"] for t in tl)))
    else:
        out.update(PR_max=np.nan, PR_f=np.nan, TNR_max=np.nan, KT_max=0, n_prominent=0)
    out["n_lines"] = len(peaks)
    return out


def match_peaks(pa, pb, tol_oct=0.02):
    """Pair lines of two measurements (frequency drift tolerated)."""
    pairs, used = [], set()
    for a in pa:
        best, bd = None, tol_oct
        for j, b in enumerate(pb):
            d = abs(np.log2(b["f"] / a["f"]))
            if j not in used and d <= bd:
                best, bd = j, d
        if best is not None:
            used.add(best); pairs.append((a, pb[best]))
        else:
            pairs.append((a, None))
    pairs += [(None, b) for j, b in enumerate(pb) if j not in used]
    return sorted(pairs, key=lambda ab: (ab[0] or ab[1])["f"])

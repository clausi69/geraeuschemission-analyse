"""End-to-end pipeline: input folder/ZIP -> digitized, analysed devices."""
from __future__ import annotations

import hashlib
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from . import analysis as an
from .digitize import digitize


@dataclass
class Floor:
    coef: np.ndarray            # ascending polynomial coefficients over u = lg(f/1 kHz)
    sigma: float                # robust residual scatter [dB]
    ref: list                   # reference measurements used
    ref_bands: np.ndarray       # (n_ref, n_bands) noise level per band of each reference


def prepare_input(inp: Path) -> tuple[Path, dict]:
    """Return a folder with PNGs and a {filename: datetime} dict (ZIP keeps file dates)."""
    inp = Path(inp)
    if inp.suffix.lower() == ".zip":
        out = Path(tempfile.mkdtemp(prefix="arta_png_"))
        mt = {}
        with zipfile.ZipFile(inp) as z:
            for zi in z.infolist():
                name = Path(zi.filename).name
                if not name.lower().endswith(".png") or name.startswith("."):
                    continue
                (out / name).write_bytes(z.read(zi))
                mt[name] = datetime(*zi.date_time)
        return out, mt
    return inp, {}


def _plot_hash(tr):
    x0, x1, y0, y1 = tr.frame
    h = hashlib.md5()
    for arr in (tr.top, tr.med, tr.bottom):
        h.update(np.round(arr, 3).tobytes())
    return h.hexdigest()


def run(inp: Path, s: dict, log=print):
    folder, mtimes = prepare_input(inp)
    devices = an.scan_folder(folder, mtimes)
    fm, lo, hi = an.band_axis(s["f_min"], s["f_max"], int(s["bands_per_octave"]))

    # 1) digitize
    seen = {}
    for d in devices:
        for m in d.measurements:
            m.trace = digitize(m.path, s["plot_f_lo"], s["plot_f_hi"], s["plot_db_top"], s["plot_db_bottom"])
            h = _plot_hash(m.trace)
            if h in seen:
                m.duplicate_of = seen[h]
            else:
                seen[h] = m.path.name
        log(f"digitized #{d.nr:02d} ({len(d.measurements)} Messungen)")

    # 2) background noise: N reference files spread evenly over the measurement period
    allm = sorted([m for d in devices for m in d.measurements if not m.duplicate_of],
                  key=lambda m: m.mtime)
    n_ref = min(int(s["floor_n_files"]), len(allm))
    idx = np.unique(np.round(np.linspace(0, len(allm) - 1, n_ref)).astype(int))
    ref = [allm[i] for i in idx]
    ff, LL, ref_bands = [], [], []
    for m in ref:
        tr = m.trace
        mask, _ = an.peak_mask(tr, int(s["peak_window_px"]), s["peak_prominence_db"])
        sel = (tr.f >= s["f_min"]) & (tr.f <= s["f_max"]) & ~mask
        ff.append(tr.f[sel]); LL.append(tr.med[sel])
    coef, sigma = an.robust_polyfit(np.concatenate(ff), np.concatenate(LL), int(s["floor_poly_degree"]))
    for m in ref:   # noise level per band (lines removed) for the documentation sheet
        pk = an.detect_peaks(m.trace, coef, s)
        ref_bands.append(_noise_bands(m.trace, pk, lo, hi))
    floor = Floor(coef, sigma, ref, np.array(ref_bands))
    log(f"Ruhegeräusch-Fit: Grad {len(coef)-1}, Streuung {sigma:.2f} dB, {len(ref)} Referenzen")

    # 3) lines, band values, metrics
    for d in devices:
        for m in d.measurements:
            m.peaks = an.detect_peaks(m.trace, coef, s)
            m.bands = an.band_values(m.trace, m.peaks, lo, hi)
            m.metrics = an.metrics(m.trace, m.peaks, s)
    return devices, floor, (fm, lo, hi)


def _noise_bands(tr, peaks, lo, hi):
    Ln = an.noise_level(tr, peaks)
    out = np.empty(lo.size)
    for k in range(lo.size):
        sel = (tr.f >= lo[k]) & (tr.f < hi[k])
        out[k] = (10 * np.log10(np.mean(10 ** (Ln[sel] / 10))) if sel.any()
                  else np.interp(np.sqrt(lo[k] * hi[k]), tr.f, Ln))
    return out

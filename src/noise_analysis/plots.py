"""Matplotlib figures for the report (change plot, background-noise plot)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

from .analysis import _poly_eval, match_peaks


def _hex(c):
    return "#" + c.lstrip("#")


def _fmt_axes(ax, s):
    ax.set_xscale("log")
    ax.set_xlim(s["f_min"], s["f_max"])
    ax.set_ylim(s["y_min"], s["y_max"])
    ticks = [200, 300, 500, 1000, 2000, 3000, 5000, 10000, 20000]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/1000:g}k" if v >= 1000 else f"{v:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.grid(True, which="both", color="#C0C0C0", lw=0.5)
    ax.set_xlabel("Frequenz [Hz]")
    ax.set_ylabel("Schalldruckpegel [dB re 20 µPa]")


def change_plot(dev, floor_coef, axis, s, out: Path):
    """Overlay of first and second measurement; line changes highlighted."""
    fm, lo, hi = axis
    m0, m1 = dev.measurements[0], dev.measurements[min(1, len(dev.measurements) - 1)]
    fl = _poly_eval(floor_coef, fm)
    lim = fl + s["limit_offset_db"]
    w_cm, h_cm = s["chart_width_cm"], s["chart_height_cm"]
    fig, ax = plt.subplots(figsize=(w_cm / 2.54, h_cm / 2.54), dpi=200)
    ax.plot(fm, fl, color=_hex(s["color_floor"]), lw=1.0, label="Ruhegeräusch")
    ax.plot(fm, lim, color=_hex(s["color_limit"]), lw=1.0, ls="--", label="Limit")
    # fine (pixel-column) traces for realism
    for m, col in ((m0, s["color_meas_0"]), (m1, s["color_meas_1"])):
        t = m.trace
        sel = (t.f >= s["f_min"]) & (t.f <= s["f_max"])
        ax.plot(t.f[sel], t.top[sel], color=_hex(col), lw=0.5, alpha=0.8, label=f"Messung {m.label}")
    # highlight changes of lines (paired peaks)
    up, dn = _hex(s["color_up"]), _hex(s["color_down"])
    for a, b in match_peaks(m0.peaks, m1.peaks, s.get("pair_tol_oct", 0.03)):
        if a and b:
            d = b["L"] - a["L"]
            c = up if d > 0 else dn
            ax.annotate("", xy=(b["f"], b["L"]), xytext=(a["f"], a["L"]),
                        arrowprops=dict(arrowstyle="->", color=c, lw=1.4))
            ax.text(b["f"], max(a["L"], b["L"]) + 1.2, f"{d:+.1f}", color=c, fontsize=6,
                    ha="center", va="bottom", fontweight="bold")
        elif b:      # new line
            ax.plot([b["f"]], [b["L"]], marker="^", color=up, ms=5)
            ax.text(b["f"], b["L"] + 1.2, "neu", color=up, fontsize=6, ha="center")
        elif a:      # vanished line
            ax.plot([a["f"]], [a["L"]], marker="v", color=dn, ms=5)
            ax.text(a["f"], a["L"] + 1.2, "weg", color=dn, fontsize=6, ha="center")
    _fmt_axes(ax, s)
    ax.set_title(f"#{dev.nr:02d} – Änderung {m0.label} → {m1.label} (Pfeile: Linienpegel, Δ in dB)",
                 fontsize=8)
    ax.tick_params(labelsize=7); ax.xaxis.label.set_size(7); ax.yaxis.label.set_size(7)
    ax.legend(fontsize=6, loc="upper right", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def floor_plot(floor, axis, s, out: Path):
    fm, lo, hi = axis
    fig, ax = plt.subplots(figsize=(s["chart_width_cm"] / 2.54, s["chart_height_cm"] / 2.54), dpi=200)
    for m in floor.ref:
        t = m.trace
        sel = (t.f >= s["f_min"]) & (t.f <= s["f_max"])
        ax.plot(t.f[sel], t.med[sel], color="#999999", lw=0.3, alpha=0.6)
    fl = _poly_eval(floor.coef, fm)
    ax.plot(fm, fl, color=_hex(s["color_floor"]), lw=1.5, label="Ruhegeräusch (Fit)")
    ax.plot(fm, fl + s["limit_offset_db"], color=_hex(s["color_limit"]), lw=1.2, ls="--", label="Limit")
    _fmt_axes(ax, s)
    ax.set_title(f"Ruhegeräusch: robuster Polynom-Fit (Grad {len(floor.coef)-1}) über "
                 f"{len(floor.ref)} Referenzmessungen (grau)", fontsize=8)
    ax.tick_params(labelsize=7); ax.xaxis.label.set_size(7); ax.yaxis.label.set_size(7)
    ax.legend(fontsize=6)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
    return out

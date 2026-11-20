"""CLI: python -m noise_analysis <input.zip|folder> [-o report.xlsx] [--settings old_report.xlsx]"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from . import analysis as an
from . import pipeline, psycho, settings
from .report import ReportBuilder


def validation_texts(devices, s):
    v = {}
    dL, df = [], []
    for d in devices:
        for m in d.measurements:
            c = m.png_trace.cursor
            if "x" in c and c.get("L_txt") is not None and c.get("f_txt") and c["x"] >= 2:
                i = c["x"]
                nb = np.nanmax(m.png_trace.top[[i - 2, i - 1, i + 1, i + 2]])
                df.append(abs(np.log2(c["f_txt"] / c["f_px"])))
                if abs(nb - c["L_txt"]) < 0.5:          # cursor placed on a line top
                    dL.append(nb - c["L_txt"])
    if dL:
        v["cursor"] = (f"Vergleich Pixel-Wert gegen ARTA-Cursor-Anzeige (OCR) an {len(dL)} Cursor-Positionen auf "
                       f"Linienspitzen: mittlere Abweichung {np.mean(dL):+.3f} dB, max |Δ| {np.max(np.abs(dL)):.2f} dB. "
                       f"Frequenzlage: max Abweichung {np.max(df)*1200:.0f} Cent ({np.max(df):.4f} Okt, ≈ 1 Pixel).")
    rows = [(m, m.png_trace.rms_a_txt) for d in devices for m in d.measurements
            if m.png_trace.rms_a_txt and not m.duplicate_of and m.csv is None]
    if rows:
        e = np.array([an.spectrum_model(m.trace, m.peaks, s).level_a() - r for m, r in rows])
        v["cal"] = (f"Rauschanteil: Bin-Pegel ÷ ENBW (1,5 Bins Hann, Δf = {s['fs']/s['fft_len']:.3f} Hz), "
                    f"Korrektur {s['cal_noise_db']:+.2f} dB. Linienanteil: Korrektur {s['cal_tone_db']:+.2f} dB, weil "
                    "die Linien durch Frequenzdrift während der 50 Mittelungen über 5–7 Bins verschmieren; "
                    "der Spitzenwert im Bild unterschätzt die Linienleistung (in den CSV-Daten von #14 gemessen: "
                    "+2,9 bzw. +3,6 dB). Kontrolle gegen das von ARTA eingeblendete RMS(A) "
                    f"({len(rows)} PNGs, 20 Hz–20 kHz): mittlere Abweichung {np.mean(e):+.2f} dB, RMS "
                    f"{np.sqrt(np.mean(e**2)):.2f} dB, max {np.max(np.abs(e)):.2f} dB. "
                    "Die Report-Werte L_A gelten für 200 Hz–20 kHz.")
    # exact CSV data vs. digitized PNG of the same measurement
    cmp = []
    for d in devices:
        for m in d.measurements:
            if m.csv is None:
                continue
            pk_png = an.detect_peaks(m.png_trace, *_floor_for(devices, s))
            mp = an.metrics(m.png_trace, pk_png, s)
            dmed = m.png_trace.med - m.trace.med
            sel = m.trace.f >= s["f_min"]
            cmp.append((d.nr, m.label, np.median(dmed[sel]), np.percentile(np.abs(dmed[sel]), 95),
                        mp["LA"] - m.metrics["LA"], mp["N"] / m.metrics["N"] - 1))
    if cmp:
        v["csv"] = ("Vergleich digitalisiertes PNG gegen ARTA-CSV derselben Messung: " + "; ".join(
            f"#{n:02d} {lab}: Rauschband-Mitte Median {a:+.2f} dB (95 % ≤ {b:.2f} dB), "
            f"L_A {c:+.2f} dB, N {dn*100:+.1f} %" for n, lab, a, b, c, dn in cmp)
            + ". Messungen mit CSV werden mit den exakten Bin-Daten ausgewertet (ohne Korrekturen).")
    G = 10 ** 0.3
    fm = 1000 * G ** (np.arange(-16, 12) / 3)
    res = []
    for L in (40, 60, 80):
        mdl = psycho.SpectrumModel(np.array([100.0]), np.array([1.0]), np.array([0.0]), [(1000.0, 10 ** (L / 10))])
        _, lt = mdl.third_octaves()
        res.append(psycho.loudness_zwicker(lt)[0])
    v["loud"] = ("1-kHz-Ton (freies Feld) 40/60/80 dB: "
                 f"{res[0]:.2f}/{res[1]:.2f}/{res[2]:.2f} sone; Referenz DIN 45631: 1,00/4,01/16,07 sone "
                 "(Abweichung durch idealisierte Terzfilter-Flanken). Schärfe Schmalbandrauschen 1 kHz/60 dB ≈ 1 acum.")
    return v


_FLOOR = {}


def _floor_for(devices, s):
    return (_FLOOR["coef"], s)


def main(argv=None):
    ap = argparse.ArgumentParser(description="ARTA-PNG Geräuschemissions-Analyse -> Excel-Report")
    ap.add_argument("input", type=Path, nargs="+",
                    help="ZIP-Dateien oder Ordner mit PNGs (+ optional ARTA-CSV); spätere ersetzen frühere Messungen")
    ap.add_argument("-o", "--output", type=Path, default=Path("Analyse_Geraeuschemission.xlsx"))
    ap.add_argument("--settings", type=Path, help="vorhandener Report: Blatt 'Einstellungen' übernehmen")
    a = ap.parse_args(argv)
    s = settings.defaults()
    if a.settings:
        s = settings.read_from_xlsx(a.settings, s)
    devices, floor, axis = pipeline.run(a.input, s)
    _FLOOR["coef"] = floor.coef
    val = validation_texts(devices, s)
    ReportBuilder(devices, floor, axis, s, " + ".join(p.name for p in a.input)).build(a.output, val)
    print(f"Report geschrieben: {a.output}")


if __name__ == "__main__":
    main()

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
            c = m.trace.cursor
            if "x" in c and c.get("L_txt") is not None and c.get("f_txt"):
                i = c["x"]
                nb = np.nanmax(m.trace.top[[i - 2, i - 1, i + 1, i + 2]])
                df.append(abs(np.log2(c["f_txt"] / c["f_px"])))
                if abs(nb - c["L_txt"]) < 0.5:          # cursor placed on a line top
                    dL.append(nb - c["L_txt"])
    if dL:
        v["cursor"] = (f"Vergleich Pixel-Wert gegen ARTA-Cursor-Anzeige (OCR) an {len(dL)} Cursor-Positionen auf "
                       f"Linienspitzen: mittlere Abweichung {np.mean(dL):+.3f} dB, max |Δ| {np.max(np.abs(dL)):.2f} dB. "
                       f"Frequenzlage: max Abweichung {np.max(df)*1200:.0f} Cent ({np.max(df):.4f} Okt, ≈ 1 Pixel).")
    rows = [(m, m.trace.rms_a_txt) for d in devices for m in d.measurements
            if m.trace.rms_a_txt and not m.duplicate_of]
    if rows:
        e = np.array([an.spectrum_model(m.trace, m.peaks, s).level_a() - r for m, r in rows])
        v["cal"] = (f"Die Bildwerte ergeben ohne Korrektur einen um ≈ 5,5 dB höheren A-Pegel als ARTA selbst anzeigt "
                    f"(RMS(A) in {len(rows)} PNGs). Zwei Korrekturen wurden daher empirisch an diesen Werten bestimmt: "
                    f"Rauschanteil {s['cal_noise_db']:+.2f} dB, Linienanteil {s['cal_tone_db']:+.2f} dB (Linien "
                    "verschmieren durch Frequenzdrift während der Mittelung, Spitzenwert < Linienleistung). "
                    f"Rest-Abweichung zu ARTA: RMS {np.sqrt(np.mean(e**2)):.2f} dB, max {np.max(np.abs(e)):.2f} dB "
                    "(Leave-one-out bei Erstellung: RMS 0,25 dB). Die ARTA-Anzeige umfasst 20 Hz–20 kHz; "
                    "die Report-Werte L_A gelten für 200 Hz–20 kHz.")
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="ARTA-PNG Geräuschemissions-Analyse -> Excel-Report")
    ap.add_argument("input", type=Path, help="ZIP-Datei oder Ordner mit PNGs")
    ap.add_argument("-o", "--output", type=Path, default=Path("Analyse_Geraeuschemission.xlsx"))
    ap.add_argument("--settings", type=Path, help="vorhandener Report: Blatt 'Einstellungen' übernehmen")
    a = ap.parse_args(argv)
    s = settings.defaults()
    if a.settings:
        s = settings.read_from_xlsx(a.settings, s)
    devices, floor, axis = pipeline.run(a.input, s)
    val = validation_texts(devices, s)
    ReportBuilder(devices, floor, axis, s, a.input.name).build(a.output, val)
    print(f"Report geschrieben: {a.output}")


if __name__ == "__main__":
    main()

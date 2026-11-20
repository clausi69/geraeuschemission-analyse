"""Settings: defaults, grouped for the 'Einstellungen' sheet, and read-back from an xlsx."""
from __future__ import annotations

from datetime import date
from pathlib import Path

# (group, key, default, unit, description)
SETTINGS_SPEC = [
    ("Report / Kopf- und Fußzeilen", "company", "Firmenname", "", "Firmenname (Kopfzeile links)"),
    ("Report / Kopf- und Fußzeilen", "title", "Analyse - Geräuschemission", "", "Titel (Kopfzeile Mitte, ergänzt um Gerätebezeichnung)"),
    ("Report / Kopf- und Fußzeilen", "analysis_date", date.today().isoformat(), "", "Analyse-Datum (Kopfzeile rechts)"),
    ("Report / Kopf- und Fußzeilen", "author", "", "", "Bearbeiter"),
    ("Report / Kopf- und Fußzeilen", "footer_left", "Messkammer, Abstand 5 cm, Idle Mode", "", "Fußzeile links"),
    ("Report / Kopf- und Fußzeilen", "footer_center", "Vertraulich", "", "Fußzeile Mitte"),
    ("Report / Kopf- und Fußzeilen", "footer_right", "Seite &P von &N", "", "Fußzeile rechts (&P = Seite, &N = Seitenzahl)"),

    ("Auswertung", "f_min", 200.0, "Hz", "Untere Grenzfrequenz der Auswertung"),
    ("Auswertung", "f_max", 20000.0, "Hz", "Obere Grenzfrequenz der Auswertung"),
    ("Auswertung", "bands_per_octave", 48, "1/Okt", "Auflösung der gemeinsamen Frequenzachse"),
    ("Auswertung", "limit_offset_db", 6.0, "dB", "Limit = Ruhegeräusch + Offset (wirkt sofort per Formel)"),
    ("Auswertung", "line_threshold_db", 3.0, "dB", "Linie, wenn Pegel > Ruhegeräusch + Schwelle"),
    ("Auswertung", "peak_prominence_db", 2.0, "dB", "Linie muss so weit über der lokalen Rauschhüllkurve liegen"),
    ("Auswertung", "peak_window_px", 31, "px", "Fensterbreite der lokalen Rauschhüllkurve (Pixelspalten)"),
    ("Auswertung", "change_min_db", 1.0, "dB", "Änderungs-Chart: Markierung, wenn |Δ| ≥ Wert und Pegel > Ruhegeräusch + Linienschwelle (wirkt sofort)"),
    ("Auswertung", "pair_tol_oct", 0.03, "Okt", "Max. Frequenzabstand zum Paaren von Linien zweier Messungen"),
    ("Auswertung", "floor_poly_degree", 3, "", "Polynomgrad des Ruhegeräusch-Fits (über lg f)"),
    ("Auswertung", "floor_n_files", 10, "", "Anzahl Referenzdateien für das Ruhegeräusch"),
    ("Auswertung", "field_type", "free", "", "Schallfeld für Lautheit (free/diffuse)"),

    ("Messsystem (ARTA)", "fft_len", 16384, "", "FFT-Länge"),
    ("Messsystem (ARTA)", "fs", 48000.0, "Hz", "Abtastrate"),
    ("Messsystem (ARTA)", "window", "Hann", "", "Fensterfunktion"),
    ("Messsystem (ARTA)", "enbw_bins", 1.5, "Bins", "Äquivalente Rauschbandbreite des Fensters"),
    ("Messsystem (ARTA)", "cal_noise_db", 0.0, "dB", "Korrektur Rauschanteil bei PNG-Daten (theoretisch 0; siehe Methodik)"),
    ("Messsystem (ARTA)", "cal_tone_db", 3.60, "dB", "Korrektur Linienleistung bei PNG-Daten: Linie über mehrere Bins verschmiert (siehe Methodik)"),
    ("Messsystem (ARTA)", "averages", 50, "", "Anzahl Mittelungen (linear)"),
    ("Messsystem (ARTA)", "distance_cm", 5, "cm", "Messabstand"),
    ("Messsystem (ARTA)", "plot_f_lo", 20.0, "Hz", "Frequenzachse PNG links"),
    ("Messsystem (ARTA)", "plot_f_hi", 20000.0, "Hz", "Frequenzachse PNG rechts"),
    ("Messsystem (ARTA)", "plot_db_top", 50.0, "dB", "Pegelachse PNG oben"),
    ("Messsystem (ARTA)", "plot_db_bottom", -20.0, "dB", "Pegelachse PNG unten"),

    ("Darstellung", "color_meas_0", "FF0000", "RGB", "Farbe Messung 0 min"),
    ("Darstellung", "color_meas_1", "8B0000", "RGB", "Farbe Messung 1 min"),
    ("Darstellung", "color_meas_2", "FF8C00", "RGB", "Farbe weitere Messung (2/3/5 min)"),
    ("Darstellung", "color_limit", "0070C0", "RGB", "Farbe Limit"),
    ("Darstellung", "color_floor", "000000", "RGB", "Farbe Ruhegeräusch"),
    ("Darstellung", "color_mark", "FFFF00", "RGB", "Füllfarbe: Limit erreicht/überschritten"),
    ("Darstellung", "color_up", "D62728", "RGB", "Änderungsbild: Pegelanstieg"),
    ("Darstellung", "color_down", "2CA02C", "RGB", "Änderungsbild: Pegelabnahme"),
    ("Darstellung", "y_min", -20.0, "dB", "Chart y-Achse min"),
    ("Darstellung", "y_max", 50.0, "dB", "Chart y-Achse max"),
    ("Darstellung", "chart_width_cm", 18.0, "cm", "Breite von Chart und Bildern"),
    ("Darstellung", "chart_height_cm", 12.0, "cm", "Höhe von Chart und Bildern"),
]

GROUP_COLORS = {"Report / Kopf- und Fußzeilen": "DDEBF7", "Auswertung": "E2EFDA",
                "Messsystem (ARTA)": "FFF2CC", "Darstellung": "FCE4D6"}


def defaults() -> dict:
    return {k: v for _, k, v, _, _ in SETTINGS_SPEC}


def _coerce(default, v):
    if v is None or v == "":
        return default
    if isinstance(default, bool):
        return str(v).lower() in ("1", "true", "ja", "yes")
    if isinstance(default, int) and not isinstance(default, bool):
        return int(float(v))
    if isinstance(default, float):
        return float(v)
    return str(v)


def read_from_xlsx(path: Path, base: dict | None = None) -> dict:
    """Read the 'Einstellungen' sheet of a previously generated report (round trip)."""
    from openpyxl import load_workbook
    s = dict(base or defaults())
    wb = load_workbook(path, data_only=True)
    if "Einstellungen" not in wb.sheetnames:
        return s
    ws = wb["Einstellungen"]
    for row in ws.iter_rows(min_row=1, values_only=True):
        if row and len(row) >= 3 and row[1] in s:
            s[row[1]] = _coerce(s[row[1]], row[2])
    return s

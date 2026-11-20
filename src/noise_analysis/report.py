"""Excel report (openpyxl): settings, background noise, overview, overall view, device tabs."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference, ScatterChart, Series
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.comments import Comment
from openpyxl.drawing.image import Image as XLImage
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as CL
from openpyxl.worksheet.pagebreak import Break, RowBreak

from . import plots
from .analysis import match_peaks
from .settings import GROUP_COLORS, SETTINGS_SPEC

FONT = "Arial"
F_N = Font(name=FONT, size=9)
F_B = Font(name=FONT, size=9, bold=True)
F_H = Font(name=FONT, size=14, bold=True)
F_H2 = Font(name=FONT, size=11, bold=True)
F_LINK = Font(name=FONT, size=9, color="008000", underline="single")
THIN = Side(style="thin", color="A6A6A6")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HDR_FILL = PatternFill("solid", fgColor="D9D9D9")
CM2PX = 96 / 2.54
ROW_CM = 0.529            # default row height 15 pt


def _rows_for(h_cm):
    return int(np.ceil(h_cm / ROW_CM)) + 1


def _hdr(ws, row, col, labels, widths=None):
    for k, t in enumerate(labels):
        c = ws.cell(row, col + k, t)
        c.font = F_B; c.fill = HDR_FILL; c.border = BOX
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _cell(ws, r, c, v, fmt=None, font=F_N, border=True):
    x = ws.cell(r, c, v)
    x.font = font
    if fmt:
        x.number_format = fmt
    if border:
        x.border = BOX
    return x


def _q(name):
    return f"'{name}'"


def _page_setup(ws, s, device_label="", landscape=False):
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.6
    ws.page_margins.top = 0.9; ws.page_margins.bottom = 0.8
    ws.page_margins.header = 0.35; ws.page_margins.footer = 0.35
    esc = lambda t: str(t).replace("&", "&&") if "&P" not in str(t) and "&N" not in str(t) else str(t)
    title = s["title"] + (f" - {device_label}" if device_label else "")
    for hf in (ws.oddHeader, ws.evenHeader, ws.firstHeader):
        hf.left.text = esc(s["company"]); hf.left.size = 9; hf.left.font = FONT
        hf.center.text = esc(title); hf.center.size = 10; hf.center.font = f"{FONT},Bold"
        hf.right.text = esc(s["analysis_date"]); hf.right.size = 9; hf.right.font = FONT
    for hf in (ws.oddFooter, ws.evenFooter, ws.firstFooter):
        hf.left.text = esc(s["footer_left"]); hf.left.size = 8; hf.left.font = FONT
        hf.center.text = esc(s["footer_center"]); hf.center.size = 8; hf.center.font = FONT
        hf.right.text = esc(s["footer_right"]); hf.right.size = 8; hf.right.font = FONT


def _style_chart(ch, s, title, y_title="Pegel [dB re 20 µPa]"):
    ch.title = title
    ch.style = 13
    ch.height = s["chart_height_cm"]; ch.width = s["chart_width_cm"]
    ch.roundedCorners = False
    ch.x_axis.title = "Frequenz [Hz]"; ch.y_axis.title = y_title
    ch.x_axis.scaling.logBase = 10
    ch.x_axis.scaling.min = s["f_min"]; ch.x_axis.scaling.max = s["f_max"]
    ch.y_axis.scaling.min = s["y_min"]; ch.y_axis.scaling.max = s["y_max"]
    ch.y_axis.majorUnit = 10
    ch.x_axis.number_format = "#,##0"; ch.y_axis.number_format = "0"
    ch.x_axis.delete = False; ch.y_axis.delete = False
    ch.x_axis.majorGridlines = ch.y_axis.majorGridlines
    from openpyxl.chart.axis import ChartLines
    ch.x_axis.minorGridlines = ChartLines()
    ch.x_axis.crosses = "min"; ch.y_axis.crosses = "min"
    ch.legend.position = "b"; ch.legend.overlay = False
    for t in (ch.title, ch.x_axis.title, ch.y_axis.title):
        if t is not None and hasattr(t, "overlay"):
            t.overlay = False


def _add_line(ch, ws, xcol, ycol, r0, r1, color, width_pt=1.25, dash=None, title_ref=True):
    x = Reference(ws, min_col=xcol, min_row=r0 + 1, max_row=r1)
    y = Reference(ws, min_col=ycol, min_row=r0, max_row=r1)
    se = Series(y, x, title_from_data=title_ref)
    se.marker.symbol = "none"
    se.smooth = False
    se.graphicalProperties.line.solidFill = color
    se.graphicalProperties.line.width = int(width_pt * 12700)
    if dash:
        se.graphicalProperties.line.dashStyle = dash
    ch.series.append(se)
    return se


class ReportBuilder:
    def __init__(self, devices, floor, axis, s, input_name=""):
        self.devs, self.floor, self.axis, self.s = devices, floor, axis, s
        self.fm, self.lo, self.hi = axis
        self.nb = len(self.fm)
        self.input_name = input_name
        self.tmp = Path(tempfile.mkdtemp(prefix="report_img_"))
        self.wb = Workbook()
        self.set_addr = {}

    # ------------------------------------------------------------------ settings
    def sheet_settings(self, ws):
        ws.title = "Einstellungen"
        ws["A1"] = "Einstellungen der Auswertung und Darstellung"; ws["A1"].font = F_H
        ws["A2"] = ("Spalte 'Wert' editieren. Limit-Offset wirkt sofort (Formeln). Farben, Kopf-/Fußzeilen, "
                    "Achsen und Auswertungsparameter wirken nach erneutem Skriptlauf: "
                    "python -m noise_analysis <PNG-Ordner|ZIP> --settings <diese Datei>")
        ws["A2"].font = Font(name=FONT, size=9, italic=True)
        ws.merge_cells("A2:E2"); ws["A2"].alignment = Alignment(wrap_text=True)
        ws.row_dimensions[2].height = 36
        _hdr(ws, 4, 1, ["Gruppe", "Schlüssel", "Wert", "Einheit", "Beschreibung"])
        r = 5
        last_group = None
        for grp, key, _, unit, desc in SETTINGS_SPEC:
            if grp != last_group:
                c = ws.cell(r, 1, grp); c.font = F_H2
                for k in range(1, 6):
                    ws.cell(r, k).fill = PatternFill("solid", fgColor=GROUP_COLORS[grp])
                r += 1; last_group = grp
            fill = PatternFill("solid", fgColor=GROUP_COLORS[grp])
            _cell(ws, r, 1, grp, font=Font(name=FONT, size=8, color="808080"))
            _cell(ws, r, 2, key)
            v = self.s[key]
            c = _cell(ws, r, 3, v, font=Font(name=FONT, size=9, color="0000FF"))
            c.fill = PatternFill("solid", fgColor="FFFFE0")
            if key.startswith("color_"):
                ws.cell(r, 4).fill = PatternFill("solid", fgColor=str(v))
            _cell(ws, r, 4, unit)
            _cell(ws, r, 5, desc)
            self.set_addr[key] = f"Einstellungen!$C${r}"
            r += 1
        for col, w in zip("ABCDE", (26, 20, 30, 8, 70)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A5"
        _page_setup(ws, self.s, "Einstellungen", landscape=True)

    # ------------------------------------------------------------------ background noise
    def sheet_floor(self, ws):
        s, fl = self.s, self.floor
        ws["A1"] = "Ruhegeräusch (gemeinsam für alle Geräte)"; ws["A1"].font = F_H
        ws["A2"] = ("Robuster Polynom-Fit (Tukey-Bisquare, IRLS) des Rauschbands (Median je Pixelspalte, "
                    "Linien ausgeschlossen) über lg(f/1 kHz). Referenzdateien gleichverteilt über den "
                    "Messzeitraum. Spalte 'Ruhegeräusch' = Polynom aus den Koeffizienten unten (Formel).")
        ws["A2"].font = Font(name=FONT, size=9, italic=True); ws["A2"].alignment = Alignment(wrap_text=True)
        ws.merge_cells("A2:L2"); ws.row_dimensions[2].height = 38
        _hdr(ws, 4, 1, ["Koeffizient", "Wert"])
        self.coef_cells = []
        for k, c in enumerate(fl.coef):
            _cell(ws, 5 + k, 1, f"c{k}  (· u^{k})")
            cc = _cell(ws, 5 + k, 2, float(c), "0.00000")
            cc.comment = Comment("Ergebnis des robusten Fits im Python-Skript", "Skript")
            self.coef_cells.append(f"$B${5 + k}")
        r = 5 + len(fl.coef)
        _cell(ws, r, 1, "Streuung σ (robust)"); _cell(ws, r, 2, fl.sigma, "0.00 \"dB\"")
        _cell(ws, r + 1, 1, "u = lg(f / 1000 Hz)")
        # reference list
        _hdr(ws, 4, 4, ["Ref.", "Datei", "Datum/Zeit"])
        for k, m in enumerate(fl.ref):
            _cell(ws, 5 + k, 4, f"R{k+1}")
            _cell(ws, 5 + k, 5, m.path.name)
            _cell(ws, 5 + k, 6, m.mtime, "yyyy-mm-dd hh:mm")
        ws.column_dimensions["E"].width = 62; ws.column_dimensions["F"].width = 16
        # data table
        t0 = 5 + max(len(fl.ref), len(fl.coef) + 2) + 2
        self.floor_t0 = t0
        nref = len(fl.ref)
        hdr = ["f [Hz]"] + [f"R{k+1}" for k in range(nref)] + ["Mittelwert R", "Ruhegeräusch"]
        _hdr(ws, t0, 1, hdr)
        self.floor_col = nref + 3
        fitcol = CL(self.floor_col)
        for i in range(self.nb):
            r = t0 + 1 + i
            _cell(ws, r, 1, float(self.fm[i]), "#,##0.0")
            for k in range(nref):
                _cell(ws, r, 2 + k, float(fl.ref_bands[k, i]), "0.00")
            _cell(ws, r, nref + 2, f"=AVERAGE(B{r}:{CL(nref+1)}{r})", "0.00")
            u = f"LOG10(A{r}/1000)"
            terms = "+".join(f"{c}*{u}^{k}" if k else c for k, c in enumerate(self.coef_cells))
            _cell(ws, r, self.floor_col, f"={terms}", "0.00", font=F_B)
        self.floor_r0, self.floor_r1 = t0 + 1, t0 + self.nb
        for k in range(2, nref + 2):
            ws.column_dimensions[CL(k)].width = 7
        ws.column_dimensions["A"].width = 18; ws.column_dimensions["B"].width = 11
        ws.column_dimensions[CL(nref + 2)].width = 12; ws.column_dimensions[fitcol].width = 13
        ws.freeze_panes = ws.cell(t0 + 1, 2)
        # chart: references + fit
        ch = ScatterChart(); _style_chart(ch, s, "Ruhegeräusch: Referenzen (grau) und Fit (schwarz)")
        for k in range(nref):
            _add_line(ch, ws, 1, 2 + k, t0, self.floor_r1, "BFBFBF", 0.5)
        _add_line(ch, ws, 1, self.floor_col, t0, self.floor_r1, s["color_floor"], 2.0)
        ws.add_chart(ch, f"{CL(self.floor_col + 2)}4")
        _page_setup(ws, s, "Ruhegeräusch")

    def floor_ref(self, i):
        return f"='Ruhegeräusch'!${CL(self.floor_col)}${self.floor_r0 + i}"

    # ------------------------------------------------------------------ device sheet
    def sheet_device(self, d):
        s = self.s
        ws = self.wb.create_sheet(d.tab)
        ms = d.measurements
        nm = len(ms)
        ws["A1"] = f"Gerät #{d.nr:02d} – {d.name}"; ws["A1"].font = F_H
        ws["A2"] = "← Übersicht"; ws["A2"].hyperlink = "#'Übersicht'!A1"; ws["A2"].font = F_LINK

        # ---- key figures
        kh = ["Messung", "Datei", "Datum/Zeit", "L_A\n[dB(A)]", "N\n[sone]", "L_N\n[phon]",
              "S\n[acum]", "max PR\n[dB]", "max K_T\n[dB]", "Linien\n(>3 dB)", "Bänder\n≥ Limit"]
        _hdr(ws, 4, 1, kh); ws.row_dimensions[4].height = 26
        T0 = 6 + nm + 2 + 2 * _rows_for(s["chart_height_cm"]) + 40  # placeholder, fixed below
        # data table position: after graphics pages
        h_rows = _rows_for(s["chart_height_cm"])
        r_chart = 6 + nm + 2
        r_change = r_chart + h_rows + 1
        r_peaks = r_change + h_rows + 1
        n_pairs = len(match_peaks(ms[0].peaks, ms[1].peaks, s['pair_tol_oct'])) if nm > 1 else len(ms[0].peaks)
        r_png = r_peaks + n_pairs + 4
        T0 = r_png + nm * (h_rows + 1) + 2
        R0, R1 = T0 + 1, T0 + self.nb
        meas_cols = list(range(4, 4 + nm))
        mc0, mcl = CL(meas_cols[0]), CL(meas_cols[-1])
        for k, m in enumerate(ms):
            r = 5 + k
            mt = m.metrics
            _cell(ws, r, 1, m.label, font=F_B)
            short = m.path.stem.split("__")[0] + ("_" + m.path.stem.split("_")[-2] + "_later" if m.minutes else "")
            c = _cell(ws, r, 2, short + (" (identisch!)" if m.duplicate_of else ""))
            c.comment = Comment(m.path.name + (f"\nPlotinhalt identisch mit {m.duplicate_of} – "
                                               "vermutlich doppelt exportiert." if m.duplicate_of else ""), "Skript")
            if m.duplicate_of:
                c.font = Font(name=FONT, size=9, color="C00000")
            _cell(ws, r, 3, m.mtime, "yyyy-mm-dd hh:mm")
            for j, (key, fmt) in enumerate((("LA", "0.0"), ("N", "0.00"), ("LN", "0.0"), ("S", "0.00"),
                                            ("PR_max", "0.0"), ("KT_max", "0"), ("n_lines", "0"))):
                v = mt.get(key)
                v = None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)
                _cell(ws, r, 4 + j, v, fmt)
            col = CL(meas_cols[k])
            _cell(ws, r, 11, f"=SUMPRODUCT(--({col}{R0}:{col}{R1}>=$B${R0}:$B${R1}))", "0")
        ws.cell(5, 4).comment = Comment(
            "L_A, N, L_N, S, PR, K_T: im Python-Skript aus der digitalisierten FFT berechnet "
            "(Bildanalyse + ISO 532-1 / DIN 45692 / ECMA-418-1 / DIN 45681), 200 Hz–20 kHz. "
            "Siehe Blatt 'Methodik'.", "Skript")
        if nm > 1:
            r = 5 + nm
            _cell(ws, r, 1, f"Δ {ms[1].label}−{ms[0].label}", font=F_B)
            _cell(ws, r, 2, "Änderung 2. gegenüber 1. Messung"); _cell(ws, r, 3, None)
            for j, fmt in zip(range(4, 12), ("+0.0;-0.0;0.0", "+0.00;-0.00;0.00", "+0.0;-0.0;0.0", "+0.00;-0.00;0.00",
                                              "+0.0;-0.0;0.0", "+0;-0;0", "+0;-0;0", "+0;-0;0")):
                a, b = f"{CL(j)}5", f"{CL(j)}6"
                _cell(ws, r, j, f'=IF(OR({a}="",{b}=""),"",{b}-{a})', fmt, font=F_B)
                ws.cell(r, j).fill = PatternFill("solid", fgColor="F2F2F2")
        ws.column_dimensions["A"].width = 12; ws.column_dimensions["B"].width = 21
        ws.column_dimensions["C"].width = 15

        # ---- data table
        heads = ["f [Hz]", "Limit [dB]", "Ruhegeräusch [dB]"] + [f"{m.label} [dB]" for m in ms]
        cd = 4 + nm
        heads += [f"Δ {ms[1].label}−{ms[0].label} [dB]" if nm > 1 else "Δ [dB]", "≥ Limit"]
        ws.cell(T0 - 1, 1, "Messwerte auf gemeinsamer Frequenzachse "
                f"(1/{int(s['bands_per_octave'])} Oktave; Pegel = Rauschband-Mitte bzw. Linienpegel)").font = F_H2
        _hdr(ws, T0, 1, heads); ws.row_dimensions[T0].height = 26
        off = self.set_addr["limit_offset_db"]
        for i in range(self.nb):
            r = R0 + i
            _cell(ws, r, 1, float(self.fm[i]), "#,##0.0")
            _cell(ws, r, 2, f"=C{r}+{off}", "0.00")
            c = _cell(ws, r, 3, self.floor_ref(i), "0.00"); c.font = Font(name=FONT, size=9, color="008000")
            for k, m in enumerate(ms):
                _cell(ws, r, 4 + k, float(np.round(m.bands[i], 2)), "0.00")
            _cell(ws, r, cd, f"={CL(5)}{r}-{CL(4)}{r}" if nm > 1 else 0, "+0.00;-0.00;0.00")
            _cell(ws, r, cd + 1, f"=IF(MAX({mc0}{r}:{mcl}{r})>=B{r},1,0)", "0")
        rng = f"A{R0}:{CL(cd + 1)}{R1}"
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=[f"MAX(${mc0}{R0}:${mcl}{R0})>=$B{R0}"],
            fill=PatternFill("solid", fgColor=s["color_mark"], bgColor=s["color_mark"])))
        for k in range(4, cd + 2):
            ws.column_dimensions[CL(k)].width = 10.5

        # ---- chart (like the ARTA plot)
        ch = ScatterChart(); _style_chart(ch, s, f"#{d.nr:02d} {d.name} – Spektrum")
        for k, m in enumerate(ms):
            colr = s["color_meas_0"] if k == 0 else s["color_meas_1"] if k == 1 else s["color_meas_2"]
            _add_line(ch, ws, 1, 4 + k, T0, R1, colr, 1.0)
        _add_line(ch, ws, 1, 3, T0, R1, s["color_floor"], 1.5)
        _add_line(ch, ws, 1, 2, T0, R1, s["color_limit"], 1.5, dash="dash")
        ws.add_chart(ch, f"A{r_chart}")

        # ---- change plot
        if nm > 1:
            p = plots.change_plot(d, self.floor.coef, self.axis, s, self.tmp / f"chg_{d.tab}.png")
            self._img(ws, p, f"A{r_change}")
        else:
            ws.cell(r_change, 1, "Nur eine Messung vorhanden – keine Änderungsdarstellung.")

        # ---- peak list
        ws.cell(r_peaks, 1, "Linienliste (Pegel > Ruhegeräusch + Schwelle und > lokale Hüllkurve + Prominenz)").font = F_H2
        ph = ["Linie", f"f {ms[0].label} [Hz]", f"L {ms[0].label} [dB]"]
        if nm > 1:
            ph += [f"f {ms[1].label} [Hz]", f"L {ms[1].label} [dB]", "Δf [Hz]", "ΔL [dB]"]
        ph += ["über Ruhegeräusch [dB]", "PR [dB]", "TNR [dB]", "K_T [dB]", "über Hörschwelle [dB]"]
        _hdr(ws, r_peaks + 1, 1, ph); ws.row_dimensions[r_peaks + 1].height = 26
        pairs = match_peaks(ms[0].peaks, ms[1].peaks, s['pair_tol_oct']) if nm > 1 else [(p, None) for p in ms[0].peaks]
        for k, (a, b) in enumerate(pairs):
            r = r_peaks + 2 + k
            _cell(ws, r, 1, k + 1)
            _cell(ws, r, 2, a["f"] if a else None, "#,##0"); _cell(ws, r, 3, a["L"] if a else None, "0.0")
            c = 4
            if nm > 1:
                _cell(ws, r, 4, b["f"] if b else None, "#,##0"); _cell(ws, r, 5, b["L"] if b else None, "0.0")
                _cell(ws, r, 6, f'=IF(OR(B{r}="",D{r}=""),"",D{r}-B{r})', "+0;-0;0")
                _cell(ws, r, 7, f'=IF(OR(C{r}="",E{r}=""),"",E{r}-C{r})', "+0.0;-0.0;0.0")
                c = 8
            ref = b if (nm > 1 and b) else a     # metrics of the latest measurement
            _cell(ws, r, c, ref["above_floor"], "0.0")
            _cell(ws, r, c + 1, ref.get("PR"), "0.0")
            _cell(ws, r, c + 2, ref.get("TNR"), "0.0")
            _cell(ws, r, c + 3, ref.get("KT"), "0")
            _cell(ws, r, c + 4, ref.get("above_Tq"), "0.0")
        if not pairs:
            ws.cell(r_peaks + 2, 1, "keine Linien erkannt")
        ws.cell(r_peaks + 2 + max(len(pairs), 1), 1,
                "PR/TNR/K_T/Hörschwelle beziehen sich auf die letzte Messung des Paares; "
                "ECMA-418-1 gilt bis 11,2 kHz.").font = Font(name=FONT, size=8, italic=True)

        # ---- original PNGs
        ws.cell(r_png - 1, 1, "Originalmessungen (ARTA-PNG)").font = F_H2
        for k, m in enumerate(ms):
            self._img(ws, m.path, f"A{r_png + k * (h_rows + 1)}")

        # ---- print layout
        ws.row_breaks.append(Break(id=r_change - 1))
        ws.row_breaks.append(Break(id=r_png - 2))
        for k in range(2, nm, 2):
            ws.row_breaks.append(Break(id=r_png + k * (h_rows + 1) - 1))
        ws.row_breaks.append(Break(id=T0 - 2))
        ws.print_title_rows = f"{T0}:{T0}"
        ws.print_area = f"A1:{CL(max(cd + 1, 12))}{R1}"
        _page_setup(ws, s, f"#{d.nr:02d} {d.name}")
        self.dev_info[d.nr] = dict(T0=T0, R0=R0, R1=R1, nm=nm, cd=cd)

    def _img(self, ws, path, anchor):
        img = XLImage(str(path))
        img.width = self.s["chart_width_cm"] * CM2PX
        img.height = self.s["chart_height_cm"] * CM2PX
        ws.add_image(img, anchor)

    # ------------------------------------------------------------------ overview
    def sheet_overview(self, ws):
        s = self.s
        ws.title = "Übersicht"
        ws["A1"] = "Analyse - Geräuschemission – Gesamtübersicht"; ws["A1"].font = F_H
        ws["A2"] = (f"Quelle: {self.input_name}   |   {len(self.devs)} Geräte, "
                    f"{sum(len(d.measurements) for d in self.devs)} Messungen   |   Auswertebereich "
                    f"{s['f_min']:g} Hz – {s['f_max']:g} Hz   |   Limit = Ruhegeräusch + Offset (Einstellungen)")
        ws["A2"].font = Font(name=FONT, size=9, italic=True)
        _cell(ws, 3, 1, "Limit-Offset [dB]", font=F_B, border=False)
        _cell(ws, 3, 3, f"={self.set_addr['limit_offset_db']}", "0.0", font=F_B, border=False)
        h = ["Nr", "Gerät", "Messungen", "L_A 1. [dB(A)]", "L_A 2. [dB(A)]", "ΔL_A [dB]",
             "N 1. [sone]", "N 2. [sone]", "ΔN [%]", "S 2. [acum]", "max PR 2. [dB]", "max K_T 2. [dB]",
             "Linien 1.", "Linien 2.", "Bänder ≥ Limit (alle Mess.)", "Status", "Hinweis"]
        r0 = 5
        _hdr(ws, r0, 1, h); ws.row_dimensions[r0].height = 38
        for k, d in enumerate(self.devs):
            r = r0 + 1 + k
            t = _q(d.tab)
            nm = len(d.measurements)
            c = _cell(ws, r, 1, d.tab, font=F_LINK); c.hyperlink = f"#{t}!A1"
            _cell(ws, r, 2, d.name)
            _cell(ws, r, 3, nm, "0")
            r2 = 6 if nm > 1 else 5
            _cell(ws, r, 4, f"={t}!D5", "0.0"); _cell(ws, r, 5, f"={t}!D{r2}", "0.0")
            _cell(ws, r, 6, f"=E{r}-D{r}", "+0.0;-0.0;0.0")
            _cell(ws, r, 7, f"={t}!E5", "0.00"); _cell(ws, r, 8, f"={t}!E{r2}", "0.00")
            _cell(ws, r, 9, f"=IF(G{r}=0,\"\",H{r}/G{r}-1)", "+0.0%;-0.0%;0.0%")
            _cell(ws, r, 10, f"={t}!G{r2}", "0.00")
            _cell(ws, r, 11, f'=IF({t}!H{r2}="","",{t}!H{r2})', "0.0")
            _cell(ws, r, 12, f"={t}!I{r2}", "0")
            _cell(ws, r, 13, f"={t}!J5", "0"); _cell(ws, r, 14, f"={t}!J{r2}", "0")
            _cell(ws, r, 15, f"=SUM({t}!K5:K{4 + nm})", "0")
            _cell(ws, r, 16, f'=IF(O{r}>0,"Limit erreicht","OK")', font=F_B)
            notes = []
            if any(m.duplicate_of for m in d.measurements):
                notes.append("2. Messung: Plot identisch mit 1. (Doppelexport?)")
            extra = [m.label for m in d.measurements[2:]]
            if extra:
                notes.append("weitere Messung: " + ", ".join(extra))
            _cell(ws, r, 17, "; ".join(notes))
        r1 = r0 + len(self.devs)
        ws.conditional_formatting.add(f"A{r0+1}:Q{r1}", FormulaRule(
            formula=[f"$O{r0+1}>0"], fill=PatternFill("solid", fgColor=s["color_mark"], bgColor=s["color_mark"])))
        widths = [6, 34, 9, 9, 9, 8, 8, 8, 8, 8, 9, 9, 7, 7, 10, 14, 40]
        for k, w in enumerate(widths):
            ws.column_dimensions[CL(k + 1)].width = w
        ws.freeze_panes = f"C{r0+1}"
        # notes
        rn = r1 + 2
        for txt in ("1. = erste Messung (0 min), 2. = zweite Messung (meist 1 min später).",
                    "L_A: A-bewerteter Pegel 200 Hz–20 kHz im Abstand 5 cm (Nahfeld; nur für Vergleiche).",
                    "N/S: Lautheit ISO 532-1 (Zwicker, stationär, freies Feld) / Schärfe DIN 45692, Bänder < 200 Hz ausgeblendet.",
                    "PR: Prominence Ratio ECMA-418-1; K_T: Tonzuschlag DIN 45681 (Klassierung siehe Methodik).",
                    "Status: 'Limit erreicht', wenn in mindestens einem Band einer Messung Pegel ≥ Limit."):
            ws.cell(rn, 1, txt).font = Font(name=FONT, size=8, italic=True); rn += 1
        # charts
        bc = BarChart(); bc.type = "col"; bc.grouping = "clustered"
        bc.title = "Lautheit N je Gerät (1. vs. 2. Messung)"; bc.y_axis.title = "N [sone]"
        bc.height = 9; bc.width = 26; bc.roundedCorners = False
        bc.add_data(Reference(ws, min_col=7, max_col=8, min_row=r0, max_row=r1), titles_from_data=True)
        bc.set_categories(Reference(ws, min_col=1, min_row=r0 + 1, max_row=r1))
        bc.series[0].graphicalProperties.solidFill = s["color_meas_0"]
        bc.series[1].graphicalProperties.solidFill = s["color_meas_1"]
        bc.y_axis.scaling.min = 0
        bc.x_axis.delete = False; bc.y_axis.delete = False; bc.legend.position = "b"; bc.legend.overlay = False
        bc.title.overlay = False
        ws.add_chart(bc, f"A{rn + 1}")
        bc2 = BarChart(); bc2.type = "col"; bc2.title = "Änderung ΔL_A und Bänder ≥ Limit je Gerät"
        bc2.y_axis.title = "ΔL_A [dB]"; bc2.height = 9; bc2.width = 26; bc2.roundedCorners = False
        bc2.add_data(Reference(ws, min_col=6, min_row=r0, max_row=r1), titles_from_data=True)
        bc2.set_categories(Reference(ws, min_col=1, min_row=r0 + 1, max_row=r1))
        bc2.series[0].graphicalProperties.solidFill = s["color_up"]
        bc2.x_axis.delete = False; bc2.y_axis.delete = False; bc2.legend.position = "b"; bc2.legend.overlay = False
        bc2.title.overlay = False
        ws.add_chart(bc2, f"A{rn + 20}")
        ws.row_breaks.append(Break(id=rn - 1))
        ws.print_title_rows = f"{r0}:{r0}"
        _page_setup(ws, s, "Gesamtübersicht", landscape=True)

    # ------------------------------------------------------------------ overall view
    def sheet_overall(self, ws):
        s = self.s
        ws["A1"] = "Gesamtdarstellung der Messwerte (verlinkt auf die Geräteblätter)"; ws["A1"].font = F_H
        ws["A2"] = "Gelb: Pegel ≥ Limit. Spalten je Gerät: 1. und 2. Messung."
        ws["A2"].font = Font(name=FONT, size=9, italic=True)
        T0 = 4 + 2 * (_rows_for(8.6) + 1) + 2
        R0, R1 = T0 + 1, T0 + self.nb
        heads = ["f [Hz]", "Limit [dB]", "Ruhegeräusch [dB]"]
        cols = []
        for d in self.devs:
            nm = len(d.measurements)
            for k in (0, 1) if nm > 1 else (0,):
                heads.append(f"#{d.tab} {d.measurements[k].label}")
                cols.append((d, k))
        _hdr(ws, T0, 1, heads); ws.row_dimensions[T0].height = 26
        for i in range(self.nb):
            r = R0 + i
            _cell(ws, r, 1, float(self.fm[i]), "#,##0.0")
            _cell(ws, r, 2, f"=C{r}+{self.set_addr['limit_offset_db']}", "0.00")
            _cell(ws, r, 3, self.floor_ref(i), "0.00").font = Font(name=FONT, size=9, color="008000")
            for j, (d, k) in enumerate(cols):
                inf = self.dev_info[d.nr]
                c = _cell(ws, r, 4 + j, f"={_q(d.tab)}!{CL(4 + k)}{inf['R0'] + i}", "0.0")
                c.font = Font(name=FONT, size=8, color="008000")
        lastc = CL(3 + len(cols))
        ws.conditional_formatting.add(f"D{R0}:{lastc}{R1}", FormulaRule(
            formula=[f"D{R0}>=$B{R0}"], fill=PatternFill("solid", fgColor=s["color_mark"], bgColor=s["color_mark"])))
        ws.column_dimensions["A"].width = 10
        for j in range(2, 4 + len(cols)):
            ws.column_dimensions[CL(j)].width = 8
        ws.freeze_panes = ws.cell(R0, 4)
        h_ov = 8.6
        for n, (k_sel, ttl, anchor) in enumerate(((0, "Alle Geräte – 1. Messung", "A4"),
                                                   (1, "Alle Geräte – 2. Messung", f"A{4 + _rows_for(h_ov) + 1}"))):
            ch = ScatterChart(); _style_chart(ch, s, ttl)
            ch.width, ch.height = 26.0, h_ov
            for j, (d, k) in enumerate(cols):
                if k == k_sel:
                    se = _add_line(ch, ws, 1, 4 + j, T0, R1, s["color_meas_0"] if k == 0 else s["color_meas_1"], 0.5)
            _add_line(ch, ws, 1, 3, T0, R1, s["color_floor"], 1.75)
            _add_line(ch, ws, 1, 2, T0, R1, s["color_limit"], 1.75, dash="dash")
            ch.legend = None
            ws.add_chart(ch, anchor)
        # print only the charts (the 70+ column table is not printable in a readable size)
        ws.print_area = f"A1:P{T0 - 2}"
        ws.cell(T0 - 1, 1, "Tabelle (nicht im Druckbereich): verlinkte Werte aller Geräte").font = F_H2
        _page_setup(ws, s, "Gesamtdarstellung", landscape=True)
        ws.page_setup.fitToHeight = 1

    # ------------------------------------------------------------------ method sheet
    def sheet_method(self, ws, validation: dict):
        s = self.s
        ws["A1"] = "Methodik, Validierung und Grenzen"; ws["A1"].font = F_H
        lines = [
            ("Datenbasis", "ARTA-PNG-Exporte (Spectrum magnitude, FFT 65536 Pkt, 48 kHz, Hann, 50 lineare Mittelungen, "
             "Kalibrierung 94 dB/1 kHz, Abstand 5 cm). Es handelt sich um FFT-Schmalbandspektren (Δf = 0,732 Hz), "
             "nicht um 1/12-Oktav-Spektren."),
            ("Digitalisierung", "Plotrahmen automatisch; rote Kurve (RGB 255,0,0) je Pixelspalte: oberstes Pixel (Linien), "
             "Median (Rauschband-Mitte). Auflösung 0,049 dB/px, 0,0044 Okt/px. Der gelbe ARTA-Cursor verdeckt eine "
             "Pixelspalte: dort aus Nachbarspalten ergänzt und mit dem per OCR gelesenen Cursor-Wert gestützt."),
            ("Validierung Digitalisierung", validation.get("cursor", "")),
            ("Gemeinsame Frequenzachse", f"1/{int(s['bands_per_octave'])} Oktave (IEC 61260, Basis 10), "
             f"{s['f_min']:g} Hz – {s['f_max']:g} Hz, {self.nb} Bänder. Bandwert = energetisches Mittel der "
             "Rauschband-Mitte; liegt eine Linie im Band, deren Spitzenpegel."),
            ("Ruhegeräusch", f"{len(self.floor.ref)} Referenzdateien gleichverteilt über den Messzeitraum (nach Dateidatum); "
             f"robuster Polynom-Fit Grad {len(self.floor.coef)-1} über lg f; Streuung σ = {self.floor.sigma:.2f} dB."),
            ("Limit", "Limit = Ruhegeräusch + Offset (Einstellungen, wirkt per Formel). Markierung gelb bei Pegel ≥ Limit."),
            ("Linienerkennung", f"Linie, wenn oberstes Pixel > Ruhegeräusch + {s['line_threshold_db']:g} dB UND "
             f"> lokale Rauschhüllkurve (gleitender Median, {int(s['peak_window_px'])} px) + {s['peak_prominence_db']:g} dB. "
             f"Linien zweier Messungen werden bei Frequenzabstand ≤ {s['pair_tol_oct']:g} Okt. gepaart "
             "(thermische Drift der Linienfrequenzen)."),
            ("Pegel/Psychoakustik", "Spektrenmodell: Rausch-PSD aus Rauschband-Mitte (÷ ENBW) + diskrete Linien. "
             "Daraus L_A (IEC 61672 A-Bewertung), Terzpegel (Butterworth-Terzfilter 3. Ordnung), Lautheit ISO 532-1 "
             "(Zwicker, stationär, freies Feld), Lautstärkepegel, Schärfe DIN 45692, Prominence Ratio und TNR "
             "(ECMA-418-1), Tonzuschlag DIN 45681 (a_v = −2 − lg(1+(f/502)^2,5); K_T-Klassen 0/1/2/3/4/5/6 dB für "
             "ΔL ≤0/≤2/≤4/≤6/≤9/≤12/>12 dB), Hörschwelle (Terhardt-Näherung)."),
            ("Kalibrierung gegen ARTA", validation.get("cal", "")),
            ("Validierung Lautheit", validation.get("loud", "")),
            ("Grenzen", "Nahfeldmessung 5 cm: Absolutwerte nicht auf Hörabstand übertragbar, Vergleiche gültig. "
             "Zwicker-Lautheit endet bei 12,5-kHz-Terz (Linien > 14 kHz gehen nicht ein; für Erwachsene meist ohnehin "
             "unter der Hörschwelle). Rauigkeit, Schwankungsstärke, ECMA-418-2 benötigen Zeitsignale und sind nicht möglich. "
             "Linienpegel: Hann-Scalloping bis −1,4 dB möglich. K_T-Klassierung aus Sekundärliteratur, bitte gegen "
             "DIN 45681:2005 prüfen."),
            ("Software", "Python-Paket noise_analysis (Repository geraeuschemission-analyse). Neu erzeugen: "
             "python -m noise_analysis <ZIP|Ordner> -o report.xlsx [--settings report.xlsx]"),
        ]
        _hdr(ws, 3, 1, ["Thema", "Beschreibung"])
        for k, (a, b) in enumerate(lines):
            r = 4 + k
            _cell(ws, r, 1, a, font=F_B).alignment = Alignment(vertical="top")
            c = _cell(ws, r, 2, b); c.alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[r].height = max(15, 13 * (len(b) // 110 + 1))
        ws.column_dimensions["A"].width = 26; ws.column_dimensions["B"].width = 120
        p = plots.floor_plot(self.floor, self.axis, s, self.tmp / "floor.png")
        self._img(ws, p, f"B{6 + len(lines)}")
        _page_setup(ws, s, "Methodik", landscape=True)

    # ------------------------------------------------------------------ build
    def build(self, out: Path, validation: dict):
        self.dev_info = {}
        ws_ov = self.wb.active
        self.sheet_overview_placeholder = ws_ov
        ws_all = self.wb.create_sheet("Gesamtdarstellung")
        ws_set = self.wb.create_sheet("Einstellungen")
        ws_floor = self.wb.create_sheet("Ruhegeräusch")
        ws_meth = self.wb.create_sheet("Methodik")
        self.sheet_settings(ws_set)
        self.sheet_floor(ws_floor)
        for d in self.devs:
            self.sheet_device(d)
        self.sheet_overview(ws_ov)
        self.sheet_overall(ws_all)
        self.sheet_method(ws_meth, validation)
        for ws in self.wb.worksheets:
            ws.sheet_view.zoomScale = 90
        self.wb.calculation.fullCalcOnLoad = True
        self.wb.save(out)
        return out

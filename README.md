# Geräuschemissions-Analyse aus ARTA-Spektren

Wertet ARTA-Spektrum-Exporte (PNG) von Testgeräten aus und erzeugt einen druckfähigen Excel-Report:
Digitalisierung der Bilder, gemeinsames Ruhegeräusch, Limit, Linienerkennung, Änderung 0 → 1 min,
A-Pegel, Lautheit (ISO 532-1), Schärfe (DIN 45692), Tonhaltigkeit (ECMA-418-1, DIN 45681).

## Setup (VS Code, Windows / macOS / Linux)

```bash
git clone https://github.com/clausi69/geraeuschemission-analyse.git
cd geraeuschemission-analyse
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
pip install -e .            # optional: Befehl `noise-analysis` verfügbar
```

VS Code: Ordner öffnen → Interpreter `.venv` wird über `.vscode/settings.json` vorgeschlagen.
Unter Windows ggf. in `settings.json` den Pfad auf `.venv\\Scripts\\python.exe` ändern.

Für die Auswertung des ARTA-Cursors und der eingeblendeten RMS(A)-Werte wird optional
[Tesseract OCR](https://github.com/tesseract-ocr/tesseract) im PATH genutzt (ohne Tesseract läuft alles,
nur die Cursor-Stützung und der Abgleich gegen ARTA-RMS entfallen).

## Benutzung

```bash
# Messungen als ZIP (bevorzugt: Dateidatum bleibt erhalten) oder als Ordner
python -m noise_analysis data/TestDevices_PNGs.zip -o output/Analyse_Geraeuschemission.xlsx

# Einstellungen (Firma, Farben, Limit, Polynomgrad …) im Blatt "Einstellungen" ändern,
# dann mit diesen Einstellungen neu erzeugen:
python -m noise_analysis data/TestDevices_PNGs.zip -o output/Analyse_v2.xlsx --settings output/Analyse_Geraeuschemission.xlsx
```

In VS Code: Debug-Konfigurationen in `.vscode/launch.json` (Daten nach `data/` legen).
Messdaten (`*.png`, `*.zip`) und Reports (`*.xlsx`) werden per `.gitignore` nicht eingecheckt.

## Dateinamen-Konvention

`NN_<Gerät>__…__Ruhegeräusch.png` = 1. Messung (0 min) von Gerät NN,
`…_1min_later.png`, `…_2min_later.png`, `…_5min_later.png` = Folgemessungen.

## Aufbau

| Modul | Inhalt |
|---|---|
| `digitize.py` | Plotrahmen, rote Kurve je Pixelspalte (Spitze/Median), gelber Cursor, OCR |
| `analysis.py` | Dateigruppen, 1/n-Oktav-Achse, robuster Ruhegeräusch-Fit, Linien, Spektrenmodell |
| `psycho.py` | A-Bewertung, Terzen, Zwicker-Lautheit, Schärfe, PR/TNR, DIN 45681, Hörschwelle |
| `report.py` | Excel-Report (openpyxl): Übersicht, Gesamtdarstellung, Einstellungen, Ruhegeräusch, Methodik, Geräteblätter |
| `plots.py` | Änderungsbild 0 → 1 min, Ruhegeräusch-Plot (matplotlib) |

## Wichtige Hinweise zur Methodik

* Die ARTA-Bilder sind **FFT-Schmalbandspektren** (65536 Pkt, 48 kHz, Hann, Δf = 0,732 Hz).
* Pegelauflösung der Bilder: 0,049 dB/px; validiert gegen ARTA-Cursor-Anzeigen (OCR).
* Die Umrechnung Bild → Leistung ist **empirisch gegen ARTA-RMS(A)** kalibriert (`cal_noise_db`,
  `cal_tone_db` im Blatt Einstellungen), Rest-Abweichung ≈ 0,2 dB RMS.
* Zwicker-Lautheit: 1-kHz-Ton 40/60/80 dB → 1,02/4,10/16,6 sone (DIN-Referenz 1,00/4,01/16,07), siehe `tests/`.
* Messung im Nahfeld (5 cm): Absolutwerte nur für Vergleiche verwenden.

Tests: `pytest`

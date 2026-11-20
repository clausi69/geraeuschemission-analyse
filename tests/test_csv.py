from pathlib import Path

import numpy as np

from noise_analysis.analysis import CSV_RE, read_arta_csv


def test_read_arta_csv(tmp_path: Path):
    p = tmp_path / "#14_1_direkt-Messung.csv"
    p.write_text("DFT Spectrum,  -\nNumpoints, 8192\nSamplingRate(Hz), 48000.000000\n"
                 "DFTresolution(Hz), 2.929688\nFrequency(Hz), Magnitude(dB)\n    2.930, 31.44\n    5.859, 39.15\n")
    f, L = read_arta_csv(p)
    assert np.allclose(f, [2.93, 5.859]) and np.allclose(L, [31.44, 39.15])


def test_csv_name_pattern():
    assert CSV_RE.match("#14_1_direkt-Messung.csv").group("nr") == "14"
    assert "1_min_later" in CSV_RE.match("#14_2_1_min_later-Messung.csv").group("rest")

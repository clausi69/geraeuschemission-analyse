"""Reference checks of the psychoacoustic implementation."""
import numpy as np

from noise_analysis import psycho as ps


def _tone_model(level_db, f=1000.0):
    return ps.SpectrumModel(np.array([100.0]), np.array([1.0]), np.array([0.0]), [(f, 10 ** (level_db / 10))])


def test_zwicker_1khz_tone_reference():
    # DIN 45631 / ISO 532-1: 1 kHz tone 40/60/80 dB -> 1.00/4.01/16.07 sone
    for L, ref in ((40, 1.00), (60, 4.01), (80, 16.07)):
        _, lt = _tone_model(L).third_octaves()
        n, _, _ = ps.loudness_zwicker(lt)
        assert abs(n / ref - 1) < 0.05, (L, n)


def test_sharpness_reference():
    # narrow-band noise at 1 kHz, 60 dB -> about 1 acum
    _, lt = _tone_model(60).third_octaves()
    n, ns, z = ps.loudness_zwicker(lt)
    assert 0.9 < ps.sharpness_din45692(ns, z) < 1.15


def test_a_weighting():
    assert abs(ps.a_weight_db(1000)) < 0.01
    assert abs(ps.a_weight_db(100) + 19.1) < 0.1
    assert abs(ps.a_weight_db(10000) + 2.5) < 0.1

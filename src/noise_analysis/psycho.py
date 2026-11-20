"""Psychoacoustic and level metrics computed from a (noise PSD + tonal lines) model.

Spectrum model (derived from the digitized ARTA narrow-band FFT):
    * noise: power spectral density G(f) [Pa^2/Hz relative to p0^2]
    * tones: list of (f_i, P_i) with P_i = rms power of the line

Implemented:
    A-weighting (IEC 61672-1), third-octave synthesis (IEC 61260 base-10),
    stationary loudness (ISO 532-1:2017 / DIN 45631, Zwicker, free field),
    loudness level (phon), sharpness (DIN 45692), hearing threshold (Terhardt
    approximation of ISO 389-7 / ISO 226), critical bandwidth (Zwicker),
    tone-to-noise ratio and prominence ratio (ECMA-418-1), tonal audibility and
    tone adjustment (DIN 45681).
"""
from __future__ import annotations

import numpy as np

# ----------------------------------------------------------------------------- basics

def a_weight_db(f):
    """A-weighting in dB (IEC 61672-1, analytic form)."""
    f = np.asarray(f, float)
    f2 = f * f
    ra = (12194.0**2 * f2**2) / ((f2 + 20.6**2) * np.sqrt((f2 + 107.7**2) * (f2 + 737.9**2))
                                * (f2 + 12194.0**2))
    return 20 * np.log10(np.maximum(ra, 1e-30)) + 2.00


def hearing_threshold_db(f):
    """Threshold in quiet [dB SPL] (Terhardt 1979 approximation)."""
    k = np.asarray(f, float) / 1000.0
    return 3.64 * k**-0.8 - 6.5 * np.exp(-0.6 * (k - 3.3) ** 2) + 1e-3 * k**4


def critical_bandwidth(f):
    """Critical bandwidth [Hz] (Zwicker & Terhardt), used by ECMA-418-1 / DIN 45681."""
    k = np.asarray(f, float) / 1000.0
    return 25.0 + 75.0 * (1 + 1.4 * k**2) ** 0.69


def db(p):
    return 10 * np.log10(np.maximum(p, 1e-30))


# ----------------------------------------------------------------------------- spectrum model

class SpectrumModel:
    """Continuous noise PSD (piecewise constant per column) + discrete tones."""

    def __init__(self, f, df, psd, tones=()):
        self.f = np.asarray(f, float)          # column centre [Hz]
        self.df = np.asarray(df, float)        # column width [Hz]
        self.psd = np.asarray(psd, float)      # power per Hz (lin, re p0^2)
        self.tones = [(float(ft), float(pt)) for ft, pt in tones]
        lo = self.f - self.df / 2
        self.edges_lo, self.edges_hi = lo, self.f + self.df / 2

    def band_power(self, f1, f2, tones=True, exclude_tone=None):
        """Power in [f1, f2] (noise integrated, tones added)."""
        ov = np.clip(np.minimum(self.edges_hi, f2) - np.maximum(self.edges_lo, f1), 0, None)
        p = float(np.sum(self.psd * ov))
        if tones:
            p += sum(pt for ft, pt in self.tones
                     if f1 <= ft < f2 and (exclude_tone is None or ft != exclude_tone))
        return p

    def noise_power(self, f1, f2):
        return self.band_power(f1, f2, tones=False)

    def level_a(self, f1=None, f2=None):
        f1 = self.edges_lo[0] if f1 is None else f1
        f2 = self.edges_hi[-1] if f2 is None else f2
        ov = np.clip(np.minimum(self.edges_hi, f2) - np.maximum(self.edges_lo, f1), 0, None)
        p = np.sum(self.psd * ov * 10 ** (a_weight_db(self.f) / 10))
        p += sum(pt * 10 ** (a_weight_db(ft) / 10) for ft, pt in self.tones if f1 <= ft < f2)
        return db(p)

    def level_z(self, f1=None, f2=None):
        f1 = self.edges_lo[0] if f1 is None else f1
        f2 = self.edges_hi[-1] if f2 is None else f2
        return db(self.band_power(f1, f2))

    def third_octaves(self, fmin_valid=None):
        """28 third-octave levels 25 Hz .. 12.5 kHz (IEC 61260, base 10).
        Bands (or parts) below fmin_valid are treated as empty (-inf -> -100 dB)."""
        G = 10 ** 0.3
        x = np.arange(-16, 12)                    # 25 Hz .. 12.5 kHz
        fm = 1000.0 * G ** (x / 3)
        # Third-octave filters are modelled as 3rd-order Butterworth band-passes
        # (IEC 61260 class-1 like). The finite filter slopes matter: ISO 532-1 is
        # calibrated with real filters (1 kHz/40 dB tone -> 1.02 sone here, 1.00 per DIN).
        qr = 1.0 / (G ** (1 / 6) - G ** (-1 / 6))
        valid = np.ones_like(self.f, bool) if fmin_valid is None else self.f >= fmin_valid
        p_col = np.where(valid, self.psd * self.df, 0.0)
        tf = np.array([t[0] for t in self.tones]) if self.tones else np.zeros(0)
        tp = np.array([t[1] for t in self.tones]) if self.tones else np.zeros(0)
        if fmin_valid is not None and tf.size:
            tp = np.where(tf >= fmin_valid, tp, 0.0)
        out = []
        for fc in fm:
            h = 1.0 / (1.0 + ((self.f / fc - fc / self.f) * qr) ** 6)
            p = np.sum(p_col * h)
            if tf.size:
                p += np.sum(tp / (1.0 + ((tf / fc - fc / tf) * qr) ** 6))
            out.append(db(p) if p > 0 else -100.0)
        return fm, np.array(out)


# ----------------------------------------------------------------------------- ISO 532-1 (Zwicker)

_RAP = np.array([45, 55, 65, 71, 80, 90, 100, 120], float)
_DLL = np.array([
    [-32, -24, -16, -10, -5, 0, -7, -3, 0, -2, 0],
    [-29, -22, -15, -10, -4, 0, -7, -2, 0, -2, 0],
    [-27, -19, -14, -9, -4, 0, -6, -2, 0, -2, 0],
    [-25, -17, -12, -9, -3, 0, -5, -2, 0, -2, 0],
    [-23, -16, -11, -7, -3, 0, -4, -1, 0, -1, 0],
    [-20, -14, -10, -6, -3, 0, -4, -1, 0, -1, 0],
    [-18, -12, -9, -6, -2, 0, -3, -1, 0, -1, 0],
    [-15, -10, -8, -4, -2, 0, -3, -1, 0, -1, 0]], float)
_LTQ = np.array([30, 18, 12, 8, 7, 6, 5, 4, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3], float)
_A0 = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -0.5, -1.6, -3.2, -5.4, -5.6, -4.0, -1.5, 2.0, 5.0, 12.0])
_DDF = np.array([0, 0, 0.5, 0.9, 1.2, 1.6, 2.3, 2.8, 3.0, 2.0, 0, -1.4, -2.0, -1.9, -1.0, 0.5, 3.0, 4.0, 4.3, 4.0])
_DCB = np.array([-0.25, -0.6, -0.8, -0.8, -0.5, 0, 0.5, 1.1, 1.5, 1.7, 1.8, 1.8, 1.7, 1.6, 1.4, 1.2, 0.8, 0.5, 0, -0.5])
_ZUP = np.array([0.9, 1.8, 2.8, 3.5, 4.4, 5.4, 6.6, 7.9, 9.2, 10.6, 12.3, 13.8, 15.2, 16.7, 18.1, 19.3, 20.6, 21.8, 22.7, 23.6, 24.0])
_RNS = np.array([21.5, 18.0, 15.1, 11.5, 9.0, 6.1, 4.4, 3.1, 2.13, 1.36, 0.82, 0.42, 0.30, 0.22, 0.15, 0.10, 0.035, 0.0])
_USL = np.array([
    [13.0, 8.2, 6.3, 5.5, 5.5, 5.5, 5.5, 5.5],
    [9.0, 7.5, 6.0, 5.1, 4.5, 4.5, 4.5, 4.5],
    [7.8, 6.7, 5.6, 4.9, 4.4, 3.9, 3.9, 3.9],
    [6.2, 5.4, 4.6, 4.0, 3.5, 3.2, 3.2, 3.2],
    [4.5, 3.8, 3.6, 3.2, 2.9, 2.7, 2.7, 2.7],
    [3.7, 3.0, 2.8, 2.35, 2.2, 2.2, 2.2, 2.2],
    [2.9, 2.3, 2.1, 1.9, 1.8, 1.7, 1.7, 1.7],
    [2.4, 1.7, 1.5, 1.35, 1.3, 1.3, 1.3, 1.3],
    [1.95, 1.45, 1.3, 1.15, 1.1, 1.1, 1.1, 1.1],
    [1.5, 1.2, 0.94, 0.86, 0.82, 0.82, 0.82, 0.82],
    [0.72, 0.67, 0.64, 0.63, 0.62, 0.62, 0.62, 0.62],
    [0.59, 0.53, 0.51, 0.5, 0.42, 0.42, 0.42, 0.42],
    [0.4, 0.33, 0.26, 0.24, 0.24, 0.22, 0.22, 0.22],
    [0.27, 0.21, 0.2, 0.18, 0.17, 0.17, 0.17, 0.17],
    [0.16, 0.15, 0.14, 0.12, 0.11, 0.11, 0.11, 0.11],
    [0.12, 0.11, 0.1, 0.08, 0.08, 0.08, 0.08, 0.08],
    [0.09, 0.08, 0.07, 0.06, 0.06, 0.06, 0.06, 0.05],
    [0.06, 0.05, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02]])


def loudness_zwicker(lt, field="free"):
    """Stationary loudness ISO 532-1 from 28 third-octave levels (25 Hz..12.5 kHz).

    Returns (N [sone], N' specific loudness on 0.1 Bark grid (240 values), z grid).
    Port of the normative program in ISO 532-1:2017 Annex A (method for stationary sounds).
    """
    lt = np.asarray(lt, float)
    assert lt.size == 28
    # 1) correction of low-frequency bands (25..250 Hz) for equal-loudness contours
    ti = np.zeros(11)
    for i in range(11):
        j = 0
        while j < 7 and lt[i] > _RAP[j] - _DLL[j, i]:
            j += 1
        ti[i] = 10 ** ((lt[i] + _DLL[j, i]) / 10)
    gi = np.array([ti[0:6].sum(), ti[6:9].sum(), ti[9:11].sum()])
    lcb = np.where(gi > 0, 10 * np.log10(np.maximum(gi, 1e-30)), -100.0)
    # 2) core loudness of the 20 critical bands
    nm = np.zeros(21)
    for i in range(20):
        le = lcb[i] if i < 3 else lt[i + 8]
        le -= _A0[i]
        if field == "diffuse":
            le += _DDF[i]
        if le > _LTQ[i]:
            le -= _DCB[i]
            s = 0.25
            mp1 = 0.0635 * 10 ** (0.025 * _LTQ[i])
            mp2 = (1 - s + s * 10 ** ((le - _LTQ[i]) / 10)) ** 0.25 - 1
            nm[i] = max(mp1 * mp2, 0.0)
    # 3) correction of the lowest critical band
    korry = min(0.4 + 0.32 * nm[0] ** 0.2, 1.0)
    nm[0] *= korry
    # 4) upper slopes, integration
    n_tot, z1, n1, z = 0.0, 0.0, 0.0, 0.1
    ns = np.zeros(240)
    iz = 0
    j = 0
    for i in range(21):
        zup = _ZUP[i] + 1e-4
        ig = min(max(i - 1, 0), 7)
        while z1 < zup:
            if n1 <= nm[i]:
                if n1 < nm[i]:
                    j = 0
                    while j < 17 and _RNS[j] > nm[i]:
                        j += 1
                z2, n2 = zup, nm[i]
                n_tot += n2 * (z2 - z1)
                while z <= z2 + 1e-9 and iz < 240:
                    ns[iz] = n2; iz += 1; z += 0.1
            else:
                n2 = max(_RNS[j], nm[i])
                dz = (n1 - n2) / _USL[j, ig]
                z2 = z1 + dz
                if z2 > zup:
                    z2 = zup
                    dz = z2 - z1
                    n2 = n1 - dz * _USL[j, ig]
                n_tot += dz * (n1 + n2) / 2
                while z <= z2 + 1e-9 and iz < 240:
                    ns[iz] = n1 - (z - z1) * _USL[j, ig]; iz += 1; z += 0.1
            if n2 == _RNS[j]:
                j += 1
            j = min(j, 17)
            z1, n1 = z2, n2
    n_tot = max(n_tot, 0.0)
    ns = np.maximum(ns, 0.0)
    zg = np.arange(1, 241) * 0.1
    return n_tot, ns, zg


def loudness_level_phon(n):
    if n <= 0:
        return 3.0
    return 40 * (n + 0.0005) ** 0.35 if n < 1 else 40 + 10 * np.log2(n)


def sharpness_din45692(ns, zg):
    """Sharpness [acum] (DIN 45692) from specific loudness N'(z)."""
    n = np.sum(ns) * 0.1
    if n <= 0:
        return 0.0
    g = np.where(zg <= 15.8, 1.0, 0.85 + 0.15 * np.exp(0.42 * (zg - 15.8)))
    return 0.11 * np.sum(ns * g * zg) * 0.1 / n


# ----------------------------------------------------------------------------- tonality

def tonality(model: SpectrumModel, ft, pt):
    """Tone metrics for a single line at ft with power pt.

    TNR, PR      : ECMA-418-1 (ANSI S1.13) definitions with Zwicker critical bands.
    dL_45681     : DIN 45681 excess level dL = L_T - L_G - a_v,
                   a_v = -2 - lg(1 + (f/502)^2.5) dB.
    KT           : tone adjustment classes per DIN 45681 Tab. 1.
    """
    bw = critical_bandwidth(ft)
    f1, f2 = ft - bw / 2, ft + bw / 2
    # tones inside the critical band count as tone power (ECMA: multiple tones in band)
    p_tones = sum(p for f, p in model.tones if f1 <= f < f2)
    p_noise = model.noise_power(f1, f2)
    tnr = db(p_tones) - db(p_noise)
    # prominence ratio: middle band vs mean of adjacent bands (upper band capped at fs/2)
    fl = ft  # lower band centred so that it ends at f1
    lo_hi = f1; lo_lo = max(f1 - critical_bandwidth(max(f1 - bw / 2, 20)), 1.0)
    up_lo = f2; up_hi = f2 + critical_bandwidth(f2 + bw / 2)
    w_m = model.band_power(f1, f2)
    w_l = model.band_power(lo_lo, lo_hi)
    w_u = model.band_power(up_lo, min(up_hi, model.edges_hi[-1]))
    if up_hi > model.edges_hi[-1]:      # band truncated by the measurement range
        w_u *= (up_hi - up_lo) / max(model.edges_hi[-1] - up_lo, 1e-9)
    pr = db(w_m) - db((w_l + w_u) / 2)
    lt_db = db(p_tones)
    lg_db = db(p_noise)
    av = -2 - np.log10(1 + (ft / 502.0) ** 2.5)
    dl = lt_db - lg_db - av
    kt = 0 if dl <= 0 else 1 if dl <= 2 else 2 if dl <= 4 else 3 if dl <= 6 else \
        4 if dl <= 9 else 5 if dl <= 12 else 6
    crit_tnr = 8.0 if ft >= 1000 else 8.0 + 2.5 * np.log10(1000 / ft)
    crit_pr = 9.0 if ft >= 1000 else 9.0 + 10 * np.log10(1000 / ft)
    return dict(bw=bw, L_tone=lt_db, L_noise_cb=lg_db, TNR=tnr, PR=pr,
                TNR_prominent=tnr >= crit_tnr, PR_prominent=pr >= crit_pr,
                dL_45681=dl, KT=kt,
                # Terhardt approximation is not meaningful above ~16 kHz
                Tq=float(hearing_threshold_db(ft)) if ft <= 16000 else None,
                above_Tq=lt_db - float(hearing_threshold_db(ft)) if ft <= 16000 else None,
                in_ecma_range=89.1 <= ft <= 11200)

"""Tempo smoothing (規格 5)."""
from __future__ import annotations
import numpy as np


def _median_filter(x, w):
    n = len(x)
    half = w // 2
    out = np.empty(n, dtype=float)
    for i in range(n):
        a = max(0, i - half)
        b = min(n, i + half + 1)
        out[i] = np.median(x[a:b])
    return out


def _mean_filter(x, w):
    n = len(x)
    half = w // 2
    out = np.empty(n, dtype=float)
    for i in range(n):
        a = max(0, i - half)
        b = min(n, i + half + 1)
        out[i] = np.mean(x[a:b])
    return out


def _ema(x, w):
    alpha = 2.0 / (w + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1.0 - alpha) * out[i - 1]
    return out


def smooth_tempo(bpm, window=5, method="median+mean", strength=0.6):
    bpm = np.asarray(bpm, dtype=float)
    if bpm.size < 3 or strength <= 0 or method == "none":
        return bpm.copy()

    w = max(3, int(window))
    if w % 2 == 0:
        w += 1

    if method == "median+mean":
        out = _median_filter(bpm, w)
        out = _mean_filter(out, w)
    elif method == "median":
        out = _median_filter(bpm, w)
    elif method == "mean":
        out = _mean_filter(bpm, w)
    elif method == "ema":
        out = _ema(bpm, w)
    else:
        out = bpm.copy()

    s = float(np.clip(strength, 0.0, 1.0))
    if s < 1.0:
        out = bpm + s * (out - bpm)

    return out.astype(float)

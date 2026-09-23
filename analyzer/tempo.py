"""Tempo curve calculation (規格 4)."""
from __future__ import annotations
import numpy as np

MIN_BPM = 25.0
MAX_BPM = 320.0


def compute_tempo_curve(beat_times, min_bpm=MIN_BPM, max_bpm=MAX_BPM):
    beat_times = np.asarray(beat_times, dtype=float)
    if len(beat_times) < 2:
        return np.array([120.0], dtype=float)

    intervals = np.diff(beat_times)
    intervals = np.clip(intervals, 1e-3, None)
    bpm = 60.0 / intervals
    bpm = np.clip(bpm, min_bpm, max_bpm)
    bpm = np.concatenate([bpm, [bpm[-1]]])
    return bpm.astype(float)


def global_bpm(bpm_curve):
    bpm_curve = np.asarray(bpm_curve, dtype=float)
    if bpm_curve.size == 0:
        return 120.0
    return float(np.median(bpm_curve))


def tempo_stats(bpm_curve):
    b = np.asarray(bpm_curve, dtype=float)
    if b.size == 0:
        return {"min": 0.0, "max": 0.0, "median": 0.0, "range": 0.0}
    return {
        "min": float(b.min()),
        "max": float(b.max()),
        "median": float(np.median(b)),
        "range": float(b.max() - b.min()),
    }

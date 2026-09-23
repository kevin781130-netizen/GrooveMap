"""Marker helpers (規格 6 / 8)."""
from __future__ import annotations
from typing import List
import numpy as np


def bar_positions(beat_times, downbeat_indices, beats_per_bar=4) -> List[dict]:
    beat_times = np.asarray(beat_times, dtype=float)
    rows = []
    for n, idx in enumerate(np.atleast_1d(downbeat_indices), start=1):
        i = int(idx)
        if i >= len(beat_times):
            continue
        rows.append({"bar": n, "beat_index": i, "time": float(beat_times[i])})
    return rows


def marker_labels(downbeat_indices) -> List[str]:
    return [f"Bar {n}" for n in range(1, len(np.atleast_1d(downbeat_indices)) + 1)]

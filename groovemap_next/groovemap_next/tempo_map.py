"""Convert beat timestamps into an exact per-beat tempo map."""
from __future__ import annotations
from bisect import bisect_right
from math import ceil
from statistics import median
from typing import Iterable
from .models import BeatAnalysis, TempoMap, TempoPoint

def _clean_times(values: Iterable[float], *, min_gap_sec: float = 0.06) -> list[float]:
    out: list[float] = []
    for value in sorted(float(v) for v in values if float(v) >= 0.0):
        if not out or value - out[-1] >= min_gap_sec:
            out.append(value)
    return out

def _nearest_index(values: list[float], target: float) -> int:
    pos = bisect_right(values, target)
    candidates = []
    if pos < len(values): candidates.append(pos)
    if pos > 0: candidates.append(pos - 1)
    return min(candidates, key=lambda i: abs(values[i] - target))

def _repair_missing_beats(beats: list[float]) -> list[float]:
    """Fill only obvious isolated 2x/3x gaps; never force global half/double tempo."""
    if len(beats) < 5:
        return beats
    intervals = [b - a for a, b in zip(beats, beats[1:])]
    med = median(intervals)
    if med <= 0:
        return beats
    repaired = [beats[0]]
    for left, right in zip(beats, beats[1:]):
        gap = right - left
        ratio = gap / med
        for div in (2, 3):
            if abs(ratio - div) <= 0.10 * div:
                step = gap / div
                repaired.extend(left + step * n for n in range(1, div))
                break
        repaired.append(right)
    return repaired

def build_tempo_map(
    analysis: BeatAnalysis, *, ppq: int = 960, beats_per_bar: int = 4,
    repair_missing_beats: bool = True,
) -> TempoMap:
    beats = _clean_times(analysis.beats_sec)
    downbeats = _clean_times(analysis.downbeats_sec)
    if repair_missing_beats:
        beats = _repair_missing_beats(beats)
    if len(beats) < 2:
        raise ValueError("need at least two detected beats to build a tempo map")

    origin_idx = 0
    if downbeats:
        idx = _nearest_index(beats, downbeats[0])
        typical = median([b - a for a, b in zip(beats, beats[1:])])
        if abs(beats[idx] - downbeats[0]) <= max(0.12, typical * 0.35):
            origin_idx = idx

    points: list[TempoPoint] = []
    for i, (left, right) in enumerate(zip(beats, beats[1:])):
        interval = right - left
        if interval <= 0:
            continue
        bpm = 60.0 / interval
        if 20.0 <= bpm <= 400.0:
            points.append(TempoPoint(i - origin_idx, left, bpm))
    if not points:
        raise ValueError("no valid tempo intervals were produced")

    return TempoMap(
        beats_sec=tuple(beats), downbeats_sec=tuple(downbeats),
        tempo_points=tuple(points), origin_sec=beats[origin_idx],
        origin_beat_index=origin_idx, ppq=ppq, beats_per_bar=beats_per_bar,
    )

def seconds_to_beat_position(tempo_map: TempoMap, time_sec: float) -> float:
    beats = tempo_map.beats_sec
    origin = tempo_map.origin_beat_index
    if len(beats) < 2:
        raise ValueError("tempo map must contain at least two beats")
    if time_sec <= beats[0]:
        interval = beats[1] - beats[0]
        return -origin + (time_sec - beats[0]) / interval
    if time_sec >= beats[-1]:
        interval = beats[-1] - beats[-2]
        return (len(beats) - 1 - origin) + (time_sec - beats[-1]) / interval
    i = bisect_right(beats, time_sec) - 1
    interval = beats[i + 1] - beats[i]
    return (i - origin) + (time_sec - beats[i]) / interval

def seconds_to_ticks(tempo_map: TempoMap, time_sec: float) -> int:
    return round(seconds_to_beat_position(tempo_map, time_sec) * tempo_map.ppq)

def choose_tick_shift(tempo_map: TempoMap, earliest_time_sec: float = 0.0) -> int:
    """Whole-bar pre-roll shift so audio material before origin remains non-negative."""
    raw_tick = seconds_to_ticks(tempo_map, earliest_time_sec)
    bar_ticks = tempo_map.ppq * tempo_map.beats_per_bar
    if raw_tick >= 0:
        return bar_ticks
    return (ceil((-raw_tick) / bar_ticks) + 1) * bar_ticks

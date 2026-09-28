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
    candidates: list[int] = []
    if pos < len(values):
        candidates.append(pos)
    if pos > 0:
        candidates.append(pos - 1)
    return min(candidates, key=lambda i: abs(values[i] - target))

def _repair_missing_beats(beats: list[float]) -> list[float]:
    """Fill only an *isolated* obvious 2x/3x gap.

    A candidate is repairable only when both immediate neighboring intervals
    agree on the local beat period. This avoids converting a legitimate slower
    section into the preceding faster tempo.
    """
    if len(beats) < 5:
        return beats

    intervals = [b - a for a, b in zip(beats, beats[1:])]
    repaired = [beats[0]]

    for i, (left, right) in enumerate(zip(beats, beats[1:])):
        gap = right - left
        split = 1

        if 0 < i < len(intervals) - 1:
            prev_gap = intervals[i - 1]
            next_gap = intervals[i + 1]
            local = median((prev_gap, next_gap))
            neighbors_agree = (
                local > 0
                and abs(prev_gap - local) <= 0.20 * local
                and abs(next_gap - local) <= 0.20 * local
            )
            if neighbors_agree:
                for div in (2, 3):
                    candidate = gap / div
                    if abs(candidate - local) <= 0.12 * local:
                        split = div
                        break

        if split > 1:
            step = gap / split
            repaired.extend(left + step * n for n in range(1, split))
        repaired.append(right)

    return repaired

def build_tempo_map(
    analysis: BeatAnalysis,
    *,
    ppq: int = 960,
    beats_per_bar: int = 4,
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
            raise ValueError(f"non-positive beat interval at index {i}: {interval}")
        bpm = 60.0 / interval
        if not 20.0 <= bpm <= 400.0:
            raise ValueError(
                f"beat interval {i} implies {bpm:.3f} BPM; refusing to export "
                "a partial tempo map because that would break audio/MIDI alignment"
            )
        points.append(TempoPoint(i - origin_idx, left, bpm))

    return TempoMap(
        beats_sec=tuple(beats),
        downbeats_sec=tuple(downbeats),
        tempo_points=tuple(points),
        origin_sec=beats[origin_idx],
        origin_beat_index=origin_idx,
        ppq=ppq,
        beats_per_bar=beats_per_bar,
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

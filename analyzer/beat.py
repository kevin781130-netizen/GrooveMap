"""Beat detection (規格 3.3)."""
from __future__ import annotations
import numpy as np
import librosa


def detect_beats(y, sr, hop_length=512, start_bpm=120.0, tightness=100.0, refine=True):
    if y.ndim > 1:
        y = np.mean(y, axis=0)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length, aggregate=np.median)

    try:
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sr, hop_length=hop_length,
            start_bpm=float(start_bpm), tightness=float(tightness),
            trim=False, units="frames",
        )
    except TypeError:
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sr, hop_length=hop_length,
            start_bpm=float(start_bpm), trim=False, units="frames",
        )

    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)

    if refine and len(beat_times) >= 4:
        beat_times = _refine_to_onsets(beat_times, onset_env, sr, hop_length)

    if len(beat_times) > 1:
        for i in range(1, len(beat_times)):
            if beat_times[i] <= beat_times[i - 1]:
                beat_times[i] = beat_times[i - 1] + 1e-3

    confidences = _beat_confidences(beat_times, onset_env, sr, hop_length)

    bpm = float(np.atleast_1d(tempo)[0])
    return np.asarray(beat_times, dtype=float), bpm, onset_env, hop_length, confidences


def _beat_confidences(beat_times, onset_env, sr, hop_length, search_ratio=0.18):
    """每一拍的偵測信心分數（0~1）：該拍附近 onset 強度峰值相對全曲 90th
    百分位數的比值。峰值越接近或超過全曲典型強拍，信心越高；模糊/若隱若現
    的拍子信心低，Tempo Curve Layer 縮減時不會被選為 control point。"""
    n_beats = len(beat_times)
    if n_beats == 0 or onset_env.size == 0:
        return np.zeros(n_beats, dtype=float)

    frame_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=hop_length)
    intervals = np.diff(beat_times) if n_beats > 1 else np.array([0.5])
    med = float(np.median(intervals)) if intervals.size else 0.5
    win = max(med * search_ratio, 0.02)

    global_ref = float(np.percentile(onset_env, 90)) if onset_env.size else 1.0
    global_ref = max(global_ref, 1e-9)

    n_frames = len(onset_env)
    conf = np.zeros(n_beats, dtype=float)
    for i, t in enumerate(beat_times):
        a = int(np.searchsorted(frame_times, t - win))
        b = int(np.searchsorted(frame_times, t + win))
        a = max(0, min(a, n_frames - 1))
        b = max(a + 1, min(b, n_frames))
        seg = onset_env[a:b]
        peak = float(seg.max()) if seg.size else 0.0
        conf[i] = float(np.clip(peak / global_ref, 0.0, 1.0))
    return conf


def _refine_to_onsets(beat_times, onset_env, sr, hop_length, search_ratio=0.18):
    intervals = np.diff(beat_times)
    if len(intervals) == 0:
        return beat_times
    med = float(np.median(intervals))
    win = max(med * search_ratio, 0.02)

    frame_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=hop_length)
    refined = beat_times.copy()
    n = len(onset_env)

    for i, t in enumerate(beat_times):
        a = int(np.searchsorted(frame_times, t - win))
        b = int(np.searchsorted(frame_times, t + win))
        a = max(0, min(a, n - 1))
        b = max(a + 1, min(b, n))
        if b - a < 2:
            continue
        seg = onset_env[a:b]
        if not np.any(seg > 0):
            continue
        peak = a + int(np.argmax(seg))
        refined[i] = frame_times[peak]

    return refined


def beat_intervals(beat_times):
    return np.diff(np.asarray(beat_times, dtype=float))

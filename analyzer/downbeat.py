"""Downbeat detection (規格 3.4)."""
from __future__ import annotations
import numpy as np
import librosa


def detect_downbeats(y, sr, beat_times, beats_per_bar=4, hop_length=512, n_fft=2048):
    beat_times = np.asarray(beat_times, dtype=float)
    n_beats = len(beat_times)

    if n_beats < beats_per_bar * 2:
        return np.arange(0, n_beats, beats_per_bar, dtype=int)

    if y.ndim > 1:
        y = np.mean(y, axis=0)

    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band = (freqs >= 35) & (freqs <= 160)
    low = S[band].sum(axis=0)

    frame_times = librosa.frames_to_time(np.arange(len(low)), sr=sr, hop_length=hop_length)
    n_frames = len(low)

    beat_energy = np.zeros(n_beats, dtype=float)
    for i, t in enumerate(beat_times):
        a = int(np.searchsorted(frame_times, t - 0.05))
        b = int(np.searchsorted(frame_times, t + 0.12))
        a = max(0, min(a, n_frames - 1))
        b = max(a + 1, min(b, n_frames))
        beat_energy[i] = float(low[a:b].max())

    med = float(np.median(beat_energy))
    if med > 1e-9:
        beat_energy = beat_energy / med

    best_phase = 0
    best_score = -np.inf
    for p in range(beats_per_bar):
        idx = np.arange(p, n_beats, beats_per_bar)
        if len(idx) == 0:
            continue
        score = float(np.mean(beat_energy[idx]))
        score *= min(1.0, len(idx) / 4.0)
        if score > best_score:
            best_score = score
            best_phase = p

    return np.arange(best_phase, n_beats, beats_per_bar, dtype=int)

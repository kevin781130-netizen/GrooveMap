"""Independent clean-room drum-stem onset transcriber.

No Magenta, DrumScript or Basic Pitch source is reused. It detects coarse GM
families from an isolated SUNO drums stem: kick 36, snare 38, closed hat 42.
Event timestamps remain in seconds until the variable tempo map is known.
"""
from __future__ import annotations
from pathlib import Path
import struct
import numpy as np
from .models import DrumEvent

_PCM_SUBFORMAT_GUID = bytes.fromhex("0100000000001000800000aa00389b71")

def _decode_pcm(raw: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        x = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        return (x - 128.0) / 128.0
    if sample_width == 2:
        usable = len(raw) - (len(raw) % 2)
        return np.frombuffer(raw[:usable], dtype="<i2").astype(np.float32) / 32768.0
    if sample_width == 3:
        b = np.frombuffer(raw, dtype=np.uint8)
        b = b[: len(b) - (len(b) % 3)]
        if b.size == 0:
            return np.empty(0, dtype=np.float32)
        t = b.reshape(-1, 3).astype(np.int32)
        x = t[:, 0] | (t[:, 1] << 8) | (t[:, 2] << 16)
        x = np.where(x & 0x800000, x - 0x1000000, x)
        return x.astype(np.float32) / 8388608.0
    if sample_width == 4:
        usable = len(raw) - (len(raw) % 4)
        return np.frombuffer(raw[:usable], dtype="<i4").astype(np.float32) / 2147483648.0
    raise ValueError(f"unsupported PCM sample width: {sample_width}")

def _read_pcm_wav(path: str | Path) -> tuple[bytes, int, int, int]:
    """Read RIFF/WAVE PCM including WAVE_FORMAT_EXTENSIBLE on Python 3.11."""
    data = Path(path).read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("expected little-endian RIFF/WAVE file")

    fmt: bytes | None = None
    pcm: bytes | None = None
    pos = 12

    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
        start = pos + 8
        end = start + chunk_size
        if end > len(data):
            raise ValueError(f"truncated WAV chunk {chunk_id!r}")
        chunk = data[start:end]
        if chunk_id == b"fmt ":
            fmt = chunk
        elif chunk_id == b"data":
            pcm = chunk
        pos = end + (chunk_size & 1)

    if fmt is None or len(fmt) < 16:
        raise ValueError("WAV fmt chunk missing or too short")
    if pcm is None:
        raise ValueError("WAV data chunk missing")

    format_tag, channels, sample_rate, _, block_align, bits = struct.unpack_from(
        "<HHIIHH", fmt, 0
    )
    if channels < 1 or sample_rate < 1:
        raise ValueError("invalid WAV channel count or sample rate")

    if format_tag == 0xFFFE:
        if len(fmt) < 40:
            raise ValueError("truncated WAVE_FORMAT_EXTENSIBLE fmt chunk")
        cb_size = struct.unpack_from("<H", fmt, 16)[0]
        subformat = fmt[24:40]
        if cb_size < 22 or subformat != _PCM_SUBFORMAT_GUID:
            raise ValueError("only PCM WAVE_FORMAT_EXTENSIBLE is supported")
    elif format_tag != 0x0001:
        raise ValueError(f"unsupported WAV format tag: {format_tag}")

    if bits not in (8, 16, 24, 32):
        raise ValueError(f"unsupported PCM bit depth: {bits}")
    sample_width = (bits + 7) // 8
    expected_align = channels * sample_width
    if block_align != expected_align:
        raise ValueError(
            f"unsupported WAV block alignment: {block_align} (expected {expected_align})"
        )
    return pcm, int(channels), int(sample_rate), sample_width

def load_wav_mono(path: str | Path) -> tuple[np.ndarray, int]:
    raw, channels, sr, width = _read_pcm_wav(path)
    signal = _decode_pcm(raw, width)
    if channels > 1:
        usable = len(signal) - (len(signal) % channels)
        signal = signal[:usable].reshape(-1, channels).mean(axis=1)
    return np.asarray(signal, dtype=np.float32), sr

def _adaptive_z(score: np.ndarray, window_frames: int) -> np.ndarray:
    if score.size == 0:
        return score
    n = max(1, min(int(window_frames), len(score)))
    kernel = np.ones(n, dtype=np.float32) / n
    baseline = np.convolve(score, kernel, mode="same")
    deviation = np.convolve(np.abs(score - baseline), kernel, mode="same")
    return (score - baseline) / (deviation + 1e-8)

def _pick_peaks(z: np.ndarray, *, threshold: float, min_gap_frames: int) -> list[int]:
    n = len(z)
    if n == 0:
        return []

    candidates: list[int] = []
    for i in range(n):
        left_ok = i == 0 or z[i] >= z[i - 1]
        right_ok = i == n - 1 or z[i] > z[i + 1]
        if z[i] >= threshold and left_ok and right_ok:
            candidates.append(i)

    chosen: list[int] = []
    for idx in sorted(candidates, key=lambda i: float(z[i]), reverse=True):
        if all(abs(idx - prev) >= min_gap_frames for prev in chosen):
            chosen.append(idx)
    return sorted(chosen)

def _velocity(z: float, threshold: float) -> int:
    strength = max(0.0, float(z) - threshold)
    value = 28.0 + 99.0 * (1.0 - np.exp(-strength / 3.0))
    return int(np.clip(round(value), 1, 127))

def transcribe_drum_stem(wav_path: str | Path, *, sensitivity: float = 1.0) -> list[DrumEvent]:
    signal, sr = load_wav_mono(wav_path)
    if signal.size < sr // 4:
        return []

    frame_size = 2048 if sr >= 32000 else 1024
    hop = max(1, round(sr * 0.010))
    if signal.size < frame_size:
        signal = np.pad(signal, (0, frame_size - signal.size))

    window = np.hanning(frame_size).astype(np.float32)
    freqs = np.fft.rfftfreq(frame_size, d=1.0 / sr)
    masks = [
        (freqs >= 35.0) & (freqs < 180.0),
        (freqs >= 180.0) & (freqs < 3500.0),
        (freqs >= 3500.0) & (freqs < min(16000.0, sr / 2.0)),
    ]

    frame_count = 1 + (len(signal) - frame_size) // hop
    scores = [np.zeros(frame_count, dtype=np.float32) for _ in range(3)]
    previous = np.zeros(frame_size // 2 + 1, dtype=np.float32)

    for i in range(frame_count):
        start = i * hop
        mag = np.abs(
            np.fft.rfft(signal[start:start + frame_size] * window)
        ).astype(np.float32)
        flux = np.maximum(mag - previous, 0.0)
        for j, mask in enumerate(masks):
            scores[j][i] = float(flux[mask].mean()) if mask.any() else 0.0
        previous = mag

    low, mid, high = scores
    for score in scores:
        scale = float(np.percentile(score, 95)) if score.size else 0.0
        if scale > 1e-9:
            score /= scale

    local_window = max(5, round(0.75 / (hop / sr)))
    z_low, z_mid, z_high = (_adaptive_z(s, local_window) for s in scores)
    sens = max(0.5, min(2.0, float(sensitivity)))
    kick_th, snare_th, hat_th = 2.6 / sens, 2.8 / sens, 2.4 / sens

    kick_idx = _pick_peaks(
        z_low, threshold=kick_th, min_gap_frames=max(2, round(0.045 * sr / hop))
    )
    snare_idx = _pick_peaks(
        z_mid, threshold=snare_th, min_gap_frames=max(2, round(0.050 * sr / hop))
    )
    hat_idx = _pick_peaks(
        z_high, threshold=hat_th, min_gap_frames=max(1, round(0.025 * sr / hop))
    )

    events: list[DrumEvent] = []
    for i in kick_idx:
        if low[i] >= 0.25 * max(mid[i], high[i], 1e-6):
            events.append(
                DrumEvent(max(0.0, i * hop / sr), 36, _velocity(z_low[i], kick_th), "kick")
            )
    for i in snare_idx:
        if high[i] <= 2.2 * max(mid[i], 1e-6):
            events.append(
                DrumEvent(max(0.0, i * hop / sr), 38, _velocity(z_mid[i], snare_th), "snare")
            )
    for i in hat_idx:
        near_snare = any(abs(i - s) <= 2 for s in snare_idx)
        if not near_snare or high[i] >= 1.15 * max(mid[i], 1e-6):
            events.append(
                DrumEvent(max(0.0, i * hop / sr), 42, _velocity(z_high[i], hat_th), "closed_hat")
            )

    return sorted(events, key=lambda e: (e.time_sec, e.note))

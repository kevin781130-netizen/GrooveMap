"""Audio loading & preprocessing (規格 3.1)."""
from __future__ import annotations
import os
import numpy as np

TARGET_SR = 44100
SUPPORTED_EXT = {".wav", ".aif", ".aiff", ".aifc", ".flac", ".mp3", ".ogg", ".m4a"}


def load_audio(path: str, target_sr: int = TARGET_SR, mono: bool = True):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"找不到音檔: {path}")

    y = None
    sr = target_sr
    try:
        import soundfile as sf
        data, sr = sf.read(path, always_2d=True, dtype="float32")
        y = data.T
    except Exception:
        y = None

    if y is None:
        import librosa
        raw, sr = librosa.load(path, sr=None, mono=False)
        y = np.atleast_2d(raw).astype(np.float32)

    if sr != target_sr:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr, res_type="soxr_hq")
        sr = target_sr

    if mono:
        if y.ndim == 2:
            y = np.mean(y, axis=0)
        y = np.ascontiguousarray(y, dtype=np.float32)

    return y.astype(np.float32), int(sr)


def normalize(y: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    y = np.asarray(y, dtype=np.float32)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak < 1e-9:
        return y
    target = 10.0 ** (peak_db / 20.0)
    return (y / peak * target).astype(np.float32)


def audio_info(path: str) -> dict:
    import soundfile as sf
    info = sf.info(path)
    return {
        "samplerate": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "duration": info.frames / float(info.samplerate),
        "format": info.format,
    }

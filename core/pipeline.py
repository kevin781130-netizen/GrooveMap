"""End-to-end analysis pipeline (規格 2)."""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
import numpy as np

from audio.loader import load_audio, normalize
from analyzer.beat import detect_beats
from analyzer.downbeat import detect_downbeats
from analyzer.tempo import compute_tempo_curve, global_bpm
from processor.smoother import smooth_tempo

log = logging.getLogger(__name__)


class Cancelled(Exception):
    """使用者中止分析。"""


@dataclass
class AnalysisResult:
    path: str = ""
    duration: float = 0.0
    sr: int = 44100
    hop_length: int = 512
    beats_per_bar: int = 4

    beat_times: np.ndarray = field(default_factory=lambda: np.zeros(0))
    bpm_raw: np.ndarray = field(default_factory=lambda: np.zeros(0))
    bpm_smooth: np.ndarray = field(default_factory=lambda: np.zeros(0))
    downbeats: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))

    global_bpm: float = 0.0
    used_demucs: bool = False

    @property
    def beat_count(self) -> int:
        return int(len(self.beat_times))

    @property
    def bar_count(self) -> int:
        return int(len(self.downbeats))

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    def summary(self) -> dict:
        return {
            "檔案": self.filename,
            "長度": f"{self.duration:.2f} s",
            "整體 BPM": round(self.global_bpm, 2),
            "Beat 數": self.beat_count,
            "小節數": self.bar_count,
            "拍號": f"{self.beats_per_bar}/4",
            "Demucs": "ON" if self.used_demucs else "OFF",
        }


DEFAULTS = dict(
    sr=44100, hop_length=512, start_bpm=120.0, tightness=100.0,
    beats_per_bar=4, smooth_window=5, smooth_strength=0.6,
    smooth_method="median+mean", use_demucs=False, device=None, peak_db=-1.0,
)


class Pipeline:
    def __init__(self, options=None):
        self.opts = dict(DEFAULTS)
        if options:
            self.opts.update({k: v for k, v in options.items() if v is not None})

    def run(self, path, progress=None, cancel=None) -> AnalysisResult:
        o = self.opts

        def report(p, msg):
            if progress:
                progress(float(p), msg)

        def check():
            if cancel and cancel():
                raise Cancelled()

        report(0.01, "讀取音檔中…")
        y, sr = load_audio(path, target_sr=o["sr"], mono=True)
        y = normalize(y, o["peak_db"])
        duration = len(y) / float(sr)
        check()

        used_demucs = False
        y_analysis = y

        if o["use_demucs"]:
            report(0.08, "Demucs 鼓軌分離中…")
            try:
                from audio.demix import separate_drums
                y_drums, sr_d = separate_drums(path, device=o["device"])
                if sr_d != sr:
                    import librosa
                    y_drums = librosa.resample(y_drums, orig_sr=sr_d, target_sr=sr)
                y_analysis = normalize(y_drums, o["peak_db"])
                used_demucs = True
            except Exception as exc:
                log.warning("Demucs 失敗 (%s)，改用全混音分析", exc)
                y_analysis = y
        check()

        report(0.28, "Beat Detection…")
        beat_times, bpm_hint, _onset, hop = detect_beats(
            y_analysis, sr, hop_length=o["hop_length"],
            start_bpm=o["start_bpm"], tightness=o["tightness"], refine=True)

        if len(beat_times) < 4:
            raise RuntimeError("偵測到的拍點太少，請調整起始 BPM 後重試。")

        check()

        report(0.58, "Tempo Curve 計算中…")
        bpm_raw = compute_tempo_curve(beat_times)

        report(0.68, "Tempo Smoothing…")
        bpm_smooth = smooth_tempo(bpm_raw, window=o["smooth_window"],
                                  method=o["smooth_method"],
                                  strength=o["smooth_strength"])
        check()

        report(0.82, "Downbeat Detection…")
        downbeats = detect_downbeats(y_analysis, sr, beat_times,
                                     beats_per_bar=o["beats_per_bar"],
                                     hop_length=o["hop_length"])
        check()

        report(0.94, "整理結果…")
        result = AnalysisResult(
            path=path, duration=duration, sr=sr, hop_length=hop,
            beats_per_bar=o["beats_per_bar"],
            beat_times=np.asarray(beat_times, dtype=float),
            bpm_raw=np.asarray(bpm_raw, dtype=float),
            bpm_smooth=np.asarray(bpm_smooth, dtype=float),
            downbeats=np.asarray(downbeats, dtype=int),
            global_bpm=global_bpm(bpm_smooth),
            used_demucs=used_demucs,
        )

        report(1.0, "分析完成 ✓")
        return result

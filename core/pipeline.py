"""End-to-end analysis pipeline (規格 2)."""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np

from audio.loader import load_audio, normalize
from analyzer.beat import detect_beats
from analyzer.downbeat import detect_downbeats
from analyzer.tempo import compute_tempo_curve, global_bpm
from processor.smoother import smooth_tempo
from core.tempo_events import build_tempo_events
from core.tempo_curve import (
    reduce_tempo_curve_with_density, TempoControlPoint, AccuracyReport, DEFAULT_DENSITY,
)

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
    beat_confidence: np.ndarray = field(default_factory=lambda: np.zeros(0))
    downbeats: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))

    # Tempo Curve Layer（規格 P3）：縮減後的 Cubase Tempo Track 控制點，
    # 與對應的 Accuracy Validation 報告。Beat Position Layer（beat_times/
    # bpm_raw）才是 Click/Marker 用的 Ground Truth，不受這裡影響。
    tempo_control_points: List[TempoControlPoint] = field(default_factory=list)
    accuracy_report: Optional[AccuracyReport] = None
    tempo_density: str = DEFAULT_DENSITY
    max_tempo_nodes: Optional[int] = None

    global_bpm: float = 0.0
    used_demucs: bool = False
    demucs_warning: str = ""

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
        s = {
            "檔案": self.filename,
            "長度": f"{self.duration:.2f} s",
            "整體 BPM": round(self.global_bpm, 2),
            "Beat 數": self.beat_count,
            "小節數": self.bar_count,
            "拍號": f"{self.beats_per_bar}/4",
            "Demucs": "ON" if self.used_demucs else "OFF",
        }
        if self.accuracy_report is not None:
            s.update(self.accuracy_report.summary())
        return s


DEFAULTS = dict(
    sr=44100, hop_length=512, start_bpm=120.0, tightness=100.0,
    beats_per_bar=4, smooth_window=5, smooth_strength=0.6,
    smooth_method="median+mean", use_demucs=False, device=None, peak_db=-1.0,
    tempo_density=DEFAULT_DENSITY, max_tempo_nodes=None,
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
        demucs_warning = ""
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
                demucs_warning = f"Demucs 分離失敗，已改用原始混音進行分析（原因：{exc}）"
                log.warning(demucs_warning)
                report(0.08, "Demucs 失敗，改用原始混音…")
                y_analysis = y
        check()

        report(0.28, "Beat Detection…")
        beat_times, bpm_hint, _onset, hop, beat_confidence = detect_beats(
            y_analysis, sr, hop_length=o["hop_length"],
            start_bpm=o["start_bpm"], tightness=o["tightness"], refine=True)

        if len(beat_times) < 4:
            raise RuntimeError("偵測到的拍點太少，請調整起始 BPM 後重試。")

        check()

        # bpm_raw = Ground Truth，逐拍區間直接反推，不經過任何平滑。
        # 匯出（MIDI/SMT）與 Accuracy Validation 一律以這份資料為準。
        report(0.58, "Tempo Curve 計算中…")
        bpm_raw = compute_tempo_curve(beat_times)

        # bpm_smooth 僅保留給人看的參考用途（例如未來的曲線視覺化），
        # 不再進入任何匯出路徑，避免平滑犧牲 Beat Sync 準確度。
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

        report(0.90, "Tempo Curve Layer 縮減 + Accuracy Validation…")
        from exporter.midi import PPQ as MIDI_PPQ
        beat_position_events = build_tempo_events(beat_times, bpm_raw)
        tempo_control_points, accuracy_report = reduce_tempo_curve_with_density(
            beat_position_events, confidences=beat_confidence, ppq=MIDI_PPQ,
            density=o["tempo_density"], max_nodes=o["max_tempo_nodes"])
        check()

        report(0.94, "整理結果…")
        result = AnalysisResult(
            path=path, duration=duration, sr=sr, hop_length=hop,
            beats_per_bar=o["beats_per_bar"],
            beat_times=np.asarray(beat_times, dtype=float),
            bpm_raw=np.asarray(bpm_raw, dtype=float),
            bpm_smooth=np.asarray(bpm_smooth, dtype=float),
            beat_confidence=np.asarray(beat_confidence, dtype=float),
            downbeats=np.asarray(downbeats, dtype=int),
            tempo_control_points=tempo_control_points,
            accuracy_report=accuracy_report,
            tempo_density=o["tempo_density"],
            max_tempo_nodes=o["max_tempo_nodes"],
            global_bpm=global_bpm(bpm_raw),
            used_demucs=used_demucs,
            demucs_warning=demucs_warning,
        )

        report(1.0, "分析完成 ✓")
        return result

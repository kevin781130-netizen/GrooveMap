"""Tempo Curve Layer 縮減與 Accuracy Validation（規格 P3 — TEMPO MAP ACCURACY FIRST）。

核心原則：Beat Detection 結果是 Ground Truth，準確度優先於曲線好不好看。

兩層資料分開：
  - Beat Position Layer（core/tempo_events.py 的 TempoEvent list，來自
    result.beat_times + result.bpm_raw）：Click / Marker / 小節位置的唯一
    依據，任何 Tempo Curve 縮減都不能反過來更動這一層。
  - Tempo Curve Layer（本模組的 TempoControlPoint list）：只決定 Cubase
    Tempo Track 要放幾個控制點。控制點數量可以遠少於拍數，但每縮減一次
    density，就要用 Accuracy Validation 檢查：如果 Click 軌沿用「每拍固定
    一格 tick」的網格（見 exporter/midi.py），套用這個縮減後的 Tempo Curve
    重建出來的每一拍『預測時間』，跟原始 beat_times 差多少（Beat Error, ms）。
    超過門檻就自動把誤差最大處附近的拍子升格回控制點，直到達標或退回全密度
    （每拍一個控制點，此時誤差趨近浮點捨入等級）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from core.tempo_events import TempoEvent

log = logging.getLogger(__name__)

TARGET_AVG_MS = 10.0   # 一般 Live Recording 可接受的平均誤差
GOOD_AVG_MS = 5.0        # 良好
MAX_ERROR_MS = 20.0      # 任何單拍誤差超過這個值就不能接受
MIN_CONFIDENCE = 0.35    # 低於此信心值的拍子不會被升格成 Tempo Control Point

# Adaptive Density Control（規格 P4）：Sparse/Balanced/Detailed 對應的
# (平均誤差門檻, 單拍誤差門檻, 最大節點數) 預設值。Balanced 是預設，
# 5 分鐘 Live 錄音（約 300~600 拍）在 max_nodes=100 的限制下仍要求
# avg <= 10ms；如果音檔真的太密集達不到，會如實回報 capped=True，
# 不會為了硬湊點數上限而假裝達標。
DENSITY_PRESETS = {
    "sparse":   dict(target_avg_ms=15.0, max_error_ms=30.0, max_nodes=40),
    "balanced": dict(target_avg_ms=10.0, max_error_ms=20.0, max_nodes=100),
    "detailed": dict(target_avg_ms=5.0,  max_error_ms=10.0, max_nodes=400),
}
DEFAULT_DENSITY = "balanced"


@dataclass
class TempoControlPoint:
    beat_index: int   # 對應 Beat Position Layer 的 index（0-based）
    time: float         # 秒（= 該拍的原始 ground-truth 時間，未被平滑過）
    bpm: float
    ramp: bool = False   # 目前一律 Jump（False）；Ramp 留給後續版本


@dataclass
class AccuracyReport:
    beat_errors_ms: List[float] = field(default_factory=list)
    avg_error_ms: float = 0.0
    max_error_ms: float = 0.0
    num_points: int = 0
    num_beats: int = 0
    capped: bool = False  # True = 因為撞到 max_nodes 上限而停止，門檻可能未達標

    @property
    def density_label(self) -> str:
        if self.num_beats == 0:
            return "N/A"
        ratio = self.num_points / self.num_beats
        if ratio <= 0.15:
            return "Low"
        if ratio <= 0.4:
            return "Medium"
        return "High"

    @property
    def quality_label(self) -> str:
        label = "良好" if self.avg_error_ms <= GOOD_AVG_MS else (
            "可接受" if self.avg_error_ms <= TARGET_AVG_MS else "不合格")
        if self.capped and self.avg_error_ms > TARGET_AVG_MS:
            label += "（受節點上限限制）"
        return label

    def summary(self) -> dict:
        return {
            "Average Beat Error": f"{self.avg_error_ms:.1f} ms",
            "Maximum Beat Error": f"{self.max_error_ms:.1f} ms",
            "Tempo Points": self.num_points,
            "Density": self.density_label,
            "Quality": self.quality_label,
        }


def _predict_beat_times(
    n_beats: int,
    control_points: Sequence[TempoControlPoint],
    ppq: int,
) -> np.ndarray:
    """假設 Click/Marker 用『每拍固定一格 tick』的網格（beat i -> tick i*ppq，
    相對於第一個控制點），Tempo Track 只在 control_points 的 tick 位置改變
    速度（Jump，維持到下一個控制點為止）。回傳這個假設下，每一拍會落在
    Cubase 時間軸上的『預測時間』，用來跟原始 beat_times 比對誤差。
    """
    if n_beats == 0 or not control_points:
        return np.zeros(n_beats)

    cps = sorted(control_points, key=lambda c: c.beat_index)
    cp_beat_idx = np.array([c.beat_index for c in cps], dtype=float)
    cp_ticks = cp_beat_idx * ppq
    cp_bpms = np.array([max(c.bpm, 1e-6) for c in cps], dtype=float)

    predicted = np.zeros(n_beats)
    predicted[cps[0].beat_index] = cps[0].time
    # 從第一個控制點往兩側各自積分（大多數情況下第一個控制點就是 beat 0）
    start_idx = cps[0].beat_index
    cur_time = cps[0].time
    cur_tick = cp_ticks[0]
    for i in range(start_idx + 1, n_beats):
        target_tick = i * ppq
        idx = int(np.searchsorted(cp_ticks, target_tick, side="left")) - 1
        idx = max(0, min(idx, len(cps) - 1))
        bpm = cp_bpms[idx]
        dt = (target_tick - cur_tick) * 60.0 / (bpm * ppq)
        cur_time += dt
        cur_tick = target_tick
        predicted[i] = cur_time

    # 若第一個控制點不是 beat 0（理論上不會發生，reduce_tempo_curve 保證
    # 一定包含 beat 0），往回補上前面幾拍避免陣列殘留 0
    for i in range(start_idx - 1, -1, -1):
        predicted[i] = predicted[i + 1]

    return predicted


def reduce_tempo_curve(
    events: Sequence[TempoEvent],
    confidences: Optional[Sequence[float]] = None,
    ppq: int = 960,
    target_avg_ms: float = TARGET_AVG_MS,
    max_error_ms: float = MAX_ERROR_MS,
    min_confidence: float = MIN_CONFIDENCE,
    max_nodes: Optional[int] = None,
) -> Tuple[List[TempoControlPoint], AccuracyReport]:
    """把 Beat Position Layer 的逐拍 TempoEvent 縮減成較少的 Tempo Control
    Point，並保證縮減後的曲線通過 Accuracy Validation（見模組 docstring）。

    演算法：
      1. 從只保留頭尾兩個控制點開始（等同先假設整段是穩定區域）。
      2. 每一輪找出目前預測誤差最大的拍子（= 局部 BPM variance 最大處），
         把離它最近、信心足夠、尚未被選中的拍子升格為新控制點。
      3. 重新驗證（Beat Reconstruction Validation），直到平均/最大誤差都
         在門檻內。
      4. 如果設了 max_nodes，一旦節點數碰到上限就停止（不會為了硬湊點數
         上限而假裝達標——AccuracyReport.capped 會誠實標示還沒達標）；
         沒設 max_nodes 時，最壞情況會退回全密度（每拍一個控制點），
         保證誤差趨近於零。
    """
    n = len(events)
    if n == 0:
        raise ValueError("events 為空，無法縮減 tempo curve")

    if confidences is None:
        conf = np.ones(n, dtype=float)
    else:
        conf = np.asarray(confidences, dtype=float)
        if len(conf) != n:
            raise ValueError(f"confidences 長度 ({len(conf)}) 與 events 長度 ({n}) 不一致")

    eligible = {i for i in range(n) if conf[i] >= min_confidence}
    eligible.add(0)
    eligible.add(n - 1)

    selected = sorted({0, n - 1})

    def _segment_average_bpms(idxs):
        """每個控制點的 BPM 用『它管轄的整段（到下一個控制點為止）剛好精確對上
        下一個控制點真實時間』反推的平均值，而不是該拍自己的瞬時 BPM——
        瞬時值只代表單拍區間，拿去代表一整段會讓誤差隨區間長度快速累積。"""
        times = [events[i].time for i in idxs]
        bpms = []
        for k, i in enumerate(idxs):
            if k == len(idxs) - 1:
                bpms.append(events[i].bpm)  # 最後一個控制點沒有下一段可平均，用瞬時值
                continue
            j = idxs[k + 1]
            span_beats = j - i
            span_time = times[k + 1] - times[k]
            bpms.append(60.0 * span_beats / span_time if span_time > 0 else events[i].bpm)
        return bpms

    def _build(idxs):
        bpms = _segment_average_bpms(idxs)
        cps = [
            TempoControlPoint(beat_index=i, time=float(events[i].time), bpm=float(b))
            for i, b in zip(idxs, bpms)
        ]
        predicted = _predict_beat_times(n, cps, ppq)
        actual = np.array([e.time for e in events], dtype=float)
        errors_ms = np.abs(predicted - actual) * 1000.0
        report = AccuracyReport(
            beat_errors_ms=errors_ms.tolist(),
            avg_error_ms=float(np.mean(errors_ms)),
            max_error_ms=float(np.max(errors_ms)),
            num_points=len(cps),
            num_beats=n,
        )
        return cps, report, errors_ms

    cps, report, errors_ms = _build(selected)

    guard = 0
    capped = False
    while (report.avg_error_ms > target_avg_ms or report.max_error_ms > max_error_ms) and guard < n:
        if max_nodes is not None and len(selected) >= max_nodes:
            capped = True
            break

        guard += 1
        worst_i = int(np.argmax(errors_ms))

        candidates = sorted(eligible - set(selected))
        if not candidates:
            # 合格拍子都用完了 → 只好連低信心的拍子也一起加入，
            # 最終保證能達到全密度（誤差趨近浮點捨入等級），除非撞到 max_nodes
            candidates = sorted(set(range(n)) - set(selected))
            if not candidates:
                break

        best = min(candidates, key=lambda i: abs(i - worst_i))
        selected = sorted(set(selected) | {best})
        cps, report, errors_ms = _build(selected)

    report.capped = capped

    log.info(
        "Tempo Curve 縮減完成：%d/%d 控制點（%s density%s），avg=%.1fms max=%.1fms",
        report.num_points, report.num_beats, report.density_label,
        "，撞到 max_nodes 上限" if capped else "",
        report.avg_error_ms, report.max_error_ms,
    )
    return cps, report


def reduce_tempo_curve_with_density(
    events: Sequence[TempoEvent],
    confidences: Optional[Sequence[float]] = None,
    ppq: int = 960,
    density: str = DEFAULT_DENSITY,
    max_nodes: Optional[int] = None,
    min_confidence: float = MIN_CONFIDENCE,
) -> Tuple[List[TempoControlPoint], AccuracyReport]:
    """Adaptive Density Control 的入口：用 Sparse/Balanced/Detailed 預設值
    呼叫 reduce_tempo_curve。max_nodes 有給的話覆蓋 preset 預設的節點上限
    （對應 GUI 的「Maximum Tempo Nodes」欄位）。
    """
    preset = dict(DENSITY_PRESETS.get(density, DENSITY_PRESETS[DEFAULT_DENSITY]))
    if max_nodes is not None:
        preset["max_nodes"] = max_nodes

    return reduce_tempo_curve(
        events,
        confidences=confidences,
        ppq=ppq,
        target_avg_ms=preset["target_avg_ms"],
        max_error_ms=preset["max_error_ms"],
        max_nodes=preset["max_nodes"],
        min_confidence=min_confidence,
    )

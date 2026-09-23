"""Beat Position Layer（規格 P3）— Click / Marker / Tempo Curve Layer 縮減
演算法唯一共用的 Ground Truth 資料來源。

TEMPO MAP ACCURACY FIRST：Beat Detection 結果是 Ground Truth，一律用逐拍
未經平滑的 beat_times / bpm_raw，不可被 processor/smoother.py 的任何平滑
結果（result.bpm_smooth）污染，也嚴禁使用 result.global_bpm（那只是給人
看的統計摘要，用 median 壓成一個數字）。這一層資料只會被拿去：
  1. 當作 Click / Marker / 小節位置（不可被更動）
  2. 餵給 core/tempo_curve.py 做 Tempo Curve Layer 縮減時的驗證基準
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class TempoEvent:
    beat_number: int  # 1-based，對應 GUI 的 #0001
    time: float        # 秒
    bpm: float


def build_tempo_events(beat_times: Sequence[float], bpm_curve: Sequence[float]) -> List[TempoEvent]:
    """把逐拍 beat_times + bpm_curve 轉成 TempoEvent list（1-based beat_number）。"""
    beat_times = np.asarray(beat_times, dtype=float)
    bpm_curve = np.asarray(bpm_curve, dtype=float)

    if len(beat_times) != len(bpm_curve):
        raise ValueError(
            f"beat_times 長度 ({len(beat_times)}) 與 bpm_curve 長度 ({len(bpm_curve)}) 不一致"
        )
    if len(beat_times) == 0:
        raise ValueError("beat_times 為空，無法建立 tempo events")

    return [
        TempoEvent(beat_number=i + 1, time=float(t), bpm=float(b))
        for i, (t, b) in enumerate(zip(beat_times, bpm_curve))
    ]


def from_result(result) -> List[TempoEvent]:
    """從 AnalysisResult 取得 Beat Position Layer（逐拍 Ground Truth）。
    一律用 result.bpm_raw（未平滑，等同每拍真實區間反推的瞬時 BPM），
    絕不使用 result.bpm_smooth 或 result.global_bpm。"""
    events = build_tempo_events(result.beat_times, result.bpm_raw)
    log.info("建立 %d 筆 Beat Position Layer events（Ground Truth，非平滑）", len(events))
    return events


def to_dicts(events: Sequence[TempoEvent]) -> List[dict]:
    """轉成 exporter/steinberg_smt.py 接受的 [{"time","bpm"}] 格式。"""
    return [{"time": e.time, "bpm": e.bpm} for e in events]

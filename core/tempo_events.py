"""Tempo Event 產生（規格 P2）— MIDI 與 Steinberg SMT exporter 唯一共用的資料來源。

嚴禁在匯出路徑上使用 AnalysisResult.global_bpm（那是給人看的統計摘要，
用 median 壓成一個數字），一律用逐拍的 beat_times / bpm_smooth，確保
匯出檔案跟 GUI 逐拍列表（#0001 1.792s 133.93 BPM ...）的數字完全一致。
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
    """從 AnalysisResult 取得逐拍 tempo events。一律用 result.bpm_smooth
    （GUI 顯示的同一份曲線），絕不使用 result.global_bpm。"""
    events = build_tempo_events(result.beat_times, result.bpm_smooth)
    log.info("建立 %d 筆 tempo events（逐拍，非 average）", len(events))
    return events


def to_dicts(events: Sequence[TempoEvent]) -> List[dict]:
    """轉成 exporter/steinberg_smt.py 接受的 [{"time","bpm"}] 格式。"""
    return [{"time": e.time, "bpm": e.bpm} for e in events]

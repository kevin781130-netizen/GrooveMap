"""Tempo Scaler（規格 P5）— Half / Normal / Double Tempo 的純數學公式。

scaled_bpm = original_bpm * multiplier

這裡只負責這個公式本身，給 GUI 顯示「Detected: 133.55 BPM → 選 Double
後會是 267.10 BPM」這種即時換算用。

倍率必須在 Beat Detection → Tempo Estimation → Human Tempo Decision 之後、
Tempo Reconstruction 之前套用，不能等到 Export 階段才乘倍——實際套用點
在 core/tempo_factor.py。那裡不是單純把這個公式套用到每一拍的 BPM，而是
連 Beat Timeline 本身的拍點密度都一起調整（Double 時內插新拍點、Half 時
合併拍點），因為如果曲子真的是雙倍/一半速度，實際鼓點數量也會跟著變，
不能只改 BPM 這個數字卻讓 Click 拍點數量不變。兩者在數學上是一致的：
對每個區間而言，scale_bpm(區間原始 bpm, multiplier) 恰好等於用新拍點
密度重新測量出的 bpm（详见 core/tempo_factor.py 的說明）。
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

VALID_MULTIPLIERS = (0.5, 1.0, 2.0)


def scale_bpm(original_bpm: float, multiplier: float) -> float:
    """scaled_bpm = original_bpm * multiplier"""
    if multiplier not in VALID_MULTIPLIERS:
        raise ValueError(f"multiplier 只支援 {VALID_MULTIPLIERS}，收到 {multiplier}")
    return float(original_bpm) * float(multiplier)


def scale_bpm_array(original_bpm: Sequence[float], multiplier: float) -> np.ndarray:
    if multiplier not in VALID_MULTIPLIERS:
        raise ValueError(f"multiplier 只支援 {VALID_MULTIPLIERS}，收到 {multiplier}")
    return np.asarray(original_bpm, dtype=float) * float(multiplier)


def label_for_multiplier(multiplier: float) -> str:
    return {0.5: "Half Time  x0.5", 1.0: "Normal  x1.0", 2.0: "Double Time  x2.0"}.get(
        multiplier, f"x{multiplier}")

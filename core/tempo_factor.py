"""Half / Double Tempo 人工切換（規格 P3 驗收項目 4）。

有些真人演奏的實際律動感是偵測結果的兩倍或一半（例如把八分音符誤判成
主拍、或整首歌其實是雙倍速的感覺）。這裡刻意做成「人工切換」而非自動
偵測——自動猜測 half/double 風險很高，猜錯比不猜更糟，交給使用者依耳朵
判斷後手動套用最安全。

套用後一律重新跑 Tempo Curve Layer 縮減與 Accuracy Validation，不沿用
套用前的控制點（beat 數量與信心分佈都變了，舊的驗證結果不再有效）。
"""
from __future__ import annotations

import copy
import logging

import numpy as np

from analyzer.tempo import compute_tempo_curve, global_bpm as _global_bpm
from processor.tempo_scaler import VALID_MULTIPLIERS as VALID_FACTORS

log = logging.getLogger(__name__)


def apply_tempo_factor(result, factor: float):
    """回傳套用 factor 後的新 AnalysisResult（不修改傳入的 result）。

    factor=2.0（Double）：在每兩個原始拍點之間內插一個新拍點，BPM 曲線
      用新的拍點間隔重新反推（而不是單純乘 2，避免忽略拍點本身可能不等距）。
    factor=0.5（Half）：只保留偶數 index 的原始拍點（每兩拍合併成一拍）。
    factor=1.0：原樣回傳（deep copy）。
    """
    if factor not in VALID_FACTORS:
        raise ValueError(f"factor 只支援 {VALID_FACTORS}，收到 {factor}")

    new_result = copy.deepcopy(result)
    if factor == 1.0:
        return new_result

    beat_times = np.asarray(result.beat_times, dtype=float)
    confidence = np.asarray(result.beat_confidence, dtype=float)
    old_downbeats = np.asarray(result.downbeats, dtype=int)

    if len(beat_times) < 2:
        log.warning("beat_times 數量不足，無法套用 tempo factor=%s", factor)
        return new_result

    if factor == 2.0:
        mid_times = (beat_times[:-1] + beat_times[1:]) / 2.0
        new_times = np.empty(len(beat_times) * 2 - 1, dtype=float)
        new_times[0::2] = beat_times
        new_times[1::2] = mid_times

        new_conf = np.empty(len(new_times), dtype=float)
        new_conf[0::2] = confidence
        # 內插出來的拍點不是真實偵測結果，信心打折，避免優先被選為控制點
        new_conf[1::2] = confidence[:-1] * 0.8

        new_result.downbeats = old_downbeats * 2

    else:  # factor == 0.5
        new_times = beat_times[0::2]
        new_conf = confidence[0::2]
        kept = old_downbeats[old_downbeats % 2 == 0] // 2
        new_result.downbeats = kept

    new_bpm_raw = compute_tempo_curve(new_times)

    new_result.beat_times = new_times
    new_result.bpm_raw = np.asarray(new_bpm_raw, dtype=float)
    new_result.beat_confidence = new_conf
    new_result.bpm_smooth = new_result.bpm_raw.copy()  # 僅供顯示參考，不入匯出
    new_result.global_bpm = _global_bpm(new_result.bpm_raw)

    # beat 數量與信心分佈都變了，必須重新跑 Tempo Curve Layer 縮減 +
    # Accuracy Validation，不能沿用套用前的控制點。Anchor（如果有）會
    # 用 rebuild_for_result 自動依 Anchor.time 重新對應到新的 beat index。
    from core.tempo_curve import rebuild_for_result
    rebuild_for_result(new_result)
    return new_result

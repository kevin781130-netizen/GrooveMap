"""Human Anchor 系統（規格 P5）— Layer 2 Musical Alignment 的核心。

Anchor 是使用者指定「絕對正確」的少量拍點（例如 Bar 1 Beat 1、Bar 8
Beat 1...），Tempo Reconstruction（Layer 3）必須在 Anchor 的位置上精確
通過它們——Anchor 是 Hard Constraint：
  - 一定會被拉進 Tempo Curve Layer 的控制點集合（core/tempo_curve.py 的
    forced_indices），縮減演算法只會加點不會刪點，所以 Anchor 永遠不會
    被 density reduction 拿掉。
  - Anchor 對應的那一拍，beat_times 會直接改成 Anchor 的精確時間（視為
    比自動偵測更準確），這是唯一允許「修改」Beat Position Layer 的方式，
    而且只動 Anchor 指到的那一拍，不是整條平滑。

Anchor 同時定義了 Bar/Beat 編號的參照點：用兩個相鄰 Anchor 之間的拍子
數量反推中間每一拍的 Bar/Beat 編號與 downbeat 位置，比規格 P4「假設全曲
同一個 phase」的做法更能處理漏拍/多抓拍等異常情況。
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

log = logging.getLogger(__name__)

SNAP_RANGE_MS_DEFAULT = 80.0


@dataclass
class Anchor:
    time: float                            # 秒（已經過 snap，是最終採用的時間）
    bar: int                                 # 1-based
    beat: int                                # 1-based，1~beats_per_bar
    source: str = "manual"                   # 目前唯一來源
    confidence: float = 1.0
    clicked_time: Optional[float] = None     # 使用者原始點擊位置（snap 前，僅供 GUI 顯示）
    beat_index: Optional[int] = None         # 對應 beat_times 的 index，resolve 後才會填入


def find_nearest_transient(onset_env, sr, hop_length, time_sec, window_ms=SNAP_RANGE_MS_DEFAULT):
    """Snap to Transient：在 time_sec ± window_ms 範圍內，找 onset envelope
    最強的位置。onset_env 跟 analyzer/beat.py 用的是同一種資料
    （librosa.onset.onset_strength 的輸出）。找不到有效峰值時原樣回傳。
    """
    if onset_env is None or len(onset_env) == 0:
        return float(time_sec)

    import librosa

    frame_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=hop_length)
    win = max(window_ms / 1000.0, 0.001)
    n = len(onset_env)
    a = int(np.searchsorted(frame_times, time_sec - win))
    b = int(np.searchsorted(frame_times, time_sec + win))
    a = max(0, min(a, n - 1))
    b = max(a + 1, min(b, n))
    seg = onset_env[a:b]
    if seg.size == 0 or not np.any(seg > 0):
        return float(time_sec)
    peak = a + int(np.argmax(seg))
    return float(frame_times[peak])


def nearest_beat_index(beat_times, time_sec) -> int:
    beat_times = np.asarray(beat_times, dtype=float)
    if beat_times.size == 0:
        raise ValueError("beat_times 為空，無法對應 Anchor")
    return int(np.argmin(np.abs(beat_times - float(time_sec))))


def make_anchor(clicked_time, bar, beat, onset_env=None, sr=None, hop_length=None,
                 snap=True, snap_range_ms=SNAP_RANGE_MS_DEFAULT, confidence=1.0) -> Anchor:
    """建立一個 Anchor。snap=True 且提供 onset_env/sr/hop_length 時，會先
    做 Snap to Transient，Anchor.time 用 snap 後的位置；clicked_time
    保留使用者原始點擊值，供 GUI 顯示「Clicked / Snapped」對照。"""
    if snap and onset_env is not None and sr is not None and hop_length is not None:
        snapped = find_nearest_transient(onset_env, sr, hop_length, clicked_time, snap_range_ms)
    else:
        snapped = float(clicked_time)
    return Anchor(time=snapped, bar=int(bar), beat=int(beat), confidence=float(confidence),
                  clicked_time=float(clicked_time))


def resolve_anchors(anchors: Sequence[Anchor], beat_times) -> List[Anchor]:
    """把每個 Anchor 對應到 beat_times 裡最接近的 index，回傳補上
    beat_index 的新 Anchor list（不修改原本物件）。"""
    return [
        Anchor(time=a.time, bar=a.bar, beat=a.beat, source=a.source,
               confidence=a.confidence, clicked_time=a.clicked_time,
               beat_index=nearest_beat_index(beat_times, a.time))
        for a in anchors
    ]


def apply_anchors_to_beat_times(beat_times, resolved_anchors: Sequence[Anchor]):
    """Anchor 是 Hard Constraint：把 beat_times 裡每個 Anchor 對應到的那
    一拍，直接改成 Anchor 的精確時間。回傳修正後的副本，不修改原陣列。
    resolved_anchors 必須是已經跑過 resolve_anchors()、有 beat_index 的版本。
    """
    beat_times = np.asarray(beat_times, dtype=float).copy()
    for a in resolved_anchors:
        beat_times[a.beat_index] = a.time
    # 修正後必須維持嚴格遞增，否則後面的區間/tick 計算會出錯
    for i in range(1, len(beat_times)):
        if beat_times[i] <= beat_times[i - 1]:
            beat_times[i] = beat_times[i - 1] + 1e-3
    return beat_times


def derive_downbeats_from_anchors(n_beats: int, beats_per_bar: int, resolved_anchors: Sequence[Anchor]):
    """用 Anchor 反推每一拍的 (bar, beat) 編號，回傳 downbeats（bar 第一拍
    的 index 陣列），跟 analyzer/downbeat.py 的輸出格式相容。

    每一拍用「beat_index 距離最近的 Anchor」當基準反推絕對拍序號，這樣
    即使兩個 Anchor 之間的實際拍數跟理論值兜不起來（代表中間漏拍/多抓拍），
    也只會讓最鄰近的區段各自合理，不會讓整曲編號從某個 Anchor 之後全部
    錯位。沒有 Anchor 時回傳 None，呼叫端應該 fallback 回自動偵測的結果。
    """
    if n_beats == 0 or not resolved_anchors:
        return None

    sorted_anchors = sorted(resolved_anchors, key=lambda a: a.beat_index)
    anchor_indices = np.array([a.beat_index for a in sorted_anchors])

    ordinals = np.zeros(n_beats, dtype=int)
    for i in range(n_beats):
        pos = int(np.searchsorted(anchor_indices, i))
        candidates = []
        if pos > 0:
            candidates.append(sorted_anchors[pos - 1])
        if pos < len(sorted_anchors):
            candidates.append(sorted_anchors[pos])
        nearest = min(candidates, key=lambda a: abs(a.beat_index - i))
        base_ordinal = (nearest.bar - 1) * beats_per_bar + (nearest.beat - 1)
        ordinals[i] = base_ordinal + (i - nearest.beat_index)

    phases = np.mod(ordinals, beats_per_bar)
    return np.where(phases == 0)[0].astype(int)


def apply_anchors(result, anchors: Sequence[Anchor]):
    """對一個已經分析完的 AnalysisResult 套用一組 Anchor，回傳新的
    AnalysisResult（不修改傳入的 result）：

      1. Anchor 對應的拍子時間直接改成 Anchor 的精確值（Hard Constraint）
      2. 用 Anchor 重新反推 downbeats（Bar/Beat 編號）
      3. 重新計算 bpm_raw（Ground Truth 曲線，因為 Anchor 改了拍點時間）
      4. 重新跑 Tempo Curve Layer 縮減，Anchor 對應的 beat index 強制成為
         控制點（見 core/tempo_curve.py 的 forced_indices）
    """
    from analyzer.tempo import compute_tempo_curve, global_bpm as _global_bpm
    from core.tempo_curve import rebuild_for_result

    new_result = copy.deepcopy(result)

    if not anchors:
        new_result.anchors = []
        return new_result

    beat_times = np.asarray(result.beat_times, dtype=float)
    if beat_times.size == 0:
        log.warning("beat_times 為空，無法套用 Anchor")
        return new_result

    resolved = resolve_anchors(anchors, beat_times)
    new_beat_times = apply_anchors_to_beat_times(beat_times, resolved)
    # Anchor 修正過位置後，index 對應的時間變了，重新 resolve 一次確保
    # beat_index 仍然指向正確的拍子（絕大多數情況下不會變，但保守起見）
    resolved = resolve_anchors(anchors, new_beat_times)

    n = len(new_beat_times)
    beats_per_bar = int(getattr(result, "beats_per_bar", 4))
    new_downbeats = derive_downbeats_from_anchors(n, beats_per_bar, resolved)
    if new_downbeats is None:
        new_downbeats = np.asarray(result.downbeats, dtype=int)

    new_confidence = np.asarray(result.beat_confidence, dtype=float).copy()
    for a in resolved:
        new_confidence[a.beat_index] = max(new_confidence[a.beat_index], a.confidence)

    new_bpm_raw = compute_tempo_curve(new_beat_times)

    new_result.beat_times = new_beat_times
    new_result.bpm_raw = np.asarray(new_bpm_raw, dtype=float)
    new_result.bpm_smooth = new_result.bpm_raw.copy()
    new_result.beat_confidence = new_confidence
    new_result.downbeats = np.asarray(new_downbeats, dtype=int)
    new_result.global_bpm = _global_bpm(new_result.bpm_raw)
    new_result.anchors = resolved

    rebuild_for_result(new_result)

    log.info("套用 %d 個 Anchor 完成", len(resolved))
    return new_result

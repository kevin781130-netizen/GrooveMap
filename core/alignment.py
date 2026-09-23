"""Bar Alignment Engine（規格 P4）— Beat 時間有抓到，但 Bar 對不齊時的校正工具。

核心原則：Beat Position Accuracy 優先於 BPM Accuracy。抓到的拍子時間可能
是對的，但「哪一拍是小節第一拍」判斷錯誤（downbeat phase 抓錯），或整條
時間軸系統性地偏移（例如 onset 偵測固定慢半拍）。這裡處理的是「對齊」，
不是「速度」，所以：

1. First Beat Offset：對整條 Beat Position Layer 做一個固定的時間平移。
   平移不改變任何拍子之間的間隔，所以 bpm_raw 完全不受影響，只是把整條
   時間軸挪到跟音樂對上的位置。
2. 手動指定 "This is Bar 1 Beat 1"：使用者聽出真正的小節起點後，直接指定
   beat_times 裡的哪一個 index 是 Bar1 Beat1，取代 analyzer/downbeat.py
   自動判斷的 phase。

校正後必須整條重新餵回 Beat Position Layer → Tempo Curve Layer（規格 P3），
不能讓匯出檔案停留在校正前的時間軸——這是本模組存在的目的。
"""
from __future__ import annotations

import copy
import logging

import numpy as np

log = logging.getLogger(__name__)

MIN_OFFSET_MS = -1000.0
MAX_OFFSET_MS = 1000.0


def apply_first_beat_offset(beat_times, offset_ms: float):
    """把整條 Beat Position Layer 平移 offset_ms 毫秒。

    平移量會被限制在不讓最早的拍子變成負數（負時間無法對應到音檔或
    MIDI tick），如果原本要求的 offset 會讓第一拍變負值，會自動收斂到
    剛好讓第一拍落在 0 秒，並記錄警告。
    """
    beat_times = np.asarray(beat_times, dtype=float)
    if beat_times.size == 0:
        return beat_times.copy()

    offset_ms = float(np.clip(offset_ms, MIN_OFFSET_MS, MAX_OFFSET_MS))
    offset_sec = offset_ms / 1000.0

    if beat_times[0] + offset_sec < 0:
        clamped = -beat_times[0]
        log.warning(
            "First Beat Offset %.0fms 會讓第一拍變成負時間，已收斂為 %.0fms",
            offset_ms, clamped * 1000.0,
        )
        offset_sec = clamped

    return beat_times + offset_sec


def downbeats_from_phase(n_beats: int, phase: int, beats_per_bar: int):
    """跟 analyzer/downbeat.py 的自動判斷同一套規則：phase 是第一個
    downbeat 的 index，之後每 beats_per_bar 拍一個。"""
    phase = int(phase) % max(int(beats_per_bar), 1)
    return np.arange(phase, n_beats, beats_per_bar, dtype=int)


def apply_manual_downbeat(n_beats: int, beats_per_bar: int, beat_number: int):
    """使用者指定「這一拍是 Bar 1 Beat 1」。beat_number 是 1-based
    （對應 GUI 顯示的 #0001），轉成 0-based phase 後重新產生 downbeats。"""
    if not (1 <= beat_number <= n_beats):
        raise ValueError(f"beat_number 必須在 1~{n_beats} 之間，收到 {beat_number}")
    beat_index = beat_number - 1
    phase = beat_index % beats_per_bar
    return downbeats_from_phase(n_beats, phase, beats_per_bar)


def apply_alignment(result, first_beat_offset_ms: float = 0.0, manual_downbeat_beat_number=None):
    """對一個已經分析完的 AnalysisResult 套用 Bar Alignment 校正，回傳
    新的 AnalysisResult（不修改傳入的 result）。校正後會重新跑 Tempo
    Curve Layer 縮減與 Accuracy Validation（規格 P3），確保所有 Tempo
    Event 都建立在校正後的 beat timeline 上。
    """
    new_result = copy.deepcopy(result)

    beat_times = np.asarray(result.beat_times, dtype=float)
    if beat_times.size == 0:
        return new_result

    n = len(beat_times)
    beats_per_bar = int(getattr(result, "beats_per_bar", 4))

    shifted_times = apply_first_beat_offset(beat_times, first_beat_offset_ms)

    if manual_downbeat_beat_number is not None:
        new_downbeats = apply_manual_downbeat(n, beats_per_bar, int(manual_downbeat_beat_number))
    else:
        new_downbeats = np.asarray(result.downbeats, dtype=int)

    new_result.beat_times = shifted_times
    new_result.downbeats = new_downbeats
    # 純平移不改變任何拍子間隔，bpm_raw/bpm_smooth 數值完全不變，
    # 但物件裡儲存的 TempoEvent.time 要跟著更新，所以還是要重建。
    new_result.bpm_smooth = np.asarray(result.bpm_smooth, dtype=float).copy()

    _rebuild_tempo_curve_layer(new_result)

    log.info(
        "Bar Alignment 套用完成：offset=%.0fms, downbeat phase=%s",
        first_beat_offset_ms,
        (manual_downbeat_beat_number if manual_downbeat_beat_number is not None else "未變更"),
    )
    return new_result


def _rebuild_tempo_curve_layer(result) -> None:
    """校正後的 beat timeline 必須是所有 Tempo Event 的唯一依據——
    重新跑一次 Beat Position Layer → Tempo Curve Layer（規格 P3），
    不能沿用校正前算出來的 tempo_control_points。沿用 result 原本
    記錄的 tempo_density/max_tempo_nodes 設定，保持跟分析當下一致。"""
    from core.tempo_events import build_tempo_events
    from core.tempo_curve import reduce_tempo_curve_with_density, DEFAULT_DENSITY
    from exporter.midi import PPQ as MIDI_PPQ

    events = build_tempo_events(result.beat_times, result.bpm_raw)
    confidences = getattr(result, "beat_confidence", None)
    density = getattr(result, "tempo_density", DEFAULT_DENSITY)
    max_nodes = getattr(result, "max_tempo_nodes", None)
    cps, report = reduce_tempo_curve_with_density(
        events, confidences=confidences, ppq=MIDI_PPQ,
        density=density, max_nodes=max_nodes)
    result.tempo_control_points = cps
    result.accuracy_report = report

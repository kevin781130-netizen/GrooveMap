"""Steinberg Master Track (.smt) XML export（規格 P1 — Cubase Tempo/Signature Track 交換格式）.

此 schema 並非 Steinberg 官方公開文件，而是依實際 Cubase 匯出的 .smt 範例檔
反查得到的結構。已確認的部分：
  - <MasterTrack> 根節點下的 <rootObjects> 用 ID 對應到下方兩個 <obj>
    （MTempoTrackEvent / MSignatureTrackEvent）。
  - Tempo 事件用 480 ticks/quarter（SMT_PPQ）為單位的 PPQ 絕對位置，
    與本專案 MIDI export 用的 PPQ=960 是兩套獨立座標系統，不可混用。
  - <int name="Func" value="1"/> 代表這個事件與前一事件之間用 Ramp
    （線性漸變，對應 accelerando / ritardando）；不寫 Func 則是 Jump
    （瞬跳，維持前一個 tempo 直到這個位置才階梯式改變）。
  - <member name="Additional Attributes"> 內的欄位（TLID / Lock 等）
    是 Cubase 編輯器的顯示狀態，與樂理資料無關；此處只填入安全的
    最小預設值，尚未在所有 Cubase 版本中驗證匯入相容性。

匯出後請實際在 Cubase 執行一次匯入驗證，再用於正式錄音室工作流程。
"""
from __future__ import annotations

import itertools
import logging
import os
from dataclasses import dataclass
from typing import List, Sequence, Union

log = logging.getLogger(__name__)

SMT_PPQ = 480  # Cubase Tempo/Signature Track 內部 tick 解析度


@dataclass
class TempoEvent:
    time: float
    bpm: float
    ramp: bool = False  # True → 輸出 Func=1（Ramp），False → Jump


@dataclass
class SignatureEvent:
    bar: int = 0
    numerator: int = 4
    denominator: int = 4
    position_ticks: int = 0
    is_first: bool = False


_id_counter = itertools.count(1_000_000_001, 2)


def _next_id() -> int:
    return next(_id_counter)


def tempo_events_from_dicts(events: Sequence[dict]) -> List[TempoEvent]:
    """把 Tempo Engine 產生的 [{"time": 秒, "bpm": float, "ramp": bool}] 轉成 TempoEvent。"""
    return [
        TempoEvent(
            time=float(e["time"]),
            bpm=float(e["bpm"]),
            ramp=bool(e.get("ramp", False)),
        )
        for e in events
    ]


def _tempo_ticks(events: Sequence[TempoEvent], ppq: int = SMT_PPQ) -> List[float]:
    """累積 tick：兩事件間的 tick 差 = 經過秒數 * (前一事件 BPM / 60) * ppq。"""
    ticks = [0.0] * len(events)
    for i in range(1, len(events)):
        dt = max(0.0, events[i].time - events[i - 1].time)
        bpm_prev = max(events[i - 1].bpm, 1e-6)
        ticks[i] = ticks[i - 1] + dt * (bpm_prev / 60.0) * ppq
    return ticks


def _fmt(value: float) -> str:
    return repr(float(value))


def _tempo_event_xml(tick: float, bpm: float, ramp: bool, indent: str) -> str:
    lines = [f'{indent}<obj class="MTempoEvent" ID="{_next_id()}">']
    lines.append(f'{indent}   <float name="BPM" value="{_fmt(bpm)}"/>')
    lines.append(f'{indent}   <float name="PPQ" value="{_fmt(tick)}"/>')
    if ramp:
        lines.append(f'{indent}   <int name="Func" value="1"/>')
    lines.append(f'{indent}</obj>')
    return "\n".join(lines)


def _signature_event_xml(sig: SignatureEvent, indent: str) -> str:
    lines = [f'{indent}<obj class="MTimeSignatureEvent" ID="{_next_id()}">']
    if sig.is_first:
        lines.append(f'{indent}   <int name="Flags" value="8"/>')
    lines.append(f'{indent}   <float name="Start" value="{_fmt(sig.bar)}"/>')
    lines.append(f'{indent}   <float name="Length" value="1"/>')
    lines.append(f'{indent}   <int name="Bar" value="{sig.bar}"/>')
    lines.append(f'{indent}   <int name="Numerator" value="{sig.numerator}"/>')
    lines.append(f'{indent}   <int name="Denominator" value="{sig.denominator}"/>')
    lines.append(f'{indent}   <int name="Position" value="{sig.position_ticks}"/>')
    lines.append(f'{indent}</obj>')
    return "\n".join(lines)


def _additional_attributes_xml(indent: str) -> str:
    return (
        f'{indent}<member name="Additional Attributes">\n'
        f'{indent}   <int name="TLID" value="1"/>\n'
        f'{indent}   <int name="Lock" value="0"/>\n'
        f'{indent}</member>'
    )


def build_master_track_xml(
    tempo_events: Union[Sequence[dict], Sequence[TempoEvent]],
    beats_per_bar: int = 4,
    denominator: int = 4,
    rehearsal_tempo: float = 120.0,
) -> str:
    """把 tempo_events 轉成 Cubase Master Track (.smt) XML 字串。

    tempo_events: [{"time": 秒, "bpm": float, "ramp": bool(可省略)}, ...]
                  或 TempoEvent 物件序列，不需事先排序。
    """
    if not tempo_events:
        raise ValueError("tempo_events 不可為空")

    if isinstance(tempo_events[0], dict):
        events = tempo_events_from_dicts(tempo_events)
    else:
        events = list(tempo_events)

    events = sorted(events, key=lambda e: e.time)
    ticks = _tempo_ticks(events)

    tempo_root_id = _next_id()
    sig_root_id = _next_id()

    tempo_items = "\n".join(
        _tempo_event_xml(t, e.bpm, e.ramp, " " * 9) for t, e in zip(ticks, events)
    )

    sig = SignatureEvent(
        bar=0, numerator=beats_per_bar, denominator=denominator,
        position_ticks=0, is_first=True,
    )
    sig_items = _signature_event_xml(sig, " " * 9)

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<MasterTrack>\n'
        '   <rootObjects>\n'
        f'      <root name="Tempo Track" ID="{tempo_root_id}"/>\n'
        f'      <root name="Signature Track" ID="{sig_root_id}"/>\n'
        '   </rootObjects>\n\n'
        f'   <obj class="MTempoTrackEvent" ID="{tempo_root_id}">\n'
        '      <list name="TempoEvent" type="obj">\n'
        f'{tempo_items}\n'
        '      </list>\n'
        f'      <float name="RehearsalTempo" value="{_fmt(rehearsal_tempo)}"/>\n'
        f'{_additional_attributes_xml("      ")}\n'
        '   </obj>\n\n'
        f'   <obj class="MSignatureTrackEvent" ID="{sig_root_id}">\n'
        '      <list name="SignatureEvent" type="obj">\n'
        f'{sig_items}\n'
        '      </list>\n'
        f'{_additional_attributes_xml("      ")}\n'
        '   </obj>\n\n'
        '</MasterTrack>\n'
    )


def export_master_track(tempo_events, out_path: str, **kwargs) -> str:
    """把 tempo_events 寫成 .smt 檔，回傳輸出路徑。"""
    xml = build_master_track_xml(tempo_events, **kwargs)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    log.info("Master Track XML 已輸出: %s", out_path)
    return out_path

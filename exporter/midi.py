"""Cubase-compatible MIDI export (規格 6)."""
from __future__ import annotations
import os
from typing import Dict
import numpy as np
import mido

PPQ = 960
CLICK_NOTE = 76
ACCENT_NOTE = 77
CLICK_GATE = 60


def beats_to_ticks(beat_times, bpm_first_beat, ppq=PPQ):
    """Beat Position Layer → 固定 tick 網格（規格 P3）。

    每一拍固定佔用一個 ppq，位置完全由 beat 的順序決定，跟 Tempo Curve
    Layer 縮減成幾個控制點無關——這正是 Click/Marker 不會被 Tempo Curve
    平滑/縮減影響的原因。第一拍之前用 bpm_first_beat（Ground Truth，
    未平滑）反推一個起始 tick，讓開場前奏/count-in 的時間感合理。
    """
    beat_times = np.asarray(beat_times, dtype=float)

    if beat_times.size == 0:
        return np.zeros(0, dtype=float)

    bpm0 = max(float(bpm_first_beat), 1e-6)

    ticks = np.zeros(len(beat_times), dtype=float)
    ticks[0] = beat_times[0] * bpm0 * ppq / 60.0
    for i in range(1, len(beat_times)):
        ticks[i] = ticks[i - 1] + ppq
    return ticks


def _us_per_beat(bpm):
    bpm = max(float(bpm), 1e-6)
    return int(round(60_000_000.0 / bpm))


def _tempo_track(tick_ints, bpm, beats_per_bar):
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name", name="Tempo Map", time=0))
    tr.append(mido.MetaMessage("time_signature", numerator=int(beats_per_bar), denominator=4, time=0))

    bpm = np.asarray(bpm, dtype=float)
    if bpm.size == 0:
        tr.append(mido.MetaMessage("end_of_track", time=0))
        return tr

    last = 0
    tr.append(mido.MetaMessage("set_tempo", tempo=_us_per_beat(bpm[0]), time=0))

    for tick, b in zip(tick_ints, bpm):
        t = int(tick)
        delta = max(0, t - last)
        tr.append(mido.MetaMessage("set_tempo", tempo=_us_per_beat(float(b)), time=delta))
        last = t

    tr.append(mido.MetaMessage("end_of_track", time=0))
    return tr


def _click_track(tick_ints, downbeat_set, note=CLICK_NOTE, accent=ACCENT_NOTE, gate=CLICK_GATE):
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name", name="Click", time=0))
    tr.append(mido.Message("program_change", channel=9, program=0, time=0))

    events = []
    for i, tick in enumerate(tick_ints):
        t = int(tick)
        n = int(accent) if i in downbeat_set else int(note)
        events.append((t, 1, n))
        events.append((t + gate, 0, n))

    events.sort(key=lambda e: (e[0], e[1]))

    last = 0
    for t, kind, n in events:
        delta = max(0, t - last)
        if kind == 1:
            tr.append(mido.Message("note_on", channel=9, note=n, velocity=110, time=delta))
        else:
            tr.append(mido.Message("note_off", channel=9, note=n, velocity=0, time=delta))
        last = t

    tr.append(mido.MetaMessage("end_of_track", time=0))
    return tr


def _marker_track(tick_ints, downbeat_set):
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name", name="Markers", time=0))

    last = 0
    bar = 0
    for i, tick in enumerate(tick_ints):
        if i not in downbeat_set:
            continue
        bar += 1
        t = int(tick)
        delta = max(0, t - last)
        tr.append(mido.MetaMessage("marker", text=f"Bar {bar}", time=delta))
        last = t

    tr.append(mido.MetaMessage("end_of_track", time=0))
    return tr


def build_midi(beat_times, tempo_control_points, downbeat_indices, beats_per_bar=4, ppq=PPQ,
               click_note=CLICK_NOTE, accent_note=ACCENT_NOTE, click_gate=CLICK_GATE,
               include_tempo=True, include_click=True, include_marker=True):
    """beat_times = Beat Position Layer（Ground Truth，決定 Click/Marker 位置，
    不受 Tempo Curve 縮減影響）。tempo_control_points = Tempo Curve Layer
    （core.tempo_curve.TempoControlPoint list，數量可遠少於 beat 數，只決定
    Tempo Track 要放幾個控制點；每個控制點的 beat_index 指到 beat_times 裡
    對應的 Ground Truth 拍子，位置仍然精確對齊固定 tick 網格）。
    """
    mid = mido.MidiFile(type=1, ticks_per_beat=ppq)

    tempo_control_points = sorted(tempo_control_points, key=lambda c: c.beat_index)
    bpm_first_beat = tempo_control_points[0].bpm if tempo_control_points else 120.0

    ticks = beats_to_ticks(beat_times, bpm_first_beat, ppq)
    tick_ints = np.round(ticks).astype(np.int64)
    downbeat_set = {int(i) for i in np.atleast_1d(downbeat_indices)}

    if include_tempo:
        cp_ticks = [int(tick_ints[cp.beat_index]) for cp in tempo_control_points]
        cp_bpms = [cp.bpm for cp in tempo_control_points]
        mid.tracks.append(_tempo_track(cp_ticks, cp_bpms, beats_per_bar))
    if include_click:
        mid.tracks.append(_click_track(tick_ints, downbeat_set, click_note, accent_note, click_gate))
    if include_marker:
        mid.tracks.append(_marker_track(tick_ints, downbeat_set))

    if not mid.tracks:
        empty = mido.MidiTrack()
        empty.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(empty)

    return mid


def export_midi(beat_times, tempo_control_points, downbeat_indices, out_path, **kwargs):
    mid = build_midi(beat_times, tempo_control_points, downbeat_indices, **kwargs)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    mid.save(out_path)
    return out_path


def export_cubase_bundle(result, out_dir, base_name, ppq=PPQ,
                         click_note=CLICK_NOTE, accent_note=ACCENT_NOTE, click_gate=CLICK_GATE,
                         include_smt=True):
    from exporter.steinberg_smt import export_master_track

    os.makedirs(out_dir, exist_ok=True)
    beats = result.beat_times           # Beat Position Layer（Ground Truth）
    cps = result.tempo_control_points   # Tempo Curve Layer（已通過 Accuracy Validation）
    dbs = result.downbeats
    bpb = result.beats_per_bar

    if not cps:
        raise RuntimeError("result.tempo_control_points 為空，請確認 Pipeline 有跑過 Tempo Curve Layer 縮減")

    out = {}

    def _save(name, **flags):
        path = os.path.join(out_dir, name)
        export_midi(beats, cps, dbs, path, beats_per_bar=bpb, ppq=ppq,
                    click_note=click_note, accent_note=accent_note,
                    click_gate=click_gate, **flags)
        return path

    out["cubase"] = _save(f"{base_name}_Cubase.mid", include_tempo=True, include_click=True, include_marker=True)
    out["tempo"]  = _save(f"{base_name}_Tempo.mid",  include_tempo=True, include_click=False, include_marker=False)
    out["click"]  = _save(f"{base_name}_Click.mid",  include_tempo=False, include_click=True, include_marker=False)
    out["marker"] = _save(f"{base_name}_Marker.mid", include_tempo=False, include_click=False, include_marker=True)

    if include_smt:
        smt_events = [{"time": cp.time, "bpm": cp.bpm, "ramp": cp.ramp} for cp in cps]
        smt_path = os.path.join(out_dir, f"{base_name}_MasterTrack.smt")
        out["smt"] = export_master_track(smt_events, smt_path, beats_per_bar=bpb)

    return out

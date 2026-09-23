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


def beats_to_ticks(beat_times, bpm_per_beat, ppq=PPQ):
    beat_times = np.asarray(beat_times, dtype=float)
    bpm_per_beat = np.asarray(bpm_per_beat, dtype=float)

    if beat_times.size == 0:
        return np.zeros(0, dtype=float)

    bpm0 = float(bpm_per_beat[0]) if bpm_per_beat.size else 120.0
    bpm0 = max(bpm0, 1e-6)

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
        events.append((t, 0, n))
        events.append((t + gate, 1, n))

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


def build_midi(beat_times, bpm_curve, downbeat_indices, beats_per_bar=4, ppq=PPQ,
               click_note=CLICK_NOTE, accent_note=ACCENT_NOTE, click_gate=CLICK_GATE,
               include_tempo=True, include_click=True, include_marker=True):
    mid = mido.MidiFile(type=1, ticks_per_beat=ppq)

    ticks = beats_to_ticks(beat_times, bpm_curve, ppq)
    tick_ints = np.round(ticks).astype(np.int64)
    downbeat_set = {int(i) for i in np.atleast_1d(downbeat_indices)}

    if include_tempo:
        mid.tracks.append(_tempo_track(tick_ints, bpm_curve, beats_per_bar))
    if include_click:
        mid.tracks.append(_click_track(tick_ints, downbeat_set, click_note, accent_note, click_gate))
    if include_marker:
        mid.tracks.append(_marker_track(tick_ints, downbeat_set))

    if not mid.tracks:
        empty = mido.MidiTrack()
        empty.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(empty)

    return mid


def export_midi(beat_times, bpm_curve, downbeat_indices, out_path, **kwargs):
    mid = build_midi(beat_times, bpm_curve, downbeat_indices, **kwargs)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    mid.save(out_path)
    return out_path


def export_cubase_bundle(result, out_dir, base_name, ppq=PPQ,
                         click_note=CLICK_NOTE, accent_note=ACCENT_NOTE, click_gate=CLICK_GATE):
    os.makedirs(out_dir, exist_ok=True)
    beats = result.beat_times
    bpm = result.bpm_smooth
    dbs = result.downbeats
    bpb = result.beats_per_bar

    out = {}

    def _save(name, **flags):
        path = os.path.join(out_dir, name)
        export_midi(beats, bpm, dbs, path, beats_per_bar=bpb, ppq=ppq,
                    click_note=click_note, accent_note=accent_note,
                    click_gate=click_gate, **flags)
        return path

    out["cubase"] = _save(f"{base_name}_Cubase.mid", include_tempo=True, include_click=True, include_marker=True)
    out["tempo"]  = _save(f"{base_name}_Tempo.mid",  include_tempo=True, include_click=False, include_marker=False)
    out["click"]  = _save(f"{base_name}_Click.mid",  include_tempo=False, include_click=True, include_marker=False)
    out["marker"] = _save(f"{base_name}_Marker.mid", include_tempo=False, include_click=False, include_marker=True)

    return out

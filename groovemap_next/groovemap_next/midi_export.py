"""MIDI export for Cubase/DAW tempo maps and drum tracks."""
from __future__ import annotations
from bisect import bisect_right
from pathlib import Path
from typing import Iterable
from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo
from .models import DrumEvent, TempoMap
from .tempo_map import seconds_to_ticks

def _append_absolute(track: MidiTrack, events: list[tuple[int, int, object]]) -> None:
    """Append (absolute_tick, priority, message) as delta-time MIDI events."""
    events.sort(key=lambda item: (item[0], item[1]))
    previous = 0
    for tick, _, msg in events:
        tick = max(0, int(tick))
        msg.time = tick - previous
        track.append(msg)
        previous = tick

def _nearest_beat_index(beats: tuple[float, ...], target: float) -> int:
    pos = bisect_right(beats, target)
    candidates: list[int] = []
    if pos < len(beats):
        candidates.append(pos)
    if pos > 0:
        candidates.append(pos - 1)
    return min(candidates, key=lambda i: abs(beats[i] - target))

def _downbeat_ticks(tempo_map: TempoMap, tick_shift: int) -> list[int]:
    """Snap every raw downbeat timestamp to its nearest accepted beat."""
    ticks: set[int] = set()
    for downbeat in tempo_map.downbeats_sec:
        idx = _nearest_beat_index(tempo_map.beats_sec, downbeat)
        tick = tick_shift + (idx - tempo_map.origin_beat_index) * tempo_map.ppq
        if tick >= 0:
            ticks.add(tick)
    return sorted(ticks)

def make_tempo_track(tempo_map: TempoMap, tick_shift: int) -> MidiTrack:
    track = MidiTrack()
    events: list[tuple[int, int, object]] = []
    first_bpm = tempo_map.tempo_points[0].bpm

    events.append((0, 0, MetaMessage("track_name", name="GrooveMap Tempo")))
    events.append((0, 1, MetaMessage(
        "time_signature",
        numerator=tempo_map.beats_per_bar,
        denominator=4,
        clocks_per_click=24,
        notated_32nd_notes_per_beat=8,
    )))
    events.append((0, 2, MetaMessage("set_tempo", tempo=bpm2tempo(first_bpm))))

    for point in tempo_map.tempo_points:
        tick = tick_shift + point.beat_index * tempo_map.ppq
        if tick >= 0:
            events.append((tick, 2, MetaMessage("set_tempo", tempo=bpm2tempo(point.bpm))))

    origin_tick = tick_shift
    events.append((origin_tick, 3, MetaMessage(
        "marker", text=f"GROOVEMAP_ORIGIN_SEC={tempo_map.origin_sec:.6f}"
    )))
    for bar_no, tick in enumerate(_downbeat_ticks(tempo_map, tick_shift), start=1):
        events.append((tick, 4, MetaMessage("marker", text=f"DOWNBEAT_{bar_no}")))

    _append_absolute(track, events)
    return track

def write_tempo_midi(
    tempo_map: TempoMap,
    output_path: str | Path,
    *,
    tick_shift: int,
) -> Path:
    output = Path(output_path)
    midi = MidiFile(type=1, ticks_per_beat=tempo_map.ppq)
    midi.tracks.append(make_tempo_track(tempo_map, tick_shift))
    midi.save(output)
    return output

def write_drum_midi(
    tempo_map: TempoMap,
    drum_events: Iterable[DrumEvent],
    output_path: str | Path,
    *,
    tick_shift: int,
    note_length_ticks: int | None = None,
) -> Path:
    output = Path(output_path)
    midi = MidiFile(type=1, ticks_per_beat=tempo_map.ppq)
    midi.tracks.append(make_tempo_track(tempo_map, tick_shift))

    drum_track = MidiTrack()
    events: list[tuple[int, int, object]] = [
        (0, 0, MetaMessage("track_name", name="GrooveMap Drums"))
    ]
    length = note_length_ticks or max(1, tempo_map.ppq // 64)

    for event in drum_events:
        tick = tick_shift + seconds_to_ticks(tempo_map, event.time_sec)
        if tick < 0:
            continue
        events.append((tick, 1, Message(
            "note_on", channel=9, note=event.note, velocity=event.velocity
        )))
        events.append((tick + length, 2, Message(
            "note_off", channel=9, note=event.note, velocity=0
        )))

    _append_absolute(drum_track, events)
    midi.tracks.append(drum_track)
    midi.save(output)
    return output

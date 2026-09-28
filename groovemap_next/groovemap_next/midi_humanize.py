"""Humanize an external drum MIDI skeleton with a GrooveMap source groove."""
from __future__ import annotations
import json
from pathlib import Path
from mido import MidiFile

from .drum_taxonomy import BY_NOTE
from .groove_humanizer import apply_groove_template, load_groove_template
from .midi_export import write_drum_midi
from .models import DrumEvent, TempoMap, TempoPoint
from .remap import load_mapping, remap_events
from .tempo_map import beat_position_to_seconds


def load_timing_context(path: str | Path) -> tuple[TempoMap, int]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") not in {
        "groovemap-next-timing-v1",
        "groovemap-next-timing-v2",
    }:
        raise ValueError("unsupported GrooveMap timing schema")

    tempo_map = TempoMap(
        beats_sec=tuple(float(x) for x in payload["beats_sec"]),
        downbeats_sec=tuple(float(x) for x in payload.get("downbeats_sec", [])),
        tempo_points=tuple(
            TempoPoint(
                beat_index=int(item["beat_index"]),
                time_sec=float(item["time_sec"]),
                bpm=float(item["bpm"]),
            )
            for item in payload["tempo_points"]
        ),
        origin_sec=float(payload["origin_sec"]),
        origin_beat_index=int(payload["origin_beat_index"]),
        ppq=int(payload["ppq"]),
        beats_per_bar=int(payload["beats_per_bar"]),
    )
    return tempo_map, int(payload["tick_shift"])


def read_drum_midi(
    path: str | Path,
    tempo_map: TempoMap,
    *,
    tick_shift: int,
    channel: int | None = 9,
) -> list[DrumEvent]:
    midi = MidiFile(path)
    shift_beats = tick_shift / tempo_map.ppq
    events: list[DrumEvent] = []

    for track in midi.tracks:
        absolute_tick = 0
        for message in track:
            absolute_tick += message.time
            if message.type != "note_on" or message.velocity <= 0:
                continue
            if channel is not None and getattr(message, "channel", None) != channel:
                continue

            beat_position = absolute_tick / midi.ticks_per_beat - shift_beats
            time_sec = beat_position_to_seconds(tempo_map, beat_position)
            drum_class = BY_NOTE.get(message.note)
            label = drum_class.label if drum_class is not None else f"note_{message.note}"
            events.append(
                DrumEvent(
                    time_sec=max(0.0, time_sec),
                    note=message.note,
                    velocity=message.velocity,
                    label=label,
                )
            )

    return sorted(events, key=lambda e: (e.time_sec, e.note, e.label))


def humanize_midi_file(
    midi_path: str | Path,
    timing_json: str | Path,
    groove_json: str | Path,
    output_path: str | Path,
    *,
    timing_strength: float = 1.0,
    velocity_strength: float = 1.0,
    mapping_json: str | Path | None = None,
    channel: int | None = 9,
) -> Path:
    tempo_map, tick_shift = load_timing_context(timing_json)
    groove = load_groove_template(groove_json)
    events = read_drum_midi(
        midi_path,
        tempo_map,
        tick_shift=tick_shift,
        channel=channel,
    )
    if not events:
        raise ValueError("input MIDI contains no matching drum note_on events")

    events = apply_groove_template(
        events,
        tempo_map,
        groove,
        timing_strength=timing_strength,
        velocity_strength=velocity_strength,
    )
    if mapping_json is not None:
        events = remap_events(events, load_mapping(mapping_json))

    return write_drum_midi(
        tempo_map,
        events,
        output_path,
        tick_shift=tick_shift,
    )

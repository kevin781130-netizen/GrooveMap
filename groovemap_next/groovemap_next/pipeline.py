"""End-to-end SUNO drums stem -> raw drum events -> beat map -> MIDI."""
from __future__ import annotations
import json
from pathlib import Path
from .beat_tracker import BeatThisTracker
from .drum_transcriber import transcribe_drum_stem
from .midi_export import write_drum_midi, write_tempo_midi
from .models import PipelineOutputs
from .remap import load_mapping, remap_events
from .tempo_map import build_tempo_map, choose_tick_shift

def run_suno_drum_pipeline(
    drums_wav: str | Path,
    output_prefix: str | Path,
    *,
    device: str = "cpu",
    checkpoint: str = "final0",
    float16: bool = False,
    sensitivity: float = 1.0,
    mapping_json: str | Path | None = None,
    ppq: int = 960,
    beats_per_bar: int = 4,
) -> PipelineOutputs:
    source = Path(drums_wav)
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    # Requested order: first create raw time-domain MIDI events from SUNO stem.
    drum_events = transcribe_drum_stem(source, sensitivity=sensitivity)
    if mapping_json is not None:
        drum_events = remap_events(drum_events, load_mapping(mapping_json))

    # Then derive the non-constant beat/downbeat timeline.
    tracker = BeatThisTracker(checkpoint=checkpoint, device=device, float16=float16)
    analysis = tracker.analyze(source)
    tempo_map = build_tempo_map(
        analysis, ppq=ppq, beats_per_bar=beats_per_bar, repair_missing_beats=True
    )

    earliest = min([0.0] + [event.time_sec for event in drum_events])
    tick_shift = choose_tick_shift(tempo_map, earliest)

    tempo_path = prefix.with_name(prefix.name + "_tempo.mid")
    drums_path = prefix.with_name(prefix.name + "_drums.mid")
    timing_path = prefix.with_name(prefix.name + "_timing.json")

    write_tempo_midi(tempo_map, tempo_path, tick_shift=tick_shift)
    write_drum_midi(tempo_map, drum_events, drums_path, tick_shift=tick_shift)

    payload = {
        "schema": "groovemap-next-timing-v1",
        "source_audio": str(source),
        "beat_source": analysis.source,
        "ppq": tempo_map.ppq,
        "beats_per_bar": tempo_map.beats_per_bar,
        "origin_sec": tempo_map.origin_sec,
        "origin_beat_index": tempo_map.origin_beat_index,
        "tick_shift": tick_shift,
        "beats_sec": list(tempo_map.beats_sec),
        "downbeats_sec": list(tempo_map.downbeats_sec),
        "tempo_points": [
            {"beat_index": p.beat_index, "time_sec": p.time_sec, "bpm": p.bpm}
            for p in tempo_map.tempo_points
        ],
        "drum_events": [
            {
                "time_sec": e.time_sec,
                "note": e.note,
                "velocity": e.velocity,
                "label": e.label,
            }
            for e in drum_events
        ],
    }
    timing_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return PipelineOutputs(tempo_path, drums_path, timing_path)

"""End-to-end SUNO drums stem -> events -> tempo -> groove -> MIDI."""
from __future__ import annotations
import json
from pathlib import Path

from .beat_tracker import BeatThisTracker
from .drum_transcriber import transcribe_drum_stem
from .groove_humanizer import (
    apply_groove_template,
    extract_groove_template,
    save_groove_template,
)
from .midi_export import write_drum_midi, write_tempo_midi
from .models import PipelineOutputs
from .remap import load_mapping, remap_events
from .tempo_map import build_tempo_map, choose_tick_shift


def _transcribe(
    source: Path,
    *,
    sensitivity: float,
    drum_model: str | Path | None,
    drum_manifest: str | Path | None,
    onnx_threshold: float | None,
):
    if drum_model is None and drum_manifest is None:
        return transcribe_drum_stem(source, sensitivity=sensitivity), "cleanroom-dsp-3class"
    if drum_model is None or drum_manifest is None:
        raise ValueError("--drum-model and --drum-manifest must be supplied together")

    from .onnx_drum import OnnxDrumTranscriber
    transcriber = OnnxDrumTranscriber(drum_model, drum_manifest)
    return (
        transcriber.transcribe(source, threshold=onnx_threshold),
        f"onnx:{Path(drum_model).name}",
    )


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
    drum_model: str | Path | None = None,
    drum_manifest: str | Path | None = None,
    onnx_threshold: float | None = None,
    humanize_source: bool = False,
    timing_strength: float = 1.0,
    velocity_strength: float = 1.0,
    pattern_bars: int = 2,
) -> PipelineOutputs:
    source = Path(drums_wav)
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    # Stage 1: extract musical events in absolute seconds.
    detected_events, transcription_source = _transcribe(
        source,
        sensitivity=sensitivity,
        drum_model=drum_model,
        drum_manifest=drum_manifest,
        onnx_threshold=onnx_threshold,
    )

    # Stage 2: recover the non-constant beat/downbeat timeline.
    tracker = BeatThisTracker(checkpoint=checkpoint, device=device, float16=float16)
    analysis = tracker.analyze(source)
    tempo_map = build_tempo_map(
        analysis,
        ppq=ppq,
        beats_per_bar=beats_per_bar,
        repair_missing_beats=True,
    )

    # Stage 3: optionally quantize the skeleton and reconstruct source feel.
    groove_path: Path | None = None
    humanized_events = None
    if humanize_source and detected_events:
        template = extract_groove_template(
            detected_events,
            tempo_map,
            subdivisions_per_beat=4,
            pattern_bars=pattern_bars,
        )
        humanized_events = apply_groove_template(
            detected_events,
            tempo_map,
            template,
            timing_strength=timing_strength,
            velocity_strength=velocity_strength,
        )
        groove_path = prefix.with_name(prefix.name + "_groove.json")
        save_groove_template(template, groove_path)

    # Stage 4: vendor-specific key mapping happens last; labels remain semantic.
    mapping = load_mapping(mapping_json) if mapping_json is not None else None
    drum_events = (
        remap_events(detected_events, mapping)
        if mapping is not None
        else detected_events
    )
    mapped_humanized = (
        remap_events(humanized_events, mapping)
        if mapping is not None and humanized_events is not None
        else humanized_events
    )

    all_events = list(drum_events)
    if mapped_humanized is not None:
        all_events.extend(mapped_humanized)
    earliest = min([0.0] + [event.time_sec for event in all_events])
    tick_shift = choose_tick_shift(tempo_map, earliest)

    tempo_path = prefix.with_name(prefix.name + "_tempo.mid")
    drums_path = prefix.with_name(prefix.name + "_drums.mid")
    timing_path = prefix.with_name(prefix.name + "_timing.json")
    humanized_path: Path | None = None

    write_tempo_midi(tempo_map, tempo_path, tick_shift=tick_shift)
    write_drum_midi(tempo_map, drum_events, drums_path, tick_shift=tick_shift)

    if mapped_humanized is not None:
        humanized_path = prefix.with_name(prefix.name + "_drums_humanized.mid")
        write_drum_midi(
            tempo_map,
            mapped_humanized,
            humanized_path,
            tick_shift=tick_shift,
        )

    def encode_events(events):
        if events is None:
            return None
        return [
            {
                "time_sec": e.time_sec,
                "note": e.note,
                "velocity": e.velocity,
                "label": e.label,
            }
            for e in events
        ]

    payload = {
        "schema": "groovemap-next-timing-v2",
        "source_audio": str(source),
        "transcription_source": transcription_source,
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
        "drum_events": encode_events(drum_events),
        "humanized_events": encode_events(mapped_humanized),
        "humanize": {
            "enabled": humanized_events is not None,
            "timing_strength": timing_strength,
            "velocity_strength": velocity_strength,
            "pattern_bars": pattern_bars,
        },
    }
    timing_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return PipelineOutputs(
        tempo_midi=tempo_path,
        drum_midi=drums_path,
        timing_json=timing_path,
        humanized_midi=humanized_path,
        groove_json=groove_path,
    )

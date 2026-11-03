"""End-to-end SUNO drums stem -> events -> tempo -> groove -> MIDI."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

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
        return (
            transcribe_drum_stem(source, sensitivity=sensitivity),
            "cleanroom-dsp-3class",
        )
    if drum_model is None or drum_manifest is None:
        raise ValueError("--drum-model and --drum-manifest must be supplied together")

    from .onnx_drum import OnnxDrumTranscriber

    transcriber = OnnxDrumTranscriber(drum_model, drum_manifest)
    return (
        transcriber.transcribe(source, threshold=onnx_threshold),
        f"onnx:{Path(drum_model).name}",
    )


def _validate_strength(value: float, name: str) -> float:
    result = float(value)
    if not 0.0 <= result <= 1.5:
        raise ValueError(f"{name} must be in 0.0..1.5")
    return result


def _optional_output_paths(prefix: Path) -> tuple[Path, Path]:
    return (
        prefix.with_name(prefix.name + "_drums_humanized.mid"),
        prefix.with_name(prefix.name + "_groove.json"),
    )


def _clear_optional_outputs(prefix: Path) -> tuple[Path, Path]:
    humanized_path, groove_path = _optional_output_paths(prefix)
    for path in (humanized_path, groove_path):
        path.unlink(missing_ok=True)
    return humanized_path, groove_path



def _publish_staged_outputs(
    staged: dict[Path, Path],
    stale: tuple[Path, ...],
    *,
    backup_dir: Path,
) -> None:
    # mkdir is atomic across processes and portable to Windows. Never remove an
    # existing lock: its owner may still be publishing or recovering a failure.
    first = next(iter(staged))
    lock = first.with_name("." + first.name + ".publication-lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise FileExistsError(f"output publication is already locked: {lock}") from exc
    try:
        _publish_unlocked(staged, stale, backup_dir=backup_dir)
    finally:
        lock.rmdir()


def _publish_unlocked(
    staged: dict[Path, Path],
    stale: tuple[Path, ...],
    *,
    backup_dir: Path,
) -> None:
    """Publish a completed run and restore prior files on a publish error.

    All candidate MIDI/JSON files are written and validated before publication.
    Backups are on the same filesystem as the destination so rollback can use
    os.replace. A hard power loss during publication still needs filesystem
    recovery; this is not a multi-file atomic filesystem transaction.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    backups: dict[Path, Path] = {}
    destinations = list(staged) + list(stale)
    for index, destination in enumerate(destinations):
        if destination.exists():
            backup = backup_dir / f"previous_{index}"
            shutil.copy2(destination, backup)
            backups[destination] = backup

    changed: list[Path] = []
    try:
        for destination, prepared in staged.items():
            os.replace(prepared, destination)
            changed.append(destination)
        for destination in stale:
            if destination.exists():
                destination.unlink()
                changed.append(destination)
    except BaseException:
        for destination in reversed(changed):
            previous = backups.get(destination)
            if previous is not None:
                os.replace(previous, destination)
            else:
                destination.unlink(missing_ok=True)
        raise


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

    destinations = [prefix.with_name(prefix.name + suffix) for suffix in (
        "_tempo.mid", "_drums.mid", "_timing.json",
        "_drums_humanized.mid", "_groove.json",
    )]
    if any(path.resolve() == source.resolve() for path in destinations):
        raise ValueError("output paths must not overwrite source audio")

    # Validate before doing expensive inference so metadata and rendering always
    # describe the exact same effective settings.
    timing_strength = _validate_strength(timing_strength, "timing_strength")
    velocity_strength = _validate_strength(
        velocity_strength,
        "velocity_strength",
    )
    if pattern_bars < 1:
        raise ValueError("pattern_bars must be >= 1")

    # Previous outputs must remain intact until all new outputs are ready.
    humanized_candidate, groove_candidate = _optional_output_paths(prefix)

    # Stage 1: extract musical events in absolute seconds.
    detected_events, transcription_source = _transcribe(
        source,
        sensitivity=sensitivity,
        drum_model=drum_model,
        drum_manifest=drum_manifest,
        onnx_threshold=onnx_threshold,
    )

    # Stage 2: recover the non-constant beat/downbeat timeline.
    tracker = BeatThisTracker(
        checkpoint=checkpoint,
        device=device,
        float16=float16,
    )
    analysis = tracker.analyze(source)
    tempo_map = build_tempo_map(
        analysis,
        ppq=ppq,
        beats_per_bar=beats_per_bar,
        repair_missing_beats=True,
    )

    with TemporaryDirectory(prefix=f".{prefix.name}.release-", dir=prefix.parent) as temp:
        staging = Path(temp)
        staged_prefix = staging / prefix.name
        staged_tempo_path = staged_prefix.with_name(staged_prefix.name + "_tempo.mid")
        staged_drums_path = staged_prefix.with_name(staged_prefix.name + "_drums.mid")
        staged_timing_path = staged_prefix.with_name(staged_prefix.name + "_timing.json")
        staged_humanized_path, staged_groove_path = _optional_output_paths(staged_prefix)
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
            groove_path = groove_candidate
            save_groove_template(template, staged_groove_path)

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

        write_tempo_midi(tempo_map, staged_tempo_path, tick_shift=tick_shift)
        write_drum_midi(
            tempo_map,
            drum_events,
            staged_drums_path,
            tick_shift=tick_shift,
        )

        if mapped_humanized is not None:
            humanized_path = humanized_candidate
            write_drum_midi(
                tempo_map,
                mapped_humanized,
                staged_humanized_path,
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
                {
                    "beat_index": p.beat_index,
                    "time_sec": p.time_sec,
                    "bpm": p.bpm,
                }
                for p in tempo_map.tempo_points
            ],
            "drum_events": encode_events(drum_events),
            "humanized_events": encode_events(mapped_humanized),
            "humanize": {
                "enabled": humanized_events is not None,
                "timing_strength": timing_strength,
                "velocity_strength": velocity_strength,
                "pattern_bars": int(pattern_bars),
            },
        }
        staged_timing_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


        publish = {
            tempo_path: staged_tempo_path,
            drums_path: staged_drums_path,
            timing_path: staged_timing_path,
        }
        if humanized_path is not None:
            publish[humanized_candidate] = staged_humanized_path
        if groove_path is not None:
            publish[groove_candidate] = staged_groove_path
        stale = tuple(
            item for item in (humanized_candidate, groove_candidate)
            if item not in publish
        )
        _publish_staged_outputs(publish, stale, backup_dir=staging / "backup")

    return PipelineOutputs(
        tempo_midi=tempo_path,
        drum_midi=drums_path,
        timing_json=timing_path,
        humanized_midi=humanized_path,
        groove_json=groove_path,
    )

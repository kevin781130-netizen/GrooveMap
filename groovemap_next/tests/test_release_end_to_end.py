"""Offline release gate: MIDI/JSON export and failure safety, no AI weights."""
import json
from pathlib import Path

import mido
import pytest

from groovemap_next import pipeline
from groovemap_next.models import BeatAnalysis, DrumEvent


class OfflineTracker:
    def __init__(self, **kwargs):
        pass

    def analyze(self, source):
        # Intentionally drifting pulse, not a fixed-BPM reference.
        return BeatAnalysis(
            beats_sec=(0.0, 0.50, 1.02, 1.51, 2.02, 2.53, 3.04, 3.53, 4.04),
            downbeats_sec=(0.0, 2.02, 4.04),
            source="offline-controlled-fixture",
        )


@pytest.fixture
def stub_ai(monkeypatch):
    monkeypatch.setattr(pipeline, "BeatThisTracker", OfflineTracker)
    events = [
        DrumEvent(0.015, 36, 90, "kick"),
        DrumEvent(0.515, 38, 105, "snare"),
        DrumEvent(1.035, 42, 70, "closed_hat"),
        DrumEvent(1.515, 38, 115, "snare"),
        DrumEvent(2.030, 36, 95, "kick"),
    ]
    monkeypatch.setattr(pipeline, "_transcribe", lambda *a, **k: (events, "offline-stub"))
    return events


def _notes(midi_path):
    midi = mido.MidiFile(midi_path)
    return [
        msg for track in midi.tracks for msg in track
        if msg.type == "note_on" and msg.velocity > 0
    ]


def test_end_to_end_variable_tempo_and_groove_exports(tmp_path, stub_ai):
    prefix = tmp_path / "song"
    out = pipeline.run_suno_drum_pipeline(
        tmp_path / "input.wav", prefix, humanize_source=True, pattern_bars=1
    )

    files = (
        out.tempo_midi, out.drum_midi, out.timing_json,
        out.humanized_midi, out.groove_json,
    )
    assert all(path and path.is_file() and path.stat().st_size > 0 for path in files)
    tempo = mido.MidiFile(out.tempo_midi)
    assert tempo.ticks_per_beat == 960
    assert len([msg for track in tempo.tracks for msg in track if msg.type == "set_tempo"]) >= 3
    notes = _notes(out.drum_midi)
    assert len(notes) == len(stub_ai)
    assert {msg.note for msg in notes} == {36, 38, 42}
    assert all(msg.channel == 9 for msg in notes)
    assert len(_notes(out.humanized_midi)) == len(stub_ai)

    data = json.loads(out.timing_json.read_text(encoding="utf-8"))
    assert data["schema"] == "groovemap-next-timing-v2"
    assert len(data["tempo_points"]) == 8
    assert data["transcription_source"] == "offline-stub"
    assert data["humanize"]["enabled"] is True
    assert len(data["drum_events"]) == len(stub_ai)

    groove = json.loads(out.groove_json.read_text(encoding="utf-8"))
    assert groove["schema"] == "groovemap-groove-v1"


def test_export_write_failure_keeps_all_previous_outputs(tmp_path, monkeypatch, stub_ai):
    prefix = tmp_path / "song"
    suffixes = (
        "_tempo.mid", "_drums.mid", "_timing.json",
        "_drums_humanized.mid", "_groove.json",
    )
    prior = {}
    for suffix in suffixes:
        p = prefix.with_name(prefix.name + suffix)
        p.write_bytes(b"previous-success" + suffix.encode())
        prior[p] = p.read_bytes()

    def fail_drum_export(*args, **kwargs):
        raise OSError("simulated disk write failure")

    monkeypatch.setattr(pipeline, "write_drum_midi", fail_drum_export)
    with pytest.raises(OSError, match="simulated disk write failure"):
        pipeline.run_suno_drum_pipeline(
            tmp_path / "input.wav", prefix, humanize_source=True
        )
    for path, expected in prior.items():
        assert path.read_bytes() == expected


def test_publication_failure_rolls_back_every_previous_output(tmp_path, monkeypatch):
    suffixes = ("_tempo.mid", "_drums.mid", "_timing.json", "_groove.json")
    old, prepared = {}, {}
    for suffix in suffixes:
        target = tmp_path / ("song" + suffix)
        stage = tmp_path / ("stage" + suffix)
        target.write_bytes(b"old:" + suffix.encode())
        stage.write_bytes(b"new:" + suffix.encode())
        old[target] = target.read_bytes()
        prepared[target] = stage

    original_replace = pipeline.os.replace
    has_failed = False

    def fail_once(src, dst):
        nonlocal has_failed
        if str(dst).endswith("_drums.mid") and not has_failed:
            has_failed = True
            raise OSError("simulated publish failure")
        return original_replace(src, dst)

    monkeypatch.setattr(pipeline.os, "replace", fail_once)
    with pytest.raises(OSError, match="simulated publish failure"):
        pipeline._publish_staged_outputs(
            prepared, (), backup_dir=tmp_path / "backup"
        )
    assert has_failed
    for target, expected in old.items():
        assert target.read_bytes() == expected

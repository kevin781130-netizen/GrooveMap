"""Structural gate regression: never accept an altered tempo map as a PASS."""
import json

import pytest

from groovemap_next import pipeline
from groovemap_next.models import BeatAnalysis, DrumEvent
from scripts.release_gate import _validate_outputs


class OfflineTracker:
    def __init__(self, **kwargs):
        pass

    def analyze(self, source):
        # Synthetic fixture. This string exercises gate validation only,
        # and is not evidence that Beat This! was executed.
        return BeatAnalysis(
            beats_sec=(0.0, 0.5, 1.02, 1.5, 2.0, 2.49, 2.99, 3.5, 4.0),
            downbeats_sec=(0.0, 2.0, 4.0),
            source="CPJKU/beat_this:minimal",
        )


@pytest.fixture
def exported(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "BeatThisTracker", OfflineTracker)
    monkeypatch.setattr(
        pipeline,
        "_transcribe",
        lambda *a, **k: (
            [
                DrumEvent(0.02, 36, 86, "kick"),
                DrumEvent(0.52, 38, 110, "snare"),
                DrumEvent(1.03, 42, 71, "closed_hat"),
            ],
            "offline-controlled-fixture",
        ),
    )
    prefix = tmp_path / "song"
    pipeline.run_suno_drum_pipeline(tmp_path / "ignored.wav", prefix, humanize_source=True)
    return prefix


def test_structural_gate_accepts_intact_synthetic_export(exported):
    result = _validate_outputs(exported, humanized=True)
    assert result["ok"] is True
    assert result["detected_events"] == 3


def test_structural_gate_rejects_tempo_bpm_mismatch(exported):
    path = exported.with_name(exported.name + "_timing.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tempo_points"][0]["bpm"] = 72.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="tempo MIDI tick/BPM mismatch"):
        _validate_outputs(exported, humanized=True)


def test_structural_gate_rejects_tempo_tick_mismatch(exported):
    path = exported.with_name(exported.name + "_timing.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tempo_points"][2]["beat_index"] += 3
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="tempo MIDI tick/BPM mismatch"):
        _validate_outputs(exported, humanized=True)


def test_structural_gate_rejects_stubbed_beat_source(exported):
    path = exported.with_name(exported.name + "_timing.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["beat_source"] = "offline-controlled-fixture"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="requires real Beat This"):
        _validate_outputs(exported, humanized=True)


def test_gate_rejects_humanized_velocity_change(exported):
    import mido
    path = exported.with_name(exported.name + '_drums_humanized.mid')
    midi = mido.MidiFile(path)
    for track in midi.tracks:
        for msg in track:
            if msg.type == 'note_on' and msg.velocity:
                msg.velocity = 1
    midi.save(path)
    with pytest.raises(ValueError, match='humanized event/tick/velocity'):
        _validate_outputs(exported, humanized=True)


def test_gate_rejects_extra_same_tick_tempo(exported):
    import mido
    path = exported.with_name(exported.name + '_tempo.mid')
    midi = mido.MidiFile(path)
    midi.tracks[0].insert(3, mido.MetaMessage('set_tempo',tempo=1000000,time=0))
    midi.save(path)
    with pytest.raises(ValueError, match='tempo MIDI tick/BPM mismatch'):
        _validate_outputs(exported, humanized=True)

"""Offline release-safety regression tests; no AI checkpoint or Actions required."""
import json

import pytest

from groovemap_next import pipeline
from groovemap_next.models import BeatAnalysis, DrumEvent


def _existing_optional_outputs(prefix):
    humanized, groove = pipeline._optional_output_paths(prefix)
    humanized.write_bytes(b"prior-successful-midi")
    groove.write_text("prior-successful-groove", encoding="utf-8")
    return humanized, groove


def _assert_prior_outputs_preserved(humanized, groove):
    assert humanized.read_bytes() == b"prior-successful-midi"
    assert groove.read_text(encoding="utf-8") == "prior-successful-groove"


def test_failed_transcription_does_not_delete_previous_success(tmp_path, monkeypatch):
    prefix = tmp_path / "song"
    humanized, groove = _existing_optional_outputs(prefix)

    def broken_transcription(*args, **kwargs):
        raise RuntimeError("transcription failed")

    monkeypatch.setattr(pipeline, "_transcribe", broken_transcription)
    with pytest.raises(RuntimeError, match="transcription failed"):
        pipeline.run_suno_drum_pipeline(
            tmp_path / "input.wav", prefix, humanize_source=False
        )

    _assert_prior_outputs_preserved(humanized, groove)


def test_failed_beat_analysis_does_not_delete_previous_success(tmp_path, monkeypatch):
    prefix = tmp_path / "song"
    humanized, groove = _existing_optional_outputs(prefix)
    monkeypatch.setattr(pipeline, "_transcribe", lambda *a, **k: ([], "offline-stub"))

    class FailingBeatTracker:
        def __init__(self, **kwargs):
            pass

        def analyze(self, source):
            raise RuntimeError("beat analysis failed")

    monkeypatch.setattr(pipeline, "BeatThisTracker", FailingBeatTracker)
    with pytest.raises(RuntimeError, match="beat analysis failed"):
        pipeline.run_suno_drum_pipeline(
            tmp_path / "input.wav", prefix, humanize_source=True
        )

    _assert_prior_outputs_preserved(humanized, groove)


def test_successful_plain_export_prunes_stale_optional_outputs(tmp_path, monkeypatch):
    prefix = tmp_path / "song"
    humanized, groove = _existing_optional_outputs(prefix)
    monkeypatch.setattr(
        pipeline, "_transcribe",
        lambda *a, **k: ([DrumEvent(0.5, 38, 100, "snare")], "offline-stub"),
    )

    class OfflineBeatTracker:
        def __init__(self, **kwargs):
            pass

        def analyze(self, source):
            return BeatAnalysis(
                beats_sec=(0.0, 0.5, 1.0, 1.5, 2.0),
                downbeats_sec=(0.0, 2.0),
                source="offline-stub",
            )

    monkeypatch.setattr(pipeline, "BeatThisTracker", OfflineBeatTracker)
    outputs = pipeline.run_suno_drum_pipeline(
        tmp_path / "input.wav", prefix, humanize_source=False
    )

    assert outputs.tempo_midi.stat().st_size > 0
    assert outputs.drum_midi.stat().st_size > 0
    timing = json.loads(outputs.timing_json.read_text(encoding="utf-8"))
    assert timing["transcription_source"] == "offline-stub"
    assert timing["drum_events"][0]["note"] == 38
    assert outputs.humanized_midi is None
    assert outputs.groove_json is None
    assert not humanized.exists()
    assert not groove.exists()

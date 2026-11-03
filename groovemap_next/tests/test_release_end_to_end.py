"""Offline release gate: MIDI/JSON export and failure safety, no AI weights."""
import json
import struct
import numpy as np
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


def test_actual_pcm_wav_dsp_to_midi_without_ai_checkpoint(tmp_path, monkeypatch):
    """Full real WAV -> real 3-class DSP -> tempo MIDI/drum MIDI/JSON/groove.

    Only Beat This! is stubbed. No drum transcriber mocking and no model weights.
    """
    sr = 48000
    audio = np.zeros(sr * 3, dtype=np.float32)
    n = np.arange(round(sr * 0.15))
    kick = (
        0.5 * np.sin(2 * np.pi * 70 * n / sr)
        * np.exp(-n / (sr * 0.045))
    ).astype(np.float32)
    for onset in (0.5, 1.5, 2.5):
        i = round(onset * sr)
        audio[i:i + len(kick)] += kick
    pcm16 = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    fmt = struct.pack("<HHIIHH", 1, 1, sr, sr * 2, 2, 16)
    body = b"WAVE"
    for name, data in ((b"fmt ", fmt), (b"data", pcm16.tobytes())):
        body += name + struct.pack("<I", len(data)) + data
        if len(data) & 1:
            body += b"\x00"
    wav = tmp_path / "synthetic-stem.wav"
    wav.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)

    class BeatStub:
        def __init__(self, **kwargs):
            pass

        def analyze(self, source):
            return BeatAnalysis(
                beats_sec=(0.0, 0.5, 1.0, 1.5, 2.0, 2.5),
                downbeats_sec=(0.0, 2.0),
                source="offline-controlled-beat-fixture",
            )

    monkeypatch.setattr(pipeline, "BeatThisTracker", BeatStub)
    prefix = tmp_path / "actual-dsp"
    out = pipeline.run_suno_drum_pipeline(
        wav, prefix, humanize_source=True, pattern_bars=1
    )
    payload = json.loads(out.timing_json.read_text(encoding="utf-8"))
    detected = [
        e["time_sec"] for e in payload["drum_events"] if e["note"] == 36
    ]
    for onset in (0.5, 1.5, 2.5):
        assert any(abs(t - onset) < 0.02 for t in detected)
    midi = mido.MidiFile(out.drum_midi)
    assert len([
        m for track in midi.tracks for m in track
        if m.type == "note_on" and m.note == 36 and m.velocity > 0
    ]) >= 3
    assert out.tempo_midi.stat().st_size > 0
    assert out.humanized_midi.stat().st_size > 0
    assert out.groove_json.stat().st_size > 0


def test_keyboard_interrupt_during_publication_restores_old_set(tmp_path, monkeypatch):
    targets = [tmp_path/'a_tempo.mid',tmp_path/'a_drums.mid']
    staged={}
    for i,target in enumerate(targets):
        target.write_bytes(b'old')
        prepared=tmp_path/f'prepared{i}';prepared.write_bytes(b'new')
        staged[target]=prepared
    replace=pipeline.os.replace
    def interrupt(src,dst):
        if src==staged[targets[1]]:
            raise KeyboardInterrupt('injected only in isolated test directory')
        return replace(src,dst)
    monkeypatch.setattr(pipeline.os,'replace',interrupt)
    with pytest.raises(KeyboardInterrupt):
        pipeline._publish_staged_outputs(staged,(),backup_dir=tmp_path/'backup')
    assert all(p.read_bytes()==b'old' for p in targets)
    assert not list(tmp_path.glob('.*publication-lock'))


def test_rollback_failure_keeps_recoverable_backups(tmp_path, monkeypatch, stub_ai):
    prefix=tmp_path/'song'
    tempo=tmp_path/'song_tempo.mid';tempo.write_bytes(b'prior-tempo')
    drums=tmp_path/'song_drums.mid';drums.write_bytes(b'prior-drums')
    replace=pipeline.os.replace
    def fail_publication_and_recovery(src,dst):
        if str(dst).endswith('_drums.mid') or 'previous_0' in str(src):
            raise OSError('persistent storage fault')
        return replace(src,dst)
    monkeypatch.setattr(pipeline.os,'replace',fail_publication_and_recovery)
    with pytest.raises(RuntimeError, match='recovery required'):
        pipeline.run_suno_drum_pipeline(tmp_path/'input.wav',prefix)
    backups=list(tmp_path.glob('.song.release-*/backup/previous_0'))
    assert len(backups)==1 and backups[0].read_bytes()==b'prior-tempo'
    assert (backups[0].parent/'recovery.json').is_file()
    assert (tmp_path/'.song_tempo.mid.publication-lock').is_dir()

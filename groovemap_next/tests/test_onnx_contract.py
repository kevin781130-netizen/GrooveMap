import json
from pathlib import Path

import numpy as np
import pytest

from groovemap_next.drum_taxonomy import DRUM_CLASSES_20
from groovemap_next.onnx_drum import (
    OnnxDrumManifest,
    _as_frames_classes,
    _resample_bandlimited,
    _velocity_to_midi,
)


def test_taxonomy_has_exactly_20_unique_classes():
    assert len(DRUM_CLASSES_20) == 20
    assert len({x.label for x in DRUM_CLASSES_20}) == 20
    assert len({x.midi_note for x in DRUM_CLASSES_20}) == 20


def test_example_manifest_matches_taxonomy():
    path = Path(__file__).parents[1] / "models" / "manifest-20class.example.json"
    manifest = OnnxDrumManifest.load(path)
    assert len(manifest.labels) == 20
    assert manifest.labels == tuple(x.label for x in DRUM_CLASSES_20)
    assert manifest.midi_notes == tuple(x.midi_note for x in DRUM_CLASSES_20)
    assert manifest.velocity_encoding == "normalized"


def test_output_layout_bct_is_transposed_to_frames_classes():
    raw = np.arange(1 * 20 * 7, dtype=np.float32).reshape(1, 20, 7)
    converted = _as_frames_classes(raw, layout="B,C,T", class_count=20)
    assert converted.shape == (7, 20)
    assert converted[3, 4] == raw[0, 4, 3]


def test_downsampling_attenuates_tone_above_target_nyquist():
    source_sr = 48000
    target_sr = 16000
    t = np.arange(source_sr // 10, dtype=np.float32) / source_sr
    source = np.sin(2.0 * np.pi * 12000.0 * t).astype(np.float32)
    converted = _resample_bandlimited(source, source_sr, target_sr)

    source_rms = float(np.sqrt(np.mean(source**2)))
    converted_rms = float(np.sqrt(np.mean(converted**2)))
    assert converted_rms < source_rms * 0.15


def test_velocity_encoding_is_explicit_and_consistent():
    assert _velocity_to_midi(0.5, "normalized") == 64
    assert _velocity_to_midi(1.0, "normalized") == 127
    assert _velocity_to_midi(1.0, "midi") == 1
    assert _velocity_to_midi(96.4, "midi") == 96


def test_velocity_output_requires_encoding(tmp_path):
    payload = {
        "schema": "groovemap-onnx-drum-v1",
        "sample_rate": 48000,
        "hop_length": 480,
        "input_name": "audio",
        "onset_output": "onsets",
        "velocity_output": "velocities",
        "labels": ["kick"],
        "midi_notes": [36],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="velocity_encoding"):
        OnnxDrumManifest.load(path)


@pytest.mark.parametrize(
    ("sample_rate", "hop_length"),
    [(0, 480), (48000, 0), (-1, 480), (48000, -1)],
)
def test_manifest_rejects_non_positive_timing(tmp_path, sample_rate, hop_length):
    payload = {
        "schema": "groovemap-onnx-drum-v1",
        "sample_rate": sample_rate,
        "hop_length": hop_length,
        "input_name": "audio",
        "onset_output": "onsets",
        "labels": ["kick"],
        "midi_notes": [36],
    }
    path = tmp_path / "bad-timing.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="positive"):
        OnnxDrumManifest.load(path)

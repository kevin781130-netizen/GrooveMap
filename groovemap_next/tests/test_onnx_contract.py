from pathlib import Path
import numpy as np

from groovemap_next.drum_taxonomy import DRUM_CLASSES_20
from groovemap_next.onnx_drum import OnnxDrumManifest, _as_frames_classes

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

def test_output_layout_bct_is_transposed_to_frames_classes():
    raw = np.arange(1 * 20 * 7, dtype=np.float32).reshape(1, 20, 7)
    converted = _as_frames_classes(raw, layout="B,C,T", class_count=20)
    assert converted.shape == (7, 20)
    assert converted[3, 4] == raw[0, 4, 3]

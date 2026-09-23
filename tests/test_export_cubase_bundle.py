"""整合測試（規格 P3）— export_cubase_bundle 必須用 Tempo Curve Layer
（result.tempo_control_points）驅動 Tempo Track/SMT，Click/Marker 則一律
用 Beat Position Layer（result.beat_times，Ground Truth）的固定拍點網格，
不受 Tempo Curve 縮減影響。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import mido

from core.tempo_events import build_tempo_events
from core.tempo_curve import reduce_tempo_curve
from exporter.midi import export_cubase_bundle, PPQ


class FakeResult:
    def __init__(self, beat_times, bpm_raw, downbeats, beats_per_bar=4,
                 path="song.wav", global_bpm=999.0, confidences=None):
        self.beat_times = np.asarray(beat_times, dtype=float)
        self.bpm_raw = np.asarray(bpm_raw, dtype=float)
        self.bpm_smooth = self.bpm_raw.copy()
        self.downbeats = np.asarray(downbeats, dtype=int)
        self.beats_per_bar = beats_per_bar
        self.path = path
        self.global_bpm = global_bpm  # 刻意跟逐拍數值差很多，確保沒被誤用
        self.demucs_warning = ""

        events = build_tempo_events(self.beat_times, self.bpm_raw)
        confidences = confidences if confidences is not None else [1.0] * len(events)
        self.tempo_control_points, self.accuracy_report = reduce_tempo_curve(
            events, confidences=confidences, ppq=PPQ)


BEAT_TIMES = [1.792, 2.240, 2.688, 3.136]
BPM_RAW = [133.93, 134.42, 133.10, 135.00]


class TestExportCubaseBundle(unittest.TestCase):
    def setUp(self):
        self.result = FakeResult(BEAT_TIMES, BPM_RAW, downbeats=[0, 2])
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_produces_both_midi_and_smt(self):
        files = export_cubase_bundle(self.result, self.tmpdir.name, "song")
        self.assertIn("cubase", files)
        self.assertIn("tempo", files)
        self.assertIn("click", files)
        self.assertIn("marker", files)
        self.assertIn("smt", files)
        for path in files.values():
            self.assertTrue(os.path.isfile(path), path)

    def test_raises_when_tempo_control_points_empty(self):
        self.result.tempo_control_points = []
        with self.assertRaises(RuntimeError):
            export_cubase_bundle(self.result, self.tmpdir.name, "song")

    def test_click_track_beat_count_matches_beat_position_layer(self):
        """Click 的拍點數量必須等於 Beat Position Layer 的拍數，
        跟 Tempo Curve Layer 縮減成幾個控制點無關。"""
        files = export_cubase_bundle(self.result, self.tmpdir.name, "song")
        mid = mido.MidiFile(files["click"])
        click_track = next(t for t in mid.tracks if t.name == "Click")
        note_on_count = sum(1 for msg in click_track if msg.type == "note_on")
        self.assertEqual(note_on_count, len(BEAT_TIMES))

    def test_smt_bpm_values_match_control_points(self):
        files = export_cubase_bundle(self.result, self.tmpdir.name, "song")
        root = ET.parse(files["smt"]).getroot()
        events = root.find('obj[@class="MTempoTrackEvent"]').find(
            'list[@name="TempoEvent"]'
        ).findall("obj")

        self.assertEqual(len(events), len(self.result.tempo_control_points))
        exported_bpms = [round(float(e.find('float[@name="BPM"]').get("value")), 2) for e in events]
        expected_bpms = [round(cp.bpm, 2) for cp in self.result.tempo_control_points]
        self.assertEqual(exported_bpms, expected_bpms)
        self.assertNotIn(round(self.result.global_bpm, 2), exported_bpms)

    def test_include_smt_false_skips_smt_file(self):
        files = export_cubase_bundle(self.result, self.tmpdir.name, "song", include_smt=False)
        self.assertNotIn("smt", files)


if __name__ == "__main__":
    unittest.main()

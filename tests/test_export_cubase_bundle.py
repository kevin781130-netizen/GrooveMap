"""整合測試（規格 P2）— export_cubase_bundle 必須同時輸出 MIDI 與 SMT，
且兩者的 tempo 數值必須與 GUI 逐拍列表（result.bpm_smooth）完全一致，
不可退化成單一固定 BPM。對應使用者回報案例：
    #0001 1.792s 133.93 BPM
    #0002 2.240s 134.42 BPM
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

from exporter.midi import export_cubase_bundle


class FakeResult:
    def __init__(self, beat_times, bpm_smooth, downbeats, beats_per_bar=4,
                 path="song.wav", global_bpm=999.0):
        self.beat_times = np.asarray(beat_times, dtype=float)
        self.bpm_smooth = np.asarray(bpm_smooth, dtype=float)
        self.downbeats = np.asarray(downbeats, dtype=int)
        self.beats_per_bar = beats_per_bar
        self.path = path
        self.global_bpm = global_bpm  # 刻意跟逐拍數值差很多，確保沒被誤用


BEAT_TIMES = [1.792, 2.240, 2.688, 3.136]
BPM_SMOOTH = [133.93, 134.42, 133.10, 135.00]


class TestExportCubaseBundle(unittest.TestCase):
    def setUp(self):
        self.result = FakeResult(BEAT_TIMES, BPM_SMOOTH, downbeats=[0, 2])
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

    def test_smt_bpm_values_match_gui_beat_list(self):
        files = export_cubase_bundle(self.result, self.tmpdir.name, "song")
        root = ET.parse(files["smt"]).getroot()
        events = root.find('obj[@class="MTempoTrackEvent"]').find(
            'list[@name="TempoEvent"]'
        ).findall("obj")

        self.assertEqual(len(events), len(BPM_SMOOTH))
        exported_bpms = [round(float(e.find('float[@name="BPM"]').get("value")), 2) for e in events]
        self.assertEqual(exported_bpms, [round(b, 2) for b in BPM_SMOOTH])

        # 不可以退化成固定 BPM
        self.assertGreater(len(set(exported_bpms)), 1)
        self.assertNotIn(round(self.result.global_bpm, 2), exported_bpms)

    def test_midi_tempo_track_bpm_values_match_gui_beat_list(self):
        files = export_cubase_bundle(self.result, self.tmpdir.name, "song")
        mid = mido.MidiFile(files["tempo"])
        tempo_track = next(t for t in mid.tracks if t.name == "Tempo Map")
        bpms = []
        for msg in tempo_track:
            if msg.type == "set_tempo":
                bpms.append(round(mido.tempo2bpm(msg.tempo), 2))

        # 第一筆 set_tempo 在建立 track 時就先寫入一次（初始值），
        # 後面逐拍各寫一次，因此至少要看到跟 BPM_SMOOTH 一樣多種不同數值
        self.assertGreater(len(set(bpms)), 1)
        for expected in BPM_SMOOTH:
            self.assertIn(round(expected, 2), bpms)

    def test_include_smt_false_skips_smt_file(self):
        files = export_cubase_bundle(self.result, self.tmpdir.name, "song", include_smt=False)
        self.assertNotIn("smt", files)


if __name__ == "__main__":
    unittest.main()

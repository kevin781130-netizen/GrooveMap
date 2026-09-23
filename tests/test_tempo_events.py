"""core/tempo_events.py 單元測試（規格 P2）— 確保 exporter 一律用逐拍資料，禁止 average BPM。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tempo_events import TempoEvent, build_tempo_events, to_dicts


class FakeResult:
    """最小化的 AnalysisResult 替身，只帶測試需要的欄位。"""

    def __init__(self, beat_times, bpm_smooth, global_bpm=999.0):
        self.beat_times = beat_times
        self.bpm_smooth = bpm_smooth
        # 刻意設一個跟逐拍數值差很多的 global_bpm，
        # 如果 from_result 不小心用到它，測試會抓到。
        self.global_bpm = global_bpm


class TestBuildTempoEvents(unittest.TestCase):
    def test_beat_number_is_1_based(self):
        events = build_tempo_events([1.792, 2.240], [133.93, 134.42])
        self.assertEqual([e.beat_number for e in events], [1, 2])

    def test_values_preserved_exactly(self):
        events = build_tempo_events([1.792, 2.240], [133.93, 134.42])
        self.assertEqual(events[0].time, 1.792)
        self.assertEqual(events[0].bpm, 133.93)
        self.assertEqual(events[1].time, 2.240)
        self.assertEqual(events[1].bpm, 134.42)

    def test_mismatched_length_raises(self):
        with self.assertRaises(ValueError):
            build_tempo_events([1.0, 2.0], [120.0])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            build_tempo_events([], [])


class TestFromResult(unittest.TestCase):
    def test_uses_bpm_smooth_not_global_bpm(self):
        result = FakeResult(
            beat_times=[1.792, 2.240],
            bpm_smooth=[133.93, 134.42],
            global_bpm=999.0,
        )
        from core.tempo_events import from_result
        events = from_result(result)
        bpms = [e.bpm for e in events]
        self.assertEqual(bpms, [133.93, 134.42])
        self.assertNotIn(999.0, bpms)

    def test_matches_gui_display_regression_case(self):
        """對應使用者回報案例：
        GUI 顯示 #0001 1.792s 133.93 BPM / #0002 2.240s 134.42 BPM，
        exporter 拿到的 tempo events 必須是同樣的數字，不能被壓成單一固定值。
        """
        result = FakeResult(
            beat_times=[1.792, 2.240, 2.688],
            bpm_smooth=[133.93, 134.42, 133.10],
        )
        from core.tempo_events import from_result
        events = from_result(result)

        self.assertEqual(len(events), 3)
        self.assertEqual(round(events[0].time, 3), 1.792)
        self.assertEqual(round(events[0].bpm, 2), 133.93)
        self.assertEqual(round(events[1].time, 3), 2.240)
        self.assertEqual(round(events[1].bpm, 2), 134.42)

        # 逐拍 BPM 不可以全部一樣（那就是變相退化成固定 BPM 匯出）
        bpm_values = {round(e.bpm, 2) for e in events}
        self.assertGreater(len(bpm_values), 1)


class TestToDicts(unittest.TestCase):
    def test_shape_matches_smt_exporter_input(self):
        events = [TempoEvent(beat_number=1, time=0.0, bpm=120.0)]
        dicts = to_dicts(events)
        self.assertEqual(dicts, [{"time": 0.0, "bpm": 120.0}])


if __name__ == "__main__":
    unittest.main()

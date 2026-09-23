"""core/tempo_factor.py 單元測試（規格 P3 驗收項目 4 — Half/Double Tempo 人工切換）。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.tempo_factor import apply_tempo_factor


class FakeResult:
    def __init__(self, beat_times, bpm_raw, downbeats, confidence=None):
        self.beat_times = np.asarray(beat_times, dtype=float)
        self.bpm_raw = np.asarray(bpm_raw, dtype=float)
        self.bpm_smooth = self.bpm_raw.copy()
        self.beat_confidence = np.asarray(
            confidence if confidence is not None else [1.0] * len(beat_times), dtype=float
        )
        self.downbeats = np.asarray(downbeats, dtype=int)
        self.global_bpm = 999.0
        self.tempo_control_points = []
        self.accuracy_report = None


def _make_result(n=8, bpm=120.0):
    interval = 60.0 / bpm
    beat_times = [i * interval for i in range(n)]
    bpm_raw = [bpm] * n
    downbeats = [0, 4] if n > 4 else [0]
    return FakeResult(beat_times, bpm_raw, downbeats)


class TestApplyTempoFactor(unittest.TestCase):
    def test_invalid_factor_raises(self):
        result = _make_result()
        with self.assertRaises(ValueError):
            apply_tempo_factor(result, 3.0)

    def test_factor_1_is_noop_copy(self):
        result = _make_result()
        new_result = apply_tempo_factor(result, 1.0)
        np.testing.assert_array_equal(new_result.beat_times, result.beat_times)
        self.assertIsNot(new_result, result)

    def test_double_tempo_interpolates_midpoints(self):
        result = _make_result(n=5, bpm=120.0)
        new_result = apply_tempo_factor(result, 2.0)

        self.assertEqual(len(new_result.beat_times), 2 * len(result.beat_times) - 1)
        # 偶數 index 保留原始拍點
        np.testing.assert_allclose(new_result.beat_times[0::2], result.beat_times)
        # 奇數 index 是相鄰兩拍的中點
        expected_mid = (result.beat_times[:-1] + result.beat_times[1:]) / 2.0
        np.testing.assert_allclose(new_result.beat_times[1::2], expected_mid)

    def test_double_tempo_doubles_downbeat_index(self):
        result = _make_result(n=8, bpm=120.0)
        new_result = apply_tempo_factor(result, 2.0)
        np.testing.assert_array_equal(new_result.downbeats, result.downbeats * 2)

    def test_half_tempo_keeps_every_other_beat(self):
        result = _make_result(n=8, bpm=120.0)
        new_result = apply_tempo_factor(result, 0.5)
        np.testing.assert_allclose(new_result.beat_times, result.beat_times[0::2])

    def test_double_then_half_roundtrip_recovers_original_beats(self):
        result = _make_result(n=9, bpm=120.0)
        doubled = apply_tempo_factor(result, 2.0)
        halved = apply_tempo_factor(doubled, 0.5)
        np.testing.assert_allclose(halved.beat_times, result.beat_times)

    def test_rebuilds_tempo_curve_layer(self):
        result = _make_result(n=10, bpm=120.0)
        new_result = apply_tempo_factor(result, 2.0)
        self.assertIsNotNone(new_result.accuracy_report)
        self.assertEqual(new_result.accuracy_report.num_beats, len(new_result.beat_times))
        self.assertTrue(len(new_result.tempo_control_points) > 0)

    def test_original_result_not_mutated(self):
        result = _make_result(n=8, bpm=120.0)
        original_len = len(result.beat_times)
        apply_tempo_factor(result, 2.0)
        self.assertEqual(len(result.beat_times), original_len)


if __name__ == "__main__":
    unittest.main()

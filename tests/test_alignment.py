"""core/alignment.py 單元測試（規格 P4 — Bar Alignment Engine）。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.alignment import (
    apply_first_beat_offset,
    downbeats_from_phase,
    apply_manual_downbeat,
    apply_alignment,
    MIN_OFFSET_MS,
    MAX_OFFSET_MS,
)


class FakeResult:
    def __init__(self, beat_times, bpm_raw, downbeats, beats_per_bar=4, confidence=None):
        self.beat_times = np.asarray(beat_times, dtype=float)
        self.bpm_raw = np.asarray(bpm_raw, dtype=float)
        self.bpm_smooth = self.bpm_raw.copy()
        self.downbeats = np.asarray(downbeats, dtype=int)
        self.beats_per_bar = beats_per_bar
        self.beat_confidence = np.asarray(
            confidence if confidence is not None else [1.0] * len(beat_times), dtype=float
        )
        self.tempo_control_points = []
        self.accuracy_report = None
        self.global_bpm = 999.0


def _make_result(n=12, bpm=120.0, beats_per_bar=4):
    interval = 60.0 / bpm
    beat_times = [i * interval for i in range(n)]
    bpm_raw = [bpm] * n
    downbeats = list(range(0, n, beats_per_bar))
    return FakeResult(beat_times, bpm_raw, downbeats, beats_per_bar=beats_per_bar)


class TestApplyFirstBeatOffset(unittest.TestCase):
    def test_empty_returns_empty(self):
        result = apply_first_beat_offset([], 100.0)
        self.assertEqual(len(result), 0)

    def test_positive_offset_shifts_all_beats(self):
        beat_times = [0.0, 0.5, 1.0]
        shifted = apply_first_beat_offset(beat_times, 200.0)
        np.testing.assert_allclose(shifted, [0.2, 0.7, 1.2])

    def test_negative_offset_shifts_all_beats(self):
        beat_times = [1.0, 1.5, 2.0]
        shifted = apply_first_beat_offset(beat_times, -300.0)
        np.testing.assert_allclose(shifted, [0.7, 1.2, 1.7])

    def test_offset_clamped_to_valid_range(self):
        beat_times = [5.0, 5.5]
        shifted = apply_first_beat_offset(beat_times, 99999.0)
        # clamp 到 MAX_OFFSET_MS(=1000ms) 之後才平移
        np.testing.assert_allclose(shifted, [5.0 + MAX_OFFSET_MS / 1000.0, 5.5 + MAX_OFFSET_MS / 1000.0])

    def test_negative_offset_never_produces_negative_time(self):
        beat_times = [0.05, 0.55, 1.05]
        shifted = apply_first_beat_offset(beat_times, -1000.0)
        self.assertGreaterEqual(shifted[0], 0.0)
        # 間隔要維持不變（只是整條平移到剛好貼齊 0）
        np.testing.assert_allclose(np.diff(shifted), np.diff(beat_times))

    def test_relative_intervals_preserved(self):
        beat_times = [2.0, 2.5, 3.3, 4.0]
        shifted = apply_first_beat_offset(beat_times, 150.0)
        np.testing.assert_allclose(np.diff(shifted), np.diff(beat_times))


class TestDownbeatPhase(unittest.TestCase):
    def test_downbeats_from_phase_basic(self):
        result = downbeats_from_phase(12, phase=0, beats_per_bar=4)
        np.testing.assert_array_equal(result, [0, 4, 8])

    def test_downbeats_from_phase_offset(self):
        result = downbeats_from_phase(12, phase=2, beats_per_bar=4)
        np.testing.assert_array_equal(result, [2, 6, 10])

    def test_apply_manual_downbeat_1_based(self):
        # beat_number=3 (1-based) -> index 2 -> phase 2 (beats_per_bar=4)
        result = apply_manual_downbeat(12, beats_per_bar=4, beat_number=3)
        np.testing.assert_array_equal(result, [2, 6, 10])

    def test_apply_manual_downbeat_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            apply_manual_downbeat(12, beats_per_bar=4, beat_number=99)
        with self.assertRaises(ValueError):
            apply_manual_downbeat(12, beats_per_bar=4, beat_number=0)


class TestApplyAlignment(unittest.TestCase):
    def test_no_change_when_offset_zero_and_no_manual_downbeat(self):
        result = _make_result()
        new_result = apply_alignment(result, first_beat_offset_ms=0.0)
        np.testing.assert_allclose(new_result.beat_times, result.beat_times)
        np.testing.assert_array_equal(new_result.downbeats, result.downbeats)

    def test_offset_applied_to_beat_times(self):
        result = _make_result()
        new_result = apply_alignment(result, first_beat_offset_ms=100.0)
        np.testing.assert_allclose(new_result.beat_times, result.beat_times + 0.1)

    def test_manual_downbeat_overrides_phase(self):
        result = _make_result(n=12, beats_per_bar=4)
        new_result = apply_alignment(result, manual_downbeat_beat_number=2)
        # beat_number=2 (1-based) -> index 1 -> phase 1
        np.testing.assert_array_equal(new_result.downbeats, [1, 5, 9])

    def test_bpm_unchanged_by_pure_offset(self):
        """平移不該改變任何拍子間隔，所以 bpm_raw 完全不變。"""
        result = _make_result(n=10, bpm=133.5)
        new_result = apply_alignment(result, first_beat_offset_ms=-321.0)
        np.testing.assert_allclose(new_result.bpm_raw, result.bpm_raw, atol=1e-9)

    def test_rebuilds_tempo_curve_layer(self):
        result = _make_result(n=20)
        new_result = apply_alignment(result, first_beat_offset_ms=50.0)
        self.assertIsNotNone(new_result.accuracy_report)
        self.assertEqual(new_result.accuracy_report.num_beats, len(new_result.beat_times))
        self.assertTrue(len(new_result.tempo_control_points) > 0)
        # 控制點的 time 必須對齊校正後的 beat_times，不能停留在校正前
        for cp in new_result.tempo_control_points:
            self.assertAlmostEqual(cp.time, new_result.beat_times[cp.beat_index], places=6)

    def test_original_result_not_mutated(self):
        result = _make_result()
        original_times = result.beat_times.copy()
        apply_alignment(result, first_beat_offset_ms=500.0, manual_downbeat_beat_number=3)
        np.testing.assert_allclose(result.beat_times, original_times)

    def test_empty_beat_times_returns_copy_without_error(self):
        result = FakeResult([], [], [])
        new_result = apply_alignment(result, first_beat_offset_ms=100.0)
        self.assertEqual(len(new_result.beat_times), 0)


if __name__ == "__main__":
    unittest.main()

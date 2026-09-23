"""core/anchors.py 單元測試（規格 P5 — Human Anchor Hard Constraint）。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.anchors import (
    Anchor,
    find_nearest_transient,
    nearest_beat_index,
    resolve_anchors,
    apply_anchors_to_beat_times,
    derive_downbeats_from_anchors,
    apply_anchors,
)


class FakeResult:
    def __init__(self, beat_times, bpm_raw, downbeats, beats_per_bar=4, confidence=None):
        self.beat_times = np.asarray(beat_times, dtype=float)
        self.bpm_raw = np.asarray(bpm_raw, dtype=float)
        self.bpm_smooth = self.bpm_raw.copy()
        self.downbeats = np.asarray(downbeats, dtype=int)
        self.beats_per_bar = beats_per_bar
        self.beat_confidence = np.asarray(
            confidence if confidence is not None else [1.0] * len(beat_times), dtype=float)
        self.tempo_control_points = []
        self.accuracy_report = None
        self.tempo_density = "balanced"
        self.max_tempo_nodes = None
        self.anchors = []
        self.global_bpm = 999.0


def _make_result(n=64, bpm=120.0, beats_per_bar=4, jitter=0.0, seed=1):
    rng = np.random.RandomState(seed)
    interval = 60.0 / bpm
    beat_times = np.array([i * interval for i in range(n)])
    if jitter:
        beat_times = beat_times + rng.normal(0, jitter, n).cumsum() * 0.01
        beat_times = np.sort(beat_times)
    bpm_raw = np.full(n, bpm)
    downbeats = np.arange(0, n, beats_per_bar)
    return FakeResult(beat_times, bpm_raw, downbeats, beats_per_bar=beats_per_bar)


class TestNearestBeatIndex(unittest.TestCase):
    def test_finds_closest(self):
        beat_times = [0.0, 1.0, 2.0, 3.0]
        self.assertEqual(nearest_beat_index(beat_times, 2.1), 2)
        self.assertEqual(nearest_beat_index(beat_times, 0.4), 0)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            nearest_beat_index([], 1.0)


class TestFindNearestTransient(unittest.TestCase):
    def test_none_onset_env_returns_original(self):
        self.assertEqual(find_nearest_transient(None, 44100, 512, 4.32), 4.32)

    def test_empty_onset_env_returns_original(self):
        self.assertEqual(find_nearest_transient(np.zeros(0), 44100, 512, 4.32), 4.32)


class TestResolveAnchors(unittest.TestCase):
    def test_resolves_beat_index(self):
        beat_times = [0.0, 0.5, 1.0, 1.5, 2.0]
        anchors = [Anchor(time=1.02, bar=1, beat=1)]
        resolved = resolve_anchors(anchors, beat_times)
        self.assertEqual(resolved[0].beat_index, 2)
        self.assertEqual(resolved[0].time, 1.02)  # 原始 anchor 物件不被修改


class TestApplyAnchorsToBeatTimes(unittest.TestCase):
    def test_overwrites_nearest_beat_exactly(self):
        beat_times = [0.0, 0.5, 1.0, 1.5]
        anchors = [Anchor(time=1.05, bar=1, beat=1, beat_index=2)]
        new_times = apply_anchors_to_beat_times(beat_times, anchors)
        self.assertEqual(new_times[2], 1.05)
        # 其餘拍子不受影響
        self.assertEqual(new_times[0], 0.0)
        self.assertEqual(new_times[1], 0.5)
        self.assertEqual(new_times[3], 1.5)

    def test_stays_strictly_increasing(self):
        beat_times = [0.0, 0.5, 1.0, 1.5]
        # Anchor 把第 2 拍的時間往後推到超過第 3 拍原本的時間
        anchors = [Anchor(time=1.6, bar=1, beat=1, beat_index=2)]
        new_times = apply_anchors_to_beat_times(beat_times, anchors)
        self.assertTrue(np.all(np.diff(new_times) > 0))


class TestDeriveDownbeatsFromAnchors(unittest.TestCase):
    def test_no_anchors_returns_none(self):
        self.assertIsNone(derive_downbeats_from_anchors(10, 4, []))

    def test_single_anchor_reproduces_modulo_phase(self):
        # Anchor 在 index=2 是 Bar1 Beat1 → phase=2，跟 P4 的 modulo 邏輯一致
        anchors = [Anchor(time=1.0, bar=1, beat=1, beat_index=2)]
        result = derive_downbeats_from_anchors(12, 4, anchors)
        np.testing.assert_array_equal(result, [2, 6, 10])

    def test_two_anchors_consistent_span_matches_expected(self):
        # Bar1 Beat1 在 index 0，Bar3 Beat1 在 index 8（跟 4/4 拍剛好對上：
        # 2 個小節 = 8 拍），中間應該完全依照 4 拍一小節排列
        anchors = [
            Anchor(time=0.0, bar=1, beat=1, beat_index=0),
            Anchor(time=4.0, bar=3, beat=1, beat_index=8),
        ]
        result = derive_downbeats_from_anchors(16, 4, anchors)
        np.testing.assert_array_equal(result, [0, 4, 8, 12])

    def test_inconsistent_anchor_span_does_not_crash_and_stays_local(self):
        # 兩個 Anchor 之間實際拍數（10）跟理論值（8）對不起來——
        # 代表中間漏拍或多抓拍，只要求不崩潰、且第二個 Anchor 自己的
        # 位置仍然正確標記為 downbeat
        anchors = [
            Anchor(time=0.0, bar=1, beat=1, beat_index=0),
            Anchor(time=5.0, bar=3, beat=1, beat_index=10),
        ]
        result = derive_downbeats_from_anchors(20, 4, anchors)
        self.assertIn(0, result)
        self.assertIn(10, result)


class TestApplyAnchors(unittest.TestCase):
    def test_no_anchors_is_noop(self):
        result = _make_result()
        new_result = apply_anchors(result, [])
        np.testing.assert_allclose(new_result.beat_times, result.beat_times)
        self.assertEqual(new_result.anchors, [])

    def test_anchor_forces_control_point_at_its_beat(self):
        result = _make_result(n=64, bpm=120.0)
        # 隨便挑一個不是頭尾的拍子當 Anchor
        anchor_time = float(result.beat_times[30])
        anchors = [Anchor(time=anchor_time, bar=8, beat=3)]
        new_result = apply_anchors(result, anchors)

        forced_idx = new_result.anchors[0].beat_index
        cp_indices = {cp.beat_index for cp in new_result.tempo_control_points}
        self.assertIn(forced_idx, cp_indices)

    def test_anchor_time_becomes_exact_beat_time(self):
        result = _make_result(n=64, bpm=120.0, jitter=1.0)
        target_idx = 20
        precise_time = float(result.beat_times[target_idx]) + 0.007  # 模擬使用者更精確的校正
        anchors = [Anchor(time=precise_time, bar=6, beat=1)]
        new_result = apply_anchors(result, anchors)
        idx = new_result.anchors[0].beat_index
        self.assertAlmostEqual(new_result.beat_times[idx], precise_time, places=9)

    def test_downbeats_updated_from_anchor(self):
        result = _make_result(n=32, bpm=120.0, beats_per_bar=4)
        # 指定 index=1 是 Bar1 Beat1（模擬原本 downbeat 判斷錯位 1 拍）
        anchor_time = float(result.beat_times[1])
        anchors = [Anchor(time=anchor_time, bar=1, beat=1)]
        new_result = apply_anchors(result, anchors)
        np.testing.assert_array_equal(new_result.downbeats, np.arange(1, 32, 4))

    def test_rebuild_produces_accuracy_report(self):
        result = _make_result(n=100, bpm=125.0)
        anchors = [
            Anchor(time=float(result.beat_times[0]), bar=1, beat=1),
            Anchor(time=float(result.beat_times[50]), bar=13, beat=3),
            Anchor(time=float(result.beat_times[99]), bar=25, beat=4),
        ]
        new_result = apply_anchors(result, anchors)
        self.assertIsNotNone(new_result.accuracy_report)
        self.assertEqual(new_result.accuracy_report.num_beats, len(new_result.beat_times))
        cp_indices = {cp.beat_index for cp in new_result.tempo_control_points}
        for a in new_result.anchors:
            self.assertIn(a.beat_index, cp_indices)

    def test_original_result_not_mutated(self):
        result = _make_result(n=32)
        original_times = result.beat_times.copy()
        apply_anchors(result, [Anchor(time=float(result.beat_times[5]), bar=2, beat=2)])
        np.testing.assert_allclose(result.beat_times, original_times)

    def test_empty_beat_times_returns_copy(self):
        result = FakeResult([], [], [])
        new_result = apply_anchors(result, [Anchor(time=1.0, bar=1, beat=1)])
        self.assertEqual(len(new_result.beat_times), 0)


if __name__ == "__main__":
    unittest.main()

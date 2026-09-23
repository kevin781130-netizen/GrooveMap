"""core/tempo_curve.py 單元測試（規格 P3）— TEMPO MAP ACCURACY FIRST。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.tempo_events import TempoEvent
from core.tempo_curve import (
    AccuracyReport,
    reduce_tempo_curve,
    reduce_tempo_curve_with_density,
    DENSITY_PRESETS,
    TARGET_AVG_MS,
    MAX_ERROR_MS,
)

PPQ = 960


def _constant_tempo_events(n=20, bpm=120.0, start=0.0):
    interval = 60.0 / bpm
    return [TempoEvent(beat_number=i + 1, time=start + i * interval, bpm=bpm) for i in range(n)]


def _wobbly_live_events(n=150, base_bpm=120.0, seed=7):
    rng = np.random.RandomState(seed)
    drift = np.cumsum(rng.normal(0, 0.25, n))
    drift = drift - np.linspace(0, drift[-1], n)
    bpm_curve = base_bpm + drift
    if n > 90:
        bpm_curve[60:75] -= np.linspace(0, 12, 15)
        bpm_curve[75:90] += np.linspace(0, 12, 15)
    beat_times = np.zeros(n)
    for i in range(1, n):
        beat_times[i] = beat_times[i - 1] + 60.0 / bpm_curve[i - 1]
    return [TempoEvent(beat_number=i + 1, time=float(beat_times[i]), bpm=float(bpm_curve[i])) for i in range(n)]


class TestReduceTempoCurveEmpty(unittest.TestCase):
    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            reduce_tempo_curve([])

    def test_mismatched_confidence_length_raises(self):
        events = _constant_tempo_events(5)
        with self.assertRaises(ValueError):
            reduce_tempo_curve(events, confidences=[1.0, 1.0])


class TestConstantTempo(unittest.TestCase):
    def test_minimal_density_when_tempo_is_stable(self):
        events = _constant_tempo_events(30, bpm=120.0)
        cps, report = reduce_tempo_curve(events, ppq=PPQ)

        # 完全穩定的速度，只需要頭尾兩個控制點就能精準重建每一拍
        self.assertEqual(report.num_points, 2)
        self.assertLess(report.avg_error_ms, 1.0)
        self.assertLess(report.max_error_ms, 1.0)
        self.assertEqual(report.density_label, "Low")
        self.assertEqual(report.quality_label, "良好")

    def test_control_points_reference_original_beats(self):
        # cp.bpm 是「這一段的平均 BPM」，等速情況下數學上等於瞬時值，
        # 但浮點運算會有極小誤差，所以用 assertAlmostEqual。
        events = _constant_tempo_events(10, bpm=100.0)
        cps, _ = reduce_tempo_curve(events, ppq=PPQ)
        for cp in cps:
            self.assertEqual(cp.time, events[cp.beat_index].time)
            self.assertAlmostEqual(cp.bpm, events[cp.beat_index].bpm, places=6)


class TestVariableTempo(unittest.TestCase):
    def _build_sudden_jump_events(self):
        # 前 15 拍 100 BPM，後 15 拍突然跳到 140 BPM（模擬段落突然變速）
        events = []
        t = 0.0
        for i in range(15):
            events.append(TempoEvent(beat_number=i + 1, time=t, bpm=100.0))
            t += 60.0 / 100.0
        for i in range(15, 30):
            events.append(TempoEvent(beat_number=i + 1, time=t, bpm=140.0))
            t += 60.0 / 140.0
        return events

    def test_density_auto_increases_to_meet_accuracy_target(self):
        events = self._build_sudden_jump_events()
        cps, report = reduce_tempo_curve(events, ppq=PPQ)

        self.assertLessEqual(report.avg_error_ms, TARGET_AVG_MS)
        self.assertLessEqual(report.max_error_ms, MAX_ERROR_MS)
        # 速度有明顯跳變，光靠頭尾兩點不夠，一定要加更多控制點
        self.assertGreater(report.num_points, 2)

    def test_low_confidence_beats_not_promoted_unless_necessary(self):
        events = self._build_sudden_jump_events()
        n = len(events)
        # 除了頭尾，其餘全部低信心；跳變點本身（第 15 拍附近）也是低信心
        confidences = [1.0] + [0.1] * (n - 2) + [1.0]

        cps, report = reduce_tempo_curve(events, confidences=confidences, ppq=PPQ)

        # 演算法仍必須達標（走 fallback：連低信心拍子都加進去也要達標）
        self.assertLessEqual(report.avg_error_ms, TARGET_AVG_MS)
        self.assertLessEqual(report.max_error_ms, MAX_ERROR_MS)


class TestAccuracyReportLabels(unittest.TestCase):
    def test_density_label_thresholds(self):
        r = AccuracyReport(num_points=2, num_beats=20)   # 0.10
        self.assertEqual(r.density_label, "Low")
        r = AccuracyReport(num_points=6, num_beats=20)    # 0.30
        self.assertEqual(r.density_label, "Medium")
        r = AccuracyReport(num_points=16, num_beats=20)   # 0.80
        self.assertEqual(r.density_label, "High")

    def test_quality_label_thresholds(self):
        self.assertEqual(AccuracyReport(avg_error_ms=3.0).quality_label, "良好")
        self.assertEqual(AccuracyReport(avg_error_ms=8.0).quality_label, "可接受")
        self.assertEqual(AccuracyReport(avg_error_ms=15.0).quality_label, "不合格")

    def test_summary_shape(self):
        r = AccuracyReport(avg_error_ms=3.0, max_error_ms=5.0, num_points=4, num_beats=40)
        s = r.summary()
        self.assertIn("Average Beat Error", s)
        self.assertIn("Maximum Beat Error", s)
        self.assertIn("Tempo Points", s)
        self.assertIn("Density", s)


class TestMaxNodesCap(unittest.TestCase):
    def test_stops_at_max_nodes_even_if_target_unmet(self):
        events = _wobbly_live_events(n=150)
        cps, report = reduce_tempo_curve(events, ppq=PPQ, max_nodes=5)

        self.assertLessEqual(report.num_points, 5)
        self.assertTrue(report.capped or report.avg_error_ms <= TARGET_AVG_MS)

    def test_capped_flag_false_when_target_met_before_limit(self):
        events = _constant_tempo_events(30, bpm=120.0)
        cps, report = reduce_tempo_curve(events, ppq=PPQ, max_nodes=100)
        self.assertFalse(report.capped)

    def test_uncapped_by_default(self):
        events = _wobbly_live_events(n=150)
        cps, report = reduce_tempo_curve(events, ppq=PPQ)
        self.assertFalse(report.capped)
        self.assertLessEqual(report.avg_error_ms, TARGET_AVG_MS)


class TestDensityPresets(unittest.TestCase):
    def test_sparse_has_fewer_or_equal_points_than_detailed(self):
        events = _wobbly_live_events(n=150)
        cps_sparse, report_sparse = reduce_tempo_curve_with_density(events, ppq=PPQ, density="sparse")
        cps_detailed, report_detailed = reduce_tempo_curve_with_density(events, ppq=PPQ, density="detailed")
        self.assertLessEqual(report_sparse.num_points, report_detailed.num_points)

    def test_unknown_density_falls_back_to_balanced(self):
        events = _constant_tempo_events(10, bpm=120.0)
        cps_a, _ = reduce_tempo_curve_with_density(events, ppq=PPQ, density="not-a-real-density")
        cps_b, _ = reduce_tempo_curve_with_density(events, ppq=PPQ, density="balanced")
        self.assertEqual(len(cps_a), len(cps_b))

    def test_explicit_max_nodes_overrides_preset(self):
        events = _wobbly_live_events(n=150)
        cps, report = reduce_tempo_curve_with_density(
            events, ppq=PPQ, density="detailed", max_nodes=5)
        self.assertLessEqual(report.num_points, 5)

    def test_balanced_preset_matches_five_minute_live_recording_budget(self):
        """5 分鐘 Live 錄音約 120 BPM 時約 600 拍，Balanced 模式的
        max_nodes=100 應該足以在合理誤差內完成（用較溫和的漂移量模擬）。"""
        n = 300  # 約 2.5 分鐘份量，控制測試執行時間
        events = _wobbly_live_events(n=n, seed=3)
        cps, report = reduce_tempo_curve_with_density(events, ppq=PPQ, density="balanced")
        self.assertLessEqual(report.num_points, DENSITY_PRESETS["balanced"]["max_nodes"])


if __name__ == "__main__":
    unittest.main()

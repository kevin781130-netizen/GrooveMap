"""processor/tempo_scaler.py 單元測試（規格 P5）。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from processor.tempo_scaler import scale_bpm, scale_bpm_array, VALID_MULTIPLIERS


class TestScaleBpm(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(scale_bpm(133.55, 2.0), 267.1, places=6)
        self.assertAlmostEqual(scale_bpm(134.0, 0.5), 67.0, places=6)
        self.assertAlmostEqual(scale_bpm(120.0, 1.0), 120.0, places=6)

    def test_invalid_multiplier_raises(self):
        with self.assertRaises(ValueError):
            scale_bpm(120.0, 3.0)

    def test_array_formula(self):
        arr = scale_bpm_array([120.0, 130.0, 140.0], 2.0)
        np.testing.assert_allclose(arr, [240.0, 260.0, 280.0])

    def test_array_invalid_multiplier_raises(self):
        with self.assertRaises(ValueError):
            scale_bpm_array([120.0], 1.5)


if __name__ == "__main__":
    unittest.main()

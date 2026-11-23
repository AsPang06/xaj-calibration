# -*- coding: utf-8 -*-
"""精度指标的单元测试：解析解与边界条件。"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xaj.metrics import (dc, evaluate, grade, kge, rmse,  # noqa: E402
                         runoff_depth_mm)


class TestDC(unittest.TestCase):
    def test_perfect_match(self):
        obs = np.array([10.0, 20.0, 30.0, 40.0])
        self.assertAlmostEqual(dc(obs, obs), 1.0, places=12)

    def test_known_value(self):
        obs = np.array([1.0, 2.0, 3.0])
        sim = np.array([1.5, 2.5, 3.5])      # 整体偏高 0.5
        # 1 − Σ0.25 / Σ2 = 1 − 0.75/2
        self.assertAlmostEqual(dc(obs, sim), 1.0 - 0.75 / 2.0, places=12)

    def test_mean_bias_penalised(self):
        obs = np.array([1.0, 2.0, 3.0, 4.0])
        self.assertLess(dc(obs, obs * 1.1), 1.0)

    def test_constant_observation_returns_nan(self):
        obs = np.full(5, 7.0)
        self.assertTrue(math.isnan(dc(obs, obs)))


class TestRMSE(unittest.TestCase):
    def test_value(self):
        obs = np.array([0.0, 0.0, 0.0])
        sim = np.array([3.0, 0.0, 0.0])
        self.assertAlmostEqual(rmse(obs, sim), math.sqrt(3.0), places=12)

    def test_zero_for_identical(self):
        q = np.array([5.0, 1.0, 9.0])
        self.assertEqual(rmse(q, q), 0.0)


class TestKGE(unittest.TestCase):
    def test_perfect(self):
        obs = np.array([1.0, 2.0, 4.0, 8.0])
        self.assertAlmostEqual(kge(obs, obs), 1.0, places=12)

    def test_decomposition_symmetric(self):
        """sim = 2·obs 时 r=1, α=2, β=2 → KGE = 1−√2。"""
        obs = np.array([1.0, 2.0, 4.0, 8.0])
        self.assertAlmostEqual(kge(obs, obs * 2.0), 1.0 - math.sqrt(2.0), places=10)


class TestRunoffDepth(unittest.TestCase):
    def test_conversion_factor(self):
        # 1 m³/s 持续一个 6 h 时段，在 2000 km² 上折合 0.0108 mm
        self.assertAlmostEqual(runoff_depth_mm([1.0]), 0.0108, places=12)

    def test_linear(self):
        self.assertAlmostEqual(runoff_depth_mm([1.0, 2.0, 3.0]), 6 * 0.0108, places=12)


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        self.obs = np.array([10.0, 50.0, 100.0, 30.0])
        self.sim = np.array([12.0, 45.0, 110.0, 28.0])

    def test_keys(self):
        out = evaluate(self.obs, self.sim)
        for key in ("dc", "rmse", "kge", "peak_obs", "peak_sim", "peak_err_pct",
                    "peak_time_err_h", "vol_obs_mm", "vol_sim_mm", "vol_err_pct"):
            self.assertIn(key, out)

    def test_peak_and_time_error(self):
        obs = np.array([10.0, 100.0, 20.0, 5.0])
        sim = np.array([10.0, 20.0, 100.0, 5.0])
        out = evaluate(obs, sim)
        self.assertEqual(out["peak_time_err_h"], 6.0)
        self.assertAlmostEqual(out["peak_err_pct"], 0.0, places=12)

    def test_volume_error_sign(self):
        out = evaluate(self.obs, self.obs * 1.1)
        self.assertAlmostEqual(out["vol_err_pct"], 10.0, places=10)


class TestGrade(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(grade(0.95), "甲级")
        self.assertEqual(grade(0.90), "甲级")
        self.assertEqual(grade(0.899999), "乙级")
        self.assertEqual(grade(0.70), "乙级")
        self.assertEqual(grade(0.699999), "丙级")
        self.assertEqual(grade(0.50), "丙级")
        self.assertEqual(grade(0.499999), "不及格")

    def test_nan_is_failing(self):
        self.assertEqual(grade(float("nan")), "不及格")


if __name__ == "__main__":
    unittest.main(verbosity=2)

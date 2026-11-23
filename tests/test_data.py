# -*- coding: utf-8 -*-
"""数据完整性测试：场次、权重、参数表、换算系数与数据包一致性。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xaj.io import (CALIBRATION_EVENTS, STATION_WEIGHTS,  # noqa: E402
                    VALIDATION_EVENTS, areal_rainfall, load_basin_info,
                    load_bounds, load_events, load_index, load_param_table,
                    load_params)
from xaj.model import PARAM_NAMES, Params  # noqa: E402


class TestDataSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = load_events()

    def test_four_events(self):
        self.assertEqual(list(self.events), ["event1", "event2", "event3", "event4"])

    def test_event_length_and_columns(self):
        for eid, ev in self.events.items():
            with self.subTest(event=eid):
                df = ev["df"]
                self.assertEqual(len(df), 40)
                self.assertEqual(ev["issues"], [])
                for col in ("时间", "面雨量P(mm)", "蒸发皿EM(mm)", "实测流量Q(m3/s)"):
                    self.assertIn(col, df.columns)
                self.assertAlmostEqual(
                    float(pd.to_datetime(df["时间"]).diff().dt.total_seconds().dropna().min()),
                    6 * 3600.0)

    def test_no_missing_or_negative(self):
        for eid, ev in self.events.items():
            df = ev["df"].drop(columns=["时间"])
            with self.subTest(event=eid):
                self.assertFalse(df.isna().any().any())
                self.assertTrue((df >= 0).all().all())

    def test_station_weights(self):
        self.assertEqual(len(STATION_WEIGHTS), 6)
        self.assertAlmostEqual(sum(STATION_WEIGHTS.values()), 1.0, places=9)

    def test_areal_rainfall_matches_package(self):
        """按泰森权重重算的面雨量应与数据包“面雨量P”列一致。

        数据包中的面雨量按两位小数取整，且权重只给到 0.01，
        因此允许 0.05 mm 的舍入差异。
        """
        for eid, ev in self.events.items():
            df = ev["df"]
            recalculated = areal_rainfall(df)
            with self.subTest(event=eid):
                np.testing.assert_allclose(recalculated, df["面雨量P(mm)"].to_numpy(float),
                                           rtol=0, atol=0.05)

    def test_state0_keys(self):
        for eid, ev in self.events.items():
            with self.subTest(event=eid):
                self.assertEqual(set(ev["state0"]),
                                 {"WU", "WL", "WD", "S", "QS", "QI", "QG"})
                self.assertGreaterEqual(ev["state0"]["S"], 0.0)


class TestParameters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = load_param_table()
        cls.bounds = load_bounds()
        cls.initial = load_params()

    def test_sixteen_parameters(self):
        self.assertEqual(len(PARAM_NAMES), 16)
        self.assertEqual(len(self.table), 16)
        self.assertEqual(list(self.table["参数"]), list(PARAM_NAMES))
        self.assertEqual(set(self.bounds), set(PARAM_NAMES))

    def test_bounds_order_and_initial_inside(self):
        for name in PARAM_NAMES:
            lo, hi = self.bounds[name]
            with self.subTest(param=name):
                self.assertLess(lo, hi)
                value = getattr(self.initial, name)
                self.assertGreaterEqual(value, lo)
                self.assertLessEqual(value, hi)

    def test_initial_inside_capacity(self):
        prm = self.initial
        self.assertGreater(prm.WUM, 0)
        self.assertGreater(prm.WLM, 0)
        self.assertGreater(prm.WDM, 0)
        self.assertLessEqual(prm.IM, 1.0)
        self.assertLessEqual(prm.B, 2.0)
        for name in ("CS", "CI", "CG"):
            self.assertTrue(0 < getattr(prm, name) < 1)


class TestBasinInfo(unittest.TestCase):
    def test_area_and_timestep(self):
        info = load_basin_info()
        text = " ".join(f"{k}={v}" for k, v in info.items())
        self.assertIn("2000", text)
        self.assertIn("6", text)

    def test_event_split(self):
        self.assertEqual(CALIBRATION_EVENTS, ("event1", "event2", "event3"))
        self.assertEqual(VALIDATION_EVENTS, ("event4",))
        self.assertEqual(len(load_index()), 4)

    def test_params_round_trip(self):
        prm = load_params()
        self.assertIsInstance(prm, Params)
        self.assertAlmostEqual(prm.WM, prm.WUM + prm.WLM + prm.WDM, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""率定流程测试：目标函数、结果复现与“率定期—检验期”一致性。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xaj.calibrate import (EventData, MultiEventObjective,  # noqa: E402
                           load_calibration_events, simulate_event)
from xaj.io import load_bounds, load_events, load_params  # noqa: E402
from xaj.metrics import evaluate  # noqa: E402
from xaj.model import Params  # noqa: E402

RESULT = ROOT / "outputs" / "calibration" / "calibration_result.json"


def _events(ids) -> list[EventData]:
    raw = load_events(ids)
    return [EventData.from_raw(eid, raw[eid]) for eid in ids]


class TestObjective(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = load_calibration_events(["event1", "event2", "event3"])
        cls.bounds = load_bounds()
        cls.objective = MultiEventObjective(cls.events, cls.bounds)

    def test_bounds_shape(self):
        self.assertEqual(len(self.bounds), 16)
        self.assertEqual(self.objective.ndim, 16)

    def test_unit_round_trip(self):
        unit = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8,
                         0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85])
        prm = self.objective.to_params(unit)
        back = self.objective.to_unit(prm)
        np.testing.assert_allclose(back, unit, rtol=0, atol=1e-12)

    def test_details_keys(self):
        unit = np.full(16, 0.5)
        details = self.objective.details(unit)
        self.assertEqual(set(details), {"J", "mean_dc", "penalty", "events"})
        self.assertEqual(set(details["events"]), {"event1", "event2", "event3"})
        for row in details["events"].values():
            self.assertIn("dc", row)
            self.assertIn("rmse", row)
            self.assertIn("Q_sim", row)

    def test_objective_equals_details(self):
        unit = np.full(16, 0.5)
        details = self.objective.details(unit)
        self.assertAlmostEqual(self.objective(unit), details["J"], places=12)
        self.assertAlmostEqual(details["J"],
                               1.0 - details["mean_dc"] + details["penalty"], places=12)

    def test_worse_than_initial(self):
        """初值参数的目标函数值应明显大于率定后的最优值。"""
        initial_unit = self.objective.to_unit(load_params())
        self.assertGreater(self.objective(initial_unit), 1e-3)


@unittest.skipUnless(RESULT.exists(), "尚未运行 scripts/01_calibrate.py")
class TestCalibrationResult(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(RESULT.read_text(encoding="utf-8"))
        cls.prm = Params.from_mapping(cls.result["params"])

    def test_all_calibration_events_grade_a(self):
        for eid, m in self.result["metrics"].items():
            with self.subTest(event=eid):
                self.assertGreater(m["dc"], 0.90)
                self.assertLess(abs(m["peak_err_pct"]), 5.0)
                self.assertLess(abs(m["vol_err_pct"]), 5.0)

    def test_validation_event_grade_a(self):
        m = self.result["validation"]
        self.assertGreater(m["dc"], 0.90)
        self.assertLess(abs(m["peak_err_pct"]), 5.0)

    def test_validate_without_recalibration(self):
        """检验场次必须用率定参数直接模拟（不得回调参数）。"""
        raw = load_events(["event4"])
        ev = EventData.from_raw("event4", raw["event4"])
        q = simulate_event(ev, self.prm)
        m = evaluate(ev.Q_obs, q)
        self.assertAlmostEqual(m["dc"], self.result["validation"]["dc"], places=10)

    def test_objective_reproduced(self):
        events = load_calibration_events(["event1", "event2", "event3"])
        objective = MultiEventObjective(events, load_bounds())
        value = objective(objective.to_unit(self.prm))
        self.assertAlmostEqual(value, self.result["objective"], places=9)

    def test_de_history_monotone(self):
        history = self.result["de_history"]
        self.assertGreater(len(history), 50)
        # 记录的是每代最优值，允许持平但不允许变差
        for a, b in zip(history[:-1], history[1:]):
            self.assertLessEqual(b, a + 1e-12)

    def test_population_stored(self):
        path = ROOT / "outputs" / "calibration" / "de_population.npz"
        if not path.exists():
            self.skipTest("未保存 DE 种群")
        data = np.load(path)
        self.assertEqual(data["unit"].shape[1], 16)
        self.assertEqual(len(data["unit"]), len(data["energy"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""模型单元测试：与数据包参考实现逐位对照、水量平衡与水动力学关系。

运行：``python -m unittest discover -s tests -v``
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xaj.io import (load_bounds, load_index, load_params, state0_from_row)  # noqa: E402
from xaj.model import (DT_H, F_BASIN_KM2, U_CONV, Params, simulate)  # noqa: E402
from xaj.validator import load_event  # noqa: E402

EVENTS = ROOT / "data" / "raw" / "events"
KEYS = ("Q", "Q_in", "QS", "QI", "QG", "R", "E", "W", "S",
        "RS_mm", "RI_mm", "RG_mm")


def load_reference():
    """按文件路径加载数据包原始模型（不改动 data/raw 中的文件）。"""
    path = ROOT / "data" / "raw" / "xaj_model_reference.py"
    spec = importlib.util.spec_from_file_location("xaj_model_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_events() -> dict:
    """读取 4 场观测，返回 {eid: (P, EM, state0)}。"""
    index = load_index().set_index("场次编号")
    data = {}
    for eid in index.index:
        df, issues = load_event(EVENTS / f"{eid}.csv")
        assert not issues, issues
        data[eid] = (df["面雨量P(mm)"].to_numpy(float),
                     df["蒸发皿EM(mm)"].to_numpy(float),
                     state0_from_row(index.loc[eid]))
    return data


class TestModelEquivalence(unittest.TestCase):
    """重写模型必须与数据包原始实现完全一致（否则后续率定结果不可信）。"""

    @classmethod
    def setUpClass(cls):
        cls.ref = load_reference()
        cls.events = read_events()
        cls.bounds = load_bounds()
        cls.initial = load_params()
        cls.calibrated = None
        result = ROOT / "outputs" / "calibration" / "calibration_result.json"
        if result.exists():
            cls.calibrated = Params.from_mapping(
                json.loads(result.read_text(encoding="utf-8"))["params"])

    def _cases(self):
        rng = np.random.default_rng(20231122)
        cases = [self.initial]
        if self.calibrated is not None:
            cases.append(self.calibrated)
        names = list(self.bounds)
        for _ in range(4):
            values = {}
            for name in names:
                lo, hi = self.bounds[name]
                # 取参考范围的中段，避免极端组合导致数值震荡
                values[name] = float(rng.uniform(lo + 0.1 * (hi - lo), hi - 0.1 * (hi - lo)))
            cases.append(Params.from_mapping(values))
        return cases

    def test_matches_reference_implementation(self):
        for prm in self._cases():
            for eid, (P, EM, state0) in self.events.items():
                ours = simulate(P, EM, prm, state0)
                theirs = self.ref.simulate(P, EM, prm.as_dict(), state0)
                for key in KEYS:
                    a = np.asarray(ours[key], dtype=float)
                    b = np.asarray(theirs[key], dtype=float)
                    scale = max(1.0, float(np.max(np.abs(b))))
                    with self.subTest(param=prm.K, event=eid, key=key):
                        self.assertLess(float(np.max(np.abs(a - b))) / scale, 1e-12)
                    self.assertEqual(a.shape, b.shape)

    def test_state_end_keys(self):
        """衔接状态必须完整，便于分段模拟或做预报延展。"""
        P, EM, state0 = self.events["event1"]
        prm = self.calibrated or self.initial
        out = simulate(P, EM, prm, state0)
        self.assertEqual(set(out["state_end"]),
                         {"WU", "WL", "WD", "S", "QS", "QI", "QG"})
        self.assertAlmostEqual(out["state_end"]["QS"], out["QS"][-1], places=12)
        self.assertAlmostEqual(out["state_end"]["QG"], out["QG"][-1], places=12)


class TestModelPhysics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = read_events()
        cls.initial = load_params()
        result = ROOT / "outputs" / "calibration" / "calibration_result.json"
        cls.prm = cls.initial
        if result.exists():
            cls.prm = Params.from_mapping(
                json.loads(result.read_text(encoding="utf-8"))["params"])

    def test_output_shapes(self):
        P, EM, state0 = self.events["event2"]
        out = simulate(P, EM, self.prm, state0)
        for key in KEYS + ("state_end",):
            self.assertIn(key, out)
        for key in KEYS:
            self.assertEqual(len(out[key]), len(P))

    def test_dry_day_storage_decreases_by_evaporation(self):
        """无雨时段不产流，土壤蓄水量恰好减少实际蒸散发量。"""
        for eid, (P, EM, state0) in self.events.items():
            out = simulate(P, EM, self.prm, state0)
            w0 = (min(state0["WU"], self.prm.WUM) + min(state0["WL"], self.prm.WLM)
                  + min(state0["WD"], self.prm.WDM))
            w = np.concatenate([[w0], out["W"]])
            for t in np.flatnonzero(np.asarray(P) == 0.0):
                with self.subTest(event=eid, step=int(t)):
                    self.assertAlmostEqual(out["R"][t], 0.0, places=12)
                    self.assertAlmostEqual(w[t + 1] - w[t], -out["E"][t], places=9)

    def test_state_within_capacity(self):
        for eid, (P, EM, state0) in self.events.items():
            out = simulate(P, EM, self.prm, state0)
            with self.subTest(event=eid):
                self.assertTrue(np.all(out["W"] >= -1e-9))
                self.assertTrue(np.all(out["W"] <= self.prm.WM + 1e-9))
                self.assertTrue(np.all(out["S"] >= -1e-9))
                self.assertTrue(np.all(out["S"] <= self.prm.SM + 1e-9))
                self.assertTrue(np.all(out["RS_mm"] >= -1e-12))

    def test_linear_reservoir_recurrence(self):
        """地表径流线性水库：QS(t) = CS·QS(t−1) + (1−CS)·U·RS(t)。"""
        P, EM, state0 = self.events["event3"]
        out = simulate(P, EM, self.prm, state0)
        qs = float(state0.get("QS", 0.0))
        expected = []
        for rs in out["RS_mm"]:
            qs = self.prm.CS * qs + (1.0 - self.prm.CS) * U_CONV * float(rs)
            expected.append(qs)
        np.testing.assert_allclose(out["QS"], expected, rtol=0, atol=1e-9)

    def test_muskingum_volume_balance(self):
        """马斯京根演算不改变总水量（首末时段外的体积差小于 1%）。"""
        P, EM, state0 = self.events["event4"]
        out = simulate(P, EM, self.prm, state0)
        vol_in = out["Q_in"].sum()
        vol_out = out["Q"].sum()
        self.assertLess(abs(vol_out - vol_in) / vol_in, 0.01)

    def test_no_negative_discharge(self):
        for eid, (P, EM, state0) in self.events.items():
            out = simulate(P, EM, self.prm, state0)
            with self.subTest(event=eid):
                self.assertGreaterEqual(float(out["Q"].min()), -1e-9)


class TestConstants(unittest.TestCase):
    def test_unit_conversion(self):
        expected = F_BASIN_KM2 / (3.6 * DT_H)
        self.assertAlmostEqual(U_CONV, expected, places=10)
        self.assertAlmostEqual(U_CONV, 92.5925925926, places=6)

    def test_params_mapping_round_trip(self):
        prm = load_params()
        self.assertEqual(Params.from_mapping(prm.as_dict()), prm)
        self.assertAlmostEqual(prm.WM, prm.WUM + prm.WLM + prm.WDM)


if __name__ == "__main__":
    unittest.main(verbosity=2)

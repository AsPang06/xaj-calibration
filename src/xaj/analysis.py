# -*- coding: utf-8 -*-
"""率定结果分析：异参同效（行为参数集）与参数敏感性。

异参同效
--------
差分进化收敛后的种群本身就是一组"行为参数集"（各场 DC 均很高但参数值不同）。
本模块把它们整理成表，统计各参数的分布范围与模拟过程的包络带。

敏感性
------
在率定最优解处做单因子（one-at-a-time）扰动：把每个参数分别推到参考范围的
上下限，观察率定期平均 DC 与检验期 DC 的变化，绘制龙卷风图。
"""
from __future__ import annotations

import numpy as np

from .calibrate import EventData, MultiEventObjective, simulate_event
from .metrics import dc, evaluate, grade
from .model import PARAM_NAMES, Params


# --------------------------------------------------------------------------- #
# 异参同效
# --------------------------------------------------------------------------- #
def behavioral_sets(objective: MultiEventObjective, unit: np.ndarray,
                    energy: np.ndarray, dc_threshold: float = 0.98
                    ) -> list[dict]:
    """筛选行为参数集：率定期平均 DC ≥ 阈值。"""
    rows = []
    for x, e in zip(unit, energy):
        det = objective.details(x)
        if det["mean_dc"] < dc_threshold:
            continue
        prm = objective.to_params(x)
        row = {"unit": np.asarray(x, dtype=float), "energy": float(e),
               "J": det["J"], "mean_dc": det["mean_dc"]}
        row.update({f"param_{n}": getattr(prm, n) for n in PARAM_NAMES})
        for eid, m in det["events"].items():
            row[f"dc_{eid}"] = m["dc"]
        rows.append(row)
    return rows


def parameter_spread(sets: list[dict]) -> list[dict]:
    """行为参数集中各参数的分布统计。"""
    out = []
    for name in PARAM_NAMES:
        vals = np.array([s[f"param_{name}"] for s in sets], dtype=float)
        out.append({
            "参数": name,
            "最小": float(vals.min()), "5%分位": float(np.percentile(vals, 5)),
            "中位数": float(np.median(vals)), "95%分位": float(np.percentile(vals, 95)),
            "最大": float(vals.max()),
            "相对极差%": float((vals.max() - vals.min()) / max(abs(np.median(vals)), 1e-9) * 100),
        })
    return out


def ensemble_band(events: list[EventData], sets: list[dict],
                  quantiles: tuple[float, float, float] = (5, 50, 95)
                  ) -> dict[str, dict[str, np.ndarray]]:
    """对每场洪水生成行为参数集模拟的包络带。"""
    result: dict[str, dict[str, np.ndarray]] = {}
    for ev in events:
        qs = np.array([simulate_event(ev, Params.from_mapping(
            {n: s[f"param_{n}"] for n in PARAM_NAMES})) for s in sets])
        result[ev.event_id] = {
            "q05": np.percentile(qs, quantiles[0], axis=0),
            "q50": np.percentile(qs, quantiles[1], axis=0),
            "q95": np.percentile(qs, quantiles[2], axis=0),
            "all": qs,
        }
    return result


def equifinality_table(sets: list[dict], events: list[EventData],
                       best: Params) -> list[dict]:
    """行为参数集的性能统计（含 event4 检验）。"""
    rows = []
    for s in sets:
        prm = Params.from_mapping({n: s[f"param_{n}"] for n in PARAM_NAMES})
        row = {"mean_dc": s["mean_dc"], "J": s["J"]}
        for ev in events:
            row[f"dc_{ev.event_id}"] = dc(ev.Q_obs, simulate_event(ev, prm))
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# 单因子敏感性
# --------------------------------------------------------------------------- #
def oat_sensitivity(objective: MultiEventObjective, x0: np.ndarray,
                    bounds: dict[str, tuple[float, float]]) -> list[dict]:
    """在 x0 处逐个参数推到上下限，记录 DC 变化量。"""
    base = objective.details(x0)
    base_dc = base["mean_dc"]
    rows = []
    x = np.asarray(x0, dtype=float).copy()
    for i, name in enumerate(PARAM_NAMES):
        rec = {"参数": name, "基准值": float(objective.to_params(x0).__dict__[name]),
               "下限": bounds[name][0], "上限": bounds[name][1],
               "基准平均DC": base_dc}
        for tag, val in (("下限", 0.0), ("上限", 1.0)):
            xx = x.copy()
            xx[i] = val
            det = objective.details(xx)
            rec[f"DC@{tag}"] = det["mean_dc"]
            rec[f"ΔDC@{tag}"] = det["mean_dc"] - base_dc
        rec["最大|ΔDC|"] = max(abs(rec["ΔDC@下限"]), abs(rec["ΔDC@上限"]))
        rows.append(rec)
    rows.sort(key=lambda r: r["最大|ΔDC|"], reverse=True)
    return rows

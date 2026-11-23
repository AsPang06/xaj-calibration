# -*- coding: utf-8 -*-
"""脚本 02：异参同效与参数敏感性分析。

读取 01 脚本保存的 DE 种群与最优参数，输出：

    outputs/analysis/behavioral_sets.csv      行为参数集（参数与各场 DC）
    outputs/analysis/parameter_spread.csv     各参数在行为集中的分布
    outputs/analysis/oat_sensitivity.csv      单因子敏感性
    outputs/analysis/ensemble_band.npz         各场洪水模拟包络带（绘图用）
    outputs/analysis/summary.json              汇总数字
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from xaj.analysis import (behavioral_sets, ensemble_band, equifinality_table,
                          oat_sensitivity, parameter_spread)
from xaj.calibrate import EventData, MultiEventObjective, load_calibration_events
from xaj.io import OUTPUT_DIR, load_bounds, load_events, load_params, save_parameter_table
from xaj.metrics import dc, grade
from xaj.model import PARAM_NAMES, Params

ANA_DIR = OUTPUT_DIR / "analysis"
CAL_DIR = OUTPUT_DIR / "calibration"


def main() -> None:
    ANA_DIR.mkdir(parents=True, exist_ok=True)
    events = load_calibration_events()
    raw = load_events(["event4"])
    ev4 = EventData.from_raw("event4", raw["event4"])
    bounds = load_bounds()
    objective = MultiEventObjective(events, bounds)

    result = json.loads((CAL_DIR / "calibration_result.json").read_text(encoding="utf-8"))
    prm_best = Params.from_mapping(result["params"])
    x_best = objective.to_unit(prm_best)

    pop = np.load(CAL_DIR / "de_population.npz")
    sets = behavioral_sets(objective, pop["unit"], pop["energy"], dc_threshold=0.98)
    print(f"DE 种群 {len(pop['unit'])} 个个体，其中行为参数集 {len(sets)} 个"
          f"（率定期平均 DC ≥ 0.98）")

    # 行为参数集性能（含 event4）
    eq = equifinality_table(sets, events + [ev4], prm_best)
    for s, row in zip(sets, eq):
        s.update({k: v for k, v in row.items() if k.startswith("dc_event4")})

    # CSV：行为参数集
    rows = []
    for s in sets:
        row = {f"param_{n}": round(s[f"param_{n}"], 6) for n in PARAM_NAMES}
        row.update({k: round(v, 5) for k, v in s.items() if k.startswith("dc_")})
        row["mean_dc"] = round(s["mean_dc"], 5)
        rows.append(row)
    save_parameter_table(rows, ANA_DIR / "behavioral_sets.csv")

    # 参数分布
    spread = parameter_spread(sets)
    save_parameter_table(spread, ANA_DIR / "parameter_spread.csv")

    # 包络带
    band = ensemble_band(events + [ev4], sets)
    np.savez(ANA_DIR / "ensemble_band.npz",
             **{f"{eid}_{k}": v for eid, d in band.items() for k, v in d.items()})

    # 单因子敏感性
    oat = oat_sensitivity(objective, x_best, bounds)
    save_parameter_table(oat, ANA_DIR / "oat_sensitivity.csv")

    # 汇总
    dc4 = np.array([s["dc_event4"] for s in sets])
    summary = {
        "n_population": int(len(pop["unit"])),
        "n_behavioral": len(sets),
        "dc_calibration_range": [float(min(s["mean_dc"] for s in sets)),
                                 float(max(s["mean_dc"] for s in sets))],
        "dc_event4_range": [float(dc4.min()), float(dc4.max())],
        "dc_event4_median": float(np.median(dc4)),
        "dc_event4_grade": grade(float(np.median(dc4))),
        "parameter_spread": spread,
        "oat_top": oat[:8],
    }
    (ANA_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n行为参数集率定期平均 DC: {summary['dc_calibration_range'][0]:.4f}"
          f" ~ {summary['dc_calibration_range'][1]:.4f}")
    print(f"检验期 DC（行为集）: {summary['dc_event4_range'][0]:.4f}"
          f" ~ {summary['dc_event4_range'][1]:.4f}，中位数 {summary['dc_event4_median']:.4f}"
          f"（{summary['dc_event4_grade']}）")

    print("\n参数在行为集中的相对极差（越大越不可辨识）:")
    for s in sorted(spread, key=lambda r: r["相对极差%"], reverse=True):
        print(f"  {s['参数']:5s} {s['最小']:9.4f} ~ {s['最大']:9.4f}"
              f"  相对极差 {s['相对极差%']:7.1f}%")

    print("\n单因子敏感性（推到下限/上限引起的平均 DC 变化）:")
    for r in oat[:8]:
        print(f"  {r['参数']:5s} 基准 {r['基准值']:8.4f}  ΔDC(下) {r['ΔDC@下限']:+.4f}"
              f"  ΔDC(上) {r['ΔDC@上限']:+.4f}")
    print(f"\n结果已写入 {ANA_DIR}")


if __name__ == "__main__":
    main()

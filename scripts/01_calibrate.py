# -*- coding: utf-8 -*-
"""脚本 01：率定新安江模型参数（event1~event3），保存参数、指标与收敛记录。

运行::

    python scripts/01_calibrate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from xaj.calibrate import calibrate, load_calibration_events
from xaj.io import (CALIBRATION_EVENTS, OUTPUT_DIR, load_bounds, load_params,
                    load_events, save_parameter_table)
from xaj.metrics import evaluate, grade
from xaj.model import PARAM_NAMES

CAL_DIR = OUTPUT_DIR / "calibration"


def main() -> None:
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    events = load_calibration_events()
    bounds = load_bounds()
    p_init = load_params()

    print("开始率定：DE(popsize=15, maxiter=400) + Nelder–Mead ...", flush=True)
    result = calibrate(events, bounds, popsize=15, maxiter=400, seed=42)

    prm = result["params"]
    det = result["details"]

    # ---- 参数对照表 ----
    rows = []
    for name in PARAM_NAMES:
        rows.append({"参数": name,
                     "初值": getattr(p_init, name),
                     "率定值": round(getattr(prm, name), 6),
                     "参考范围": f"{bounds[name][0]}~{bounds[name][1]}"})
    save_parameter_table(rows, CAL_DIR / "best_params.csv")

    # ---- 指标表 ----
    metric_rows = []
    for eid in CALIBRATION_EVENTS:
        m = det["events"][eid]
        metric_rows.append({
            "场次": eid, "用途": "率定",
            "DC": round(m["dc"], 4), "等级": grade(m["dc"]),
            "RMSE": round(m["rmse"], 2), "KGE": round(m["kge"], 4),
            "实测洪峰": round(m["peak_obs"], 1), "模拟洪峰": round(m["peak_sim"], 1),
            "洪峰误差%": round(m["peak_err_pct"], 2),
            "峰现时差h": m["peak_time_err_h"],
            "实测径流深mm": round(m["vol_obs_mm"], 2),
            "模拟径流深mm": round(m["vol_sim_mm"], 2),
            "径流深误差%": round(m["vol_err_pct"], 2),
        })
    save_parameter_table(metric_rows, CAL_DIR / "calibration_metrics.csv")

    # ---- DE 种群档案（供异参同效分析） ----
    np.savez(CAL_DIR / "de_population.npz",
             unit=result["de"].population,
             energy=result["de"].energies)

    summary = {
        "objective": result["objective"],
        "mean_dc": det["mean_dc"],
        "nfev": result["de"].nfev,
        "de_history": result["de"].history,
        "nm_history": result["nm"].history,
        "params": prm.as_dict(),
        "initial_params": p_init.as_dict(),
        "metrics": {eid: {k: v for k, v in det["events"][eid].items() if k != "Q_sim"}
                    for eid in CALIBRATION_EVENTS},
        "bounds": {k: list(v) for k, v in bounds.items()},
    }
    (CAL_DIR / "calibration_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 控制台输出 ----
    print("\n率定结果（event1~event3）")
    print(f"目标函数 J = {result['objective']:.6f}  平均 DC = {det['mean_dc']:.4f}")
    print(f"{'场次':<8}{'DC':>8}{'等级':>6}{'RMSE':>9}{'洪峰误差%':>10}{'峰现时差h':>10}{'径流深误差%':>11}")
    for row in metric_rows:
        print(f"{row['场次']:<8}{row['DC']:>8.4f}{row['等级']:>6}{row['RMSE']:>9.2f}"
              f"{row['洪峰误差%']:>10.2f}{row['峰现时差h']:>10.0f}{row['径流深误差%']:>11.2f}")

    # ---- event4 检验（不参与率定） ----
    print("\n检验场次（event4，参数不回调）")
    raw = load_events(list(("event4",)))["event4"]
    from xaj.calibrate import EventData, simulate_event
    ev4 = EventData.from_raw("event4", raw)
    q4 = simulate_event(ev4, prm)
    m4 = evaluate(ev4.Q_obs, q4)
    print(f"DC={m4['dc']:.4f} ({grade(m4['dc'])})  RMSE={m4['rmse']:.2f}  "
          f"洪峰 {m4['peak_sim']:.1f}/{m4['peak_obs']:.1f} ({m4['peak_err_pct']:+.2f}%)  "
          f"径流深误差 {m4['vol_err_pct']:+.2f}%")
    summary["validation"] = {k: v for k, v in m4.items()}
    (CAL_DIR / "calibration_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {CAL_DIR}")


if __name__ == "__main__":
    main()

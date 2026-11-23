# -*- coding: utf-8 -*-
"""精度评定指标。

主指标沿用《水文情报预报规范》思路：
  DC  确定性系数（Nash–Sutcliffe 效率系数）
  RMSE 均方根误差
辅助指标：
  洪峰流量误差、峰现时间误差、径流深（水量）误差、KGE。
"""
from __future__ import annotations

import numpy as np

from .model import DT_H, F_BASIN_KM2, U_CONV

# 由流量序列反算时段径流深的系数：mm = ΣQ(m³/s) × Δt(s) / F × 1000
_MM_PER_CMS = DT_H * 3600.0 / (F_BASIN_KM2 * 1e6) * 1000.0   # = 0.0108 mm/(m³/s)


def dc(q_obs, q_sim) -> float:
    """确定性系数 DC = 1 − Σ(Qobs−Qsim)² / Σ(Qobs−Q̄obs)²。"""
    q_obs = np.asarray(q_obs, dtype=float)
    q_sim = np.asarray(q_sim, dtype=float)
    den = np.sum((q_obs - q_obs.mean()) ** 2)
    if den <= 0:
        return float("nan")
    return float(1.0 - np.sum((q_obs - q_sim) ** 2) / den)


def rmse(q_obs, q_sim) -> float:
    """均方根误差 (m³/s)。"""
    q_obs = np.asarray(q_obs, dtype=float)
    q_sim = np.asarray(q_sim, dtype=float)
    return float(np.sqrt(np.mean((q_obs - q_sim) ** 2)))


def kge(q_obs, q_sim) -> float:
    """Kling–Gupta 效率系数 KGE = 1 − √[(r−1)² + (α−1)² + (β−1)²]。"""
    q_obs = np.asarray(q_obs, dtype=float)
    q_sim = np.asarray(q_sim, dtype=float)
    if q_obs.std() == 0 or q_obs.mean() == 0:
        return float("nan")
    r = float(np.corrcoef(q_obs, q_sim)[0, 1])
    alpha = float(q_sim.std() / q_obs.std())
    beta = float(q_sim.mean() / q_obs.mean())
    return float(1.0 - np.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2))


def runoff_depth_mm(q) -> float:
    """由流量序列积分得到时段总径流深 (mm)。"""
    return float(np.sum(np.asarray(q, dtype=float)) * _MM_PER_CMS)


def evaluate(q_obs, q_sim) -> dict[str, float]:
    """计算一场洪水的全部评定指标。"""
    q_obs = np.asarray(q_obs, dtype=float)
    q_sim = np.asarray(q_sim, dtype=float)
    i_obs, i_sim = int(np.argmax(q_obs)), int(np.argmax(q_sim))
    peak_obs, peak_sim = float(q_obs[i_obs]), float(q_sim[i_sim])
    vol_obs, vol_sim = runoff_depth_mm(q_obs), runoff_depth_mm(q_sim)
    return {
        "dc": dc(q_obs, q_sim),
        "rmse": rmse(q_obs, q_sim),
        "kge": kge(q_obs, q_sim),
        "peak_obs": peak_obs,
        "peak_sim": peak_sim,
        "peak_err_pct": (peak_sim - peak_obs) / peak_obs * 100.0 if peak_obs else float("nan"),
        "peak_time_err_h": (i_sim - i_obs) * DT_H,
        "vol_obs_mm": vol_obs,
        "vol_sim_mm": vol_sim,
        "vol_err_pct": (vol_sim - vol_obs) / vol_obs * 100.0 if vol_obs else float("nan"),
    }


def grade(dc_value: float) -> str:
    """按 SL 250—2000 思路划分精度等级：甲级 DC≥0.90，乙级 0.70~0.90，丙级 0.50~0.70。"""
    if dc_value >= 0.90:
        return "甲级"
    if dc_value >= 0.70:
        return "乙级"
    if dc_value >= 0.50:
        return "丙级"
    return "不及格"


__all__ = ["dc", "rmse", "kge", "runoff_depth_mm", "evaluate", "grade", "U_CONV"]

# -*- coding: utf-8 -*-
"""参数率定：多场次目标函数 + 差分进化（DE）+ Nelder–Mead 局部精化。

设计要点
--------
1. 目标函数取率定场次确定性系数 DC 的均值::

       J = mean_i (1 - DC_i)

   DC 对洪峰误差敏感（峰值的平方误差被放大），因此直接以 DC 为目标
   可以同时兼顾整体过程与洪峰。
2. 参数在参考范围内按 ``x ∈ [0,1]^d`` 归一化搜索，便于 DE 设步长。
3. 对马斯京根参数组合（KE、X）可能导致的负流量施加轻量罚函数，
   避免 DE 停留在非物理区域。
4. DE 结束后用 Nelder–Mead 在最优个体附近精化，保证收敛到局部最优。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import numpy as np

from .io import CALIBRATION_EVENTS, EVENTS_DIR, load_bounds, load_events
from .metrics import dc, evaluate
from .model import PARAM_NAMES, Params, simulate


# --------------------------------------------------------------------------- #
# 场次对象与单场模拟
# --------------------------------------------------------------------------- #
@dataclass
class EventData:
    """一场洪水的输入与实测过程。"""

    event_id: str
    P: np.ndarray
    EM: np.ndarray
    Q_obs: np.ndarray
    state0: dict[str, float]

    @classmethod
    def from_raw(cls, event_id: str, raw: dict) -> "EventData":
        df = raw["df"]
        return cls(
            event_id=event_id,
            P=df["面雨量P(mm)"].to_numpy(dtype=float),
            EM=df["蒸发皿EM(mm)"].to_numpy(dtype=float),
            Q_obs=df["实测流量Q(m3/s)"].to_numpy(dtype=float),
            state0=raw["state0"],
        )


def load_calibration_events(ids: Sequence[str] | None = None) -> list[EventData]:
    """读取率定场次（默认 event1~event3）。"""
    ids = list(ids) if ids is not None else list(CALIBRATION_EVENTS)
    raw = load_events(ids)
    return [EventData.from_raw(eid, raw[eid]) for eid in ids]


def simulate_event(ev: EventData, prm: Params) -> np.ndarray:
    """模拟一场洪水，返回出口流量过程 Q (m³/s)。"""
    out = simulate(ev.P, ev.EM, prm, ev.state0)
    return np.asarray(out["Q"], dtype=float)


# --------------------------------------------------------------------------- #
# 目标函数
# --------------------------------------------------------------------------- #
class MultiEventObjective:
    """多场次 DC 目标函数，参数向量为归一化坐标 [0,1]^d。"""

    def __init__(self, events: Iterable[EventData],
                 bounds: dict[str, tuple[float, float]],
                 neg_penalty: float = 5.0):
        self.events = list(events)
        self.bounds = bounds
        self.neg_penalty = neg_penalty
        self._lo = np.array([bounds[n][0] for n in PARAM_NAMES], dtype=float)
        self._hi = np.array([bounds[n][1] for n in PARAM_NAMES], dtype=float)
        self.nfev = 0
        self.events_cache_obs_total = sum(float(ev.Q_obs.sum()) for ev in self.events)

    @property
    def ndim(self) -> int:
        """参数个数（归一化搜索维数）。"""
        return len(PARAM_NAMES)

    # -- 坐标变换 ---------------------------------------------------------
    def to_params(self, x: Sequence[float]) -> Params:
        x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
        values = self._lo + x * (self._hi - self._lo)
        return Params.from_mapping(dict(zip(PARAM_NAMES, values.tolist())))

    def to_unit(self, prm: Params) -> np.ndarray:
        values = np.array([getattr(prm, n) for n in PARAM_NAMES], dtype=float)
        return (values - self._lo) / (self._hi - self._lo)

    # -- 评价 -------------------------------------------------------------
    def details(self, x: Sequence[float]) -> dict:
        """返回目标值与各场指标，供报告使用。"""
        prm = self.to_params(x)
        rows = {}
        total_penalty = 0.0
        for ev in self.events:
            q = simulate_event(ev, prm)
            rows[ev.event_id] = evaluate(ev.Q_obs, q)
            rows[ev.event_id]["Q_sim"] = q
            neg = float(np.clip(-q, 0.0, None).sum())
            total_penalty += neg
        mean_dc = float(np.mean([rows[e.event_id]["dc"] for e in self.events]))
        penalty = self.neg_penalty * total_penalty / self.events_cache_obs_total
        return {"J": 1.0 - mean_dc + penalty, "mean_dc": mean_dc,
                "penalty": penalty, "events": rows}

    def __call__(self, x: Sequence[float]) -> float:
        self.nfev += 1
        return float(self.details(x)["J"])


# --------------------------------------------------------------------------- #
# 差分进化
# --------------------------------------------------------------------------- #
@dataclass
class OptimizeResult:
    x: np.ndarray
    fun: float
    nfev: int
    nit: int
    history: list[float] = field(default_factory=list)
    population: np.ndarray | None = None
    energies: np.ndarray | None = None
    message: str = ""


def differential_evolution(func: Callable[[np.ndarray], float], ndim: int,
                           popsize: int = 15, maxiter: int = 400,
                           F: float = 0.7, CR: float = 0.9,
                           seed: int = 42, tol: float = 1e-7,
                           patience: int = 80,
                           callback: Callable[[int, float], None] | None = None
                           ) -> OptimizeResult:
    """经典 DE/rand/1/bin，边界用越界回弹处理，带停滞早停。"""
    rng = np.random.default_rng(seed)
    n_pop = popsize * ndim
    pop = rng.random((n_pop, ndim))
    energy = np.array([func(ind) for ind in pop], dtype=float)
    best_i = int(np.argmin(energy))
    best_x, best_f = pop[best_i].copy(), float(energy[best_i])
    history = [best_f]
    stall = 0

    for gen in range(maxiter):
        for i in range(n_pop):
            idxs = [j for j in range(n_pop) if j != i]
            a, b, c = rng.choice(idxs, 3, replace=False)
            mutant = pop[a] + F * (pop[b] - pop[c])
            mutant = np.clip(mutant, 0.0, 1.0)
            cross = rng.random(ndim) < CR
            cross[rng.integers(ndim)] = True
            trial = np.where(cross, mutant, pop[i])
            f_trial = func(trial)
            if f_trial < energy[i]:
                pop[i], energy[i] = trial, f_trial
                if f_trial < best_f - 1e-12:
                    best_f, best_x, stall = float(f_trial), trial.copy(), 0
        history.append(best_f)
        if callback is not None:
            callback(gen, best_f)
        # 停滞早停：种群最优连续 patience 代无改进
        stall = 0 if history[-1] < history[-2] - 1e-10 else stall + 1
        if stall >= patience or best_f <= tol:
            break

    return OptimizeResult(x=best_x.copy(), fun=best_f, nfev=func.nfev if hasattr(func, "nfev") else -1,
                          nit=len(history) - 1, history=history,
                          population=pop.copy(), energies=energy.copy(),
                          message="stagnation" if stall >= patience else "maxiter")


# --------------------------------------------------------------------------- #
# Nelder–Mead（带边界裁剪与重启）
# --------------------------------------------------------------------------- #
def _nelder_mead_once(func: Callable[[np.ndarray], float], x0: np.ndarray,
                      step: np.ndarray, maxiter: int) -> tuple[np.ndarray, float, int, list[float]]:
    d = len(x0)
    simplex = [np.clip(x0, 0, 1)]
    for i in range(d):
        x = x0.copy()
        x[i] = min(1.0, x[i] + step[i])
        simplex.append(x)
    simplex = np.array(simplex)
    values = np.array([func(p) for p in simplex])
    nfev = d + 1
    history = [float(values.min())]

    alpha, gamma, rho, sigma = 1.0, 2.0, 0.5, 0.5
    for _ in range(maxiter):
        order = np.argsort(values)
        simplex, values = simplex[order], values[order]
        if np.max(np.abs(simplex[1:] - simplex[0])) < 1e-10:
            break
        centroid = simplex[:-1].mean(axis=0)
        xr = np.clip(centroid + alpha * (centroid - simplex[-1]), 0, 1)
        fr = func(xr); nfev += 1
        if fr < values[0]:
            xe = np.clip(centroid + gamma * (xr - centroid), 0, 1)
            fe = func(xe); nfev += 1
            if fe < fr:
                simplex[-1], values[-1] = xe, fe
            else:
                simplex[-1], values[-1] = xr, fr
        elif fr < values[-2]:
            simplex[-1], values[-1] = xr, fr
        else:
            xc = np.clip(centroid + rho * (simplex[-1] - centroid), 0, 1)
            fc = func(xc); nfev += 1
            if fc < values[-1]:
                simplex[-1], values[-1] = xc, fc
            else:
                for i in range(1, d + 1):
                    simplex[i] = np.clip(simplex[0] + sigma * (simplex[i] - simplex[0]), 0, 1)
                    values[i] = func(simplex[i]); nfev += 1
        history.append(float(values.min()))
    i = int(np.argmin(values))
    return simplex[i], float(values[i]), nfev, history


def nelder_mead(func: Callable[[np.ndarray], float], x0: np.ndarray,
                step: float = 0.02, restarts: int = 3, maxiter: int = 2000
                ) -> OptimizeResult:
    """从同一起点多次收缩重启的 Nelder–Mead。"""
    x = np.asarray(x0, dtype=float)
    best_x, best_f = x.copy(), float(func(x))
    history: list[float] = [best_f]
    total_nfev = 0
    for k in range(restarts):
        s = np.full_like(x, step / (2 ** k))
        xk, fk, nfev, hist = _nelder_mead_once(func, best_x, s, maxiter)
        total_nfev += nfev
        history.extend(hist[1:])
        if fk < best_f:
            best_f, best_x = fk, xk
        else:
            break
    return OptimizeResult(x=best_x, fun=best_f, nfev=total_nfev,
                          nit=len(history) - 1, history=history, message="nm")


# --------------------------------------------------------------------------- #
# 率定入口
# --------------------------------------------------------------------------- #
def calibrate(events: Sequence[EventData] | None = None,
              bounds: dict[str, tuple[float, float]] | None = None,
              popsize: int = 15, maxiter: int = 400, seed: int = 42,
              nm_restarts: int = 3, verbose: bool = True) -> dict:
    """运行完整率定流程，返回参数、目标值、收敛曲线与种群档案。"""
    events = list(events) if events is not None else load_calibration_events()
    bounds = bounds if bounds is not None else load_bounds()
    objective = MultiEventObjective(events, bounds)

    def report(gen: int, best: float) -> None:
        if verbose and (gen % 50 == 0 or gen == 0):
            print(f"  DE gen {gen:3d}: best J = {best:.6f}  (nfev={objective.nfev})", flush=True)

    de = differential_evolution(objective, len(PARAM_NAMES), popsize=popsize,
                                maxiter=maxiter, seed=seed, callback=report)
    if verbose:
        print(f"  DE 结束: J = {de.fun:.6f}, nfev = {objective.nfev}", flush=True)

    nm = nelder_mead(objective, de.x, step=0.02, restarts=nm_restarts)
    best_x = nm.x if nm.fun <= de.fun else de.x
    best_f = min(nm.fun, de.fun)
    prm = objective.to_params(best_x)
    detail = objective.details(best_x)

    if verbose:
        print(f"  精化结束: J = {best_f:.6f}", flush=True)

    return {
        "params": prm,
        "unit": best_x,
        "objective": best_f,
        "de": de,
        "nm": nm,
        "details": detail,
        "events": events,
        "bounds": bounds,
        "objective_fn": objective,
    }


__all__ = ["EventData", "load_calibration_events", "simulate_event",
           "MultiEventObjective", "differential_evolution", "nelder_mead",
           "calibrate", "OptimizeResult"]

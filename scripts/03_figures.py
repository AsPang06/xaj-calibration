# -*- coding: utf-8 -*-
"""脚本 03：生成报告图件（Pillow 自绘，无 matplotlib 依赖）。

输出到 outputs/figures/：

    fig01_calibration_hydrographs.png  率定期 3 场洪水过程线（初值 vs 率定）
    fig02_validation_ensemble.png      检验期过程线 + 行为参数集包络带
    fig03_convergence.png              差分进化收敛曲线
    fig04_scatter.png                  实测—模拟散点图
    fig05_parameter_spread.png         行为参数集中各参数的分布（可辨识性）
    fig06_sensitivity.png              单因子敏感性龙卷风图
    fig07_water_balance.png            三水源径流深构成与水量平衡
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from xaj.calibrate import EventData, simulate_event
from xaj.io import OUTPUT_DIR, load_bounds, load_events, load_params
from xaj.metrics import evaluate
from xaj.model import Params, simulate
from xaj.plotting import Figure, nice_ticks

FIG_DIR = OUTPUT_DIR / "figures"
CAL_DIR = OUTPUT_DIR / "calibration"
ANA_DIR = OUTPUT_DIR / "analysis"

C_OBS = "#262626"
C_SIM = "#1f4e79"
C_INIT = "#a6a6a6"
C_RAIN = "#8faadc"
C_BAND = "#9dc3e6"
DPI = 170


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_all_events() -> dict[str, EventData]:
    raw = load_events(["event1", "event2", "event3", "event4"])
    return {eid: EventData.from_raw(eid, raw[eid]) for eid in raw}


# --------------------------------------------------------------------------- #
# 图 1：率定期过程线
# --------------------------------------------------------------------------- #
def fig01(events: dict[str, EventData], prm_best: Params, prm_init: Params,
          metrics: dict) -> str:
    ids = ["event1", "event2", "event3"]
    fig = Figure(8.6, 9.8, dpi=DPI)
    left, right = 0.085, 0.975
    top, bottom = 0.905, 0.07
    gap = 0.055
    h = (top - bottom - gap * 2) / 3
    t = np.arange(40)
    for i, eid in enumerate(ids):
        ev = events[eid]
        y1 = top - i * (h + gap)
        y0 = y1 - h
        q_best = simulate_event(ev, prm_best)
        q_init = simulate_event(ev, prm_init)
        m = metrics[eid]
        rain_frac = 0.28
        axr = fig.axes((left, y0 + h * (1 - rain_frac), right, y1),
                       (0, 39), (0, max(ev.P) * 1.08), invert_y=True)
        axq = fig.axes((left, y0, right, y0 + h * (1 - rain_frac) - 0.008),
                       (0, 39), (0, max(ev.Q_obs.max(), q_best.max(), q_init.max()) * 1.12))
        axr.bars(t, ev.P, 0.82, color=C_RAIN)
        pmax = float(max(ev.P))
        axr.frame(ticks_y=[0, round(pmax / 2), round(pmax)],
                  label_y="P (mm)", grid=False, tick_size=7)
        axq.plot(t, q_init, C_INIT, 1.2, dash=(5, 3))
        axq.plot(t, q_best, C_SIM, 1.7)
        axq.scatter(t, ev.Q_obs, 2.0, C_OBS)
        axq.frame(ticks_x=nice_ticks(0, 39, 6), ticks_y=nice_ticks(0, float(axq.ylim[1]), 5),
                  label_x="时段 t (Δt=6h)" if i == 2 else "",
                  label_y="Q (m³/s)", tick_size=7)
        fig.text(left, y1 + 0.010,
                 f"{eid}（率定）：DC={m['dc']:.4f}，洪峰误差 {m['peak_sim']/m['peak_obs']*100-100:+.1f}%",
                 size=8.6, bold=True, va="bottom")
    fig.text(left, 0.977, "率定期三场洪水：实测与模拟过程线", size=11, bold=True, va="center")
    fig.legend([{"label": "实测流量", "color": C_OBS, "marker": True},
                {"label": "率定参数模拟", "color": C_SIM},
                {"label": "初值参数模拟", "color": C_INIT, "dash": (5, 3)}],
               left, 0.945, size=8.6, horizontal=True)
    path = FIG_DIR / "fig01_calibration_hydrographs.png"
    return fig.save(str(path))


# --------------------------------------------------------------------------- #
# 图 2：检验期 + 包络带
# --------------------------------------------------------------------------- #
def fig02(ev: EventData, prm_best: Params, prm_init: Params, band: dict,
          m4: dict) -> str:
    q_best = simulate_event(ev, prm_best)
    q_init = simulate_event(ev, prm_init)
    fig = Figure(8.6, 5.8, dpi=DPI)
    left, right = 0.085, 0.975
    axr = fig.axes((left, 0.68, right, 0.895), (0, 39), (0, max(ev.P) * 1.08), invert_y=True)
    axq = fig.axes((left, 0.095, right, 0.665), (0, 39),
                   (0, max(ev.Q_obs.max(), q_best.max(), float(band["q95"].max())) * 1.12))
    t = np.arange(40)
    axr.bars(t, ev.P, 0.82, color=C_RAIN)
    pmax = float(max(ev.P))
    axr.frame(ticks_y=[0, round(pmax / 2), round(pmax)],
              label_y="P (mm)", grid=False, tick_size=7)
    axq.fill_between(t, band["q05"], band["q95"], C_BAND, alpha=110)
    axq.plot(t, q_init, C_INIT, 1.2, dash=(5, 3))
    axq.plot(t, q_best, C_SIM, 1.8)
    axq.scatter(t, ev.Q_obs, 2.2, C_OBS)
    axq.frame(ticks_x=nice_ticks(0, 39, 7), ticks_y=nice_ticks(0, float(axq.ylim[1]), 6),
              label_x="时段 t (Δt=6h)", label_y="Q (m³/s)", tick_size=7.5)
    fig.text(left, 0.965,
             f"检验期（event4，参数不参与率定）：DC={m4['dc']:.4f}（甲级），"
             f"洪峰 {m4['peak_sim']:.1f}/{m4['peak_obs']:.1f} m³/s（{m4['peak_err_pct']:+.1f}%），"
             f"径流深误差 {m4['vol_err_pct']:+.1f}%",
             size=9, bold=True, va="center")
    fig.legend([{"label": "实测流量", "color": C_OBS, "marker": True},
                {"label": "率定参数模拟", "color": C_SIM},
                {"label": "初值参数模拟", "color": C_INIT, "dash": (5, 3)},
                {"label": "行为参数集 5%~95% 包络", "color": C_BAND, "fill": True}],
               left, 0.925, size=8.4, horizontal=True)
    path = FIG_DIR / "fig02_validation_ensemble.png"
    return fig.save(str(path))


# --------------------------------------------------------------------------- #
# 图 3：收敛曲线（对数纵轴）
# --------------------------------------------------------------------------- #
def fig03(history: list[float], final_j: float) -> str:
    fig = Figure(8.0, 4.8, dpi=DPI)
    left, right, bottom, top = 0.095, 0.965, 0.155, 0.90
    lo, hi = -4.6, -1.6
    ax = fig.axes((left, bottom, right, top), (1, len(history)), (lo, hi))
    gens = np.arange(1, len(history) + 1)
    y = np.log10(np.maximum(history, 10 ** lo))
    ax.plot(gens, y, C_SIM, 1.6)
    ax.scatter([gens[-1]], [np.log10(max(final_j, 10 ** lo))], 3.2, "#c00000")
    fig.text(0.42, 0.80, f"最终 J = {final_j:.2e}", size=9, color="#c00000")
    ticks = [-4, -3, -2]
    ax.frame(ticks_x=nice_ticks(1, len(history), 8), ticks_y=ticks,
             labels_y=["1e-4", "1e-3", "1e-2"],
             label_x="差分进化代数", label_y="目标函数 J（对数刻度）", tick_size=8)
    fig.text(left, 0.965, "差分进化收敛曲线（约 9.6 万次模型评价）", size=10, bold=True, va="center")
    path = FIG_DIR / "fig03_convergence.png"
    return fig.save(str(path))


# --------------------------------------------------------------------------- #
# 图 4：散点
# --------------------------------------------------------------------------- #
def fig04(events: dict[str, EventData], prm_best: Params) -> str:
    fig = Figure(8.0, 6.4, dpi=DPI)
    left, right, bottom, top = 0.105, 0.965, 0.105, 0.885
    qmax = max(float(ev.Q_obs.max()) for ev in events.values()) * 1.05
    ax = fig.axes((left, bottom, right, top), (0, qmax), (0, qmax))
    colors = {"event1": "#1f4e79", "event2": "#c00000", "event3": "#2e7d32", "event4": "#7030a0"}
    markers = {"event1": "o", "event2": "s", "event3": "^", "event4": "D"}
    entries = []
    for eid, ev in events.items():
        q = simulate_event(ev, prm_best)
        ax.scatter(ev.Q_obs, q, 2.8, colors[eid], marker=markers[eid])
        entries.append({"label": f"{eid}（DC={evaluate(ev.Q_obs, q)['dc']:.4f}）",
                        "color": colors[eid], "marker": True, "shape": markers[eid]})
    ax.plot([0, qmax], [0, qmax], "#7f7f7f", 1.3, dash=(6, 4))
    ax.frame(ticks_x=nice_ticks(0, qmax, 6), ticks_y=nice_ticks(0, qmax, 6),
             label_x="实测流量 Qobs (m³/s)", label_y="模拟流量 Qsim (m³/s)", tick_size=8)
    fig.legend(entries, 0.105, 0.945, size=8.6, horizontal=True)
    fig.text(left, 0.982, "实测—模拟流量散点（率定参数）", size=10.5, bold=True, va="center")
    path = FIG_DIR / "fig04_scatter.png"
    return fig.save(str(path))


# --------------------------------------------------------------------------- #
# 图 5：参数可辨识性
# --------------------------------------------------------------------------- #
def fig05(spread_rows: list[dict], bounds: dict[str, tuple[float, float]]) -> str:
    for r in spread_rows:
        for k in ("最小", "5%分位", "中位数", "95%分位", "最大", "相对极差%"):
            r[k] = float(r[k])
    rows = sorted(spread_rows, key=lambda r: r["相对极差%"])
    n = len(rows)
    fig = Figure(8.6, 5.6, dpi=DPI)
    left, right, bottom, top = 0.085, 0.855, 0.10, 0.885
    ax = fig.axes((left, bottom, right, top), (0, 1.18), (-0.6, n - 0.4))
    for i, r in enumerate(rows):
        lo, hi = bounds[r["参数"]]
        span = hi - lo
        u = lambda v, lo=lo, span=span: (float(v) - lo) / span
        ax.plot([u(r["最小"]), u(r["最大"])], [i, i], "#2e75b6", 5.0)
        ax.scatter([u(r["中位数"])], [i], 3.0, "#c00000")
        ax.text(1.03, i, f"{r['相对极差%']:.0f}%", size=7.6, va="center", color="#595959")
    ax.frame(ticks_x=[0, 0.25, 0.5, 0.75, 1.0],
             labels_x=["0", "25%", "50%", "75%", "100%"],
             ticks_y=list(range(n)), labels_y=[r["参数"] for r in rows],
             label_x="归一化取值（相对参数参考范围）", tick_size=8, grid=False)
    fig.text(left, 0.945, "行为参数集（240 组）中各参数的分布范围", size=10.5, bold=True, va="center")
    fig.text(0.87, 0.945, "右列为相对极差", size=8, va="center", color="#595959")
    fig.legend([{"label": "取值范围", "color": "#2e75b6"},
                {"label": "中位数", "color": "#c00000", "marker": True}],
               0.62, 0.945, size=8.2, horizontal=True)
    path = FIG_DIR / "fig05_parameter_spread.png"
    return fig.save(str(path))


# --------------------------------------------------------------------------- #
# 图 6：单因子敏感性（龙卷风图）
# --------------------------------------------------------------------------- #
def fig06(oat_rows: list[dict]) -> str:
    rows = oat_rows[:10][::-1]  # 最敏感者置于顶部
    n = len(rows)
    lim = max(max(abs(r["ΔDC@下限"]), abs(r["ΔDC@上限"])) for r in rows) * 1.18
    fig = Figure(8.6, 5.6, dpi=DPI)
    left, right, bottom, top = 0.10, 0.95, 0.13, 0.875
    ax = fig.axes((left, bottom, right, top), (-lim, lim * 0.06), (-0.6, n - 0.4))
    for i, r in enumerate(rows):
        ax.hbar([i + 0.17], [r["ΔDC@下限"]], 0.30, "#c00000")
        ax.hbar([i - 0.17], [r["ΔDC@上限"]], 0.30, "#2e75b6")
    ax.vline(0.0, "#595959", 1.0)
    ax.frame(ticks_x=nice_ticks(-lim, lim * 0.06, 6),
             ticks_y=list(range(n)), labels_y=[r["参数"] for r in rows],
             label_x="率定期平均 DC 的变化量 ΔDC", tick_size=8, grid=False)
    fig.text(left, 0.935, "单因子敏感性：参数分别推至参考范围上下限",
             size=10.5, bold=True, va="center")
    fig.legend([{"label": "取参考范围下限", "color": "#c00000", "fill": True, "alpha": 255},
                {"label": "取参考范围上限", "color": "#2e75b6", "fill": True, "alpha": 255}],
               0.60, 0.935, size=8.4, horizontal=True)
    path = FIG_DIR / "fig06_sensitivity.png"
    return fig.save(str(path))


# --------------------------------------------------------------------------- #
# 图 7：三水源构成
# --------------------------------------------------------------------------- #
def fig07(events: dict[str, EventData], prm_best: Params) -> str:
    fig = Figure(8.6, 5.2, dpi=DPI)
    left, right, bottom, top = 0.085, 0.975, 0.13, 0.855
    ids = list(events)
    data = []
    for eid in ids:
        ev = events[eid]
        out = simulate(ev.P, ev.EM, prm_best, ev.state0)
        rs = float(np.sum(out["RS_mm"])); ri = float(np.sum(out["RI_mm"]))
        rg = float(np.sum(out["RG_mm"]))
        obs_mm = evaluate(ev.Q_obs, ev.Q_obs)["vol_obs_mm"]
        data.append((eid, rs, ri, rg, obs_mm))
    ymax = max(d[1] + d[2] + d[3] for d in data) * 1.20
    ax = fig.axes((left, bottom, right, top), (-0.5, len(data) - 0.5), (0, ymax))
    colors = {"RS": "#c00000", "RI": "#2e75b6", "RG": "#548235"}
    for i, (eid, rs, ri, rg, obs_mm) in enumerate(data):
        base = 0.0
        for key, val in (("RS", rs), ("RI", ri), ("RG", rg)):
            ax.bars([i], [val], 0.56, color=colors[key], baseline=base)
            base += val
        ax.scatter([i], [obs_mm], 3.6, "#000000", marker="D")
    ax.frame(ticks_x=list(range(len(data))), labels_x=ids,
             ticks_y=nice_ticks(0, ymax, 6), label_y="时段径流深 (mm)", tick_size=8.5,
             grid=False)
    fig.legend([{"label": "地表径流 RS", "color": colors["RS"], "fill": True, "alpha": 255},
                {"label": "壤中流 RI", "color": colors["RI"], "fill": True, "alpha": 255},
                {"label": "地下径流 RG", "color": colors["RG"], "fill": True, "alpha": 255},
                {"label": "实测总径流深", "color": "#000000", "marker": True, "shape": "D"}],
               0.10, 0.925, size=8.4, horizontal=True)
    fig.text(left, 0.965, "三水源径流深构成与水量平衡（率定参数）", size=10.5, bold=True, va="center")
    path = FIG_DIR / "fig07_water_balance.png"
    return fig.save(str(path))


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    result = read_json(CAL_DIR / "calibration_result.json")
    prm_best = Params.from_mapping(result["params"])
    prm_init = load_params()
    bounds = load_bounds()
    events = load_all_events()
    band = np.load(ANA_DIR / "ensemble_band.npz")

    print("saved", fig01(events, prm_best, prm_init, result["metrics"]))
    band4 = {k.replace("event4_", ""): band[k] for k in band.files if k.startswith("event4_")}
    print("saved", fig02(events["event4"], prm_best, prm_init, band4, result["validation"]))
    print("saved", fig03(result["de_history"], result["objective"]))
    print("saved", fig04(events, prm_best))

    spread_rows = read_csv_rows(ANA_DIR / "parameter_spread.csv")
    print("saved", fig05(spread_rows, bounds))

    oat_rows = read_csv_rows(ANA_DIR / "oat_sensitivity.csv")
    for r in oat_rows:
        for k in ("基准值", "DC@下限", "DC@上限", "ΔDC@下限", "ΔDC@上限", "最大|ΔDC|", "基准平均DC"):
            r[k] = float(r[k])
    print("saved", fig06(oat_rows))
    print("saved", fig07(events, prm_best))


if __name__ == "__main__":
    main()

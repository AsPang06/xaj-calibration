# -*- coding: utf-8 -*-
"""脚本 05：复现一致性自检。

把当前 ``outputs/`` 与 ``report/`` 里的结果和项目定稿时冻结的期望值逐项比对，
用于“手动复现一次”之后确认结果没有漂移。

运行::

    python scripts/05_verify.py

全部一致时退出码为 0；有任何一项不一致时打印差异并返回 1。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CAL_DIR = ROOT / "outputs" / "calibration"
ANA_DIR = ROOT / "outputs" / "analysis"
FIG_DIR = ROOT / "outputs" / "figures"
REPORT = ROOT / "report" / "新安江模型参数率定报告.docx"

# ---------------------------------------------------------------------------
# 冻结的期望值（来自项目定稿：seed=42，numpy 2.3.5 / Python 3.12）
# ---------------------------------------------------------------------------
EXPECT_J = 0.0007146931490243924
EXPECT_MEAN_DC = 0.9992853068509756
EXPECT_NFEV = 96240

EXPECT_PARAMS = {
    "K": 0.7540040778117667, "WUM": 20.047939395248704,
    "WLM": 58.47711251117799, "WDM": 26.170562727418982,
    "C": 0.1180724818610088, "B": 0.34854392351959196,
    "IM": 0.00116657593693555, "SM": 18.240063839738674,
    "EX": 1.812758260700361, "KI": 0.17096905201965784,
    "KG": 0.16125407424051946, "CS": 0.6264239242415381,
    "CI": 0.5569116890979008, "CG": 0.9522597716076612,
    "KE": 13.446909010342548, "X": 0.16483670557611327,
}

# 每场：dc, rmse, peak_err_pct, peak_time_err_h, vol_err_pct
EXPECT_METRICS = {
    "event1": (0.9997380393193921, 1.215317491427022,
               -1.4052183715401723, 0.0, -0.4231216450638324),
    "event2": (0.9983877170861174, 9.158834094918136,
               1.917913167243484, 0.0, 0.244809137868872),
    "event3": (0.9997301641474172, 3.0124956045719467,
               0.5431290224611262, 0.0, -0.029932314699166185),
    "event4": (0.9990564177863496, 3.4966822328808647,
               1.6264112870057899, 6.0, -0.9358248468916992),
}

EXPECT_ANA = {
    "n_population": 240,
    "n_behavioral": 240,
    "dc_calibration_range": (0.9987331785962127, 0.9992362774959181),
    "dc_event4_range": (0.9964891257880704, 0.9995135013157201),
    "dc_event4_median": 0.998759558885358,
}

EXPECT_FIGS = [
    "fig01_calibration_hydrographs.png", "fig02_validation_ensemble.png",
    "fig03_convergence.png", "fig04_scatter.png", "fig05_parameter_spread.png",
    "fig06_sensitivity.png", "fig07_water_balance.png",
]

TOL_NUM = 1e-9       # 目标函数、DC、参数：本模型全程纯 Python 浮点，应当逐位一致
TOL_RMSE = 1e-5      # 量级 1~10，留一点余量
TOL_PCT = 1e-5
TOL_PEAK = 1e-5

rows: list[tuple[str, str, str, bool]] = []


def check_num(name: str, got, want, tol: float = TOL_NUM) -> None:
    """数值比较：把结果记入 rows。tol=0 表示必须完全相等。"""
    got_f, want_f = float(got), float(want)
    ok = abs(got_f - want_f) <= tol * max(1.0, abs(want_f))
    rows.append((name, f"{got_f:.10g}", f"{want_f:.10g}", ok))


def main() -> int:
    # ---- 1. 文件是否齐全 ----
    need = [
        CAL_DIR / "best_params.csv", CAL_DIR / "calibration_metrics.csv",
        CAL_DIR / "calibration_result.json", CAL_DIR / "de_population.npz",
        ANA_DIR / "behavioral_sets.csv", ANA_DIR / "parameter_spread.csv",
        ANA_DIR / "oat_sensitivity.csv", ANA_DIR / "ensemble_band.npz",
        ANA_DIR / "summary.json", REPORT,
    ]
    for p in need:
        rows.append((f"文件存在 {p.relative_to(ROOT)}", "是" if p.exists() else "缺失",
                     "是", p.exists()))
    for name in EXPECT_FIGS:
        p = FIG_DIR / name
        ok = p.exists() and p.stat().st_size > 20_000
        rows.append((f"图件 {name}", f"{p.stat().st_size // 1024 if p.exists() else 0} KB",
                     ">20 KB", ok))

    if not (CAL_DIR / "calibration_result.json").exists():
        print("未找到 outputs/calibration/calibration_result.json，请先运行 01_calibrate.py")
        return 1

    cal = json.loads((CAL_DIR / "calibration_result.json").read_text(encoding="utf-8"))

    # ---- 2. 率定数值 ----
    check_num("目标函数 J", cal["objective"], EXPECT_J)
    check_num("平均 DC", cal["mean_dc"], EXPECT_MEAN_DC)
    check_num("DE 评价次数 nfev", cal["nfev"], EXPECT_NFEV, 0)
    for name, want in EXPECT_PARAMS.items():
        check_num(f"参数 {name}", cal["params"][name], want)

    # ---- 3. 四场指标 ----
    merged = dict(cal["metrics"])
    merged["event4"] = cal["validation"]
    for eid, want in EXPECT_METRICS.items():
        m = merged[eid]
        dc, rmse, perr, ph, verr = want
        check_num(f"{eid} DC", m["dc"], dc)
        check_num(f"{eid} RMSE", m["rmse"], rmse, TOL_RMSE)
        check_num(f"{eid} 洪峰误差%", m["peak_err_pct"], perr, TOL_PCT)
        check_num(f"{eid} 峰现时差h", m["peak_time_err_h"], ph, 0)
        check_num(f"{eid} 径流深误差%", m["vol_err_pct"], verr, TOL_PCT)

    # ---- 4. 异参同效分析 ----
    ana_path = ANA_DIR / "summary.json"
    if ana_path.exists():
        ana = json.loads(ana_path.read_text(encoding="utf-8"))
        check_num("行为参数集个数", ana["n_behavioral"], EXPECT_ANA["n_behavioral"], 0)
        check_num("DE 种群规模", ana["n_population"], EXPECT_ANA["n_population"], 0)
        check_num("检验期 DC 下界", ana["dc_event4_range"][0],
                  EXPECT_ANA["dc_event4_range"][0], 1e-6)
        check_num("检验期 DC 上界", ana["dc_event4_range"][1],
                  EXPECT_ANA["dc_event4_range"][1], 1e-6)
        check_num("检验期 DC 中位数", ana["dc_event4_median"],
                  EXPECT_ANA["dc_event4_median"], 1e-6)

    # ---- 5. 报告结构 ----
    if REPORT.exists():
        try:
            from docx import Document

            doc = Document(str(REPORT))
            text = "\n".join(p.text for p in doc.paragraphs)
            rows.append(("报告插图数", str(len(doc.inline_shapes)), "7",
                         len(doc.inline_shapes) == 7))
            rows.append(("报告表格数", str(len(doc.tables)), "10",
                         len(doc.tables) == 10))
            for key in ["峰现时间误差 6 h", "68%~76%", "12 个输出序列",
                        "5.3  误差分析", "水量平衡校验"]:
                rows.append((f"报告包含“{key}”", "是" if key in text else "否", "是",
                             key in text))
        except ImportError:
            rows.append(("python-docx 可用", "否", "是", False))

    # ---- 输出 ----
    width = max(len(r[0]) for r in rows)
    print(f"{'检查项'.ljust(width)}  {'当前值':>16}  {'期望值':>16}  结果")
    print("-" * (width + 50))
    failed = 0
    for name, got, want, ok in rows:
        print(f"{name.ljust(width)}  {got:>16}  {want:>16}  {'PASS' if ok else 'FAIL'}")
        failed += 0 if ok else 1
    print("-" * (width + 50))
    total = len(rows)
    if failed:
        print(f"共 {total} 项，{failed} 项不一致。若刚改过参数/随机种子，属预期；"
              f"否则检查是否用了同一解释器（numpy/pandas 版本见 README 3.1 节）。")
        return 1
    print(f"共 {total} 项，全部一致 —— 复现成功。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

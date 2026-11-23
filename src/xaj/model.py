# -*- coding: utf-8 -*-
"""新安江模型（三水源）正向模拟核心。

结构（与课件/数据包 v2 一致）::

    降雨 P ─→ 三层蒸散发(K, WUM, WLM, WDM, C) ─→ 净雨 PE
    PE ─→ 蓄满产流(B, IM; 状态 W) ─→ 产流 R、产流面积比 FR
    R  ─→ 自由水蓄水库三水源划分(SM, EX, KI, KG; 状态 S) ─→ RS / RI / RG
    RS/RI/RG ─→ 线性水库(CS/CI/CG) ─→ QS/QI/QG ─→ Q_in
    Q_in ─→ 马斯京根河道演算(KE, X) ─→ 出口断面 Q

时段长 Δt = 6 h，流域面积 F = 2000 km²，换算系数 U = F/(3.6·Δt)。

本模块为教学数据包 ``xaj_model.py`` 的工程化重写：
公式逐行对齐，但改为标量运算（率定时单次模拟约快 3~4 倍），
并通过 ``tests/test_model_equivalence.py`` 与原始实现做数值等价性校验。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

import numpy as np

# ---------------- 流域与时段常量 ----------------
F_BASIN_KM2 = 2000.0                       # 流域面积 (km²)
DT_H = 6.0                                 # 时段长 (h)
U_CONV = F_BASIN_KM2 / (3.6 * DT_H)        # 换算系数: 1 mm/时段 ≈ 92.6 m³/s

# 16 个模型参数（顺序即参数表顺序）
PARAM_NAMES = ["K", "WUM", "WLM", "WDM", "C", "B", "IM",
               "SM", "EX", "KI", "KG", "CS", "CI", "CG", "KE", "X"]


@dataclass(frozen=True)
class Params:
    """新安江模型参数集合（不可变，便于缓存与并行）。"""

    K: float
    WUM: float
    WLM: float
    WDM: float
    C: float
    B: float
    IM: float
    SM: float
    EX: float
    KI: float
    KG: float
    CS: float
    CI: float
    CG: float
    KE: float
    X: float

    @classmethod
    def from_mapping(cls, m: Mapping[str, float]) -> "Params":
        """由 {参数名: 数值} 构造；缺少参数时抛出带明细的异常。"""
        missing = [k for k in PARAM_NAMES if k not in m]
        if missing:
            raise ValueError(f"参数缺失: {missing}")
        return cls(**{k: float(m[k]) for k in PARAM_NAMES})

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    @property
    def WM(self) -> float:
        """流域平均张力水蓄水容量 WM = WUM + WLM + WDM (mm)。"""
        return self.WUM + self.WLM + self.WDM


@dataclass
class State:
    """时段初模型状态。"""

    WU: float
    WL: float
    WD: float
    S: float
    QS: float
    QI: float
    QG: float

    @classmethod
    def from_mapping(cls, m: Mapping[str, float]) -> "State":
        return cls(WU=float(m["WU"]), WL=float(m["WL"]), WD=float(m["WD"]),
                   S=float(m["S"]), QS=float(m.get("QS", 0.0)),
                   QI=float(m["QI"]), QG=float(m["QG"]))

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


# ---------------- 1. 三层蒸散发 ----------------
def evapotranspire(P: float, EP: float, WU: float, WL: float, WD: float,
                   prm: Params) -> tuple[float, float, float, float]:
    """三层蒸散发。

    P: 时段降雨(mm); EP: 时段蒸散发能力(mm)=K·EM。
    返回 (E, WU, WL, WD)，E 为实际蒸散发(mm)。
    """
    WUM, WLM, C = prm.WUM, prm.WLM, prm.C
    if WU + P >= EP:
        EU, EL, ED = EP, 0.0, 0.0
    else:
        EU = WU + P
        if WL >= C * WLM:
            EL, ED = min((EP - EU) * WL / WLM, WL), 0.0
        elif WL >= C * (EP - EU):
            EL, ED = C * (EP - EU), 0.0
        else:
            EL = WL
            ED = min(C * (EP - EU) - EL, WD)      # 深层蒸散发不超过深层蓄水
    WU = WU + P - EU
    WL = WL - EL
    WD = WD - ED
    return EU + EL + ED, WU, WL, WD


# ---------------- 2. 蓄满产流 ----------------
def runoff(PE: float, W: float, prm: Params) -> tuple[float, float, float, float]:
    """蓄满产流。

    PE: 时段净雨(mm); W: 时段初（降雨前）流域土壤蓄水(mm)。
    返回 (R, RIM, FR, W_over)：
      R      总产流(mm)，含不透水产流与串层溢出；
      RIM    不透水面积产流(mm) = PE·IM；
      FR     透水面积产流面积比；
      W_over 超过 WM 的异常滞蓄（正常为 0）。
    """
    WM = prm.WM
    B, IM = prm.B, prm.IM
    W_over = max(W - WM, 0.0)          # 土层串层溢出的水，直接产流
    W = min(W, WM)
    if PE <= 0.0:
        return W_over, 0.0, 0.0, W_over
    WMM = WM * (1.0 + B)
    A0 = WMM * (1.0 - (1.0 - W / WM) ** (1.0 / (1.0 + B)))
    if PE + A0 < WMM:
        R = PE - WM + W + WM * (1.0 - (PE + A0) / WMM) ** (1.0 + B)
    else:
        R = PE - (WM - W)
    R = max(R, 0.0) + W_over
    RIM = PE * IM                       # 不透水面积直接产流
    FR = max(R - W_over, 0.0) / PE      # 透水面积产流比（供水水源划分用）
    return R, RIM, FR, W_over


# ---------------- 3. 三水源划分（自由水蓄水库） ----------------
def split_sources(R_perm: float, FR: float, S: float,
                  prm: Params) -> tuple[float, float, float, float]:
    """自由水蓄水库划分三水源。

    R_perm: 透水面积产流 R−W_over(mm); FR: 产流面积比; S: 自由水蓄水(mm)。
    返回 (RS, RI, RG, S_new)。
    """
    SM, EX, KI, KG = prm.SM, prm.EX, prm.KI, prm.KG
    S = min(max(S, 0.0), SM)            # 容错：率定中 SM 变小时自由水蓄量不越界
    if R_perm <= 0.0 or FR <= 0.0:
        return 0.0, 0.0, 0.0, S
    SMM = SM * (1.0 + EX)
    AU = SMM * (1.0 - (1.0 - S / SM) ** (1.0 / (1.0 + EX)))
    if R_perm + AU < SMM:
        RB = FR * (R_perm - (SM - S) + SM * (1.0 - (R_perm + AU) / SMM) ** (1.0 + EX))
    else:
        RB = FR * (R_perm - SM + S)
    RI = KI * S * FR
    RG = KG * S * FR
    if RI + RG > RB:                    # 壤中流+地下径流不超过总出流，等比缩减保证守恒
        f = RB / (RI + RG)
        RI, RG = RI * f, RG * f
    RS = max(RB - RI - RG, 0.0)
    # 自由水蓄量更新（流域平均口径）：ΔS = 产流量 − 三水源出流；
    # 超过 SM 的溢出部分补回地表径流，保证水量守恒。
    S_raw = S + R_perm - RB
    S_new = min(max(S_raw, 0.0), SM)
    RS = RS + max(S_raw - SM, 0.0)
    return RS, RI, RG, S_new


# ---------------- 4. 汇流（三水源均为线性水库） ----------------
def route(RS_mm: Sequence[float], RI_mm: Sequence[float], RG_mm: Sequence[float],
          QS0: float, QI0: float, QG0: float,
          prm: Params) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """三水源线性水库汇流。

    线性水库: Q(t) = C·Q(t−1) + (1−C)·U·I(t)，地表/壤中/地下分别用 CS/CI/CG。
    输入为 mm/时段，输出为 m³/s。
    """
    n = len(RS_mm)
    CS, CI, CG = prm.CS, prm.CI, prm.CG
    qs, qi, qg = QS0, QI0, QG0
    QS = np.empty(n)
    QI = np.empty(n)
    QG = np.empty(n)
    for t in range(n):
        qs = CS * qs + (1.0 - CS) * U_CONV * RS_mm[t]
        qi = CI * qi + (1.0 - CI) * U_CONV * RI_mm[t]
        qg = CG * qg + (1.0 - CG) * U_CONV * RG_mm[t]
        QS[t] = qs
        QI[t] = qi
        QG[t] = qg
    return QS, QI, QG


def muskingum(I: Sequence[float], KE: float, x: float,
              dt_h: float = DT_H) -> np.ndarray:
    """马斯京根河道演算。

    KE: 河段传播时间(h); x: 楔蓄权重(0~0.5)。
    C0/C1/C2 按经典形式计算，O[0] = I[0]。
    """
    dt = dt_h
    den = KE - KE * x + 0.5 * dt
    C0 = (0.5 * dt - KE * x) / den
    C1 = (0.5 * dt + KE * x) / den
    C2 = (KE - KE * x - 0.5 * dt) / den
    n = len(I)
    O = np.empty(n)
    O[0] = I[0]
    for t in range(1, n):
        O[t] = C0 * I[t] + C1 * I[t - 1] + C2 * O[t - 1]
    return O


# ---------------- 正向模拟主程序 ----------------
def simulate(P, EM, prm: Params, state0: Mapping[str, float]) -> dict:
    """正向模拟一场洪水。

    参数
        P, EM : 等长序列，时段降雨 / 蒸发皿蒸发 (mm/6h)
        prm   : Params
        state0: 初始状态 {"WU","WL","WD","S","QS","QI","QG"}
    返回
        dict：Q(出口断面流量)、Q_in(河道演算前)、QS/QI/QG、
              R/E/W/S 过程、RS_mm/RI_mm/RG_mm、state_end。
    """
    P = np.asarray(P, dtype=float).tolist()
    EM = np.asarray(EM, dtype=float).tolist()
    n = len(P)
    if len(EM) != n:
        raise ValueError("P 与 EM 长度不一致")

    WUM, WLM, WDM = prm.WUM, prm.WLM, prm.WDM
    WM = WUM + WLM + WDM
    K, C, B, IM = prm.K, prm.C, prm.B, prm.IM
    SM, EX, KI, KG = prm.SM, prm.EX, prm.KI, prm.KG
    CS, CI, CG = prm.CS, prm.CI, prm.CG

    # 初始状态容错：不超过各层容量
    WU = min(float(state0["WU"]), WUM)
    WL = min(float(state0["WL"]), WLM)
    WD = min(float(state0["WD"]), WDM)
    S = min(float(state0["S"]), SM)
    QS0 = float(state0.get("QS", 0.0))
    QI0, QG0 = float(state0["QI"]), float(state0["QG"])

    E_a = [0.0] * n
    R_a = [0.0] * n
    W_a = [0.0] * n
    S_a = [0.0] * n
    RSs = [0.0] * n
    RIa = [0.0] * n
    RGa = [0.0] * n

    for t in range(n):
        Pt = P[t]
        W0 = WU + WL + WD                       # 时段初（降雨前）蓄水
        EP = K * EM[t]

        # --- 三层蒸散发（内联以提升率定速度） ---
        if WU + Pt >= EP:
            EU, EL, ED = EP, 0.0, 0.0
        else:
            EU = WU + Pt
            if WL >= C * WLM:
                EL, ED = min((EP - EU) * WL / WLM, WL), 0.0
            elif WL >= C * (EP - EU):
                EL, ED = C * (EP - EU), 0.0
            else:
                EL = WL
                ED = min(C * (EP - EU) - EL, WD)
        WU = WU + Pt - EU
        WL = WL - EL
        WD = WD - ED
        E = EU + EL + ED

        PE = Pt - E
        PE_pos = PE if PE > 0.0 else 0.0

        # --- 蓄满产流 ---
        W_over = W0 - WM if W0 > WM else 0.0
        Wt = W0 if W0 < WM else WM
        if PE_pos <= 0.0:
            R, RIM, FR = W_over, 0.0, 0.0
        else:
            WMM = WM * (1.0 + B)
            A0 = WMM * (1.0 - (1.0 - Wt / WM) ** (1.0 / (1.0 + B)))
            if PE_pos + A0 < WMM:
                R = PE_pos - WM + Wt + WM * (1.0 - (PE_pos + A0) / WMM) ** (1.0 + B)
            else:
                R = PE_pos - (WM - Wt)
            R = max(R, 0.0) + W_over
            RIM = PE_pos * IM
            FR = (R - W_over) / PE_pos

        # --- 流域蓄水更新：W' = W0 + PE − (R − W_over) ---
        W_new = (W0 if W0 < WM else WM) + PE - (R - W_over)
        W_new = min(max(W_new, 0.0), WM)
        WU = W_new if W_new < WUM else WUM
        WL = W_new - WU
        WL = min(max(WL, 0.0), WLM)
        WD = max(W_new - WU - WL, 0.0)

        # --- 三水源划分 ---
        R_perm = R - W_over
        if R_perm <= 0.0 or FR <= 0.0:
            RS, RI, RG, S_new = 0.0, 0.0, 0.0, S
        else:
            S_c = min(max(S, 0.0), SM)
            SMM = SM * (1.0 + EX)
            AU = SM * (1.0 + EX) * (1.0 - (1.0 - S_c / SM) ** (1.0 / (1.0 + EX)))
            if R_perm + AU < SMM:
                RB = FR * (R_perm - (SM - S_c) + SM * (1.0 - (R_perm + AU) / SMM) ** (1.0 + EX))
            else:
                RB = FR * (R_perm - SM + S_c)
            RI = KI * S_c * FR
            RG = KG * S_c * FR
            if RI + RG > RB:
                f = RB / (RI + RG)
                RI, RG = RI * f, RG * f
            RS = max(RB - RI - RG, 0.0)
            S_raw = S_c + R_perm - RB
            S_new = min(max(S_raw, 0.0), SM)
            RS = RS + max(S_raw - SM, 0.0)

        S = S_new
        RSs[t] = RS + RIM + W_over              # 不透水产流与串层溢出直接进入地表
        RIa[t] = RI
        RGa[t] = RG
        E_a[t] = E
        R_a[t] = R + RIM
        W_a[t] = W_new
        S_a[t] = S

    # --- 汇流：线性水库 + 马斯京根 ---
    QS = np.empty(n)
    QI = np.empty(n)
    QG = np.empty(n)
    qs, qi, qg = QS0, QI0, QG0
    for t in range(n):
        qs = CS * qs + (1.0 - CS) * U_CONV * RSs[t]
        qi = CI * qi + (1.0 - CI) * U_CONV * RIa[t]
        qg = CG * qg + (1.0 - CG) * U_CONV * RGa[t]
        QS[t] = qs
        QI[t] = qi
        QG[t] = qg
    Q_in = QS + QI + QG

    # 马斯京根演算至出口断面
    dt = DT_H
    den = prm.KE - prm.KE * prm.X + 0.5 * dt
    C0 = (0.5 * dt - prm.KE * prm.X) / den
    C1 = (0.5 * dt + prm.KE * prm.X) / den
    C2 = (prm.KE - prm.KE * prm.X - 0.5 * dt) / den
    Q = np.empty(n)
    Q[0] = Q_in[0]
    for t in range(1, n):
        Q[t] = C0 * Q_in[t] + C1 * Q_in[t - 1] + C2 * Q[t - 1]

    return {
        "Q": Q, "Q_in": Q_in, "QS": QS, "QI": QI, "QG": QG,
        "R": np.asarray(R_a), "E": np.asarray(E_a),
        "W": np.asarray(W_a), "S": np.asarray(S_a),
        "RS_mm": np.asarray(RSs), "RI_mm": np.asarray(RIa), "RG_mm": np.asarray(RGa),
        "state_end": {"WU": WU, "WL": WL, "WD": WD, "S": S,
                      "QS": float(QS[-1]), "QI": float(QI[-1]), "QG": float(QG[-1])},
    }

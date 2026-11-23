# -*- coding: utf-8 -*-
"""数据校验器（第 1 讲配套）。

``load_event(path)`` 读取一场洪水的观测 CSV，只报告、不修改，
拦截三类问题：

1. 缺测 —— 数据列为空（或行业惯用的 -999 缺测标记）
2. 负值 —— 雨量、蒸发、流量出现物理上不可能的负数
3. 乱序 —— 时间列不是严格的 6 小时间隔递增序列

结构性问题（缺列、时间无法解析）直接抛 ``ValueError``。

本模块由数据包 ``data_validator.py`` 重构而来，行为与报错文案保持一致，
并补充了 ``validate_dataframe`` 以便单元测试直接复用。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["时间",
                    "P_青岭(mm)", "P_石林(mm)", "P_溪口(mm)",
                    "P_龙潭(mm)", "P_白沙(mm)", "P_梅溪(mm)",
                    "面雨量P(mm)", "蒸发皿EM(mm)", "实测流量Q(m3/s)"]
DT_HOURS = 6             # 数据时段长
MISSING_MARK = -999.0    # 水文行业惯用的缺测标记


def load_event(path: str | Path, strict: bool = False) -> tuple[pd.DataFrame, list[str]]:
    """读取并校验一场洪水的观测 CSV。

    参数
        path   : CSV 文件路径
        strict : True 时发现问题即抛 ValueError（汇总全部问题）；
                 False（默认）时正常返回，问题记录在 issues 里
    返回
        (df, issues)
        df     : 原始数据的 DataFrame（不做任何修补）
        issues : list[str]，形如 "缺测 | 第18行(2023-07-18 06:00) | P_白沙(mm)：空值"
    """
    df = pd.read_csv(path)

    # ---- 结构检查：缺列属于致命问题，直接抛异常 ----
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"文件缺少必需的数据列: {missing_cols}")

    # ---- 时间列必须能解析 ----
    try:
        times = pd.to_datetime(df["时间"])
    except Exception as exc:  # noqa: BLE001 - 保留原始异常文本给使用者
        raise ValueError(f"时间列无法解析: {exc}") from exc

    issues = _check_frame(df, times)

    if strict and issues:
        raise ValueError(f"数据校验未通过，共 {len(issues)} 处问题：\n" + "\n".join(issues))
    return df, issues


def validate_dataframe(df: pd.DataFrame, strict: bool = False) -> list[str]:
    """对已在内存中的 DataFrame 执行同样的三类检查。"""
    times = pd.to_datetime(df["时间"])
    issues = _check_frame(df, times)
    if strict and issues:
        raise ValueError(f"数据校验未通过，共 {len(issues)} 处问题：\n" + "\n".join(issues))
    return issues


def _check_frame(df: pd.DataFrame, times: pd.Series) -> list[str]:
    issues: list[str] = []
    t_str = times.dt.strftime("%Y-%m-%d %H:%M")

    # ---- 第 1 类：缺测（空值 或 -999 标记） ----
    for col in REQUIRED_COLUMNS[1:]:
        vals = df[col]
        for i in df.index[vals.isna()]:
            issues.append(f"缺测 | 第{i + 2}行({t_str[i]}) | {col}：空值")
        for i in df.index[vals == MISSING_MARK]:
            issues.append(f"缺测 | 第{i + 2}行({t_str[i]}) | {col}：缺测标记 -999")

    # ---- 第 2 类：负值（-999 已按缺测报告，这里只报其余负数） ----
    for col in REQUIRED_COLUMNS[1:]:
        vals = df[col]
        bad = df.index[(vals < 0) & (vals != MISSING_MARK) & vals.notna()]
        for i in bad:
            issues.append(f"负值 | 第{i + 2}行({t_str[i]}) | {col}：{vals[i]}")

    # ---- 第 3 类：乱序（时间回退 或 间隔不为 6 小时） ----
    diffs = times.diff().dt.total_seconds() / 3600.0
    for i in range(1, len(times)):
        if diffs[i] <= 0:
            issues.append(f"乱序 | 第{i + 2}行({t_str[i]}) | 时间回退，早于或等于上一行({t_str[i - 1]})")
        elif diffs[i] != DT_HOURS:
            issues.append(f"乱序 | 第{i + 2}行({t_str[i]}) | 与上一行间隔 {diffs[i]:g} 小时，应为 {DT_HOURS} 小时")
    return issues

# -*- coding: utf-8 -*-
"""数据读写与工程配置。

项目根目录下::

    data/raw/basin_info.csv         流域信息（含泰森权重）
    data/raw/params_initial.csv     16 个参数初值与参考范围
    data/raw/events_index.csv       4 场洪水的索引与初始状态
    data/raw/events/eventN.csv      场次观测数据
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .model import PARAM_NAMES, Params
from .validator import load_event

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
EVENTS_DIR = RAW_DIR / "events"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

#: 率定 / 检验场次划分（README §5：场次 1~3 率定，场次 4 检验）
CALIBRATION_EVENTS = ("event1", "event2", "event3")
VALIDATION_EVENTS = ("event4",)

STATION_WEIGHTS = {"青岭": 0.22, "石林": 0.18, "溪口": 0.15,
                   "龙潭": 0.17, "白沙": 0.13, "梅溪": 0.15}


def _read_csv(path: Path) -> pd.DataFrame:
    """统一以 UTF-8-SIG 读取数据包 CSV。"""
    return pd.read_csv(path, encoding="utf-8-sig")


def load_param_table(path: str | Path | None = None) -> pd.DataFrame:
    """读取参数表：参数 / 含义 / 单位 / 参考范围 / 参数值。"""
    path = Path(path) if path is not None else RAW_DIR / "params_initial.csv"
    df = _read_csv(path)
    missing = [p for p in PARAM_NAMES if p not in set(df["参数"])]
    if missing:
        raise ValueError(f"参数表缺少参数: {missing}")
    return df


def parse_range(text: str) -> tuple[float, float]:
    """解析参考范围字符串，如 ``'0.7~1.1'`` → (0.7, 1.1)。"""
    nums = re.findall(r"-?\d+(?:\.\d+)?", str(text))
    if len(nums) < 2:
        raise ValueError(f"无法解析参数范围: {text!r}")
    return float(nums[0]), float(nums[1])


def load_bounds(path: str | Path | None = None) -> dict[str, tuple[float, float]]:
    """参数上下限（取自参数表“参考范围”列）。"""
    table = load_param_table(path)
    bounds = {}
    for _, row in table.iterrows():
        lo, hi = parse_range(row["参考范围"])
        bounds[row["参数"]] = (lo, hi)
    return {name: bounds[name] for name in PARAM_NAMES}


def load_params(path: str | Path | None = None) -> Params:
    """读取 16 个参数为 ``Params``。"""
    table = load_param_table(path)
    values = dict(zip(table["参数"], table["参数值"].astype(float)))
    return Params.from_mapping(values)


def load_index(path: str | Path | None = None) -> pd.DataFrame:
    """读取洪水场次索引。"""
    path = Path(path) if path is not None else RAW_DIR / "events_index.csv"
    return _read_csv(path)


def state0_from_row(row: pd.Series) -> dict[str, float]:
    """把索引表一行转换为模型初始状态字典。"""
    return {"WU": float(row["初始WU(mm)"]), "WL": float(row["初始WL(mm)"]),
            "WD": float(row["初始WD(mm)"]), "S": float(row["初始S(mm)"]),
            "QS": float(row["初始QS(m³/s)"]), "QI": float(row["初始QI(m³/s)"]),
            "QG": float(row["初始QG(m³/s)"])}


def load_events(ids: Iterable[str] | None = None) -> dict[str, dict]:
    """按场次编号读取观测数据与初始状态。

    返回 ``{event_id: {"df": DataFrame, "state0": dict, "issues": list[str]}}``。
    """
    index = load_index().set_index("场次编号")
    ids = list(ids) if ids is not None else list(index.index)
    events: dict[str, dict] = {}
    for eid in ids:
        df, issues = load_event(EVENTS_DIR / f"{eid}.csv")
        events[eid] = {"df": df, "state0": state0_from_row(index.loc[eid]), "issues": issues}
    return events


def areal_rainfall(df: pd.DataFrame, weights: dict[str, float] | None = None) -> np.ndarray:
    """按泰森权重由 6 站雨量重算面雨量，用于复核数据包中的“面雨量P”列。"""
    weights = weights or STATION_WEIGHTS
    total = np.zeros(len(df))
    for station, w in weights.items():
        total += w * df[f"P_{station}(mm)"].to_numpy(dtype=float)
    return total


def load_basin_info(path: str | Path | None = None) -> dict[str, str]:
    """读取流域信息为 {项目: 取值} 字典。"""
    path = Path(path) if path is not None else RAW_DIR / "basin_info.csv"
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {row["项目"]: row["取值"] for row in csv.DictReader(fh)}


def save_parameter_table(rows: list[dict], path: str | Path) -> Path:
    """把参数对照表写为 UTF-8-SIG CSV（Excel 可直接打开）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path

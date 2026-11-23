# -*- coding: utf-8 -*-
"""青河流域新安江模型参数率定 —— 工程化实现包。"""

from .io import (CALIBRATION_EVENTS, VALIDATION_EVENTS, areal_rainfall,
                 load_bounds, load_events, load_index, load_params)
from .metrics import dc, evaluate, grade, kge, rmse, runoff_depth_mm
from .model import DT_H, F_BASIN_KM2, PARAM_NAMES, Params, State, simulate

__version__ = "1.0.0"

__all__ = [
    "CALIBRATION_EVENTS", "VALIDATION_EVENTS", "DT_H", "F_BASIN_KM2",
    "PARAM_NAMES", "Params", "State", "areal_rainfall", "dc", "evaluate",
    "grade", "kge", "load_bounds", "load_events", "load_index", "load_params",
    "rmse", "runoff_depth_mm", "simulate",
]

# -*- coding: utf-8 -*-
"""数据校验器单元测试：四类夹具（正常 / 缺测 / 负值 / 乱序）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd  # noqa: E402

from xaj.validator import (MISSING_MARK, load_event,  # noqa: E402
                           validate_dataframe)

DATA = ROOT / "tests" / "data"


class TestValidator(unittest.TestCase):
    def test_normal_file_has_no_issue(self):
        _, issues = load_event(DATA / "event1_正常.csv")
        self.assertEqual(issues, [])

    def test_missing_values(self):
        _, issues = load_event(DATA / "event1_缺测.csv")
        self.assertEqual(len(issues), 2)
        self.assertTrue(all(i.startswith("缺测") for i in issues))
        text = "\n".join(issues)
        self.assertIn("P_白沙(mm)", text)
        self.assertIn("空值", text)
        self.assertIn("缺测标记 -999", text)

    def test_negative_value(self):
        _, issues = load_event(DATA / "event1_负值.csv")
        self.assertEqual(len(issues), 1)
        self.assertTrue(issues[0].startswith("负值"))
        self.assertIn("P_龙潭(mm)", issues[0])
        self.assertIn("-2.5", issues[0])

    def test_time_disorder(self):
        _, issues = load_event(DATA / "event1_乱序.csv")
        self.assertEqual(len(issues), 2)
        self.assertTrue(all(i.startswith("乱序") for i in issues))
        text = "\n".join(issues)
        self.assertIn("时间回退", text)
        self.assertIn("间隔 12 小时", text)

    def test_issue_message_format(self):
        """报错文案约定：类别 | 第N行(时间) | 列名：说明。"""
        _, issues = load_event(DATA / "event1_缺测.csv")
        first = issues[0]
        self.assertEqual(first.count("|"), 2)
        self.assertRegex(first, r"^缺测 \| 第\d+行\(\d{4}-\d{2}-\d{2} \d{2}:\d{2}\) \| ")

    def test_strict_mode_raises(self):
        with self.assertRaises(ValueError) as ctx:
            load_event(DATA / "event1_缺测.csv", strict=True)
        self.assertIn("数据校验未通过", str(ctx.exception))

    def test_missing_column_raises(self):
        df = pd.read_csv(DATA / "event1_正常.csv")
        broken = df.drop(columns=["面雨量P(mm)"])
        tmp = DATA / "_tmp_missing_column.csv"
        broken.to_csv(tmp, index=False, encoding="utf-8-sig")
        try:
            with self.assertRaises(ValueError):
                load_event(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def test_missing_mark_constant(self):
        self.assertEqual(MISSING_MARK, -999.0)

    def test_validate_dataframe_matches_file(self):
        df = pd.read_csv(DATA / "event1_负值.csv")
        issues = validate_dataframe(df)
        _, issues_file = load_event(DATA / "event1_负值.csv")
        self.assertEqual(issues, issues_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""連動率（同方向率）＋条件分解のテスト（ネット不要）。"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.coactivity import coactivity, same_dir_rate  # noqa: E402


class TestSameDir(unittest.TestCase):
    def test_all_same(self):
        r, n = same_dir_rate([1, -2, 3], [4, -5, 6])
        self.assertEqual(r, 1.0)
        self.assertEqual(n, 3)

    def test_half(self):
        r, n = same_dir_rate([1, 1, 1, 1], [1, 1, -1, -1])
        self.assertEqual(r, 0.5)
        self.assertEqual(n, 4)

    def test_zero_excluded(self):
        r, n = same_dir_rate([0, 1, -1], [5, 1, 1])
        self.assertEqual(n, 2)          # 0 の日は除外
        self.assertEqual(r, 0.5)


class TestCoactivity(unittest.TestCase):
    def _weekday_dates(self, n, start=_dt.date(2025, 1, 6)):  # 月曜開始
        days, d = [], start
        while len(days) < n:
            if d.weekday() < 5:
                days.append(d.isoformat())
            d += _dt.timedelta(days=1)
        return days

    def test_monday_stands_out(self):
        # 月曜は必ず同方向、他の曜日はランダムに半々にする
        dates = self._weekday_dates(200)
        x, y = [], []
        flip = False
        for d in dates:
            wd = _dt.date.fromisoformat(d).weekday()
            x.append(1.0)
            if wd == 0:              # 月曜: 必ず同方向
                y.append(1.0)
            else:                    # 他: 交互に反転
                y.append(1.0 if flip else -1.0)
                flip = not flip
        st = coactivity(dates, x, y)
        self.assertEqual(st.best_wd, 0)                 # 月曜が最強
        self.assertAlmostEqual(st.weekday[0][0], 1.0)   # 月曜100%
        self.assertLess(st.weekday[1][0], 0.9)          # 火曜は低い

    def test_trend_rising(self):
        # 前半は逆方向、後半は同方向 → recent>prior（上昇中）
        dates = self._weekday_dates(100)
        x = [1.0] * 100
        y = [-1.0] * 50 + [1.0] * 50
        st = coactivity(dates, x, y, recent_frac=0.5)
        self.assertAlmostEqual(st.recent, 1.0)
        self.assertAlmostEqual(st.prior, 0.0)
        self.assertGreater(st.trend, 0.5)
        self.assertIn("上昇中", st.trend_label())

    def test_labels(self):
        dates = self._weekday_dates(60)
        x = [1.0] * 60
        y = [1.0] * 60
        st = coactivity(dates, x, y)
        self.assertAlmostEqual(st.overall, 1.0)
        self.assertIn("曜", st.best_weekday_label())


if __name__ == "__main__":
    unittest.main()

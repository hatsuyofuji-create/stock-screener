# -*- coding: utf-8 -*-
"""コア計算の単体テスト（ネット不要・純Python）。

    python -m unittest discover -s tests   （pair-analysis ディレクトリで実行）
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis import (  # noqa: E402
    analyze_pair, classify_thickness, linreg, pct_returns, align,
)
from src.universe import classify_market, default_lag, to_yahoo_symbol  # noqa: E402


class TestStats(unittest.TestCase):
    def test_pct_returns(self):
        got = pct_returns([100, 110, 99])
        self.assertAlmostEqual(got[0], 0.1, places=9)
        self.assertAlmostEqual(got[1], -0.1, places=9)

    def test_pct_returns_zero_guard(self):
        self.assertEqual(pct_returns([0, 100]), [0.0])

    def test_linreg_perfect(self):
        # y = 2x で slope=2, r=+1
        x = [0.0, 1.0, 2.0, 3.0]
        y = [0.0, 2.0, 4.0, 6.0]
        slope, intercept, r = linreg(x, y)
        self.assertAlmostEqual(slope, 2.0, places=9)
        self.assertAlmostEqual(intercept, 0.0, places=9)
        self.assertAlmostEqual(r, 1.0, places=9)

    def test_linreg_degenerate(self):
        self.assertEqual(linreg([1.0], [1.0]), (0.0, 0.0, 0.0))
        # x 分散ゼロ
        self.assertEqual(linreg([2.0, 2.0], [1.0, 3.0])[0], 0.0)

    def test_align_intersection(self):
        d, a, b = align(["d1", "d2", "d3"], [1, 2, 3],
                        ["d2", "d3", "d4"], [20, 30, 40])
        self.assertEqual(d, ["d2", "d3"])
        self.assertEqual(a, [2, 3])
        self.assertEqual(b, [20, 30])

    def test_classify_thickness(self):
        self.assertEqual(classify_thickness(0.30), "太い")
        self.assertEqual(classify_thickness(-0.30), "太い")
        self.assertEqual(classify_thickness(0.20), "中")
        self.assertEqual(classify_thickness(0.05), "細い")


class TestUniverse(unittest.TestCase):
    def test_to_yahoo_symbol(self):
        self.assertEqual(to_yahoo_symbol("6146"), "6146.T")
        self.assertEqual(to_yahoo_symbol("tsm"), "TSM")
        self.assertEqual(to_yahoo_symbol("^sox"), "^SOX")
        self.assertEqual(to_yahoo_symbol("005930.KS"), "005930.KS")

    def test_classify_market(self):
        self.assertEqual(classify_market("6146.T"), "JP")
        self.assertEqual(classify_market("TSM"), "US")
        self.assertEqual(classify_market("^SOX"), "US")
        self.assertEqual(classify_market("2330.TW"), "TW")
        self.assertEqual(classify_market("005930.KS"), "KR")

    def test_default_lag(self):
        self.assertEqual(default_lag("TSM"), 1)


class TestAnalyzePair(unittest.TestCase):
    def _mk(self, n=200):
        """先行 lead と、その前日リターンに連動する後続 foll を作る。"""
        import random
        rng = random.Random(42)
        dates = [f"2025-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}" for i in range(n)]
        lead = [100.0]
        lead_ret = []
        for _ in range(n - 1):
            r = rng.gauss(0, 0.02)
            lead_ret.append(r)
            lead.append(lead[-1] * (1 + r))
        # 後続は「先行の前日リターン × 0.5 ＋ ノイズ」で動く（lag=1で連動）
        foll = [100.0]
        for i in range(n - 1):
            base = lead_ret[i - 1] * 0.5 if i >= 1 else 0.0
            r = base + rng.gauss(0, 0.005)
            foll.append(foll[-1] * (1 + r))
        return dates, lead, foll

    def test_beta_positive_and_lag(self):
        dates, lead, foll = self._mk()
        res = analyze_pair("LEAD", "FOLL", dates, lead, dates, foll,
                           lag=1, threshold=0.03)
        # 連動を仕込んだので beta と相関は正で有意
        self.assertGreater(res.beta, 0.2)
        self.assertGreater(res.corr, 0.3)
        self.assertEqual(res.thickness, "太い")
        self.assertEqual(res.n_days, len(dates) - 2)  # lag=1 で1本減る

    def test_event_stats_counts(self):
        dates, lead, foll = self._mk()
        res = analyze_pair("LEAD", "FOLL", dates, lead, dates, foll,
                           lag=1, threshold=0.03)
        # scatter は up/down イベント数の合計
        self.assertEqual(len(res.scatter), res.up.n + res.down.n)
        for _lr, _fr, followed in res.scatter:
            self.assertIn(followed, (True, False))

    def test_overlay_normalized_to_100(self):
        dates, lead, foll = self._mk(50)
        res = analyze_pair("LEAD", "FOLL", dates, lead, dates, foll, lag=1)
        self.assertAlmostEqual(res.overlay_leader[0], 100.0, places=6)
        self.assertAlmostEqual(res.overlay_follower[0], 100.0, places=6)

    def test_insufficient_data(self):
        res = analyze_pair("A", "B", ["d1"], [100], ["d1"], [100], lag=1)
        self.assertEqual(res.n_days, 0)
        self.assertEqual(res.beta, 0.0)


if __name__ == "__main__":
    unittest.main()

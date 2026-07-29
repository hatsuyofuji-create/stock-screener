# -*- coding: utf-8 -*-
"""連動ランキングの単体テスト（ネット不要・純Python）。"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rank import corr_beta_at_lag, rank_peers  # noqa: E402


def _series(n, rng, drift=0.0003, vol=0.02):
    p = [100.0]
    rets = []
    for _ in range(n - 1):
        r = rng.gauss(drift, vol)
        rets.append(r)
        p.append(p[-1] * (1 + r))
    return p, rets


class TestCorrAtLag(unittest.TestCase):
    def test_lag_alignment_lengths(self):
        t = [0.0, 1.0, 2.0, 3.0, 4.0]
        c = [10.0, 11.0, 12.0, 13.0, 14.0]
        # lag>0/<0/0 で標本数が縮む
        self.assertEqual(corr_beta_at_lag(t, c, 0)[2], 5)
        self.assertEqual(corr_beta_at_lag(t, c, 2)[2], 3)
        self.assertEqual(corr_beta_at_lag(t, c, -2)[2], 3)

    def test_too_short(self):
        self.assertEqual(corr_beta_at_lag([1.0, 2.0], [1.0, 2.0], 0)[2], 2)
        self.assertEqual(corr_beta_at_lag([1.0, 2.0], [1.0, 2.0], 0)[1], 0.0)


class TestRankPeers(unittest.TestCase):
    def _dates(self, n):
        return [f"2025-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}" for i in range(n)]

    def test_leader_detected_and_ranked_top(self):
        """候補に1日先行する『LEADER』を仕込み、最上位かつ best_lag>0 を確認。"""
        rng = random.Random(7)
        n = 300
        dates = self._dates(n)
        # target のリターンを作る
        tgt, t_ret = _series(n, rng)
        # LEADER: 今日のリターンが target の「翌日」リターンを先取り（＝1日先行）
        lead = [100.0]
        for i in range(n - 1):
            drive = t_ret[i + 1] if i + 1 < len(t_ret) else 0.0
            r = 0.8 * drive + rng.gauss(0, 0.004)
            lead.append(lead[-1] * (1 + r))
        # NOISE: 無関係
        noise, _ = _series(n, random.Random(999))

        cands = {
            "LEADER": (dates, lead),
            "NOISE": (dates, noise),
        }
        rows = rank_peers("TGT", dates, tgt, cands, mode="time_lag")
        self.assertEqual(rows[0].symbol, "LEADER")
        self.assertGreater(rows[0].best_lag, 0)       # LEADER が先行
        self.assertGreater(abs(rows[0].best_corr), abs(rows[1].best_corr))
        self.assertIn("順", rows[0].relation)

    def test_inverse_relation_flagged(self):
        rng = random.Random(3)
        n = 200
        dates = self._dates(n)
        tgt, t_ret = _series(n, rng)
        # 逆相関（同日で符号反転）
        inv = [100.0]
        for i in range(n - 1):
            r = -0.9 * t_ret[i] + rng.gauss(0, 0.003)
            inv.append(inv[-1] * (1 + r))
        rows = rank_peers("TGT", dates, tgt, {"INV": (dates, inv)},
                          mode="same_day")
        self.assertIn("逆", rows[0].relation)
        self.assertLess(rows[0].corr0, 0)

    def test_skips_short_and_self(self):
        dates = self._dates(50)
        tgt, _ = _series(50, random.Random(1))
        cands = {
            "TGT": (dates, tgt),                     # 自分自身は除外
            "SHORT": (dates[:10], tgt[:10]),         # 短すぎ → min_days で除外
        }
        rows = rank_peers("TGT", dates, tgt, cands, mode="time_lag", min_days=30)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()

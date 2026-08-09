# -*- coding: utf-8 -*-
"""
累計→単独 変換のテスト。
画像の実データ（DMG森精機・岡本工作機械）で検算します。
外部ネットワークやAPIキーは不要（純粋な計算のみ）。
"""

from src.transform.quarterly import (
    to_million_yen,
    cumulative_to_single,
    DocumentExtraction,
    build_quarterly,
)


def test_unit_conversion():
    assert to_million_yen(1554, "億円") == 155400.0   # 1,554億円 = 155,400百万円
    assert to_million_yen(30191, "百万円") == 30191.0
    assert to_million_yen(None, "億円") is None


def test_cumulative_to_single_basic():
    # 森精機: Q1累計=1,554億, Q2(中間)累計=3,352億 （百万円換算）
    cum = {1: 155400.0, 2: 335200.0}
    single = cumulative_to_single(cum)
    assert single[1] == 155400.0                 # 単独Q1 = 累計Q1
    assert single[2] == 179800.0                 # 単独Q2 = 3,352 - 1,554 = 1,798億
    assert single[3] is None                     # Q3累計が無いので計算不能
    assert single[4] is None


def test_cumulative_to_single_okamoto_q4():
    # 岡本(工作機械セグメント): Q3累計=22,612, 通期=30,547（百万円）
    cum = {3: 22612.0, 4: 30547.0}
    single = cumulative_to_single(cum)
    assert single[4] == 7935.0                   # 単独Q4 = 30,547 - 22,612
    assert single[1] is None                     # Q1が無い
    assert single[2] is None


def test_quarter_period_type_used_directly():
    # 既に「単独」で載っている会社は引き算しない
    docs = [
        DocumentExtraction("9999", "テスト社", "2026-03", 2, "quarter",
                           "百万円", total=500.0),
        DocumentExtraction("9999", "テスト社", "2026-03", 1, "quarter",
                           "百万円", total=400.0),
    ]
    (r,) = build_quarterly(docs)
    assert r.single_total[1] == 400.0
    assert r.single_total[2] == 500.0            # 900-400 の引き算をしない


def test_build_quarterly_end_to_end():
    # 森精機の合計を Q1/Q2 の2本の短信から組み立てる
    docs = [
        DocumentExtraction("6141", "DMG森精機", "2026-12", 1, "cumulative",
                           "億円", total=1554.0),
        DocumentExtraction("6141", "DMG森精機", "2026-12", 2, "cumulative",
                           "億円", total=3352.0),
    ]
    (r,) = build_quarterly(docs)
    assert r.company == "DMG森精機"
    assert r.single_total[1] == 155400.0
    assert r.single_total[2] == 179800.0

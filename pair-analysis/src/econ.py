# -*- coding: utf-8 -*-
"""
「筋が通った」ペアを上位に出すための経済テーマ辞書。

総当たりスキャン（scan.py）は相関の強さで並べるが、それだけだと偶然の相関も
上位に来る。同じテーマ（例: 半導体、銅・非鉄）に属するペアは加点して、
「銅→住友金属鉱山」のように意味の通るペアが上位に出やすくする。

これは "説明可能性" のヒントであって、因果の保証ではない。
"""

from __future__ import annotations

# テーマ名 -> そのテーマに属するシンボル（Yahoo 記法）の集合
THEMES: dict[str, set[str]] = {
    "半導体": {
        "^SOX", "TSM", "NVDA", "MU", "AMD", "INTC", "ASML",
        "8035.T", "6857.T", "6146.T", "6920.T", "6723.T", "6963.T",
    },
    "非鉄・銅": {
        "FCX", "HG=F", "CPER",          # 銅先物・銅ETF・自由港
        "5713.T", "5711.T", "5714.T",   # 住友鉱山・三菱マテリアル・DOWA
    },
    "海運": {"9101.T", "9104.T", "9107.T"},
    "銀行": {"8306.T", "8316.T", "8411.T"},
    "自動車": {"7203.T", "7267.T", "7201.T", "TM", "HMC"},
    "原油・エネルギー": {"CL=F", "XOM", "CVX", "5020.T", "1605.T"},
    "金・貴金属": {"GC=F", "GLD", "1540.T"},
}


def theme_of(symbol: str) -> str | None:
    """シンボルが属するテーマ名を返す（複数該当時は最初の一致）。"""
    s = symbol.strip().upper()
    for name, members in THEMES.items():
        if s in members:
            return name
    return None


def same_theme(a: str, b: str) -> bool:
    """2つのシンボルが同じ経済テーマに属するか。"""
    ta = theme_of(a)
    return ta is not None and ta == theme_of(b)

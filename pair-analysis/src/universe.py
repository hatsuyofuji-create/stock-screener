# -*- coding: utf-8 -*-
"""
ティッカー正規化と市場・時間帯の判定。

Yahoo Finance の記法に合わせる:
  - 日本株   : 4桁コード（6146 → 6146.T）
  - 韓国     : .KS / .KQ
  - 台湾     : .TW / .TWO
  - 指数     : ^SOX, ^N225 など（先頭 ^）
  - 米国     : 英字ティッカー（TSM, MU, NVDA …）
"""

from __future__ import annotations

# 先行の市場ごとの既定 lag（後続=日本株を想定）。
# 米欧は日本の場中より後に引けるため「翌営業日(1)」に伝わる。
# 同時間帯（日本・韓国・台湾）は当日(0)が「連れ高確認」だが、
# 「遅れて張れる分」を測るため既定は 1 とし、UI で 0 に切替可能にする。
_DEFAULT_LAG = {
    "US": 1,
    "EU": 1,
    "JP": 1,
    "KR": 1,
    "TW": 1,
}


def to_yahoo_symbol(code: str) -> str:
    """入力コードを Yahoo Finance のシンボルに正規化する。"""
    s = code.strip().upper()
    if not s:
        return s
    if s.startswith("^"):
        return s
    if "." in s:
        return s  # 既に .T / .KS / .TW など付き
    if s.isdigit():
        return f"{s}.T"  # 4桁数字 → 日本株
    return s  # 英字 → 米国ティッカー等


def classify_market(code: str) -> str:
    """シンボルからおおよその市場を判定する（US/JP/KR/TW/INDEX/EU）。"""
    s = code.strip().upper()
    if s.startswith("^"):
        # 主要指数のうち日本・韓国・台湾を個別判定、それ以外は US 扱い
        if s in {"^N225", "^TPX"}:
            return "JP"
        if s in {"^KS11", "^KQ11"}:
            return "KR"
        if s in {"^TWII"}:
            return "TW"
        return "US"
    if s.endswith((".KS", ".KQ")):
        return "KR"
    if s.endswith((".TW", ".TWO")):
        return "TW"
    if s.endswith(".T") or s.replace(".T", "").isdigit() or s.isdigit():
        return "JP"
    if "." in s:
        return "EU"  # .L(ロンドン) .DE(独) 等
    return "US"


def default_lag(leader: str) -> int:
    """先行の市場に応じた既定 lag を返す。"""
    return _DEFAULT_LAG.get(classify_market(leader), 1)


def load_universe_file(path: str) -> tuple[list[str], dict[str, str]]:
    """
    ユニバース定義ファイルを読み込み (シンボル一覧, 名前マップ) を返す。

    書式（1行1銘柄）:
        6146   ディスコ          # コードのあとに空白区切りで名前（任意）
        NVDA   エヌビディア
        # 先頭 # の行と空行は無視
    シンボルは to_yahoo_symbol で正規化（6146 → 6146.T）。名前は表示用。
    """
    symbols: list[str] = []
    names: dict[str, str] = {}
    seen: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            line = line.split("#", 1)[0].strip()   # 行末コメント除去
            if not line:
                continue
            parts = line.split(None, 1)
            sym = to_yahoo_symbol(parts[0])
            if sym in seen:
                continue
            seen.add(sym)
            symbols.append(sym)
            if len(parts) > 1:
                names[sym] = parts[1].strip()
    return symbols, names


# 期間ラベル → (yfinance period, おおよその営業日数)
PERIODS: dict[str, tuple[str, int]] = {
    "半年": ("6mo", 120),
    "1年": ("1y", 245),
    "2年": ("2y", 490),
    "3年": ("3y", 735),
    "5年": ("5y", 1225),
}

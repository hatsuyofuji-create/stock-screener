# -*- coding: utf-8 -*-
"""
notify_test.py — LINE通知だけを素早く試すためのテスト送信。

データ取得はせず、既存の db/ranking.csv・meta.json を読んで
上位業種のメッセージを組み立て、LINE に push する。
（トークン設定の確認用。数十秒で結果が分かる）
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.notify import line as line_notify  # noqa: E402

TOP_N = 3


def main() -> int:
    load_dotenv(ROOT / ".env")

    rank = pd.read_csv(ROOT / "db" / "ranking.csv")
    meta_path = ROOT / "db" / "meta.json"
    asof = ""
    if meta_path.exists():
        asof = json.loads(meta_path.read_text(encoding="utf-8")).get("asof", "")

    def direction(pm) -> str:
        if pm is None or pd.isna(pm):
            return "— 方向不明"
        return f"🟢買い優勢 +{pm:.1f}%" if pm >= 0 else f"🔴売り優勢 {pm:.1f}%"

    page_url = os.getenv("PAGE_URL") or "https://hatsuyofuji-create.github.io/stock-screener/sector-flow/"
    lines = [f"📊 セクター資金フロー {asof}（テスト送信）", "売買代金 上位業種（＋価格の方向）:"]
    for _, r in rank.head(TOP_N).iterrows():
        pm = r["price_mom"] if "price_mom" in r else None
        lines.append(
            f"{int(r['rank'])}. {r['sector']}　{r['turnover']:,.0f}億円\n"
            f"　　{direction(pm)}"
        )
    lines.append("")
    lines.append("📈 グラフ・全業種ランキング:")
    lines.append(page_url)
    message = "\n".join(lines)

    sent = line_notify.notify(message)
    if sent:
        print("LINE送信OK（テスト）")
        return 0
    print("LINE送信できませんでした（トークン/ユーザーID/友だち追加を確認）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

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

    def pm(v) -> str:
        if v is None or pd.isna(v):
            return "—"
        return f"🟢+{v:.1f}%" if v >= 0 else f"🔴{v:.1f}%"

    def col(r, name):
        return r[name] if name in r else None

    page_url = os.getenv("PAGE_URL") or "https://hatsuyofuji-create.github.io/stock-screener/sector-flow/"
    lines = [f"📊 セクター資金フロー {asof}（テスト送信）", "売買代金 上位業種（価格の方向 15/30/150日）:"]
    for _, r in rank.head(TOP_N).iterrows():
        lines.append(
            f"{int(r['rank'])}. {r['sector']}　{r['turnover']:,.0f}億円\n"
            f"　　15日{pm(col(r,'price_mom_15'))} / 30日{pm(col(r,'price_mom_30'))} / 150日{pm(col(r,'price_mom_150'))}"
        )
    lines.append("")
    lines.append("📈 全業種ランキング:")
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

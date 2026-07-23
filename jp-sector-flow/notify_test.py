# -*- coding: utf-8 -*-
"""
notify_test.py — LINE通知だけを素早く試すためのテスト送信。

データ取得はせず、既存の db/ranking.csv・meta.json を読んで
上位業種のメッセージを組み立て、LINE に push する。
（トークン設定の確認用。数十秒で結果が分かる）
"""

from __future__ import annotations

import json
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

    lines = [f"📊 セクター売買代金 {asof}（テスト送信）", "上位業種（売買代金）:"]
    for _, r in rank.head(TOP_N).iterrows():
        arrow = "↑" if r["momentum"] >= 0 else "↓"
        lines.append(
            f"{int(r['rank'])}. {r['sector']} "
            f"（{r['turnover']:,.0f}億円 / 勢い {r['momentum']:+.1f}% {arrow}）"
        )
    message = "\n".join(lines)

    sent = line_notify.notify(message)
    if sent:
        print("LINE送信OK（テスト）")
        return 0
    print("LINE送信できませんでした（トークン/ユーザーID/友だち追加を確認）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

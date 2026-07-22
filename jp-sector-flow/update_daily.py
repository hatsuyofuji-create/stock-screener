# -*- coding: utf-8 -*-
"""
update_daily.py — 引け後の日次バッチ。

流れ:
  1. .env を読む
  2. DataProvider（mock / jquants）でデータ取得
  3. セクター売買代金（資金フロー）を集計
  4. db/ に CSV / meta.json を書き出す（app.py が読む）
  5. 上位セクターを LINE 通知（未設定ならコンソール出力）

使い方:
  python update_daily.py                    # mock（鍵不要）
  PROVIDER=jquants python update_daily.py   # 本番（.env に鍵が必要）
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

# src をパスに通す
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.compute import money_flow as flow_mod  # noqa: E402
from src.data.provider import get_provider  # noqa: E402
from src.notify import line as line_notify  # noqa: E402

DB_DIR = ROOT / "db"
TOP_N = 3  # 通知に載せる上位セクター数


def is_weekday(d: date | None = None) -> bool:
    """平日（月〜金）なら True。
    TODO: 祝日は未対応。取引カレンダー判定に置き換えると祝日も除外できる。
    """
    d = d or date.today()
    return d.weekday() < 5


def _build_message(ranking, asof) -> str:
    lines = [f"📊 セクター売買代金 {asof.strftime('%Y-%m-%d')}", "上位業種（売買代金）:"]
    for _, row in ranking.head(TOP_N).iterrows():
        arrow = "↑" if row["momentum"] >= 0 else "↓"
        lines.append(
            f"{int(row['rank'])}. {row['sector']} "
            f"（{row['turnover']:,.0f}億円 / 勢い {row['momentum']:+.1f}% {arrow}）"
        )
    return "\n".join(lines)


def main() -> int:
    load_dotenv(ROOT / ".env")

    if not is_weekday():
        print("本日は土日のためスキップしました。")
        return 0

    provider = get_provider()
    print(f"データ提供元: {provider.name}")

    turnover = provider.get_turnover_history()
    sector_map = provider.get_sector_map()
    print(f"取得: {turnover.shape[1]} 銘柄 / {turnover.shape[0]} 営業日")

    result = flow_mod.compute(turnover, sector_map)
    flow_df = result["flow"]
    ranking = result["ranking"]
    monthly = result["monthly"]
    asof = result["asof"]

    # 書き出し
    DB_DIR.mkdir(exist_ok=True)
    flow_df.to_csv(DB_DIR / "turnover.csv", encoding="utf-8")
    ranking.to_csv(DB_DIR / "ranking.csv", index=False, encoding="utf-8")
    monthly.to_csv(DB_DIR / "monthly.csv", index=False, encoding="utf-8")
    meta = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider.name,
        "asof": asof.strftime("%Y-%m-%d"),
        "metric": "turnover_oku",  # 売買代金（億円）
        "n_sectors": int(ranking.shape[0]),
        "n_days": int(flow_df.shape[0]),
        "top": ranking.head(TOP_N)["sector"].tolist(),
    }
    (DB_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 通知
    message = _build_message(ranking, asof)
    line_notify.notify(message)

    top_str = " / ".join(meta["top"])
    print(f"更新完了 / 上位: {top_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

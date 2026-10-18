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

import pandas as pd
from dotenv import load_dotenv

# src をパスに通す
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.compute import money_flow as flow_mod  # noqa: E402
from src.data.provider import get_provider  # noqa: E402
from src.data import sox as sox_mod  # noqa: E402
from src.notify import line as line_notify  # noqa: E402

DB_DIR = ROOT / "db"
TOP_N = 3  # 通知に載せる上位セクター数

# LINE通知に載せる「グラフ・全業種ランキング」ページのURL（環境変数で上書き可）
PAGE_URL = os.getenv("PAGE_URL") or "https://hatsuyofuji-create.github.io/stock-screener/sector-flow/"


def is_weekday(d: date | None = None) -> bool:
    """平日（月〜金）なら True。
    TODO: 祝日は未対応。取引カレンダー判定に置き換えると祝日も除外できる。
    """
    d = d or date.today()
    return d.weekday() < 5


def _pm(v) -> str:
    """価格の方向1期間ぶんを 🟢+x.x% / 🔴x.x% / — で表す。"""
    if v is None or pd.isna(v):
        return "—"
    return f"🟢+{v:.1f}%" if v >= 0 else f"🔴{v:.1f}%"


def _four(m: dict, keys=(5, 15, 30, 150)) -> str:
    """5/15/30/150日の方向を1行にまとめる。m のキーは int でも str でも可。"""
    def g(k):
        return m.get(k, m.get(str(k)))
    return f"5日{_pm(g(5))} / 15日{_pm(g(15))} / 30日{_pm(g(30))} / 150日{_pm(g(150))}"


def _build_message(ranking, asof, sox=None, market=None) -> str:
    lines = [f"📊 セクター資金フロー {asof.strftime('%Y-%m-%d')}"]
    if sox:
        lines.append(f"参考 SOX指数(米・半導体) {sox['level']:,.0f}")
        lines.append(f"　　{_four(sox['mom'])}")
        lines.append("")
    # 2026-10-18 追加：日本株全体（東証全銘柄）の売買代金（5日平均・兆円）と株価の方向
    if market and market.get("total_oku"):
        lines.append(f"日本株全体 売買代金 {market['total_oku'] / 1e4:.2f}兆円/日（5日平均）")
        if market.get("mom"):
            lines.append(f"　　{_four(market['mom'])}")
        lines.append("")
    lines.append("売買代金 上位業種（価格の方向 5/15/30/150日）:")
    for _, row in ranking.head(TOP_N).iterrows():
        pm = {5: row.get("price_mom_5"), 15: row.get("price_mom_15"),
              30: row.get("price_mom_30"), 150: row.get("price_mom_150")}
        lines.append(
            f"{int(row['rank'])}. {row['sector']}　{row['turnover']:,.0f}億円\n"
            f"　　{_four(pm)}"
        )
    # 2026-10-18 追加（上原さんの助言）：シェア（業種÷合計）のZスコア。いつもより資金が集まっている／抜けている業種
    if "share_z" in ranking.columns and ranking["share_z"].notna().any():
        zr = ranking.dropna(subset=["share_z"]).sort_values("share_z", ascending=False)
        lines.append("")
        lines.append("資金が集まっている業種（売買代金シェアのZスコア 上位）:")
        for _, row in zr.head(TOP_N).iterrows():
            lines.append(f"・{row['sector']}　Z {row['share_z']:+.2f}（シェア {row['share_pct']:.1f}%）")
        lines.append("資金が抜けている業種（Zスコア 下位）:")
        for _, row in zr.tail(TOP_N).iloc[::-1].iterrows():
            lines.append(f"・{row['sector']}　Z {row['share_z']:+.2f}（シェア {row['share_pct']:.1f}%）")
    lines.append("")
    lines.append("📈 全業種ランキング:")
    lines.append(PAGE_URL)
    return "\n".join(lines)


def main() -> int:
    load_dotenv(ROOT / ".env")

    force = os.getenv("FORCE_RUN", "").strip().lower() in ("1", "true", "yes")
    if not is_weekday() and not force:
        print("本日は土日のためスキップしました。（FORCE_RUN=true で強制実行できます）")
        return 0

    provider = get_provider()
    print(f"データ提供元: {provider.name}")

    turnover = provider.get_turnover_history()
    close = provider.get_close_history()
    sector_map = provider.get_sector_map()
    print(f"取得: {turnover.shape[1]} 銘柄 / {turnover.shape[0]} 営業日")

    result = flow_mod.compute(turnover, sector_map, close=close)
    flow_df = result["flow"]
    ranking = result["ranking"]
    monthly = result["monthly"]
    asof = result["asof"]

    # 書き出し
    DB_DIR.mkdir(exist_ok=True)
    flow_df.to_csv(DB_DIR / "turnover.csv", encoding="utf-8")
    ranking.to_csv(DB_DIR / "ranking.csv", index=False, encoding="utf-8")
    monthly.to_csv(DB_DIR / "monthly.csv", index=False, encoding="utf-8")
    # 2026-10-18 追加：日本株全体（売買代金・株価指数）と業種ごとの株価指数（ページのチャート用）
    market = result.get("market")
    market_mom = result.get("market_mom") or {}
    if market is not None and not market.empty:
        market.to_csv(DB_DIR / "market.csv", encoding="utf-8")
    pindex = result.get("pindex")
    if pindex is not None and not pindex.empty:
        pindex.to_csv(DB_DIR / "sector_index.csv", encoding="utf-8")
    meta = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider.name,
        "asof": asof.strftime("%Y-%m-%d"),
        "metric": "turnover_oku",  # 売買代金（億円）
        "n_sectors": int(ranking.shape[0]),
        "n_days": int(flow_df.shape[0]),
        "top": ranking.head(TOP_N)["sector"].tolist(),
        "market": {
            "total_oku": float(market["total_oku"].iloc[-1]) if market is not None and not market.empty else None,
            "mom": {str(k): v for k, v in market_mom.items()},
        },
    }
    (DB_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 参考指標: SOX（米・半導体）。取得失敗しても本体は続行。
    sox = sox_mod.get_sox()
    if sox:
        (DB_DIR / "sox.json").write_text(
            json.dumps(sox, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"SOX: {sox['level']} ({sox['asof']})")
    else:
        print("SOX: 取得できませんでした（参考指標のみ・本体は継続）")

    # 通知
    message = _build_message(ranking, asof, sox=sox, market=meta.get("market"))
    line_notify.notify(message)

    top_str = " / ".join(meta["top"])
    print(f"更新完了 / 上位: {top_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

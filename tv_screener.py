# -*- coding: utf-8 -*-
"""
=====================================================================
 TradingView スクリーナー → LINE 通知（クラウド自動実行版）
=====================================================================
 「ラッキーさんアプリ」の7条件に合う日本株を TradingView の
 スクリーナー（内部API）で取得し、LINE にプッシュ通知する。

 元は Windows のタスクスケジューラで毎日実行していたが、パス／文字化け
 （¥・全角・日本語フォルダ）や py ランチャー解決の問題が起きやすかった。
 このスクリプトは GitHub Actions 上（.github/workflows/tv-screener.yml）で
 毎営業日 15:50 JST に自動実行する前提。PC を起動しておく必要はない。

 必要な環境変数（GitHub の Secrets に登録済み）:
   - LINE_CHANNEL_ACCESS_TOKEN
   - LINE_USER_ID
 どちらか未設定でもクラッシュせず、画面出力にフォールバックする。

 ※ 無料・ログインなしのため約15分遅延データ。件数が TradingView 画面より
   少なく出るのは仕様。大引け後（15:50 JST）に確定値を取る想定。
"""

from __future__ import annotations

import datetime
import os

import requests
from tradingview_screener import Query, col


# =========================================================
# パート1：TradingViewから条件に合う銘柄を取得する（7条件）
# =========================================================
def fetch_stocks():
    q = (
        Query()
        .set_markets("japan")  # 日本市場
        .select(
            "name",              # 証券コード（例: 8395）
            "description",       # 会社名
            "close",             # 現在値
            "change",            # 本日の変動率(%)
            "volume",            # 出来高
            "market_cap_basic",  # 時価総額
        )
        .where(
            col("close") > 300,                                       # ① 価格 > 300円
            col("change") > 1,                                        # ② 本日 +1%以上
            col("market_cap_basic").between(10_000_000_000,           # ③ 時価総額
                                            100_000_000_000),         #    100億〜1000億
            col("price_earnings_growth_ttm") < 1,                     # ④ PEG < 1
            col("SMA50") > col("SMA150"),                             # ⑤ 50 > 150
            col("SMA150") > col("SMA200"),                            # ⑤ 150 > 200
            col("volume") > 100_000,                                  # ⑥ 出来高 10万株以上
            col("net_income") > 0,                                    # ⑦ 純利益プラス
        )
        .order_by("change", ascending=False)  # 上昇率の高い順
        .limit(200)
    )
    count, df = q.get_scanner_data()
    return count, df


# =========================================================
# パート2：LINE Messaging API でプッシュ通知する
# =========================================================
_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def send_line(text: str) -> bool:
    """LINE に push する。送信できたら True、未設定/失敗なら False。"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("LINE_USER_ID", "").strip()

    if not (token and user_id):
        print("[LINE未設定→コンソール出力のみ]\n" + text)
        return False

    try:
        r = requests.post(
            _PUSH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"to": user_id, "messages": [{"type": "text", "text": text}]},
            timeout=30,
        )
        r.raise_for_status()
        print("[LINE送信OK]")
        return True
    except Exception as e:  # 通知失敗で pipeline を止めない
        print(f"[LINE送信失敗→コンソール出力] {e}\n{text}")
        return False


# =========================================================
# メッセージの整形
# =========================================================
def build_message(count, df) -> str:
    today = datetime.date.today().strftime("%Y-%m-%d")
    if df is None or len(df) == 0:
        return f"📉 {today}\n条件に合う銘柄はありませんでした。"

    lines = [f"📈 本日の該当銘柄 {today}", f"該当 {len(df)}件", ""]
    for _, row in df.iterrows():
        code = row.get("name", "")
        nm = str(row.get("description", ""))[:12]  # 会社名は長すぎる時カット
        price = row.get("close", 0)
        chg = row.get("change", 0)
        lines.append(f"{code} {nm}  {price:,.0f}円 ({chg:+.1f}%)")

    text = "\n".join(lines)
    # LINEのテキストは5000文字まで。長すぎる場合は切り詰める。
    return text[:4900]


# =========================================================
# 実行
# =========================================================
def main():
    count, df = fetch_stocks()
    msg = build_message(count, df)

    print(msg)
    print("-" * 30)

    send_line(msg)


if __name__ == "__main__":
    main()

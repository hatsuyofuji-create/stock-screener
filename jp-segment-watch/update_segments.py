# -*- coding: utf-8 -*-
"""
update_segments.py — 有価証券報告書の“新セグメント出現”監視バッチ。

流れ:
  1. .env を読む
  2. 提供元（mock / edinet）で、直近ウィンドウ内に提出された有報を列挙
  3. 各有報の XBRL からセグメント名の集合を取得
  4. 同一銘柄の“1つ前の有報”と比べ、増えたセグメントがあれば検知
  5. 履歴（db/segments.csv）と検知結果（db/new_segments.csv）を更新
  6. 検知があれば LINE 通知（未設定ならコンソール出力）

使い方:
  python update_segments.py                       # mock（鍵不要・動作確認）
  PROVIDER=edinet python update_segments.py       # 本番（.env に EDINET_API_KEY）

環境変数:
  PROVIDER              mock / edinet（既定: EDINET_API_KEY があれば edinet、無ければ mock）
  EDINET_API_KEY        EDINET 購読キー（本番で必須）
  SEGMENT_WINDOW_DAYS   直近何日ぶんの提出を見るか（既定: 3）
  SEGMENT_SINCE         'YYYY-MM-DD' 指定でその日から今日までを走査（初期の履歴づくり用）
  LINE_CHANNEL_ACCESS_TOKEN / LINE_USER_ID  LINE 通知（任意）
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import detect  # noqa: E402
from src.notify import line as line_notify  # noqa: E402

DB_DIR = ROOT / "db"
HISTORY_CSV = DB_DIR / "segments.csv"
HITS_CSV = DB_DIR / "new_segments.csv"
META_JSON = DB_DIR / "meta.json"
MAX_NOTIFY = 20  # 1通に載せる検知件数の上限


def _get_provider():
    """PROVIDER に応じて提供元を返す。既定は鍵の有無で自動判定。"""
    name = (os.getenv("PROVIDER") or "").strip().lower()
    if not name:
        name = "edinet" if os.getenv("EDINET_API_KEY", "").strip() else "mock"
    if name == "mock":
        from src.mock import MockProvider
        return MockProvider()
    if name == "edinet":
        from src.edinet import EdinetClient
        client = EdinetClient()
        # EdinetClient に fetch_segments を生やして提供元インターフェースを揃える
        from src.segments import parse_segments_from_zip

        def fetch_segments(meta: dict) -> list[str]:
            return parse_segments_from_zip(client.download_xbrl_zip(meta["docID"]))

        client.fetch_segments = fetch_segments  # type: ignore[attr-defined]
        return client
    raise ValueError(f"未知の PROVIDER です: {name!r}（'mock' か 'edinet'）")


def _window_days() -> list[date]:
    """走査対象の日付リストを返す。SEGMENT_SINCE 優先、無ければ直近 N 日。"""
    since = os.getenv("SEGMENT_SINCE", "").strip()
    today = date.today()
    if since:
        start = datetime.strptime(since, "%Y-%m-%d").date()
        n = (today - start).days + 1
        return [today - timedelta(days=i) for i in range(max(1, n))]
    n = int(os.getenv("SEGMENT_WINDOW_DAYS", "3"))
    return [today - timedelta(days=i) for i in range(max(1, n))]


def _build_message(hits: list[dict], asof: str) -> str:
    lines = [f"🆕 新セグメント検知 {asof}", f"過去の有報になかったセグメントが増えた銘柄（{len(hits)}件）:", ""]
    for h in hits[:MAX_NOTIFY]:
        new = "・".join(detect.split_segments(h["new_segments"]))
        lines.append(f"[{h['ticker']}] {h['filerName']}")
        lines.append(f"　＋{new}（{h['prior_periodEnd']}→{h['periodEnd']}）")
    if len(hits) > MAX_NOTIFY:
        lines.append(f"…ほか {len(hits) - MAX_NOTIFY} 件")
    return "\n".join(lines)


def main() -> int:
    load_dotenv(ROOT / ".env")

    provider = _get_provider()
    print(f"データ提供元: {provider.name}")

    days = _window_days()
    print(f"走査対象: {days[-1]}〜{days[0]}（{len(days)}日）")

    docmetas = provider.list_securities_reports(days)
    print(f"対象有報: {len(docmetas)} 件")

    history = detect.load_history(HISTORY_CSV)
    today = date.today().strftime("%Y-%m-%d")

    updated, hits = detect.process(
        docmetas, history, provider.fetch_segments, today=today
    )

    # 書き出し
    DB_DIR.mkdir(exist_ok=True)
    detect.write_history(HISTORY_CSV, updated)
    detect.append_hits(HITS_CSV, hits)
    meta = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider.name,
        "asof": today,
        "window_days": len(days),
        "n_docs_scanned": len(docmetas),
        "n_history": len(updated),
        "n_hits_this_run": len(hits),
        "hits": [
            {
                "ticker": h["ticker"],
                "filerName": h["filerName"],
                "new_segments": detect.split_segments(h["new_segments"]),
                "periodEnd": h["periodEnd"],
            }
            for h in hits
        ],
    }
    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 通知（検知があったときだけ）
    if hits:
        line_notify.notify(_build_message(hits, today))
    else:
        print("新セグメントの検知はありませんでした。")

    print(f"完了 / 履歴 {len(updated)} 行・今回検知 {len(hits)} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

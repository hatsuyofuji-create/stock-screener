# -*- coding: utf-8 -*-
"""
render_page.py — db/ の実データから GitHub Pages 用の 1枚もの HTML を生成する。

update_daily.py が書き出した db/turnover.csv・ranking.csv・monthly.csv を読み、
page_template.html（表示専用ビューア）にデータを埋め込んで、
リポジトリ直下の docs/sector-flow/index.html に書き出す。

GitHub Actions が毎営業日これを実行してコミットするので、公開ページが自動更新される。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DB = ROOT / "db"
TEMPLATE = ROOT / "page_template.html"
OUT = ROOT.parent / "docs" / "sector-flow" / "index.html"

# 8色の CVD 対応カテゴリカルパレット（テンプレート側と対応）
PAL = [
    {"light": "#2a78d6", "dark": "#3987e5"},
    {"light": "#eb6834", "dark": "#d95926"},
    {"light": "#1baf7a", "dark": "#199e70"},
    {"light": "#eda100", "dark": "#c98500"},
    {"light": "#e87ba4", "dark": "#d55181"},
    {"light": "#008300", "dark": "#008300"},
    {"light": "#4a3aa7", "dark": "#9085e9"},
    {"light": "#e34948", "dark": "#e66767"},
]


def build_payload() -> dict:
    flow = pd.read_csv(DB / "turnover.csv", index_col=0)
    ranking = pd.read_csv(DB / "ranking.csv")
    monthly = pd.read_csv(DB / "monthly.csv")
    return {
        "dates": [str(d) for d in flow.index],
        "series": {c: [round(float(x), 1) for x in flow[c]] for c in flow.columns},
        "ranking": ranking.to_dict(orient="records"),
        "monthly": [
            {
                "month": str(m["month"]),
                "tri": float(m["tri"]),
                "days": int(m["days"]),
                "partial": bool(m["partial"]),
            }
            for _, m in monthly.iterrows()
        ],
        "pal": PAL,
    }


def main() -> int:
    payload = build_payload()
    blob = json.dumps(payload, ensure_ascii=False)

    tmpl = TEMPLATE.read_text(encoding="utf-8")
    page = tmpl.replace("__BLOB__", blob)

    # テンプレートは <title>…<style>…（head相当）＋ <div class="wrap">…<script>（body相当）
    idx = page.index('<div class="wrap">')
    head, body = page[:idx], page[idx:]
    doc = (
        "<!doctype html>\n<html lang=\"ja\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        + head
        + "</head>\n<body>\n"
        + body
        + "\n</body>\n</html>\n"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT} ({len(doc)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

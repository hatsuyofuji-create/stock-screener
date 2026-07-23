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


def build_payload() -> dict:
    ranking = pd.read_csv(DB / "ranking.csv")
    asof = ""
    meta_path = DB / "meta.json"
    if meta_path.exists():
        asof = json.loads(meta_path.read_text(encoding="utf-8")).get("asof", "")
    # NaN を None（JSONのnull）にして渡す
    records = ranking.where(pd.notnull(ranking), None).to_dict(orient="records")
    return {"ranking": records, "asof": asof}


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

# -*- coding: utf-8 -*-
"""
render_page.py — db/ の実データから GitHub Pages 用の 1枚もの HTML を生成する。

update_daily.py が書き出した db/turnover.csv・ranking.csv・monthly.csv（＋market.csv・sector_index.csv）を読み、
page_template.html（表示専用ビューア）にデータを埋め込んで、
リポジトリ直下の docs/sector-flow/index.html に書き出す。

2026-10-18 追加：日本株全体（東証全銘柄）の売買代金と、業種ごとの過去1年の売買代金・株価指数の推移を
ページに埋め込む（業種名をクリックするとチャートが出る）。market.csv / sector_index.csv が無い古い db でも、
turnover.csv の合計から全体の売買代金を作って動く。

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


def _series(df: pd.DataFrame, col: str) -> list:
    s = pd.to_numeric(df[col], errors="coerce")
    return [None if pd.isna(v) else round(float(v), 2) for v in s]


def build_payload() -> dict:
    ranking = pd.read_csv(DB / "ranking.csv")
    asof = ""
    meta = {}
    meta_path = DB / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        asof = meta.get("asof", "")
    sox = None
    sox_path = DB / "sox.json"
    if sox_path.exists():
        sox = json.loads(sox_path.read_text(encoding="utf-8"))
    # 業種ごとの売買代金の推移（億円・5日平均）。日付 × 業種
    flow = pd.read_csv(DB / "turnover.csv", index_col=0)
    flow.index = pd.to_datetime(flow.index)
    flow = flow.sort_index()

    # シェアのZスコア（2026-10-18 追加）。古い ranking.csv に列が無ければ turnover.csv から計算する
    if "share_z" not in ranking.columns:
        import sys
        sys.path.insert(0, str(ROOT))
        from src.compute.money_flow import share_z
        sz = share_z(flow)
        ranking["share_pct"] = ranking["sector"].map(sz["share_pct"])
        ranking["share_z"] = ranking["sector"].map(sz["share_z"])
        ranking["z_rank"] = ranking["share_z"].rank(ascending=False, method="min")
    # NaN を None（JSONのnull）にして渡す
    records = ranking.astype(object).where(pd.notnull(ranking), None).to_dict(orient="records")
    dates = [d.strftime("%Y-%m-%d") for d in flow.index]
    sectors = {sec: _series(flow, sec) for sec in flow.columns}

    # 業種ごとの株価指数（先頭=100）。無ければ空
    pidx = {}
    p = DB / "sector_index.csv"
    if p.exists():
        pi = pd.read_csv(p, index_col=0)
        pi.index = pd.to_datetime(pi.index)
        pi = pi.reindex(flow.index)
        pidx = {sec: _series(pi, sec) for sec in pi.columns}

    # 日本株全体：market.csv（total_oku, index）。無ければ turnover.csv の合計（＝全銘柄の5日平均の合計）
    market = {"dates": dates, "total": None, "index": None, "mom": {}}
    m = DB / "market.csv"
    if m.exists():
        mk = pd.read_csv(m, index_col=0)
        mk.index = pd.to_datetime(mk.index)
        mk = mk.reindex(flow.index)
        market["total"] = _series(mk, "total_oku") if "total_oku" in mk.columns else None
        market["index"] = _series(mk, "index") if "index" in mk.columns else None
    if market["total"] is None:
        tot = flow.sum(axis=1, skipna=True)
        market["total"] = [round(float(v), 1) for v in tot]
    market["mom"] = (meta.get("market") or {}).get("mom") or {}
    market["latest"] = market["total"][-1] if market["total"] else None

    return {"ranking": records, "asof": asof, "sox": sox,
            "flow": {"dates": dates, "sectors": sectors}, "pindex": pidx, "market": market}


def main() -> int:
    payload = build_payload()
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

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

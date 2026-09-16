# -*- coding: utf-8 -*-
"""
pipeline.analyze(code, years): 取得 → 急騰検出 → 文脈付け をまとめた入口。
analyze.py（CLI）と app.py（Streamlit）の両方がこれを呼ぶ。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import EDINET_WINDOW, SpikeConfig  # noqa: E402
from src.compute import context as ctx_mod  # noqa: E402
from src.compute import reactions as reactions_mod  # noqa: E402
from src.compute import spikes as spikes_mod  # noqa: E402
from src.data import edinet as edinet_mod  # noqa: E402
from src.data import mock as mock_mod  # noqa: E402
from src.data import news as news_mod  # noqa: E402
from src.data.provider import get_provider, is_mock, normalize_code  # noqa: E402
from src.data.tdnet import TdnetStore  # noqa: E402


def ensure_tdnet_uptodate(store: TdnetStore, *, log=print, max_days: int = 31) -> int:
    """公式 TDnet（直近1か月のみ閲覧可）から、まだ貯めていない日を取り込む。

    最後に貯めた日から今日までを平日ごとに読む（最後の日は取りこぼし防止で読み直す）。
    失敗しても分析は続ける。戻り値は追加件数。"""
    from datetime import date, timedelta

    from src.data import tdnet

    today = date.today()
    _, hi = store.coverage()
    first = today - timedelta(days=max_days)
    if hi is not None:
        first = max(first, hi.date() - timedelta(days=1))
    days = [first + timedelta(days=i) for i in range((today - first).days + 1)]
    days = [d for d in days if d.weekday() < 5]
    if not days:
        return 0
    added = 0
    ok = 0
    try:
        import requests

        session = requests.Session()
        for d in days:
            df = tdnet.fetch_official_day(d, session=session, sleep=0.3)
            added += store.upsert(df)
            ok += 1
    except Exception as e:  # noqa: BLE001
        log(f"[tdnet] 自動取り込みを中断（{ok}/{len(days)} 日まで）: {str(e)[:120]}")
    if hi is not None and (first - hi.date()).days > max_days:
        log(f"[tdnet] 前回の蓄積（{hi.date()}）から1か月以上空いています。"
            f" 抜けは `python backfill_tdnet.py --range {hi.date()} {today}` で補えます")
    log(f"適時開示の自動取り込み: {len(days)} 日分を確認 / {added} 件追加")
    return added


def analyze(code: str, years: float | None = None, *, cfg: SpikeConfig | None = None,
            with_news: bool = True, with_edinet: bool = True, name: str | None = None,
            log=print) -> dict:
    """銘柄コードを受け取り、急騰日と文脈をまとめた dict を返す。"""
    cfg = cfg or SpikeConfig.from_env()
    years = cfg.years if years is None else years
    code = normalize_code(code)
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=years)
    provider = get_provider()
    log(f"データ提供元: {provider.name} / 銘柄: {code} / 期間: {start.date()}〜{end.date()}")

    bars = provider.get_daily_bars(code, start, end)
    if bars.empty:
        raise RuntimeError(f"{code} の日足が空でした。")
    company = name or provider.get_company_name(code)
    log(f"日足 {len(bars)} 営業日 / 銘柄名: {company}")

    spikes = spikes_mod.detect_spikes(bars, cfg)
    n_up = int((spikes["direction"] == "up").sum()) if len(spikes) else 0
    n_down = int((spikes["direction"] == "down").sum()) if len(spikes) else 0
    what = {"up": f"急騰日: {n_up} 件（前日終値比 +{cfg.pct:g}% 以上）",
            "down": f"急落日: {n_down} 件（前日終値比 -{cfg.drop_pct:g}% 以下）"}.get(
        cfg.direction, f"急騰日 {n_up} 件（+{cfg.pct:g}% 以上）/ 急落日 {n_down} 件（-{cfg.drop_pct:g}% 以下）")
    log(what)

    topix = provider.get_market_index(start, end)
    statements = provider.get_statements(code)
    log(f"決算情報: {len(statements)} 件 / 指数: {len(topix)} 営業日")

    mock = is_mock()
    if mock:
        disclosures = mock_mod.mock_disclosures(code, start, end)
    else:
        store = TdnetStore()
        ensure_tdnet_uptodate(store, log=log)
        disclosures = store.load(code, start, end)
    log(f"適時開示: {len(disclosures)} 件（蓄積分）")

    edinet = None
    if with_edinet:
        if mock:
            edinet = mock_mod.mock_edinet(code, start, end)
        elif edinet_mod.has_key() and not spikes.empty:
            days = pd.DatetimeIndex(bars.index).normalize()
            wanted: list[pd.Timestamp] = []
            for d in spikes["date"]:
                a, b = ctx_mod.window(days, pd.Timestamp(d).normalize(), EDINET_WINDOW)
                wanted.extend(days[(days >= a) & (days <= b)].tolist())
            edinet = edinet_mod.EdinetClient().documents(code, wanted)
            log(f"EDINET: {len(edinet)} 件")
        else:
            log("EDINET: キー未設定のためスキップ（EDINET_API_KEY）")

    news_fetcher = None
    if with_news:
        if mock:
            news_fetcher = lambda a, b: mock_mod.mock_news(company, a, b)  # noqa: E731
        else:
            news_fetcher = lambda a, b: news_mod.fetch_news(company, a, b)  # noqa: E731

    events = ctx_mod.enrich(
        spikes, bars, topix=topix, statements=statements, disclosures=disclosures,
        edinet=edinet, news_fetcher=news_fetcher,
    )
    return {
        "code": code,
        "name": company,
        "provider": provider.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "config": {"pct": cfg.pct, "drop_pct": cfg.drop_pct, "direction": cfg.direction, "years": years},
        "n_days": int(len(bars)),
        "spikes": events,
        "_bars": bars,  # 画面のチャート用（JSON には書かない）
    }


def analyze_earnings(code: str, years: float | None = None, *, include_dividend: bool = True,
                     name: str | None = None, log=print) -> dict:
    """銘柄コードを受け取り、決算ごとの業績と株価反応をまとめた dict を返す。"""
    cfg = SpikeConfig.from_env()
    years = cfg.years if years is None else years
    code = normalize_code(code)
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=years)
    provider = get_provider()
    log(f"データ提供元: {provider.name} / 銘柄: {code} / 期間: {start.date()}〜{end.date()}")

    # 前年同期比を出すため、決算は期間より1年余分に取る（株価は期間内のみ）
    bars = provider.get_daily_bars(code, start - pd.DateOffset(days=40), end)
    if bars.empty:
        raise RuntimeError(f"{code} の日足が空でした。")
    company = name or provider.get_company_name(code)
    statements = provider.get_statements(code)
    topix = provider.get_market_index(start - pd.DateOffset(days=40), end)
    log(f"日足 {len(bars)} 営業日 / 決算情報 {len(statements)} 件 / 指数 {len(topix)} 営業日 / 銘柄名: {company}")

    events = reactions_mod.build_events(statements, bars, topix, include_dividend=include_dividend)
    events = [e for e in events if pd.Timestamp(e["reaction_date"]) >= start]
    summary = reactions_mod.summarize(events)
    log(f"決算イベント: {len(events)} 件（期間内）")
    return {
        "code": code,
        "name": company,
        "provider": provider.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "n_days": int((bars.index >= start).sum()),
        "events": events,
        "summary": summary,
        "_bars": bars[bars.index >= start],
    }

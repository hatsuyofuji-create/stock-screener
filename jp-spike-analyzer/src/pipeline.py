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
from src.compute import spikes as spikes_mod  # noqa: E402
from src.data import edinet as edinet_mod  # noqa: E402
from src.data import mock as mock_mod  # noqa: E402
from src.data import news as news_mod  # noqa: E402
from src.data.provider import get_provider, is_mock, normalize_code  # noqa: E402
from src.data.tdnet import TdnetStore  # noqa: E402


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
    log(f"急騰日: {len(spikes)} 件（前日終値比 {cfg.pct:g}% 以上）")

    topix = provider.get_market_index(start, end)
    statements = provider.get_statements(code)

    mock = is_mock()
    if mock:
        disclosures = mock_mod.mock_disclosures(code, start, end)
    else:
        disclosures = TdnetStore().load(code, start, end)
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
        "config": {"pct": cfg.pct, "years": years},
        "n_days": int(len(bars)),
        "spikes": events,
        "_bars": bars,  # 画面のチャート用（JSON には書かない）
    }

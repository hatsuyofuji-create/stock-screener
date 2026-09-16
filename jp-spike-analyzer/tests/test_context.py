import pandas as pd

from config import SpikeConfig
from src.compute.context import enrich
from src.compute.spikes import detect_spikes
from src.data import edinet, news
from src.data.mock import MockProvider, mock_disclosures, mock_edinet, mock_news


def test_enrich_tags_from_mock_sources():
    p = MockProvider()
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=3)
    bars = p.get_daily_bars("7203", start, end)
    spikes = detect_spikes(bars, SpikeConfig())
    events = enrich(
        spikes, bars, topix=p.get_market_index(start, end), statements=p.get_statements("7203"),
        disclosures=mock_disclosures("7203", start, end), edinet=mock_edinet("7203", start, end),
        news_fetcher=lambda a, b: mock_news("X", a, b),
    )
    all_tags = {t for e in events for t in e["tags"]}
    assert {"決算", "TOB", "大量保有", "業績修正"} <= all_tags
    assert any(t.startswith("地合い") for t in all_tags)
    # 前日引け後の開示は「前日」ラベル
    tob = next(e for e in events if "TOB" in e["tags"])
    assert tob["disclosures"][0]["rel"] == "前日"
    assert tob["edinet"][0]["rel"] == "+3日"
    assert tob["news"]


def test_no_disclosure_means_unknown():
    p = MockProvider()
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=3)
    bars = p.get_daily_bars("7203", start, end)
    spikes = detect_spikes(bars, SpikeConfig())
    events = enrich(spikes, bars, news_fetcher=lambda a, b: mock_news("X", a, b))  # 開示なし・ニュースのみ
    assert events and all("材料不明" in e["tags"] for e in events)


def test_edinet_parse_filters_withdrawn():
    payload = {"results": [
        {"docID": "S1", "secCode": "72030", "filerName": "A", "docTypeCode": "350", "docDescription": "大量保有報告書", "withdrawalStatus": "0"},
        {"docID": "S2", "secCode": "72030", "filerName": "B", "docTypeCode": "180", "docDescription": "臨時報告書", "withdrawalStatus": "1"},
    ]}
    df = edinet.parse_results(payload, pd.Timestamp("2026-08-26"))
    assert list(df["doc_id"]) == ["S1"]
    assert df["code"].iloc[0] == "7203"
    assert "S1" in df["url"].iloc[0]


def test_news_parse_rss():
    xml = """<?xml version="1.0"?><rss><channel>
    <item><title>トヨタ、上期営業益が過去最高</title><link>https://example.com/a</link>
      <pubDate>Wed, 26 Aug 2026 01:00:00 GMT</pubDate><source url="https://x">日経</source></item>
    </channel></rss>"""
    df = news.parse_rss(xml)
    assert len(df) == 1
    assert df["publisher"].iloc[0] == "日経"
    assert df["date"].iloc[0] == pd.Timestamp("2026-08-26 10:00:00")  # JST に変換

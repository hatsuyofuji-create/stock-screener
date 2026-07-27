"""データ自動取得のテスト（仕様書 4.9 / Phase 5）。MockProvider でオフライン検証。"""

import os
import tempfile

import pytest

from app.data.provider import get_provider
from app.data.mock import MockProvider


def test_get_provider_default_mock():
    assert get_provider("mock").name == "mock"
    assert get_provider().name == "mock"  # デフォルト


def test_get_provider_unknown():
    with pytest.raises(ValueError):
        get_provider("bloomberg")


def test_mock_provider_shape():
    p = MockProvider()
    stmts = p.fetch_statements("0001")
    assert len(stmts) == 3
    assert stmts[0]["fiscal_period"] == "2023-03"
    assert all(s["source"] == "mock" for s in stmts)
    assert p.fetch_market("0001")["price"] == 0.5
    assert p.fetch_company("0001")["sector"] == "機械"


def test_ingest_populates_db_and_downstream():
    """取得 → 保存 → 指標・Fスコアが自動取得データから算出できる（手入力の置き換え）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app import models  # noqa: F401
    from app.ingest import ingest_company
    from app.services import build_snapshot

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine("sqlite:///" + tmp.name)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        res = ingest_company(db, "0001", MockProvider())
        assert res["statements_added"] == 3
        assert res["market"] is True

        company = db.get(models.Company, "0001")
        assert company is not None
        assert len(company.statements) == 3

        # 冪等性：再取得は追加0・更新3
        res2 = ingest_company(db, "0001", MockProvider())
        assert res2["statements_added"] == 0
        assert res2["statements_updated"] == 3

        # 自動取得データからスナップショット（Fスコア含む）が作れる
        market = db.get(models.MarketData, "0001")
        snap = build_snapshot(company, market)
        assert snap.fscore is not None
        assert snap.pbr is not None
    finally:
        db.close()
        os.unlink(tmp.name)

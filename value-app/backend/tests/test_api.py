"""API 統合テスト（Phase 0/1）。一時 SQLite を使う。"""

import os
import tempfile

import pytest

# app を import する前にテスト用 DB を指定する。
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = "sqlite:///" + _tmp.name

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.db import init_db  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c
    os.unlink(_tmp.name)


def test_disclaimer_present(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "投資助言" in r.json()["disclaimer"]


def test_full_flow(client):
    # 企業作成
    r = client.post("/api/companies", json={
        "code": "9999", "name": "テスト商事", "sector": "卸売",
        "growth_type": "安定成長", "moat_tags": ["ブランド", "コスト競争力"],
        "qualitative_note": "テスト用の定性メモ",
    })
    assert r.status_code == 200
    assert r.json()["is_cyclical"] is False

    # 前期・最新期を投入
    prior = {
        "fiscal_period": "2024-03", "revenue": 1000, "cogs": 600,
        "operating_income": 100, "ordinary_income": 90, "net_income": 60,
        "operating_cf": 80, "total_assets": 1000, "equity": 500,
        "current_assets": 400, "current_liabilities": 200,
        "interest_bearing_debt": 200, "cash": 100, "capital_stock": 100,
    }
    latest = {
        "fiscal_period": "2025-03", "revenue": 1200, "cogs": 680,
        "operating_income": 150, "ordinary_income": 140, "net_income": 95,
        "operating_cf": 160, "total_assets": 1100, "equity": 600,
        "current_assets": 500, "current_liabilities": 220,
        "interest_bearing_debt": 180, "cash": 150, "capital_stock": 100,
    }
    assert client.post("/api/companies/9999/statements", json=prior).status_code == 200
    assert client.post("/api/companies/9999/statements", json=latest).status_code == 200

    # 指標
    r = client.get("/api/companies/9999/metrics")
    assert r.status_code == 200
    body = r.json()
    assert len(body["metrics"]) == 2
    assert body["changes"] is not None

    # Fスコア
    r = client.get("/api/companies/9999/fscore")
    assert r.status_code == 200
    fs = r.json()
    assert fs["total"] == 9
    assert fs["is_healthy"] is True


def test_fscore_requires_two_periods(client):
    client.post("/api/companies", json={"code": "8888", "name": "一期のみ"})
    client.post("/api/companies/8888/statements", json={
        "fiscal_period": "2025-03", "net_income": 10, "operating_cf": 20,
    })
    r = client.get("/api/companies/8888/fscore")
    assert r.status_code == 400


def test_cyclical_flag(client):
    client.post("/api/companies", json={
        "code": "7777", "name": "シクリカル鋼業", "growth_type": "シクリカル",
    })
    r = client.get("/api/companies/7777")
    assert r.json()["is_cyclical"] is True

"""サンプル銘柄を1社投入する最小シード（仕様書 Phase 0）。

使い方:
    cd value-app/backend
    python seed.py
"""

from app.db import init_db, SessionLocal
from app import models


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.get(models.Company, "0001"):
            print("サンプル銘柄は既に投入済みです。")
            return

        company = models.Company(
            code="0001", name="サンプル製作所", sector="機械",
            market_cap=80_000_000_000, growth_type="安定成長",
            moat_tags="コスト競争力,ブランド",
            qualitative_note="サンプル。実データ投入前の動作確認用。",
        )
        db.add(company)

        rows = [
            dict(fiscal_period="2023-03", revenue=900, cogs=560, operating_income=80,
                 ordinary_income=75, net_income=48, operating_cf=70, total_assets=950,
                 equity=460, current_assets=380, current_liabilities=190,
                 interest_bearing_debt=210, cash=90, inventory=95, receivables=140,
                 payables=115, capital_stock=100, shares_outstanding=1000),
            dict(fiscal_period="2024-03", revenue=1000, cogs=600, operating_income=100,
                 ordinary_income=90, net_income=60, operating_cf=80, total_assets=1000,
                 equity=500, current_assets=400, current_liabilities=200,
                 interest_bearing_debt=200, cash=100, inventory=100, receivables=150,
                 payables=120, capital_stock=100, shares_outstanding=1000),
            dict(fiscal_period="2025-03", revenue=1200, cogs=680, operating_income=150,
                 ordinary_income=140, net_income=95, operating_cf=160, total_assets=1100,
                 equity=600, current_assets=500, current_liabilities=220,
                 interest_bearing_debt=180, cash=150, inventory=110, receivables=160,
                 payables=130, capital_stock=100, shares_outstanding=1000),
        ]
        for row in rows:
            db.add(models.FinancialStatement(company_code="0001", source="manual", **row))
        db.commit()
        print("サンプル銘柄 0001（サンプル製作所, 3期分）を投入しました。")
    finally:
        db.close()


if __name__ == "__main__":
    run()

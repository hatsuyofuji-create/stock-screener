# バリュー投資アプリ（上原メソッド）

個人投資家が「価値が拡大する優良企業を、割安な価格で買う」判断を、再現性のある
ルールとして半自動で行うための意思決定支援アプリ。仕様は [`../docs/SPEC.md`](../docs/SPEC.md) を参照。

> **免責**：本アプリは投資助言ツールではありません。投資判断は利用者自身の責任で
> 行ってください。外部データの取得は各サービスの利用規約を遵守してください。

## 実装状況（フェーズ）

- [x] **Phase 0** — 雛形・データモデル（第3章）
- [x] **Phase 1** — 財務指標エンジン（4.1）＋ Fスコアエンジン（4.2）＝**心臓部**
- [ ] Phase 2 — 適正株価・安全域 ＋ Park24型シナリオ計算（4.3）
- [ ] Phase 3 — 予想Excelアップロード＆マッピング（4.6）
- [ ] Phase 4 — スクリーニング＋銘柄マトリクス（4.5 / 4.7）
- [ ] Phase 5 — データ自動取得（EDINET/TDnet, 4.9）
- [ ] Phase 6 — ポートフォリオ管理＋アラート＋景気局面（4.8 / 4.4）

## 構成

```
value-app/
  backend/
    app/
      db.py            DB 接続（SQLite → 将来 PostgreSQL）
      models.py        DB モデル（Company / FinancialStatement / Forecast / Holding）
      schemas.py       API スキーマ（Pydantic）
      services.py      DB ⇄ 計算エンジンの橋渡し
      engines/
        financials.py  4.1 財務指標計算エンジン
        fscore.py      4.2 Fスコア計算エンジン
      main.py          FastAPI エントリポイント
    tests/             pytest（計算の正しさを担保）
    seed.py            サンプル銘柄1社を投入
    requirements.txt
```

計算ロジックはすべて `engines/` に置き、API・DB は「集める→採点→返す」に徹する
（仕様書 2章の方針）。

## セットアップ

```bash
cd value-app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## テスト

```bash
cd value-app/backend
source .venv/bin/activate
pytest
```

受け入れ基準（仕様書 6章）のうち Phase 1 分を実装：
- **Fスコア**：既知サンプルで合計点が一致。特に項目8（増資判定＝資本金の前期比）と
  項目4（営業CF > 純利益）の境界値をテスト。
- **財務指標**：ROA（経常利益ベース）、ROIC、CCC、デュポン分解などが手計算と一致。

## 起動（開発サーバ）

```bash
cd value-app/backend
source .venv/bin/activate
python seed.py                 # サンプル銘柄 0001 を投入
uvicorn app.main:app --reload  # http://127.0.0.1:8000/docs で API を確認
```

主なエンドポイント：

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/companies` | 企業を登録 |
| POST | `/api/companies/{code}/statements` | 財務データ（1期）を登録 |
| POST | `/api/companies/{code}/statements/import_csv` | 財務データを CSV 一括取込 |
| GET | `/api/companies/{code}/metrics` | 全期の財務指標＋前年比（4.1） |
| GET | `/api/companies/{code}/fscore` | Fスコア 実績版（4.2） |

## 設計メモ

- **ROA は経常利益ベース**（仕様書 4.1）。収益性の主指標は ROA / ROIC。
- **実効税率**のデフォルトは 0.30（`effective_tax_rate` で上書き可）。Park24 モデルは
  0.35 を採用（Phase 2 で対応）。
- 欠損値（None）やゼロ除算が絡む指標は `None`（算出不能）を返す。Fスコアは判定
  できない項目を No=0 とする（安全側）。
- Fスコア**予想版**は `build_forecast_snapshot()` で最新実績に予想値を上書きして算出
  （Phase 3 の Excel 取込と接続予定）。

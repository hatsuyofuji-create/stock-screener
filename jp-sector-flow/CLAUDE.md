# CLAUDE.md — jp-sector-flow 設計メモ

セクター資金フロー（**売買代金**）を毎営業日 自動更新して、グラフ表示と LINE 通知を
行う **表示専用ツール**。売買判断・発注ロジックは持たない。

## 全体像

```
                データ取得              計算              書き出し           表示 / 通知
 update_daily → DataProvider → money_flow.compute → db/*.csv,meta → app.py(表示)
   (バッチ)     (mock/jquants)                       db/*.json      line.notify(通知)
```

- **更新（バッチ）**: `update_daily.py`
- **表示**: `app.py`（Streamlit）
- 両者は `db/` の生成物を介して疎結合。`app.py` は計算しない（CSVを読むだけ）。

## ディレクトリ

```
jp-sector-flow/
├── update_daily.py        引け後バッチ（取得→計算→書き出し→通知）
├── app.py                 Streamlit 表示（db/ を読むだけ）
├── requirements.txt
├── .env.example           → .env にコピーして鍵を記入（.env は .gitignore 済み）
├── src/
│   ├── data/
│   │   ├── provider.py    DataProvider 抽象基底 + get_provider() ファクトリ
│   │   ├── mock.py        MockProvider（鍵不要・乱数データ）
│   │   └── jquants.py     JQuantsProvider（本番・Bearer認証）
│   ├── compute/
│   │   └── money_flow.py  セクター売買代金（資金フロー）の集計
│   └── notify/
│       └── line.py        LINE Messaging API 通知（未設定ならコンソール）
├── db/                    生成物（turnover.csv / ranking.csv / meta.json）
└── logs/                  update.log など
```

## データ取得の方針

- `app.py` / `update_daily.py` に `requests` を**直書きしない**。必ず
  `DataProvider` 経由（`get_provider()`）で取得する。
- プロバイダは次の2つを返すだけの薄い契約:
  - `get_turnover_history() -> DataFrame`（index=日付, columns=銘柄コード, values=売買代金[円]）
  - `get_sector_map() -> dict[コード, セクター名]`
- 提供元は環境変数 `PROVIDER`（`mock` / `jquants`）で切り替え。
- J-Quants は `daily_quotes` の `TurnoverValue`（売買代金）を採用。

### J-Quants の認証（重要・V2 APIキー方式）

2025-12-22 以降のアカウントは **V2** のみ。旧トークン方式は廃止され
（`/v1/token/auth_user` は 410 Gone）、**APIキー方式**に変わった:

1. ダッシュボードで **APIキー** を発行し、`JQUANTS_API_KEY` に設定
2. すべてのリクエストに `x-api-key: <APIキー>` ヘッダを付ける（トークン交換なし）

- ベース: `https://api.jquants.com/v2`（`JQUANTS_BASE` で上書き可）
- 参考: <https://jpx-jquants.com/en/spec/migration-v1-v2>

> 当初は V1（リフレッシュトークン→IDトークン→Bearer）で実装したが、実アカウントで
> 410 Gone となり V2 APIキー方式へ移行。指示書の「V2はAPIキー方式」が正しかった。

## 計算（money_flow.compute）

1. 各銘柄の売買代金（円）を業種別に合計 → 業種の日次売買代金。
2. 見やすさのため 億円 に換算し、`SMOOTH_DAYS`(=5) 日の移動平均で均す。
3. 直近の売買代金（億円）が大きい順にランキング。`MOMENTUM_DAYS`(=5) 日の
   変化率を「勢い」として併記（増加＝資金が入りつつある）。

出力:
- `turnover.csv`: 日付 × 業種の売買代金[億円]（推移グラフ用・5日移動平均）
- `ranking.csv`: `rank, sector, turnover, momentum`
- `meta.json`: `updated_at, provider, asof, metric, n_sectors, n_days, top[]`

> 判定は「売買代金の金額そのもの」（B方式）。株価ベースの相対強度ではない。

## 既知の TODO

- **祝日スキップは未実装**。`update_daily.is_weekday()` は土日のみ除外。
  取引カレンダー判定（例: J-Quants `/markets/trading_calendar`）に置き換えると
  祝日も除外できる。
- `jquants.py` の universe は「その日の全銘柄」を日付ごとに取得する方式。
  営業日数ぶん API を叩くので、`JQUANTS_LOOKBACK_DAYS` を大きくすると時間がかかる。

## ルール

- 秘密情報はコード直書き禁止。必ず `.env`（`.gitignore` 済み）。
- 表示専用の方針を変えない（売買判断・発注は追加しない）。
- 迷ったら大改造せず人間に確認。

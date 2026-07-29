# pair-analysis — 自由ペア分析（先行→後続の連動）

「先行（先に動く銘柄・指数）」と「後続（遅れて動く銘柄）」の連動を **その場で測る**
検証ツール。しんぽこさんの相関アプリ（自由ペア分析／総当たり相関）の再現・実装です。

> 表示・検証用です。過去統計であって将来を保証しません。売買は自己責任で。

## 何を計算するか

例: `先行 TSM（TSMC）→ 後続 6146（ディスコ）`

| 指標 | 意味 |
|---|---|
| **ベータ** `+0.43%` | 先行が **1%** 動いた翌営業日に後続が平均どれだけ動くか（回帰の傾き） |
| **つながりの太さ** | 翌営業日リターンの相関 r（\|r\|≥0.25 太い / ≥0.15 中）|
| **↑急騰時** | 先行がしきい値超で急騰した日、後続が翌日に追随した割合と平均リターン |
| **↓急落時** | 先行が急落した日の、後続の追随率と平均リターン（＝守りのアラート検証）|

- **ベータ・相関は全営業日**で測る（しきい値に依らない）。
- **↑↓の集計はしきい値（±3%/±5%）超の急変日**だけで測る。
- **lag**（後続をずらす営業日数）は先行の市場で自動決定。米欧→日本は `1`（翌営業日）。

## 使い方

### オフラインで動作確認（鍵・ネット不要 / synthetic データ）

```bash
cd pair-analysis
python -m unittest discover -s tests     # テスト（純Python）
python analyze.py TSM 6146               # 1ペア分析
python scan.py --universe "TSM,NVDA,MU,6146,6857,5713,FCX" --top 6
```

> synthetic は乱数の擬似データなので相関はほぼ0になります（配線確認用）。
> 実際の連動を見るには下の yahoo プロバイダを使ってください。

### 本番データ（yfinance）

```bash
pip install -r requirements.txt
PRICE_PROVIDER=yahoo python analyze.py TSM 6146 --period 2年 --threshold 0.03
PRICE_PROVIDER=yahoo streamlit run app.py          # スクショの Web UI
```

### Windows：ダブルクリックで起動（推奨）

`自由ペア分析アプリ起動.bat` をダブルクリックするだけで、UI（`app.py`）が
ブラウザで開きます。

- **初回だけ**自動で仮想環境（`.venv`）を作り、必要なパッケージを入れます（数分）。
- 2回目以降はすぐ起動します。データは本番（yfinance）を使います。
- 終了は黒い画面で **Ctrl+C**。
- 事前に [Python](https://www.python.org/downloads/) が必要です
  （インストール時「Add python.exe to PATH」にチェック）。

### 総当たりスキャン（「700万通り」構想版）

全ペア（先行→後続）を測り、連動の強い順に並べます。同じ経済テーマ（`src/econ.py`）の
ペアは加点され、「銅→住友鉱山」「半導体→半導体装置」のような **筋の通ったペアが上位**
に出やすくなります。

```bash
PRICE_PROVIDER=yahoo python scan.py --universe-file tickers.txt --period 半年 --top 30
```

> ペア数は N×(N-1)。700万通り ≒ 先行約2600 × 後続約2600。大ユニバースは取得に
> 時間がかかるので、まず小さめで試してください。

## シンボルの書き方（Yahoo Finance 記法）

| 市場 | 例 |
|---|---|
| 日本株 | `6146`（→ `6146.T` に自動変換）|
| 米国 | `TSM` / `NVDA` / `MU` |
| 指数 | `^SOX` / `^N225` |
| 韓国 / 台湾 | `005930.KS` / `2330.TW` |

## 構成

```
pair-analysis/
├── analyze.py            1ペア分析 CLI
├── scan.py               総当たりスキャン CLI
├── app.py                Streamlit UI（自由ペア分析）
├── src/
│   ├── analysis.py       コア計算（純Python: β・相関・イベント集計）
│   ├── universe.py       シンボル正規化・市場判定・既定lag・期間
│   ├── econ.py           経済テーマ辞書（スキャンの筋通し加点）
│   └── data/
│       ├── provider.py   PriceProvider 抽象 + get_provider()
│       ├── yahoo.py      yfinance（本番）
│       └── synthetic.py  擬似データ（鍵不要・テスト/オフライン）
└── tests/test_analysis.py
```

データ取得は必ず `PriceProvider` 経由（yfinance を直書きしない）。`PRICE_PROVIDER`
環境変数で `synthetic`（既定）/ `yahoo` を切り替えます。

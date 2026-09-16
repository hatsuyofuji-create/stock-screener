# CLAUDE.md — jp-spike-analyzer 設計メモ

過去の株価から急騰日を抽出し、「その時何が起きていたか」を決算・適時開示・EDINET・ニュース・TOPIX で
説明する **表示専用ツール**。売買判断・発注ロジックは持たない。

## 全体像

```
 J-Quants(日足/決算/TOPIX) ─┐
 TDnet 蓄積 db/tdnet/*.csv ─┼→ pipeline.analyze → spikes.detect_spikes → context.enrich → dict
 EDINET API                ─┤        ↑                                                   ↓
 Google News RSS           ─┘   analyze.py(CLI) / app.py(Streamlit)          db/analysis/<code>.json

 pipeline.ensure_tdnet_uptodate → TDnet 公式一覧（未取得日・全銘柄）→ TdnetStore.upsert → db/tdnet/YYYY-MM.csv
 update_daily.py   → 同じことを手動で
 backfill_tdnet.py → 非公式 TDnet WebAPI（過去分・一度だけ）→ 同じ store
```

## ディレクトリ

```
jp-spike-analyzer/
├── analyze.py            CLI（取得→検出→文脈付け→JSON 保存）
├── app.py                Streamlit（pipeline を呼んで表示するだけ）
├── update_daily.py       TDnet 公式の取り込み（手動用。通常は分析時に自動）
├── backfill_tdnet.py     蓄積開始前の過去分を非公式 API で補完
├── config.py             急騰しきい値・照合窓（.env で上書き可）
├── src/
│   ├── pipeline.py       analyze(code, years) の入口
│   ├── data/
│   │   ├── provider.py   PriceProvider 抽象基底 + get_provider() + normalize_code()
│   │   ├── mock.py       MockProvider + mock_disclosures / mock_edinet / mock_news
│   │   ├── jquants.py    JQuantsProvider（V2 APIキー、銘柄単位、1日キャッシュ）
│   │   ├── tdnet.py      公式 TDnet の HTML パース + TdnetStore + tag_title()
│   │   ├── tdnet_backfill.py  非公式 TDnet WebAPI クライアント
│   │   ├── edinet.py     EDINET API v2（日付一覧→secCode で絞る、日付キャッシュ）
│   │   └── news.py       Google News RSS
│   └── compute/
│       ├── spikes.py     急騰検出（pct / gap / vol_ratio / fwd_N）
│       └── context.py    急騰日ごとの文脈収集と要因タグ
├── tests/                pytest（ネット不要）
└── db/
    ├── tdnet/            適時開示の蓄積（各自のパソコン内のみ・無視）
    ├── cache/            J-Quants / EDINET のキャッシュ（無視）
    └── analysis/         analyze.py の出力（無視）
```

## 方針

- `analyze.py` / `app.py` に `requests` を直書きしない。株価は `PriceProvider`、開示は `TdnetStore`、
  EDINET は `EdinetClient`、ニュースは `news.fetch_news` 経由。
- `PROVIDER=mock` のときは開示・EDINET・ニュースも全部モックにして、鍵なしで一通り動くようにする。
- 外部ソースが落ちても本体は続行する（TOPIX / EDINET / ニュースは空で返す）。
- J-Quants は **Light** 前提（日足5年、決算 `/fins/summary`）。指数は Light で取れないので TOPIX連動ETF 1306.T を yfinance で代用。フィールド名は V2 短縮名を第一候補に
  V1 名へフォールバック（`_first()`）。特定できないときは実フィールド名を例外に出す。
- 適時開示は **公式 TDnet を分析のたびに自動で貯める**（直近1か月しか見られないため）。非公式 API は
  バックフィル専用で、止まっても自動取り込みに影響しない。蓄積は各自のパソコン内で、git には入れない。
- 秘密情報はコード直書き禁止。`.env`（`.gitignore` 済み）と GitHub Secrets のみ。
- 表示専用の方針を変えない（売買判定・発注は追加しない）。

## 急騰の定義と文脈の窓（config.py）

- 急騰（起点）: 前日終値→翌営業日終値 `pct >= 8%`。出来高倍率は表示のみ（判定に使わない）。既定で5年遡る
- 窓（営業日）: 決算 -1..0 / 適時開示 -1..+1 / EDINET -1..+5 / ニュース -2..+1
- 地合い: TOPIX 同日 +2% 以上
- 要因タグ: 決算, 業績修正, 自己株, 配当, 株式分割, TOB, M&A, 資本提携, 増資, 大株主, 大量保有, 臨時報告書,
  契約・受注, 株価照会, 地合い(TOPIX+x%), 出来高急増, 材料不明（開示系タグが無いとき。ニュースは参考表示のみ）

## 未検証・TODO

- J-Quants（日足・銘柄名・/fins/summary）、TDnet 公式クロール、非公式バックフィル、Google News、yfinance(1306.T) は
  実データで動作確認済み（2026-09-16）。EDINET は未確認。エラー時は例外メッセージ中の
  実フィールド名を見て `_first()` の候補を直す。
- TDnet 一覧 HTML の td クラス名（kjTime / kjCode / kjName / kjTitle）が変わったら `tdnet.parse_list_page` を直す。
- 祝日判定は未実装（土日のみ除外。休場日は TDnet が空を返すので実害なし）。
- 銘柄コードが英字入り（例: 130A）の場合の J-Quants 側の扱いは未確認。

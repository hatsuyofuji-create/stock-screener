# jp-spike-analyzer

**決算で株価がどう動いたか**を、業績の数字つきで確認する**表示専用ツール**。売買判断・発注は行いません。
設計の詳細は [`CLAUDE.md`](CLAUDE.md)。

- モード1「決算と株価の反応」（メイン）: 過去の決算短信・業績予想修正・配当予想修正を並べ、
  売上・営業利益・経常利益・純利益と前年同期比、進捗率、予想修正幅、評価（好決算 / 悪決算 / 上方修正 / 下方修正 / 増配 / 減配）、
  翌営業日以降の株価の反応（翌日・寄付・高値安値・出来高・5日後・20日後・対TOPIX）を表示。評価ごとの傾向表つき。
- モード2「急騰・急落の要因」: 前日終値比 ±8% の日を抽出し、決算・適時開示・EDINET・ニュース見出しと突き合わせる。
- CLI: `analyze_earnings.py`（モード1）/ `analyze.py`（モード2）、表示: `app.py`（Streamlit）
- データは Provider 経由（`mock` = 鍵不要 / `jquants` = 本番・Light プラン想定）

---

## いちばん簡単な使い方（Windows・ダブルクリック）

`株価急騰分析アプリ` フォルダ（このフォルダの1つ上）にあるバッチファイルを使います。

| ファイル | 何をするか |
|---|---|
| `アプリ起動.bat` | 画面版を起動してブラウザを開く。初回は Python 環境の作成と `.env` の作成（メモ帳が開く）も自動で行う |
| `分析.bat` | 銘柄コードを聞いてきて、決算ごとの業績と株価の反応をコマンド画面に表示する |
| `更新.bat` | GitHub から最新版を取り込み、必要な部品を入れ直す |

## セットアップ（手動）

```bash
cd jp-spike-analyzer
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 1. まず mock で動作確認（鍵不要）

```bash
python analyze_earnings.py 7203    # 決算ごとの業績と株価反応がコンソールに出る
python analyze.py 7203             # 急騰日と要因タグ
streamlit run app.py               # 左のサイドバーで「分析する」
python -m pytest -q tests          # テスト
```

mock では株価・決算・適時開示・EDINET・ニュースが全部ダミーになります。

## 2. 本番データへ切り替え

```bash
cp .env.example .env
# .env を編集: PROVIDER=jquants, JQUANTS_API_KEY=..., EDINET_API_KEY=...
```

### J-Quants（V2・APIキー方式・Light プラン）

- ダッシュボードで **APIキー** を発行し `JQUANTS_API_KEY` に入れる（`x-api-key` ヘッダで送られます）
- Light は日足が過去5年ぶん。既定は3年（`--years 5` で最大5年）
- 指数データ（TOPIX を含む）は Standard 以上。Light では **TOPIX連動ETF（1306.T）を yfinance で代用**して地合いを判定します
- 取得結果は `db/cache/jquants/` に1日キャッシュされます

### EDINET API（金融庁・無料）

臨時報告書・大量保有報告書・公開買付届出書・自己株券買付状況報告書を急騰日と照合します。

1. <https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1> を開く
2. メールアドレスを登録 → 届いた認証コードを入力 → パスワードを設定
3. ログインして「APIキー発行」→ 表示された文字列を `EDINET_API_KEY` に入れる

未設定なら EDINET の照合だけスキップされます。日付ごとの結果は `db/cache/edinet/` にキャッシュされます。

### 適時開示（TDnet）

公式の TDnet 一覧は**直近1か月しか見られない**ので、手元に貯めて使います。
**`analyze.py` / `app.py` を実行するたびに、まだ貯めていない日を自動で取りに行く**ので、
月に1回以上使っていれば途切れません。手動で取り込むこともできます。

```bash
python update_daily.py --days 30   # 手動で直近30日を取り込む
```

貯まる先は `db/tdnet/YYYY-MM.csv`（全銘柄・種別タグ付き。各自のパソコン内のみ、git には入れない）。
1か月以上使わずに抜けができた場合は `python backfill_tdnet.py --range 開始日 終了日` で埋められます。

蓄積開始より前の期間は、非公式の TDnet WebAPI（yanoshin.jp）で一度だけ補完できます。

```bash
python backfill_tdnet.py 7203 --years 5
```

個人運営の API なので止まる可能性があります。止まっても日次の公式クロールには影響しません。

### ニュース見出し

Google News RSS を「会社名 + 日付範囲」で検索し、見出しとリンクだけ表示します（本文は取りません）。
会社名は J-Quants から取りますが、`--name` で上書きできます。`--no-news` で省略可。

## 3. 分析する

```bash
PROVIDER=jquants python analyze_earnings.py 7203   # 決算と株価の反応
PROVIDER=jquants python analyze.py 7203            # 急騰・急落の要因
streamlit run app.py
```

### 決算と株価の反応（モード1）

- 対象: 決算短信（1Q/2Q/3Q/FY）、業績予想修正、配当予想修正（配当は切り替え可）
- 反応日: 発表が 15:00 より前ならその日、15:00 以降なら次の営業日
- 反応の指標はすべて「反応日の前営業日の終値」からの変化率（翌日・寄付・高値・安値・5日後・20日後・対TOPIX）
- 評価（`src/compute/earnings.py`）: 営業利益を軸に、前年同期比・進捗率（1Q 25% / 2Q 50% / 3Q 75% 目安）・
  予想修正幅・通期の会社予想比・来期予想を点数化。配当修正は年間配当予想の増減
- 傾向表: 評価ごとに回数・翌日上昇回数・翌日/寄付/5日後/20日後/対TOPIX の平均

### 急騰・急落の要因（モード2）

急騰・急落（起点）の定義（初期値、`.env` かサイドバーで変更可）:

- 急騰: **前日終値 → 翌営業日終値 が +8% 以上**
- 急落: **前日終値 → 翌営業日終値 が -8% 以下**（`--down` / `--both`、画面では「対象」で切り替え）
- 出来高倍率・寄付ギャップは参考として併記するだけで、判定には使わない
- 開示・決算・EDINET のどれにも該当が無ければ **「材料不明」**（ニュース見出しは参考表示のみ）

急騰日ごとに出るもの:

| 項目 | 出所 | 窓 |
|---|---|---|
| 前日比・寄付ギャップ・出来高倍率・5日後/20日後 | J-Quants 日足 | 当日 |
| TOPIX 同日騰落・対TOPIX 超過（急騰は +2% 以上、急落は -2% 以下で「地合い」） | ETF 1306（yfinance） | 当日 |
| 決算・業績予想修正の数値評価（好決算 / 悪決算 / 上方修正 / 下方修正） | J-Quants `/fins/summary` | 前日〜当日 |
| 適時開示（種別タグ付き） | TDnet 蓄積 + バックフィル | 前日〜翌日 |
| EDINET 提出書類 | EDINET API | 前日〜5営業日後 |
| ニュース見出し | Google News RSS | 2営業日前〜翌日 |
| 要因タグ | 上を機械的に要約 | 好決算 / 悪決算 / 上方修正 / 下方修正 / 自己株 / TOB / 大量保有 / 増資 / 特別損益 / 不祥事・処分 / 地合い / 出来高急増 / 材料不明 |

決算の評価（`src/compute/earnings.py`）は営業利益を軸に、前年同期比・通期予想に対する進捗率（1Q 25% / 2Q 50% / 3Q 75% が目安）・
予想の修正幅・通期の会社予想比・来期予想を点数化し、根拠の数字を文章で併記します。

## 4. 更新の取り込み

コードが更新されたら、`jp-spike-analyzer` フォルダで次を実行します。

```bash
git pull
pip install -r requirements.txt
```

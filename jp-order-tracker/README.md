# jp-order-tracker — 決算短信の受注高トラッカー

銘柄コードと決算短信PDFを渡すと、**受注高（各Q単独・百万円）**を抽出して
Excelに書き出します。

## なぜこの作りなのか（要点）

- **受注高はPDF本文にしか無い。** J-Quants(有料版でも)の財務データはXBRL標準
  サマリー（売上・利益など）だけで、「受注高」は含まれません。だから短信PDFを解析します。
- **文章型も表型も、Claudeに直接PDFを渡して両対応。** DMG森精機のような文章
  （「第1四半期の連結受注額は1,554億円」）も、岡本工作機械のような表も、
  ClaudeがネイティブでPDFを読みます。スキャン画像PDFも視覚的に読めるので**OCRは不要**。
- **累計→各Q単独に変換。** 短信の数字は多くが累計（上期・9ヶ月・通期）。
  各Qの単独値は累計どうしを引き算して求めます（例: 単独Q2 = 上期累計 − Q1累計）。
  会社が最初から単独で載せている場合は引き算しません（自動判定）。

## 全体像

```
銘柄コード + 短信PDF(複数四半期)
      │
      ▼
 src/extract/llm.py     PDF → Claude → 受注高JSON（セグメント別/合計・累計or単独）
      │
      ▼
 src/transform/quarterly.py   累計→各Q単独へ変換、単位を百万円に正規化
      │
      ▼
 src/excel/writer.py    受注一覧.xlsx に書き出し
```

（`src/fetch/` は将来の自動取得用。`jquants.py`=開示日の特定、`tdnet.py`=PDF取得の土台）

## セットアップ

```bash
cd jp-order-tracker
pip install -r requirements.txt
cp .env.example .env      # ANTHROPIC_API_KEY を記入
export ANTHROPIC_API_KEY=...
```

## 使い方

```bash
# フォルダ内の短信PDFをまとめて処理（Q1〜通期を入れておく）
python main.py 6141 --dir ./tanshin/6141 --out 受注一覧.xlsx

# PDFを個別指定
python main.py 6141 --pdfs q1.pdf q2.pdf q3.pdf fy.pdf --out 受注一覧.xlsx

# 開示予定日の確認（J-Quants。受注高そのものは入っていない点に注意）
export JQUANTS_API_KEY=...
python main.py 6141 --announcements
```

出力Excel（シート「受注高_各Q単独」）は
`銘柄コード / 会社名 / 決算期 / セグメント / Q1単独 … Q4単独 / 単位(百万円)`。
セグメント別の行と「合計」行が入ります。

## テスト

```bash
python -m pytest tests/ -q
```

累計→単独の変換ロジックを、画像の実データ（森精機・岡本）で検算しています。

## 現状と次のステップ

- ✅ 抽出エンジン（PDF→受注高→各Q単独→Excel）… 完成。手元のPDFで動きます。
- ⏭ 自動取得（銘柄コードだけで短信PDFを自動DL）… `src/fetch/` に土台あり。
  TDnetは日付単位・直近のみ・HTML構造変化ありで保守が要るため、まず手元PDFで
  精度を固め、その後に J-Quants の開示日特定 → TDnet/IR からのDL を接続します。

## 注意

- 秘密情報（APIキー）はコード直書きしない。必ず `.env`（`.gitignore` 済み）。
- 抽出モデルは既定 `claude-opus-5`。コスト優先なら `ANTHROPIC_MODEL=claude-sonnet-5`
  等に変更可（1短信あたり数円〜程度が目安）。
- 抽出結果は必ず原本の短信と照合してください（金額は投資判断に直結するため）。

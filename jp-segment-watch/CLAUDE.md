# CLAUDE.md — jp-segment-watch 設計メモ

有価証券報告書の **事業セグメント** を年ごとに比べ、**前期になかったセグメントが
増えた銘柄** を検知して LINE 通知する監視ツール。**気づき用**であり、売買判断・
発注ロジックは持たない。

## 全体像

```
              列挙                 抽出                   検知               記録/通知
 update_segments → EdinetClient → parse_segments_from_zip → detect.process → db/*.csv
   (バッチ)        (mock/edinet)   (セグメント軸メンバー)    (増えた名前)     line.notify
```

- **更新（バッチ）**: `update_segments.py`
- 生成物は `db/`（`segments.csv` 履歴 / `new_segments.csv` 検知 / `meta.json`）。
- 履歴 CSV をリポジトリに貯めることで、次回以降の“前期比較”が成立する。

## なぜ J-Quants ではなく EDINET か（重要）

当初 J-Quants を想定していたが、**J-Quants の財務API はセグメント内訳を返さない**:

- `/fins/statements`（財務情報）… 決算短信サマリーの財務値のみ。
- `/fins/fs_details`（財務諸表 BS/PL/CF）… 標準化された本表科目のみ。

セグメント（報告セグメント軸の内訳・セグメント名）は XBRL の注記側にあり、
**EDINET 有報の XBRL** から取得する。J-Quants はユニバース取得等には使えるが、
本ツールのセグメント本体には使わない。

## EDINET の使い方（V2・APIキー方式）

- 購読キー（`EDINET_API_KEY`）を全リクエストに `?Subscription-Key=` で付与。
- `GET /documents.json?date=YYYY-MM-DD&type=2` … 当日提出書類の一覧。
- `GET /documents/{docID}?type=1` … XBRL 一式 ZIP（type=5=CSV, type=2=PDF）。
- 有価証券報告書は `docTypeCode == "120"`。訂正版(130)は既定で追わない。
- ベース: `https://api.edinet-fsa.go.jp/api/v2`（`EDINET_BASE` で上書き可）。

## セグメント抽出（segments.py）の勘所

XBRL インスタンスのコンテキストに付く明示メンバーを見る:

```xml
<xbrldi:explicitMember dimension="jpcrp_cor:OperatingSegmentsAxis">
  jpcrp030000-asr_E01234-000:ElectronicsReportableSegmentsMember
</xbrldi:explicitMember>
```

1. 軸（dimension）の Local 名に `Segment` を含むメンバーを全部集める
   （会社により `OperatingSegmentsAxis` / `ReportableSegmentsAxis` 等）。
2. **会社独自（拡張）メンバーだけ残す**。拡張はプレフィックスに EDINETコード
   `_E#####-###` を含むのが目印。標準タクソノミ（`jpXXX_cor`）の合計・調整額・
   全社などは自然に外れる。
3. セグメント名（日本語）は **ラベルリンクベース `*_lab.xml`** の標準ラベル
   （role=label, `xml:lang="ja"`）から引く。要素IDは QName の `:` を `_` にした形。
   引けなければ Local 名末尾一致 → Local 名から復元、の順でフォールバック。
4. 一般名称（合計・調整額 等）は保険で除外。「その他」は実セグメントであり得る
   ので**除外しない**。

> ねらいは厳密な会計集計ではなく「セグメント名の集合を年ごとに安定して得る」
> こと。年次で集合を比較し“増えた名前”を拾う。

## 検知（detect.py）の勘所

- 名寄せキーは EDINETコード優先（無ければ証券コード）。
- 同一銘柄で `periodEnd` がより過去の履歴のうち最新を「前期」とし、今回の集合と
  差分を取る。今回だけにある名前 = 新セグメント。
- `process()` は `periodEnd` 昇順で処理。こうすると同一 run 内に「前期＋今期」が
  そろうとき、先に前期を記録してから今期で差分が取れる（バックフィルで有効）。
- 既知 docID はスキップ（再取得・重複通知を防ぐ＝冪等）。
- 前期が無い初回は**検知しない**（ベースライン記録のみ）。

## 動作モード

- `PROVIDER=mock`（既定・鍵なし）: `src/mock.py` のダミーで一巡を確認。
  7203 に新セグメントが出るデモになっている。
- `PROVIDER=edinet`（本番）: `EDINET_API_KEY` が必要。

## テスト（ネット不要）

- `tests/test_segments.py`: **合成 XBRL 一式**（`tests/fixtures.py`）を組み、
  実物と同じ経路で抽出を検証（拡張メンバー抽出・ラベル解決・合計除外・軸名ゆれ）。
- `tests/test_detect.py`: 検知・冪等・初回ベースライン・履歴経由比較。

## ルール

- 秘密情報はコード直書き禁止。必ず `.env`（`.gitignore` 済み）/ Actions Secrets。
- 気づき用の方針を変えない（売買判断・発注は追加しない）。
- `db/` の履歴は Actions がコミットして貯める前提。手動で消すと検知が鈍る。
- 迷ったら大改造せず人間に確認。

## TODO / 拡張余地

- 四半期粒度（TDnet 決算短信 XBRL）対応。公式フリーAPIが弱いため要調査。
- 銘柄名の充実や業種付与に J-Quants を併用（ユニバース取得は J-Quants が得意）。
- セグメント名の表記ゆれ吸収（正規化辞書）で誤検知を減らす。
- GitHub Pages への公開ページ生成（sector-flow と同様）。今は LINE＋CSVのみ。

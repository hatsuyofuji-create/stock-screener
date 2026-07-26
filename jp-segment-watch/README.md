# jp-segment-watch — 新セグメント出現モニター

決算開示（**有価証券報告書**）の **事業セグメント** を時系列で見て、
**過去（前期＝約1年前）になかったセグメントが新しく増えた銘柄** を検知し、
**LINE 通知** する監視ツール。GitHub Actions で定期実行できる。

新セグメントの出現は、事業の多角化・新規参入・組織再編（セグメント区分の
変更）のサインになりやすく、地味だが有用なシグナル。

## なぜ EDINET なのか（J-Quants ではなく）

やりたいのは「セグメント名の内訳」を年ごとに比べること。
**J-Quants の財務API はセグメントの内訳を返さない**（`/fins/statements` は
決算短信のサマリー財務値、`/fins/fs_details` は BS/PL/CF の標準科目まで）。
一方 **EDINET は有報の XBRL を配布**しており、セグメント情報が
「セグメント軸（`〜SegmentsAxis`）＋会社独自メンバー」として正規に入って
いる。そこでセグメント本体は EDINET から取得する。

> 粒度は年次（有報ベース）。セグメント区分の変更は通常“期初”から適用される
> ため、年次比較で「新セグメント出現」は十分検知できる。四半期粒度が必要な
> 場合は TDnet 決算短信 XBRL の取り込みが要るが、公式フリーAPIが弱く別課題。

## しくみ

```
 直近提出の有報を列挙   XBRLからセグメント抽出        前期と比較          記録・通知
 EdinetClient  ──────▶  parse_segments_from_zip ──▶ detect.process ──▶ db/*.csv
 (documents.json)       (セグメント軸のメンバー)     (増えた名前)       line.notify
```

- 有報は年1回。ある銘柄の「今回のセグメント集合」を「1つ前（約1年前）の
  有報のセグメント集合」と比べ、**今回だけにある名前**を新セグメントとする。
- 履歴 `db/segments.csv` をリポジトリに貯めることで、次回以降の比較材料にする。
- 検知結果は `db/new_segments.csv` に追記し、LINE に push する。

## ディレクトリ

```
jp-segment-watch/
├── update_segments.py     監視バッチ（列挙→抽出→検知→記録→通知）
├── requirements.txt
├── .env.example           → .env にコピーして鍵を記入（.env は .gitignore 済み）
├── src/
│   ├── edinet.py          EDINET API v2 クライアント（一覧・ZIP取得）
│   ├── segments.py        XBRL からセグメント名を抽出（軸メンバー＋ラベル）
│   ├── detect.py          新セグメント検知と履歴 I/O
│   ├── mock.py            鍵不要のダミー提供元（動作確認・CI用）
│   └── notify/line.py     LINE Messaging API 通知（未設定ならコンソール）
├── db/                    生成物（segments.csv / new_segments.csv / meta.json）
└── tests/                 合成XBRLでの抽出テスト・検知テスト（ネット不要）
```

## 使い方

```bash
pip install -r requirements.txt

# 鍵なしで動作確認（mock。新セグメント検知が1件出るデモ）
python update_segments.py

# 本番: EDINET の購読キーを .env に設定してから
PROVIDER=edinet python update_segments.py
```

### 鍵の準備

1. **EDINET APIキー**: 金融庁 EDINET の「アカウント管理」で購読キーを無料発行し、
   `EDINET_API_KEY` に設定。
2. **LINE（任意）**: `LINE_CHANNEL_ACCESS_TOKEN` と `LINE_USER_ID`。
   未設定ならコンソール出力にフォールバックする。

### 初期の履歴づくり（バックフィル）

初回は比較対象（前期の有報）が履歴に無いため、その銘柄は「ベースライン記録」
だけで検知は出ない。過去にさかのぼって履歴を作ると、以後の検知が効くように
なる。多くの3月決算企業は6月に有報を出すので、直近13か月ほどを走査すると
「前期＋今期」の2点がそろい、すぐ検知できる。

```bash
# 例: 2025-06-01 から今日までを走査（提出日ベース）
SEGMENT_SINCE=2025-06-01 PROVIDER=edinet python update_segments.py
```

> バックフィルは日数ぶん `documents.json` を叩き、対象有報を1件ずつダウンロード
> するので時間がかかる。普段の定期実行は `SEGMENT_WINDOW_DAYS`（既定3日）で十分。

## 環境変数

| 変数 | 既定 | 意味 |
|---|---|---|
| `PROVIDER` | 自動 | `mock` / `edinet`。未指定なら `EDINET_API_KEY` の有無で判定 |
| `EDINET_API_KEY` | — | EDINET 購読キー（本番で必須） |
| `SEGMENT_WINDOW_DAYS` | `3` | 直近何日ぶんの提出を見るか |
| `SEGMENT_SINCE` | — | `YYYY-MM-DD`。指定でその日から今日まで走査（バックフィル） |
| `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_USER_ID` | — | LINE 通知（任意） |

## テスト

```bash
python tests/test_segments.py   # 合成XBRLでセグメント抽出を検証（ネット不要）
python tests/test_detect.py     # 検知ロジックの単体テスト
# pytest 派なら: python -m pytest tests/
```

## 既知の限界

- **粒度は年次（有報）**。四半期での検知は対象外（TDnet 決算短信が必要）。
- セグメント名は XBRL のラベルから復元する。会社がラベルや区分名を微妙に
  変えると、同一セグメントでも別名に見えて誤検知することがある。人が
  `db/new_segments.csv` で最終確認する前提の“気づきツール”。
- 訂正有報（docTypeCode=130）は既定では追わない。

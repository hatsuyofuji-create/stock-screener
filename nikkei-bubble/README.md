# nikkei-bubble — 日経平均バブルチャート（LPPLS信頼度指標）

ディディエ・ソネット教授らの **ドラゴンキング理論 / LPPLS（Log-Periodic Power Law
Singularity＝対数周期べき乗則特異点）モデル** を日経平均株価に当てはめ、
「バブルシグナル」を可視化する Python ツールです。

- **上段**: 日経平均の終値（対数軸）＋ **バブルシグナル**（LPPLS ポジティブバブル信頼度、赤バー・右軸）
- **下段**: **バブル終了シグナル**（LPPLS ネガティブバブル信頼度、紺バー）

---

## 最速で試す

```bash
python bubble_chart.py --outer 20 --inner 20 --searches 8
```

粗い設定なので 1 分程度で `output/nikkei_bubble_chart.png` が出ます。
まずこれで動作確認し、納得したら既定パラメータ（下記）で本番計算してください。

---

## セットアップ

Python 3.10 以上が必要です。

```bash
cd nikkei-bubble
python3 -m venv .venv
source .venv/bin/activate          # Windows は .venv\Scripts\activate
pip install -r requirements.txt
```

インストールされる主なパッケージ:

| パッケージ | 用途 |
| --- | --- |
| `lppls` | LPPLS モデル本体（Boulder Investment Technologies 製の OSS） |
| `yfinance` | 日経平均（`^N225`）の日足取得 |
| `pandas` / `numpy` | データ整形 |
| `matplotlib` / `japanize-matplotlib` | チャート描画（日本語対応） |
| `tqdm` | 進捗表示 |

---

## 使い方

### 1. 既定設定で実行（本番）

```bash
python bubble_chart.py
```

- yfinance で `^N225` の日足を取得 → `data/nikkei_YYYYMMDD.csv` にキャッシュ
- 2023-06-01 〜 直近について LPPLS 信頼度を計算
- `output/indicators.csv`（指標）と `output/nikkei_bubble_chart.png`（チャート、dpi=150）を出力

> **計算は重く、既定パラメータでは数分〜十数分かかります。**
> tqdm の進捗バーが出るので、残り時間の目安はそこで確認してください。
> 軽く試したいときは `--outer 10`（あるいは `--outer 20 --inner 20 --searches 8`）を使ってください。

### 2. ローカル CSV を使う

```bash
python bubble_chart.py --csv path/to/nikkei.csv
```

- `Date` / `日付` / `年月日` などの日付列と、`Close` / `終値` / `調整後終値` などの
  終値列を自動で探します（大文字小文字・全角半角・空白のゆらぎに対応）。
- `35,000.25` のようなカンマ入り数値、`¥` や `円` 付きの数値も読めます。
- 日付として解釈できない行（yfinance が書き出す `Ticker` 行など）は自動で捨てられます。
- 列名から特定できない場合は「1 列目＝日付・数値化できる最後の列＝終値」で救済し、警告を出します。

### 3. キャッシュ

- 取得結果は `data/nikkei_YYYYMMDD.csv` に保存され、**同日中の再実行はキャッシュを再利用**します
  （ダウンロードが走らないぶん高速）。
- 強制的に取り直したいときは `--refresh`。

### 4. 再描画だけしたい

```bash
python bubble_chart.py --replot
```

`output/indicators.csv` を読み直して描画だけやり直します（LPPLS の再計算なし＝数秒）。

### 5. セルフテスト

```bash
python bubble_chart.py --selftest
```

LPPLS 式そのものから合成バブル（臨界点はデータ末尾の直後）を生成し、
末尾付近で `pos_conf` が立ち上がるかを検証して **PASS / FAIL** を表示します
（PASS で終了コード 0、FAIL で 1）。実行時間は 15 秒程度です。

---

## 主なオプション

| オプション | 既定値 | 説明 |
| --- | --- | --- |
| `--ticker` | `^N225` | yfinance のティッカー（他指数・他銘柄も一応可） |
| `--csv PATH` | なし | yfinance の代わりに CSV を読む |
| `--refresh` | off | 当日キャッシュを無視して再取得 |
| `--start` | `2023-06-01` | チャート・指標の開始日 |
| `--end` | なし（直近） | 終了日 |
| `--window` | `252` | 最大窓（営業日 ≒ 1 年） |
| `--smallest-window` | `60` | 最小窓（営業日 ≒ 3 か月） |
| `--outer` | `5` | `outer_increment`：指標を計算する日付の間隔 |
| `--inner` | `5` | `inner_increment`：窓を縮小する刻み |
| `--searches` | `25` | `max_searches`：1 フィットあたりの初期値探索回数（文献の推奨は 25） |
| `--workers` | CPU コア数 | 並列プロセス数 |
| `--output-dir` | `output` | PNG・指標 CSV の出力先 |
| `--replot` | off | 保存済み指標から描画だけやり直す |
| `--show` | off | 画面にも表示する（未指定なら PNG 保存のみ） |
| `--selftest` | off | 合成データによる自己検証 |

計算量はおおよそ
`(データ本数 / --outer) × ((--window − --smallest-window) / --inner) × --searches`
に比例します。`--outer` と `--inner` を大きくするほど速くなり、そのぶん時間分解能が粗くなります。

### `--start` と助走データについて

LPPLS 信頼度は「窓の右端の日付」に対して求まるため、`--start` の時点で指標を出すには
その前に `--window` 本ぶんの観測が必要です。本ツールは **`--start` より前のデータを
自動的に助走ぶんとして読み込む**ので、`--start 2023-06-01` を指定すれば
2023-06-01 から指標が並びます（助走データが足りない場合は警告を出し、
指標の開始日が後ろにずれます）。

---

## 出力

```
output/
├── indicators.csv            # date, price, pos_conf, neg_conf
└── nikkei_bubble_chart.png   # 2段チャート（dpi=150）
```

`indicators.csv` の列:

| 列 | 意味 |
| --- | --- |
| `date` | 窓の右端の日付 |
| `price` | その日の終値 |
| `pos_conf` | ポジティブバブル信頼度（バブルシグナル、0〜1） |
| `neg_conf` | ネガティブバブル信頼度（バブル終了シグナル、0〜1） |

---

## 指標の読み方

LPPLS モデルは、バブルの終盤で価格の対数がこの形に近づくと考えます。

```
ln p(t) = A + B(tc − t)^m + C(tc − t)^m · cos(ω ln(tc − t) − φ)
```

- `B(tc − t)^m` … **超指数的（faster-than-exponential）な上昇**
- `C(tc − t)^m cos(...)` … 臨界点 `tc` に向かって周期が縮んでいく **対数周期振動**
- `tc` … 特異点＝「バブルが終わる（相転移が起きる）と推定される時刻」

本ツールは、終了日をずらしながら（`--outer` 刻み）多数の窓を置き、さらに各窓の中で
窓幅を `--window` から `--smallest-window` まで縮めながら（`--inner` 刻み）モデルを当てはめます。

- **`pos_conf`（バブルシグナル、上段の赤バー）**
  … その日を右端とする窓のうち、**「バブル的パターン（超指数上昇＋対数周期振動）」として
  品質条件を満たしたフィットの割合**。
  高いほど「多くの時間スケールで一貫してバブル的な形が検出されており、
  臨界点が近い可能性がある」ことを意味します。
- **`neg_conf`（バブル終了シグナル、下段の紺バー）**
  … 同じ判定を**下落側**（逆バブル）に対して行ったもの。

品質条件は `lppls` パッケージの既定フィルタで、主に次のとおりです。

| 条件 | 既定値 | 意味 |
| --- | --- | --- |
| `0 < m < 1` | — | べき指数が発散的な範囲にある |
| `2 < ω < 15` | — | 対数周期振動の角振動数が現実的な範囲 |
| `O > 2.5` | 振動回数 | 窓内で対数周期振動が十分な回数観測される |
| `D = m·\|B\| / (ω·\|C\|) > 0.5` | 減衰率 | 振動成分が発散項を上回らない |
| `tc` が窓の近傍 | — | 推定された臨界点が窓から離れすぎていない |

### 注意点

- `pos_conf` は **確率ではなく「窓の一致率」** です。0.5 でも「50% の確率で暴落する」という
  意味ではありません。
- 窓の右端が最新日に近いほど、まだ確定していない振動を見ているため値は不安定になります。
  1 本のバーではなく **バーが継続的に立ち続けているか**を見るのが実務的です。
- `--outer` / `--inner` / `--searches` を変えると値は変わります。比較するときは
  同じパラメータで揃えてください（`fit` は初期値をランダムに振るため、
  同じ設定でも実行ごとに数値がわずかに変動します）。

---

## トラブルシューティング

| 症状 | 対処 |
| --- | --- |
| `^N225 の取得に失敗しました` | ネットワーク・プロキシ設定を確認。ダメなら `--csv` でローカル CSV を使う |
| `データ本数が足りません` | `--start` を早めるか `--window` を小さくする |
| `終値列を特定できませんでした` | CSV の列名を `Date` / `Close`（または `日付` / `終値`）にする |
| 日本語が □ になる | `japanize-matplotlib` が入っているか確認（`pip install -r requirements.txt`） |
| 計算が終わらない | `--outer 20 --inner 20 --searches 8` で粗く試す。`--workers` も確認 |

---

## 免責事項

本ツールが計算する LPPLS 信頼度指標は**学術研究に由来する分析指標**であり、
**暴落の発生や時期を予測・保証するものではありません**。
指標が高い状態が続いたまま相場が上昇を続けることも、指標が低いまま急落することもあります。

本ツールの出力を利用したいかなる投資判断も、**利用者ご自身の責任**において行ってください。
作者および本リポジトリは、本ツールの利用によって生じたいかなる損害についても責任を負いません。

---

## 参考

- D. Sornette, *Why Stock Markets Crash: Critical Events in Complex Financial Systems*
- ETH Zurich Financial Crisis Observatory (FCO)
- [`lppls` (PyPI)](https://pypi.org/project/lppls/) — Boulder Investment Technologies

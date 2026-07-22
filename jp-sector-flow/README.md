# jp-sector-flow

セクター資金フロー（売買代金）を毎営業日 自動更新し、グラフ表示と LINE 通知を行う
**表示専用ツール**。売買判断・発注は行いません。設計の詳細は [`CLAUDE.md`](CLAUDE.md)。

- 更新（バッチ）: `update_daily.py`
- 表示: `app.py`（Streamlit）
- データは `DataProvider` 経由（`mock` = 鍵不要 / `jquants` = 本番）

---

## セットアップ

```bash
cd jp-sector-flow
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 1. まず mock で動作確認（鍵不要）

```bash
python update_daily.py             # → 「更新完了 / 上位: …」が出る
streamlit run app.py               # → ランキングと推移グラフ。確認したら Ctrl+C
```

`db/turnover.csv` / `ranking.csv` / `meta.json` が生成されれば土台OK。

## 2. J-Quants 本番データへ切り替え

```bash
cp .env.example .env
# .env を編集して JQUANTS_REFRESH_TOKEN を記入（下の「認証」参照）
PROVIDER=jquants python update_daily.py
```

### J-Quants の認証について

J-Quants は **APIキー直挿しではなく**、リフレッシュトークン → IDトークン →
`Authorization: Bearer` の方式です（公式ドキュメントで確認済み）。

- ダッシュボードで発行した値を `JQUANTS_REFRESH_TOKEN` に入れる
  （ダッシュボードの「APIキー」は実質リフレッシュトークンとして使えます）
- または `JQUANTS_MAILADDRESS` / `JQUANTS_PASSWORD` を入れると自動発行します
- Light プランのベースは `https://api.jquants.com/v1`（`.env` で変更可）
- 401/403 が出たら、トークンの有効期限（リフレッシュ約1週間 / ID約24時間）と
  プランを確認してください。

## 3. LINE 通知の設定

LINE Notify は終了済みのため、**LINE 公式アカウントの Messaging API** を使います。

1. [LINE Developers](https://developers.line.biz/) でプロバイダー＋
   **Messaging API チャネル**を作成
2. チャネルの「Messaging API設定」から **チャネルアクセストークン（長期）** を発行
   → `.env` の `LINE_CHANNEL_ACCESS_TOKEN`
3. 同画面のQRなどで**自分の公式アカウントを友だち追加**する
4. 自分の **ユーザーID（`Uxxxx…`）** を取得 → `.env` の `LINE_USER_ID`
   （Webhook で `source.userId` を確認する、等）
5. 動作確認:

```bash
PROVIDER=jquants python update_daily.py   # 実機のLINEに通知が届く
```

> `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_USER_ID` が未設定の間は、通知は自動で
> コンソール出力にフォールバックします（pipeline は止まりません）。

---

## 4. 自動実行の登録（平日 引け後 18:30）

スケジューラからは **仮想環境の python を絶対パスで**呼びます。`.env` は
`python-dotenv` で読み込まれます。付属の [`run_update.sh`](run_update.sh) を
使うと簡単です（venv の python を絶対パスで呼び、logs に追記）。

### Mac / Linux（cron）

`crontab -e` に次を追加（パスは実際の絶対パスに置換）:

```cron
30 18 * * 1-5 cd /ABSOLUTE/PATH/jp-sector-flow && PROVIDER=jquants /ABSOLUTE/PATH/jp-sector-flow/.venv/bin/python update_daily.py >> logs/update.log 2>&1
```

または `run_update.sh` を使って:

```cron
30 18 * * 1-5 /ABSOLUTE/PATH/jp-sector-flow/run_update.sh
```

### macOS（launchd）

cron が使いにくい場合は [`deploy/com.jpsectorflow.update.plist.example`](deploy/com.jpsectorflow.update.plist.example)
を編集して使います:

```bash
cp deploy/com.jpsectorflow.update.plist.example ~/Library/LaunchAgents/com.jpsectorflow.update.plist
# /ABSOLUTE/PATH を実際のパスに置換してから
launchctl load ~/Library/LaunchAgents/com.jpsectorflow.update.plist
```

### Windows（タスク スケジューラ）

平日18:30 トリガーで、作業ディレクトリをこのフォルダにして実行:

```bat
schtasks /Create /TN "jp-sector-flow" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:30 ^
  /TR "cmd /c cd /d C:\ABSOLUTE\PATH\jp-sector-flow && set PROVIDER=jquants && .venv\Scripts\python.exe update_daily.py >> logs\update.log 2>&1"
```

登録後は一度手動実行し、`logs/update.log` に成功が記録され、（設定済みなら）
LINE通知が届くことを確認してください。

### （任意）GitHub Actions でクラウド実行

手元PCを常時起動しておけない場合は、リポジトリ直下の
[`.github/workflows/sector-flow.yml`](../.github/workflows/sector-flow.yml)
で毎営業日 更新＋通知できます。GitHub の
Settings → Secrets に `JQUANTS_REFRESH_TOKEN` / `LINE_CHANNEL_ACCESS_TOKEN` /
`LINE_USER_ID` を登録してください。ローカル運用だけなら無効化して構いません。

---

## 既知の TODO

- **祝日スキップ未実装**: `update_daily.is_weekday()` は土日のみ除外。取引カレンダー
  判定に置き換えると祝日も除外できます。

## ルール

- 秘密情報（APIキー / LINEトークン）は必ず `.env`（`.gitignore` 済み）へ。コード直書き禁止。
- データ取得は必ず `DataProvider` 経由。`app.py` / `update_daily.py` に `requests` を直書きしない。
- 表示専用の方針は変えない（売買判断・発注ロジックは追加しない）。

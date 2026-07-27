# フロントエンド（React + TypeScript + Tailwind + Recharts）

バリュー投資アプリの表示層。計算はすべてバックエンド（FastAPI）で行い、フロントは
表示に徹する（仕様書 2章）。

## 画面

| ルート | 画面 | 仕様書 |
|---|---|---|
| `/` | 銘柄マトリクス（横軸PBR×縦軸Fスコアの散布図、4象限色分け、高ROE×低PBRハイライト、点クリックで詳細） | 4.7 |
| `/company/:code` | 銘柄詳細（Fスコア内訳・収益性トレンド・主要指標・定性メモ） | 4.1/4.2 |
| `/screening` | スクリーニング（閾値フィルター＝リアルタイム件数／魔法の公式） | 4.5 |
| `/portfolio` | ポートフォリオ（保有・分散チェック） | 4.8 |
| `/business-cycle` | 景気局面セレクター（主指標の自動切替・信頼度） | 4.4 |
| `/excel` | 予想Excel取込（アップロード→見出し自動検出→値セル候補） | 4.6 |

免責文はヘッダ直下に常時表示（バックエンドの `/api/disclaimer` を表示）。

## セットアップ・起動

バックエンド（別ターミナル）:

```bash
cd ../backend
source .venv/bin/activate
uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

フロントエンド:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173（/api は 8000 にプロキシ）
```

`VITE_API_TARGET` でバックエンドの向き先を上書き可能。

## ビルド

```bash
npm run build      # tsc 型チェック + vite build → dist/
```

## 使い方（初回）

マトリクス画面の「サンプル取込（mock）」ボタンで、鍵不要のモックデータを数銘柄
投入できます（バックエンドの `PROVIDER=jquants` ＋ `JQUANTS_API_KEY` を設定すれば
実データ取込も可能）。

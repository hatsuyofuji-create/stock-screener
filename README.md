# stock-screener

## fill_table.py — 銘柄一覧表（Excel）の空欄を J-Quants で埋める

```bash
export JQUANTS_API_KEY=xxxx            # J-Quants V2 の APIキー
python fill_table.py 銘柄一覧.xlsx -o 銘柄一覧_filled.xlsx
python fill_table.py 銘柄一覧.xlsx --provider mock --limit 20   # 鍵なしの動作確認
```

- 空欄のセルだけを埋める（既に入っている値は上書きしない）
- 埋める列: 業種(G)・市場(Q)・J-Quantsコード(R)・PBR(J)・ROA(K)・
  下値限定的(C)・PBR3以下(D)・PER15以下(E)・配利3％以上(F)
- `--rerank` で PBR順(M)・ROA順(N)・合成(O) を値のある全行で振り直す
- 詳細業種(H)・ROIC(I)・ROIC順(L)・受注開示(P) は埋めない（人の判断／データ不足）

## merge_scouter.py — 銘柄スカウターの CSV を表に流し込む

```bash
python merge_scouter.py 銘柄一覧_filled.xlsx screening_1.csv screening_2.csv -o 銘柄一覧_final.xlsx --original 銘柄一覧_補完.xlsx --rerank
```

- マネックス証券「銘柄スカウター 10年スクリーニング」の CSV（Shift-JIS、1回200行まで）を複数まとめて読み込む
- ROIC(I)・PBR(J)・ROA(K) と、そこから判定した D/E/F、業種(G)・市場(Q) を入れる
- `--original` で渡した元の表で空欄だったセルだけ上書きする（手入力の値は残す）
- `--rerank` で L/M/N 列に RANK 式、O 列に合成式を入れる

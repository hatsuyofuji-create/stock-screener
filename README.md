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

# 業績予想アプリ：受注高の抽出を「PDF直読み」に強化するパッチ

表型（岡本工作機械など）や文字化けPDFで受注高の抽出が失敗していた問題を、
**PDFそのものをClaudeに渡す**方式に替えて解消します。
既存の `ai_analyzer.py` は触らず、フォールバックとして残すので安全です。

## やること（2ステップ）

### ステップ1：新ファイルを置く

`ai_pdf_extract.py` を、**`ir_scraper.py` と同じフォルダ**（業績予想アプリのフォルダ）に
コピーするだけ。

### ステップ2：`ir_scraper.py` を1か所だけ書き換える

`ir_scraper.py` をテキストエディタで開き、**下の「変更前」の16行を探して**、
まるごと「変更後」に置き換えます（`extract_financials_from_pdf` 関数の中、
コメント `# ── AI抽出（本命）。キーがあればまずAIで読む ──` のところ）。

#### 変更前（この16行を探す）

```python
    # ── AI抽出（本命）。キーがあればまずAIで読む ──
    ai_ok = False
    if api_key:
        try:
            import ai_analyzer
            fin_text = _pages_to_text(pages_data, prioritize=True)
            ai = ai_analyzer.extract_financials_with_ai(
                fin_text, quarter=quarter, company_name=company_name,
                api_key=api_key)
            result["sales"] = ai.get("sales")
            result["orders"] = ai.get("orders")
            result["backlog"] = ai.get("backlog")
            result["source"] = "ai"
            result["ai_meta"] = {k: ai.get(k) for k in
                                 ("unit_in_source", "basis", "confidence")}
            ai_ok = True
        except Exception as e:
            result["note"] = f"AI抽出に失敗し正規表現にフォールバック: {e}"
```

#### 変更後（これに置き換える）

```python
    # ── AI抽出（本命）。キーがあればまずAIで読む ──
    # まず PDF そのものを Claude に渡す方式（表型・文字化けPDFに強い）。
    # 失敗したときだけ、従来のテキスト渡し方式にフォールバックする。
    ai_ok = False
    if api_key:
        try:
            try:
                import ai_pdf_extract
                ai = ai_pdf_extract.extract_financials_from_pdf_ai(
                    pdf_bytes, quarter=quarter, company_name=company_name,
                    api_key=api_key)
                result["source"] = "ai_pdf"
            except Exception as e_pdf:
                import ai_analyzer
                fin_text = _pages_to_text(pages_data, prioritize=True)
                ai = ai_analyzer.extract_financials_with_ai(
                    fin_text, quarter=quarter, company_name=company_name,
                    api_key=api_key)
                result["source"] = "ai"
                result["note"] = f"PDF直読みに失敗しテキスト方式へ: {e_pdf}"
            result["sales"] = ai.get("sales")
            result["orders"] = ai.get("orders")
            result["backlog"] = ai.get("backlog")
            result["ai_meta"] = {k: ai.get(k) for k in
                                 ("unit_in_source", "basis", "confidence")}
            ai_ok = True
        except Exception as e:
            result["note"] = f"AI抽出に失敗し正規表現にフォールバック: {e}"
```

これだけです。保存して、いつも通りアプリを起動してください。

## 動きの説明（何が変わるか）

- これまで：PDF → pdfplumberで**テキスト化** → その文字列をClaudeへ（表が崩れて失敗）
- これから：PDF → **そのままClaudeへ**（表も文章も画像も直接読む）
- PDF直読みが万一失敗した時だけ、従来のテキスト方式 → 正規表現、と自動で降りていく
  （＝今まで動いていた銘柄が壊れることはない）

## 確認方法

アプリの「AIで抽出する」を**ON**にして解析すると、結果表の「抽出元」列が
`ai_pdf` になっていれば新方式で読めています。今まで受注高が空欄だった表型銘柄
（岡本工作機械など）で値が入るか見てください。

- 「AIで抽出する」がOFFのときは、従来どおり正規表現のみ（このパッチは影響しません）。
- モデルは既定で `claude-opus-4-8`（既存アプリと同じ）。変えたい場合は環境変数
  `ANTHROPIC_MODEL` で指定できます。

## 元に戻したいとき

`ir_scraper.py` を元の16行に戻し、`ai_pdf_extract.py` を消すだけで完全に元通りです。

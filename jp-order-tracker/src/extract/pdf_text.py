# -*- coding: utf-8 -*-
"""
=====================================================================
 pdfplumber によるテキスト＋表の事前抽出（任意・補助）
=====================================================================
 通常は src/extract/llm.py が PDF をそのまま Claude に渡すので、これは不要です。
 ただし次のような用途に使えます:
   - PDFにそもそも「受注」の語が含まれるか、事前にざっと確認する
   - トークン節約のため、受注が載っていそうなページだけを抜き出す
   - デバッグで中身をテキストで見たいとき

 スキャン画像PDF（テキストが埋め込まれていない）では文字は取れません。
 その場合は llm.py の Claude 直接読み取り（視覚）に任せてください。
=====================================================================
"""

from __future__ import annotations


def extract_text(pdf_path: str) -> str:
    """PDF全ページのテキストを結合して返す（表も可能な範囲でテキスト化）。"""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
            for table in page.extract_tables() or []:
                for row in table:
                    parts.append(
                        "\t".join("" if c is None else str(c) for c in row)
                    )
    return "\n".join(parts)


def mentions_orders(pdf_path: str) -> bool:
    """『受注』という語がテキストとして含まれるかどうか（簡易チェック）。"""
    try:
        return "受注" in extract_text(pdf_path)
    except Exception:
        # 画像PDFなどでテキストが取れない場合は判定不能 → Trueにして Claude に任せる
        return True

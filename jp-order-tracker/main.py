# -*- coding: utf-8 -*-
"""
=====================================================================
 受注高トラッカー — メイン
=====================================================================
 銘柄コードと短信PDFを渡すと、受注高（各Q単独・百万円）を抽出して
 Excelに書き出します。

 使い方（例）:
   # フォルダ内の全PDFをまとめて処理
   python main.py 6141 --dir ./tanshin/6141 --out 受注一覧.xlsx

   # PDFを個別指定
   python main.py 6141 --pdfs q1.pdf q2.pdf q3.pdf fy.pdf --out 受注一覧.xlsx

   # 開示日の当たりをつける（J-Quants。受注高そのものは入っていない点に注意）
   python main.py 6141 --announcements

 事前準備:
   pip install -r requirements.txt
   export ANTHROPIC_API_KEY=...        # 抽出に必須
   export JQUANTS_API_KEY=...          # --announcements を使うときだけ
   # 抽出モデルを変えたい場合（コスト優先など）:
   export ANTHROPIC_MODEL=claude-sonnet-5
=====================================================================
"""

from __future__ import annotations
import argparse
import glob
import os
import sys

from src.extract.llm import extract_orders_from_pdf
from src.transform.quarterly import build_quarterly
from src.excel.writer import write_xlsx


def _collect_pdfs(args) -> list[str]:
    pdfs: list[str] = []
    if args.dir:
        pdfs += sorted(glob.glob(os.path.join(args.dir, "*.pdf")))
    if args.pdfs:
        pdfs += args.pdfs
    return pdfs


def main() -> int:
    p = argparse.ArgumentParser(description="決算短信から受注高(各Q単独)を抽出")
    p.add_argument("code", help="銘柄コード 例: 6141")
    p.add_argument("--dir", help="短信PDFが入ったフォルダ")
    p.add_argument("--pdfs", nargs="*", help="短信PDFのパス（複数可）")
    p.add_argument("--out", default="受注一覧.xlsx", help="出力Excelのパス")
    p.add_argument("--announcements", action="store_true",
                   help="J-Quantsで開示予定日を表示して終了")
    args = p.parse_args()

    if args.announcements:
        from src.fetch.jquants import announcements
        rows = announcements(args.code)
        if not rows:
            print("開示予定は見つかりませんでした。")
            return 0
        for r in rows:
            print(f'{r.get("Date","?")}  {r.get("Code","")}  '
                  f'{r.get("CompanyName","")}  {r.get("FiscalQuarter","")}')
        return 0

    pdfs = _collect_pdfs(args)
    if not pdfs:
        print("PDFが指定されていません。--dir か --pdfs を使ってください。",
              file=sys.stderr)
        return 1

    docs = []
    for path in pdfs:
        print(f"抽出中: {path}")
        try:
            doc = extract_orders_from_pdf(args.code, path)
            docs.append(doc)
            label = "累計" if doc.period_type == "cumulative" else "単独"
            print(f"  → {doc.company} {doc.fiscal_year} Q{doc.quarter} "
                  f"受注高 合計={doc.total}{doc.unit}({label}) "
                  f"セグメント{len(doc.segments)}件")
        except Exception as e:
            print(f"  × 失敗: {e}", file=sys.stderr)

    if not docs:
        print("抽出できた短信がありませんでした。", file=sys.stderr)
        return 1

    results = build_quarterly(docs)
    write_xlsx(results, args.out)
    print(f"完了。{args.out} に {len(results)} 件（決算期）を書き出しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
=====================================================================
 短信PDF → 受注高（構造化データ）を Claude で抽出
=====================================================================
 ・PDFを Claude にそのまま渡します。Claudeはネイティブで
   「文章型（DMG森精機）」「表型（岡本工作機械）」の両方を読めます。
   スキャン画像PDFも視覚的に読めるので、別途OCRは不要です。
 ・出力は JSON（構造化出力で形を保証）。受注高だけを、
   セグメント別＋合計、累計か単独かの判定つきで返させます。

 使い方:
   from src.extract.llm import extract_orders_from_pdf
   doc = extract_orders_from_pdf("6141", "path/to/tanshin.pdf")
=====================================================================
"""

from __future__ import annotations
import base64
import json
import os
from typing import Optional

import anthropic

from src.transform.quarterly import DocumentExtraction


# 既定は最新・最高性能の Opus 5。コスト優先なら環境変数で
#   ANTHROPIC_MODEL=claude-sonnet-5  や  claude-haiku-4-5  に変更できます。
_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

_SYSTEM = """あなたは日本の「決算短信」を読み取る専門アシスタントです。
PDFの中から『受注高（受注額）』だけを正確に抜き出してください。

重要な区別:
- 「受注高」「受注額」= orders received（今回抽出したいのはこれ）
- 「受注残高」= order backlog（← これは違う。抽出しない）
- 「売上高」「販売高」「生産実績」= sales/production（← これも違う。抽出しない）

判断のポイント:
- 文章で書かれている場合（例:「第1四半期の連結受注額は1,554億円」）も、
  表で書かれている場合（例: セグメント別の受注高テーブル）も、両方対応する。
- セグメント別の内訳があれば各セグメントを、なければ合計だけを返す。
- 金額は原文の単位（百万円/億円 など）のまま、数値はカンマを除いた数だけを返す。
- その短信が「第何四半期」か（1/2/3、通期は4）を判定する。
- 数字が『累計（期首からの合計）』か『当四半期単独』かを判定する:
    * 中間期・第2四半期・第3四半期の短信は通常『累計』。
    * 通期(本決算)は『累計(=通期合計)』。cumulative とする。
    * 明確に「当四半期」「3か月」と書かれた単独値のみ quarter とする。
    * 迷ったら cumulative とする（累計が既定）。
- 受注高がPDFに全く書かれていなければ total を null、segments を空にする。
- 推測で数字を作らない。読み取れた数字だけを返す。"""

# 構造化出力のスキーマ（受注高だけに絞る）
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company": {"type": "string", "description": "会社名"},
        "fiscal_year": {
            "type": "string",
            "description": "決算期。'YYYY-MM' 形式（例: 2026年12月期なら 2026-12）",
        },
        "quarter": {
            "type": "integer",
            "enum": [1, 2, 3, 4],
            "description": "第何四半期か。通期(本決算)は 4",
        },
        "period_type": {
            "type": "string",
            "enum": ["cumulative", "quarter"],
            "description": "数字が累計なら cumulative、当四半期単独なら quarter",
        },
        "unit": {
            "type": "string",
            "enum": ["百万円", "億円", "千円", "円"],
            "description": "受注高の金額単位",
        },
        "total": {
            "anyOf": [{"type": "number"}, {"type": "null"}],
            "description": "受注高の合計（原単位、カンマ無し）。無ければ null",
        },
        "segments": {
            "type": "array",
            "description": "セグメント別の受注高。無ければ空配列",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "description": "セグメント名"},
                    "orders_received": {
                        "anyOf": [{"type": "number"}, {"type": "null"}],
                        "description": "そのセグメントの受注高（原単位、カンマ無し）",
                    },
                },
                "required": ["name", "orders_received"],
            },
        },
        "found": {
            "type": "boolean",
            "description": "受注高がPDF内に見つかったら true",
        },
    },
    "required": [
        "company", "fiscal_year", "quarter", "period_type",
        "unit", "total", "segments", "found",
    ],
}


def _pdf_to_base64(pdf_path: str) -> str:
    with open(pdf_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def extract_orders_from_pdf(
    code: str,
    pdf_path: str,
    client: Optional[anthropic.Anthropic] = None,
) -> DocumentExtraction:
    """1つの短信PDFから受注高を抽出して DocumentExtraction を返す。"""
    client = client or anthropic.Anthropic()
    pdf_b64 = _pdf_to_base64(pdf_path)

    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"銘柄コード {code} のこの決算短信から、受注高を抽出して"
                            "スキーマ通りのJSONで返してください。"
                        ),
                    },
                ],
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )

    # 構造化出力なので最初のテキストブロックは必ず有効なJSON
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    segments = {
        s["name"]: s["orders_received"]
        for s in data.get("segments", [])
        if s.get("name")
    }

    return DocumentExtraction(
        code=code,
        company=data.get("company", ""),
        fiscal_year=data.get("fiscal_year", ""),
        quarter=int(data.get("quarter", 0)),
        period_type=data.get("period_type", "cumulative"),
        unit=data.get("unit", "百万円"),
        total=data.get("total"),
        segments=segments,
    )

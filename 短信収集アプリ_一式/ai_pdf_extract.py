"""
PDF直渡し版の財務抽出（受注高・売上高・受注残高）。

既存 ai_analyzer.extract_financials_with_ai は「pdfplumberでテキスト化した文字列」を
Claudeに渡すため、表型・フォント破損の短信で情報が落ちて失敗しやすい。
このモジュールは **PDFそのもの（バイト列）を Claude に渡す**（ネイティブPDF読取り）。
表も文章もスキャン画像も、pdfplumberを介さず直接読むので取りこぼしが激減する。

返り値の形・単位・累計の約束は ai_analyzer.extract_financials_with_ai と完全に同じ:
  {
    "sales":   float|None,   # 売上高   … 当期首からの【累計】・百万円
    "orders":  float|None,   # 受注高   … 当期首からの【累計】・百万円
    "backlog": float|None,   # 受注残高 … その四半期【末】の残高・百万円
    "unit_in_source": str, "basis": str, "confidence": str
  }
→ 呼び出し側（ir_scraper / tanshin_collector）の単独Q換算がそのまま使える。

APIキーは引数 api_key、なければ環境変数 ANTHROPIC_API_KEY。
モデルは環境変数 ANTHROPIC_MODEL で上書き可（既定は ai_analyzer と同じ claude-opus-4-8）。
"""

import base64
import json
import os

import anthropic

# 既存 ai_analyzer と同じモデルに合わせる（挙動・コストを揃える）。
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")

# 返す形は ai_analyzer._FIN_SCHEMA と同一（累計・百万円）。
_FIN_SCHEMA = {
    "type": "object",
    "properties": {
        "sales_cumulative_million":  {"type": ["number", "null"]},
        "orders_cumulative_million": {"type": ["number", "null"]},
        "backlog_end_million":       {"type": ["number", "null"]},
        "unit_in_source": {"type": "string"},   # 資料の元単位（百万円/千円/億円）
        "basis": {"type": "string"},            # どの表・見出し・行・列から取ったか
        "confidence": {"type": "string"},       # high / medium / low
    },
    "required": ["sales_cumulative_million", "orders_cumulative_million",
                 "backlog_end_million", "unit_in_source", "basis", "confidence"],
    "additionalProperties": False,
}


def _build_prompt(quarter, company_name):
    company_part = f"対象企業は「{company_name}」です。\n" if company_name else ""
    q_part = (f"抽出対象は第{quarter}四半期（{quarter}Q）の数値です。\n"
              if quarter else "")
    return (
        f"{company_part}{q_part}"
        "あなたは日本の決算短信を正確に読む財務データ抽出エンジンです。\n"
        "添付したPDF（決算短信そのもの）を直接読み、次の3つの数値を抽出してください。"
        "**すべて単位は百万円の数値**で返します。PDFには文章型の記載も、"
        "セグメント別の表もあります。表はレイアウト・列見出しをそのまま読み取れます。\n\n"
        "1. sales_cumulative_million: 売上高。**当期首からの累計値**（単独四半期ではなく累計）。\n"
        "   例: 第2四半期なら『上期累計』、第3四半期なら『第3四半期累計』の値。\n"
        "2. orders_cumulative_million: 受注高。同じく**当期首からの累計値**。\n"
        "   受注高は財務諸表本表ではなく『生産、受注及び販売の状況』『補足情報』等の"
        "表や本文にあることが多い。DMG森精機のように文章（『連結受注額は◯◯億円』）で"
        "書かれる場合も、岡本工作機械のように表で書かれる場合もある。両方対応すること。\n"
        "3. backlog_end_million: 受注残高。**その四半期末時点の残高**（累計ではなく時点値）。\n\n"
        "■厳守ルール:\n"
        "- 連結（連結財務諸表）の数値を優先。連結が無ければ単体。\n"
        "- 元資料の単位を必ず確認し、百万円に換算する（千円→÷1000、億円→×100、円→÷1,000,000）。\n"
        "  換算に使った元単位を unit_in_source に記載。\n"
        "- 受注高・受注残高がセグメント別に分かれている場合は**全セグメントの合計**を返す"
        "（『合計』『計』の行があればそれを、無ければ各セグメントの単純合算）。\n"
        "- 数値列が複数（前年同期 と 当第N四半期、前期末 と 当期末など）並ぶ場合は、"
        "**必ず『当期側』の列**を採用する。前年・前期の列は絶対に採らない。\n"
        "- 会社予想・前年同期・前期末など『当四半期の実績以外』と混同しない。\n"
        "- 『受注高』と『受注残高』を取り違えない（受注残高は残高＝backlogであって受注高ではない）。\n"
        "- 該当する数値がPDFに無い場合は必ず null。**推測やこじつけで数字を作らない**。\n"
        "- basis に各項目ごとに『どの表・見出し・行・列から取ったか』を具体的に書く。\n"
        "  confidence に high/medium/low。自信が持てない場合は low にし、"
        "basis に迷った理由（候補の数値も）を書く。\n"
    )


def extract_financials_from_pdf_ai(pdf_bytes, quarter=None,
                                   company_name="", api_key=None):
    """
    決算短信PDF（バイト列）から売上高・受注高（累計）・受注残高（期末）を
    Claudeで抽出する。単位は百万円。取れない項目は None。

    返り値: ai_analyzer.extract_financials_with_ai と同一形式の dict。
    """
    client = (anthropic.Anthropic(api_key=api_key) if api_key
              else anthropic.Anthropic())
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")

    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{
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
                {"type": "text", "text": _build_prompt(quarter, company_name)},
            ],
        }],
        output_config={"format": {"type": "json_schema", "schema": _FIN_SCHEMA}},
    )
    raw = next((b.text for b in resp.content if b.type == "text"), "")
    data = json.loads(raw)
    return {
        "sales":   data.get("sales_cumulative_million"),
        "orders":  data.get("orders_cumulative_million"),
        "backlog": data.get("backlog_end_million"),
        "unit_in_source": data.get("unit_in_source", ""),
        "basis": data.get("basis", ""),
        "confidence": data.get("confidence", ""),
    }

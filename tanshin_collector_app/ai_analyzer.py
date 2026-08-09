"""
Claude API を使った製品用途・成長ドライバーの調査モジュール。

- 製品カテゴリごとに「用途・主な顧客・おおよその構成」を推定
- 決算説明資料の本文を読み、「成長ドライバー（中長期の牽引役）」を抽出

APIキーは引数 api_key、なければ環境変数 ANTHROPIC_API_KEY を使用。
"""

import json
import anthropic

MODEL = "claude-opus-4-8"


# ──────────────────────────────────────────────
# 決算短信/決算資料の本文から、売上高・受注高（累計）・受注残高（期末）をAIで抽出
#   正規表現抽出（ir_scraper）が銘柄ごとの様式差で外すのを補うための本命エンジン。
#   返す単位は「百万円」。売上高・受注高は当期首からの【累計】、受注残高は【期末残高】。
#   → 呼び出し側（app.py）の cumulative_to_single がそのまま単独Q換算できる。
# ──────────────────────────────────────────────

_FIN_SCHEMA = {
    "type": "object",
    "properties": {
        # いずれも百万円。資料に無ければ null（推測で数字を作らない）
        "sales_cumulative_million":  {"type": ["number", "null"]},
        "orders_cumulative_million": {"type": ["number", "null"]},
        "backlog_end_million":       {"type": ["number", "null"]},
        "unit_in_source": {"type": "string"},   # 資料の元単位（例: 百万円 / 千円 / 億円）
        "basis": {"type": "string"},            # 連結/単体、どの箇所から取ったか
        "confidence": {"type": "string"},       # high / medium / low
    },
    "required": ["sales_cumulative_million", "orders_cumulative_million",
                 "backlog_end_million", "unit_in_source", "basis", "confidence"],
    "additionalProperties": False,
}


def extract_financials_with_ai(financial_text, quarter=None,
                               company_name="", api_key=None):
    """
    決算短信/決算資料の本文テキストから、売上高・受注高（累計）・受注残高（期末）を
    AIで抽出する。単位は百万円。取れない項目は None。

    返り値: {
      "sales":   float|None,   # 累計・百万円
      "orders":  float|None,   # 累計・百万円
      "backlog": float|None,   # 期末・百万円
      "unit_in_source": str, "basis": str, "confidence": str
    }
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    text = (financial_text or "")[:40000]
    company_part = f"対象企業は「{company_name}」です。\n" if company_name else ""
    q_part = f"抽出対象は第{quarter}四半期（{quarter}Q）の数値です。\n" if quarter else ""

    prompt = (
        f"{company_part}{q_part}"
        "あなたは日本の決算短信を正確に読む財務データ抽出エンジンです。\n"
        "以下の本文（決算短信・決算説明資料などのテキスト。表がテキスト化され読みにくい場合あり）から、"
        "次の3つの数値を抽出してください。**すべて単位は百万円の数値**で返します。\n\n"
        "1. sales_cumulative_million: 売上高。**当期首からの累計値**（単独四半期ではなく累計）。\n"
        "   例: 第2四半期なら『上期累計』、第3四半期なら『第3四半期累計』の値。\n"
        "2. orders_cumulative_million: 受注高。同じく**当期首からの累計値**。\n"
        "   受注高は財務諸表本表ではなく『生産、受注及び販売の状況』等の本文・注記の表にあることが多い。\n"
        "3. backlog_end_million: 受注残高。**その四半期末時点の残高**（累計ではなく時点値）。\n\n"
        "■厳守ルール:\n"
        "- 連結（連結財務諸表）の数値を優先。連結が無ければ単体。\n"
        "- 元資料の単位を必ず確認し、百万円に換算する（千円→÷1000、億円→×100、円→÷1,000,000）。\n"
        "  換算に使った元単位を unit_in_source に記載。\n"
        "- 受注高・受注残高が事業セグメント別に分かれている場合は**全セグメントの合計**を返す"
        "（本文に『合計』『計』の行があればそれを、無ければ各セグメントの単純合算）。\n"
        "- 会社予想・前年同期・前期末など『当四半期の実績以外』の数値と混同しない。\n"
        "- 該当する数値が本文に無い場合は必ず null。**推測やこじつけで数字を作らない**。\n"
        "- basis に、各項目ごとに『どの表・見出し・行・列から取ったか』を具体的に書く"
        "（例: 受注残高＝『③受注残高』表の合計行×当連結会計年度列）。confidence に high/medium/low。\n\n"
        "■表の読み方（銘柄ごとに様式が違う。型に決め打ちせず意味で判断）:\n"
        "- 各表の直前に『[この表の見出し] ○○』が付く場合がある。見出しは表の外にあることが多いので、"
        "これを使ってその表が何の表か（売上高/受注高/受注残高）を判断してよい。\n"
        "- 数値列が複数（例: 前年同期 と 当第N四半期、前連結会計年度 と 当連結会計年度、前期末 と 当期末）"
        "並ぶことが多い。**必ず『当期側』（当第N四半期／当連結会計年度／当期末）の列を採用**し、"
        "前年・前期の列は絶対に採らない。列見出しをよく見て取り違えないこと。\n"
        "- 受注高・売上高は当期首からの累計、受注残高は当四半期末の時点値。\n"
        "- 数値が表ではなく本文（『受注高は○○百万円…』等）に書かれている銘柄もある。その場合は本文から取る。\n"
        "- どのセルを取るか確信が持てない、列や見出しの対応が曖昧な場合は、"
        "最も妥当な値を返しつつ confidence を low にし、basis に迷った理由（候補の数値も）を書く。\n\n"
        "【本文】\n"
        f"{text}\n"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
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

_SCHEMA = {
    "type": "object",
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "use": {"type": "string"},          # 用途
                    "customers": {"type": "string"},    # 主な顧客
                    "composition": {"type": "string"},  # おおよその構成（資料に数値があれば）
                },
                "required": ["name", "use", "customers", "composition"],
                "additionalProperties": False,
            },
        },
        "growth_drivers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},   # 牽引役の見出し（例: ロジック）
                    "detail": {"type": "string"},  # 具体的な根拠（資料の数値・コメント）
                },
                "required": ["title", "detail"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},  # 全体の一言まとめ
    },
    "required": ["products", "growth_drivers", "summary"],
    "additionalProperties": False,
}


def analyze_products_and_drivers(product_names, presentation_text="",
                                 company_name="", api_key=None):
    """
    製品カテゴリと決算説明資料テキストから、
    用途・主な顧客・構成・成長ドライバーをAIで分析して返す。

    返り値: {
      "products": [{"name","use","customers","composition"}, ...],
      "growth_drivers": [{"title","detail"}, ...],
      "summary": "..."
    }
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    product_lines = "\n".join(f"- {p}" for p in product_names) if product_names else "（製品リストなし）"
    company_part = f"対象企業は「{company_name}」です。\n" if company_name else ""

    # 説明資料テキストは長すぎる場合に備えて先頭を中心に制限
    pres = presentation_text[:12000] if presentation_text else "（説明資料テキストなし）"

    prompt = (
        f"{company_part}"
        "あなたは日本株の業績アナリストです。以下の情報をもとに、"
        "投資家が『どの製品がどの産業に使われ、何が業績の成長を牽引するか』を理解できるよう分析してください。\n\n"
        "【製品・事業カテゴリ】\n"
        f"{product_lines}\n\n"
        "【最新の決算説明資料の本文（抜粋・グラフ数値が混在し読みにくい場合があります）】\n"
        f"{pres}\n\n"
        "【出力してほしい内容】\n"
        "1. products: 各製品カテゴリについて\n"
        "   - use（用途）: その製品が何の製造・処理に使われるか\n"
        "   - customers（主な顧客）: 最終ユーザー産業や顧客タイプ（例: ロジック・メモリ半導体メーカー、OLEDパネルメーカー等）\n"
        "   - composition（おおよその構成）: 説明資料に受注高・売上高の構成比や金額があれば記載。なければ『—』\n"
        "2. growth_drivers: 決算説明資料で会社が『中長期的に牽引する』と示している成長ドライバー。\n"
        "   title（牽引役）と detail（具体的根拠: 資料中のYoY%・受注増加・上方修正などの数値やコメント）。\n"
        "   資料に明記がない推測は避け、資料の記述を根拠にしてください。\n"
        "3. summary: 全体を1〜2文で要約。\n"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )

    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


_SUPPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "company_basis": {"type": "string"},  # 基盤技術など一言
        "upstream": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},                 # 調達カテゴリ
                    "companies": {"type": "array", "items": {"type": "string"}},  # 具体的企業名
                },
                "required": ["category", "companies"],
                "additionalProperties": False,
            },
        },
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},      # 事業名
                    "order": {"type": "string"},     # 受注金額など
                    "drivers": {"type": "string"},   # 牽引要因の短い説明
                    "customers": {"type": "array", "items": {"type": "string"}},  # 主な顧客（企業名）
                    "customer_basis": {"type": "string"},  # 推測/開示などの注記
                },
                "required": ["name", "order", "drivers", "customers", "customer_basis"],
                "additionalProperties": False,
            },
        },
        "leading_indicators": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indicator": {"type": "string"},  # 先行指標（企業名 or 統計名）
                    "kind": {"type": "string"},       # 「企業」か「統計データ」
                    "detail": {"type": "string"},     # なぜ先行指標になるか
                },
                "required": ["indicator", "kind", "detail"],
                "additionalProperties": False,
            },
        },
        "caveat": {"type": "string"},  # 注意点（推測を含む旨など）
    },
    "required": ["company", "company_basis", "upstream", "segments",
                 "leading_indicators", "caveat"],
    "additionalProperties": False,
}


def analyze_supply_chain(product_names, presentation_text="",
                         company_name="", api_key=None):
    """
    企業のサプライチェーン（上流調達先→自社→事業→顧客）を具体的企業名つきで推定し、
    先行指標となりうる企業・統計データを列挙する。
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    product_lines = "\n".join(f"- {p}" for p in product_names) if product_names else "（製品リストなし）"
    company_part = company_name or "対象企業"
    pres = presentation_text[:12000] if presentation_text else "（説明資料テキストなし）"

    prompt = (
        f"対象企業は「{company_part}」です。\n"
        "あなたは日本株のアナリストです。この企業のサプライチェーンを、"
        "投資家が一目で理解できるように整理してください。"
        "可能な限り**具体的な企業名**を入れてください（業界構造からの推測でも可。ただし推測であることを注記）。\n\n"
        "【製品・事業カテゴリ】\n"
        f"{product_lines}\n\n"
        "【最新の決算説明資料の本文（グラフ数値が混在し読みにくい場合があります）】\n"
        f"{pres}\n\n"
        "【出力してほしい内容】\n"
        "1. company / company_basis: 企業名と基盤技術（例: 真空技術が基盤）\n"
        "2. upstream: 上流の調達先カテゴリと、その具体的な供給企業名（例: 真空ポンプ→エドワーズ、ターゲット材料→JX金属・田中貴金属 など）\n"
        "3. segments: 各メイン事業について name / order（受注金額。資料の品目別予想を使用）/ "
        "drivers（牽引要因）/ customers（主な顧客の企業名。例: DRAMならサムスン・SK・マイクロン）/ "
        "customer_basis（『推測』『資料開示』などの根拠区分）\n"
        "4. leading_indicators: この企業の業績の**先行指標になりうる**ものを列挙。"
        "サプライチェーン上の他社（顧客・競合・調達先の上場企業名）や、"
        "業界統計（例: 半導体製造装置の北米BB比、DRAMスポット価格、各社設備投資計画 等）を、"
        "kind（『企業』or『統計データ』）と detail（なぜ先行指標になるか）つきで。\n"
        "5. caveat: 企業名は業界構造からの推測を含み公式開示ではない旨などの注意点。\n"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _SUPPLY_SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


def _collect_text(resp):
    return "\n".join(b.text for b in resp.content if b.type == "text")


def _clean_report_text(text):
    """Web検索の途中ナレーション・citeタグを除去し、本文（見出し以降）を残す。"""
    import re
    text = re.sub(r"</?cite[^>]*>", "", text)
    # 最初の見出し（## ① など）以降を本文とみなす
    m = re.search(r"#{0,3}\s*①", text)
    if m:
        text = text[m.start():]
    keep = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            keep.append("")
            continue
        # 進捗ナレーション行を除外
        if any(k in s for k in ["調べます", "確認します", "Let me", "I have", "I now",
                                "There's", "Search tool", "web search"]):
            continue
        keep.append(ln)
    return "\n".join(keep).strip()


def analyze_industry_trends(company_name, presentation_text="", reference_companies=None,
                            api_key=None, use_web_search=True):
    """
    主力事業の業界市場動向（将来見通し）を分析する。

    reference_companies: 参考にする同業メーカーのリスト [{"code":.., "name":..}, ...]
        指定すると、各社の最新決算説明資料/IRをWeb検索で調べ、① の業界将来見通しの根拠にする。
    指定がなければ業界全体をWeb検索（use_web_search=Falseならknowledge）。

    返り値: {"text": マークダウン本文, "web_used": bool}
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    pres = presentation_text[:10000] if presentation_text else "（説明資料テキストなし）"
    reference_companies = reference_companies or []

    # ①の情報源の指定
    if reference_companies:
        names = "、".join(f"{r.get('name') or r.get('code')}（{r.get('code')}）"
                          for r in reference_companies)
        source_line = (
            f"①の業界将来見通しは、次の同業メーカーの**最新の決算説明資料・IR情報をWeb検索で調べて**"
            f"根拠にしてください: {names}。\n"
            "各社が業界（半導体製造装置＝WFE市場等）の**今後（翌年・中期）の成長率・市場規模を"
            "どう見通しているか**を、具体的な数値と出典（資料名・日付）つきで抽出してください。\n"
            "検索は各社1〜2回程度に絞り、効率的に行ってください。")
        want_web = True
    elif use_web_search:
        source_line = ("①の業界将来見通しは、**Web検索で最新情報を調べて**整理してください。"
                       "出典（URL/媒体）を併記してください。")
        want_web = True
    else:
        source_line = ("①の業界将来見通しは、あなたの知識（学習データ）に基づいて整理してください。"
                       "最新版と乖離する可能性があるため、市場の数値見通しには『推定』と明記してください。")
        want_web = False

    prompt = (
        f"対象企業は「{company_name}」です。\n"
        "あなたは日本株の業界アナリストです。この企業の**主力事業が属する業界**の"
        "**将来の市場成長見通し**を分析してください。\n"
        "まず決算説明資料から主力事業の業界（例: 半導体製造装置＝WFE市場）を特定してください。\n"
        f"{source_line}\n\n"
        "【自社の最新決算説明資料（抜粋）】\n"
        f"{pres}\n\n"
        "【出力フォーマット（日本語・マークダウン。前置きや進捗報告は書かず、いきなり見出しから始める）】\n"
        "## ① 業界市場の将来成長見通し\n"
        "対象業界の**今後（翌年・中期）の市場規模・成長率の見通し**を、"
        "参考メーカー（または統計）が何と見ているか具体的な数値とともに整理。"
        "業界全体の成長率レンジ（例: 年+15〜20%）を明示してください。\n\n"
        "## ② 自社の成長率を業界比で評価\n"
        "決算説明資料の自社の受注/売上成長率（具体的数値）を引用し、"
        "①の業界見通しと比較。\n\n"
        "## ③ 自社は業界成長を上回るか（判定）\n"
        "①の業界成長率に対し、②の自社の成長率が**上回るか/下回るか**を明確に判定してください。"
        "結論を最初に一言（例: 『半導体関連は業界を大きく上回る』）で述べ、"
        "セグメント別に上回る/下回るを整理。\n\n"
        "## ④ 注意点\n"
        "業界統計でカバーされない事業（例: WFEは前工程のみでディスプレイ/レアアースは別）や、"
        "見通しの不確実性など。\n\n"
        "重要: 調査の進捗（『〜を調べます』等）やツールの状態は本文に書かないこと。"
        "結論の分析だけをマークダウンで出力してください。"
    )

    kwargs = dict(
        model=MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    web_used = False
    if want_web:
        # 参考メーカー数に応じて検索回数の上限を確保
        max_uses = min(4 + 2 * len(reference_companies), 12)
        kwargs["tools"] = [{"type": "web_search_20260209", "name": "web_search",
                            "max_uses": max_uses}]

    try:
        resp = client.messages.create(**kwargs)
        web_used = want_web
        # サーバー側ツールループが途中停止した場合は継続
        msgs = list(kwargs["messages"])
        guard = 0
        while resp.stop_reason == "pause_turn" and guard < 4:
            msgs.append({"role": "assistant", "content": resp.content})
            resp = client.messages.create(
                model=MODEL, max_tokens=8000, messages=msgs,
                tools=kwargs.get("tools"))
            guard += 1
        return {"text": _clean_report_text(_collect_text(resp)), "web_used": web_used}
    except Exception:
        # Web検索が使えない環境などはツールなしで再試行（知識ベース）
        resp = client.messages.create(
            model=MODEL, max_tokens=8000,
            messages=[{"role": "user", "content": prompt}])
        return {"text": _clean_report_text(_collect_text(resp)), "web_used": False}


# ──────────────────────────────────────────────
# 上振れ・下振れ分析（ファイルを読み、上振れ/下振れ要因を金額化）
# ──────────────────────────────────────────────

_UPDOWN_SCHEMA = {
    "type": "object",
    "properties": {
        "target": {"type": "string"},   # 分析対象（会社計画など）の説明
        "factors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},        # 要因名
                    "direction": {"type": "string"},   # 上振れ / 下振れ / 中立
                    "amount": {"type": "string"},      # 影響額（例: +5億円、▲2億円、±0、不明）
                    "basis": {"type": "string"},       # 根拠・計算方法
                },
                "required": ["name", "direction", "amount", "basis"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},   # 総合判定（上振れ寄り/下振れ寄り/中立＋一言）
        "caveat": {"type": "string"},    # 推測を含む旨などの注意点
    },
    "required": ["target", "factors", "summary", "caveat"],
    "additionalProperties": False,
}


def analyze_upside_downside(material_text, company_name="", api_key=None):
    """
    アップロードされた資料（決算資料/業績計画など）を読み、
    会社計画に対する上振れ要因・下振れ要因を特定して金額に落とす。

    返り値: {"target", "factors":[{name,direction,amount,basis}], "summary", "caveat"}
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    text = material_text[:16000] if material_text else ""
    company_part = f"対象企業は「{company_name}」です。\n" if company_name else ""

    prompt = (
        f"{company_part}"
        "あなたは日本株のアナリストです。以下の資料は、ある企業の業績（会社計画・実績・"
        "増減益要因など）に関するものです。\n"
        "この**会社計画（業績予想）に対する上振れ要因・下振れ要因**を特定し、"
        "**可能な限り金額（億円・百万円など）に落として**ください。\n\n"
        "考え方の例（ただし要因の数や種類は資料に応じて自由に。4要因に固定しない）:\n"
        "- 売上増減の効果（限界利益／前期粗利率ベース）\n"
        "- 原価率・粗利率の変化による効果（コスト改善・値上げ・ミックス等）\n"
        "- 販管費の増減\n"
        "- 為替影響\n"
        "- その他、資料から読み取れる固有の要因（特定セグメントの増減など）\n\n"
        "各要因について、それが会社計画に対して『上振れ要因（計画が保守的＝上に振れやすい）』か"
        "『下振れ要因（計画が強気＝下に振れやすい）』か『中立』かを判定し、影響額と根拠を示してください。\n"
        "資料に数値の根拠がない部分は推測でも構いませんが、その旨を root（根拠）に明記してください。\n\n"
        "【資料本文】\n"
        f"{text}\n\n"
        "【出力】\n"
        "- target: 何の計画を分析したか（例: 2026年度 会社営業利益計画 51億円）\n"
        "- factors: 上振れ/下振れ要因のリスト（name=要因名 / direction=上振れ・下振れ・中立 / "
        "amount=影響額 例『+5億円』『▲2億円』『±0』『不明』 / basis=根拠・計算方法）\n"
        "- summary: 総合判定（全体として上振れ寄りか下振れ寄りか中立か、を一言＋理由）\n"
        "- caveat: 外部推測を含む旨などの注意点\n"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _UPDOWN_SCHEMA}},
    )
    text_out = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text_out)


# ──────────────────────────────────────────────
# 業績予想の上振れ・下振れ「定量」判定
#   会社予想（今期通期）に対し、資料から読む実力ベースの増減を比較し、
#   上振れ額／下振れ額を金額で出す。
# ──────────────────────────────────────────────

_FACTOR_ITEM = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "amount_oku": {"type": "number"},  # 影響額（億円・符号つき。上振れ/増益=＋、下振れ/減益=−）
        "basis": {"type": "string"},       # 根拠・計算
    },
    "required": ["name", "amount_oku", "basis"],
    "additionalProperties": False,
}

_SECTION = {
    "type": "object",
    "properties": {
        "forecast_text": {"type": "string"},  # 今期通期の会社予想（前期比つき）
        "baseline_oku": {"type": "number"},    # 基準額（億円）。着地水準＝基準＋要因合計
        "factors": {"type": "array", "items": _FACTOR_ITEM},
        "verdict": {"type": "string"},
    },
    "required": ["forecast_text", "baseline_oku", "factors", "verdict"],
    "additionalProperties": False,
}

_HIGH_MARGIN_ITEM = {
    "type": "object",
    "properties": {
        "segment": {"type": "string"},  # 高収益とされるセグメント名（資料の表記）
        "quote": {"type": "string"},    # 「高収益」「利益率が高い」等の該当文言の引用
    },
    "required": ["segment", "quote"],
    "additionalProperties": False,
}

_GUIDANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "sales": _SECTION,        # 今期：売上高（会社予想に対する上振れ/下振れ）
        "op": _SECTION,           # 今期：営業利益
        "next_sales": _SECTION,   # 来期：売上高（今期会社予想を基準とした増減要因）
        "next_op": _SECTION,      # 来期：営業利益
        "high_margin_segments": {"type": "array", "items": _HIGH_MARGIN_ITEM},  # 高収益文言のあるセグメント
        "next_note": {"type": "string"},  # 来期見通しの根拠・前提
        "caveat": {"type": "string"},
    },
    "required": ["sales", "op", "next_sales", "next_op",
                 "high_margin_segments", "next_note", "caveat"],
    "additionalProperties": False,
}


def analyze_guidance_updown(company_name, source_text, manual=None, api_key=None):
    """
    会社の業績予想（今期通期）に対する上振れ・下振れを、売上高と営業利益に分けて定量判定する。

    各要因の影響額は億円の数値（amount_oku、符号つき）で返すので、呼び出し側で
    加算してネット（会社予想比）を計算できる。
    返り値: {"sales": _SECTION, "op": _SECTION, "caveat": str}
      _SECTION = {"forecast_text", "factors":[{name, amount_oku, basis}], "verdict"}
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    text = source_text[:18000] if source_text else ""
    company_part = f"対象企業は「{company_name}」です。\n" if company_name else ""

    prompt = (
        f"{company_part}"
        "あなたは日本株のアナリストです。以下の資料（決算短信・決算説明資料・質疑応答など）を読み、"
        "**会社の今期通期予想に対する上振れ／下振れを、売上高と営業利益に分けて定量判定**してください。\n\n"
        "■共通ルール:\n"
        "- 金額はすべて『億円』の数値(amount_oku)で出す。決算短信が百万円なら100で割って億円に。\n"
        "- 符号: 上振れ（増収・増益）＝プラス、下振れ（減収・減益）＝マイナス。\n"
        "- factorsは『会社予想に対する上振れ/下振れ要因』。各要因は会社予想からの増減額。\n"
        "- 定性的で金額化できない要因は amount_oku=0 とし、basisに説明を書く。\n"
        "- baseline_oku: 各セクションの基準額を億円の数値で出す。"
        "今期セクションは『今期の会社予想の絶対額』、来期セクションは『今期会社予想の絶対額』を入れる"
        "（例: 売上なら2600、営業利益なら190）。着地水準＝baseline_oku＋要因合計 で計算できるようにする。\n\n"
        "■売上高(sales):\n"
        "- forecast_text: 今期通期の売上予想（前期比つき。例『2,600億円・前期比+88億』）\n"
        "- factors: 受注動向・期ズレ・特定セグメント増減など、会社の売上予想に対する上振れ/下振れ要因を金額で。\n\n"
        "■営業利益(op):\n"
        "- forecast_text: 今期通期の営業利益予想（前期比つき）\n"
        "- factors: 会社の営業利益予想に対する上振れ/下振れ要因を金額で。以下のルールを必ず適用:\n"
        "  ★ルールA（売上由来で営業利益額の明記がない場合）: 売上の上振れ/下振れ要因について"
        "資料に営業利益への影響額が明記されていなければ、『売上の影響額 × 前年の営業利益率』で"
        "営業利益への影響を試算する。basisに『売上+X億 × 前年営業利益率a% = +P億 ※試算』と明記。\n"
        "  ★ルールB（利益率改善コメントがある場合）: 資料に『営業利益率が前年より上がる/改善する』旨の"
        "コメントがあれば、営業利益率が+3ポイント改善する前提で『今期予想売上 × 3%』を増益要因として加える。"
        "basisに『今期売上○億 × 3% = +Q億 ※3%営業利益率が改善予想』と明記。\n"
        "  ★一過性費用・期ズレなど資料に金額が明記されたものはそのまま使う。\n\n"
        "■今期セクションの verdict: 会社予想に対する売上/営業利益のネット上振れ・下振れを一言（定量的に）。\n\n"
        "■来期予想(next_sales / next_op):\n"
        "資料から読み取れる来期（次期）の見通しを、**今期の会社予想を基準**として定量化してください。\n"
        "- forecast_text: 基準＝今期会社予想（例『今期会社予想 売上2,600億円 を基準』）\n"
        "- factors: 今期会社予想から来期にかけての増減要因（amount_oku 符号つき・億円）。例:\n"
        "  ・受注残（過去最高水準）の来期への売上寄与（来期挽回コメント等）→ 増収/増益要因(＋)\n"
        "  ・今期計上の一過性費用（EV関連費用等）の来期剥落 → 増益要因(＋)\n"
        "  ・今期の期ズレ売上の来期計上 → 増収/増益要因(＋)\n"
        "  ・高利益率案件の来期挽回 → 増益要因(＋)\n"
        "  ・中期計画や会社コメントから読める来期の方向性\n"
        "  営業利益factorsには今期と同じ★ルールA（売上由来は前年営業利益率で試算）を適用。\n"
        "  ※来期の『利益率改善（+3%）』はアプリ側がセグメント別に確定計算するため、"
        "ここでは利益率改善を理由とする増益要因（今期売上×3%等）は入れないこと。\n"
        "- verdict: 来期が今期会社予想をどれだけ上回る/下回るか、ネットを一言（定量的に）。\n"
        "資料に来期の明示が乏しい場合は、受注残・一過性費用・期ズレ・会社の来期コメントから推定し、推定である旨をbasisに書く。\n"
        "■high_margin_segments: 決算説明資料の本文に『高収益』『利益率が高い』『高採算』"
        "『高付加価値』『収益性が高い』等、そのセグメント／製品の利益率の高さを示す文言があるものを抽出。"
        "segment＝資料の表記のセグメント／製品名、quote＝その文言を含む実際の記述を引用。"
        "該当が無ければ空配列。利益率改善の影響額はアプリ側がこのセグメントに対して計算する。\n\n"
        "■next_note: 来期見通しの前提・根拠（どのコメントや数値を使ったか）。\n\n"
        "■caveat: 外部推測・試算を含む旨などの注意点。\n\n"
        "【資料本文】\n"
        f"{text}\n"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _GUIDANCE_SCHEMA}},
    )
    out = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(out)


# ──────────────────────────────────────────────
# アップロードされたサプライチェーン資料から、対象銘柄の位置を特定
# ──────────────────────────────────────────────

_LOCATE_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},      # 資料内で見つかったか
        "stage": {"type": "string"},       # 位置する段階（上流/中流/下流などの大分類）
        "category": {"type": "string"},    # 細分類・カテゴリ
        "role": {"type": "string"},        # 役割・取扱い
        "upstream": {"type": "string"},    # この銘柄の上流（供給する側）
        "downstream": {"type": "string"},  # この銘柄の下流（顧客側）
        "peers": {"type": "string"},       # 同じ位置の他社
        "summary": {"type": "string"},     # 要約
    },
    "required": ["found", "stage", "category", "role",
                 "upstream", "downstream", "peers", "summary"],
    "additionalProperties": False,
}


def locate_in_supply_chain(material_text, company_name="", code="", api_key=None):
    """
    アップロードされたサプライチェーン資料の中で、対象銘柄がどこに位置するかを特定する。
    返り値: _LOCATE_SCHEMA に沿ったdict。
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    text = material_text[:16000] if material_text else ""
    who = f"対象企業は「{company_name}」（証券コード{code}）です。\n" if company_name else f"証券コード{code}。\n"

    prompt = (
        f"{who}"
        "以下は、ある業界のサプライチェーンに関する資料です。\n"
        "この資料のサプライチェーン構造の中で、**対象企業がどこに位置するか**を特定してください。\n"
        "- 資料内に対象企業（社名やコード）が明記されていればそれを使う。\n"
        "- 明記がなくても、対象企業の事業内容から、この資料のどの段階・カテゴリに当てはまるか推定してよい"
        "（その場合 summary に推定である旨を書く）。\n"
        "- 上流（対象企業に供給する側）・下流（対象企業の顧客側）・同じ位置の他社も、資料から読み取って示す。\n"
        "- どうしても位置づけられない場合のみ found=false。\n\n"
        "【サプライチェーン資料】\n"
        f"{text}\n\n"
        "【出力】found / stage（段階）/ category（カテゴリ）/ role（役割）/ "
        "upstream（上流）/ downstream（下流）/ peers（同じ位置の他社）/ summary（要約）"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _LOCATE_SCHEMA}},
    )
    out = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(out)


# ──────────────────────────────────────────────
# 業界市場動向のテキストから、各セグメントの業界成長率(%)を抽出
# ──────────────────────────────────────────────

_SEGGROWTH_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},        # 渡したセグメント名
                    "growth_pct": {"type": "number"},  # 業界成長率(年率%)。数値のみ
                    "basis": {"type": "string"},       # 根拠（業界見通しのどの数字か）
                },
                "required": ["name", "growth_pct", "basis"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["segments"],
    "additionalProperties": False,
}


def extract_segment_growth(industry_text, segment_names, api_key=None):
    """
    業界市場動向の分析テキストから、指定セグメントの『業界成長率(年率%)』を数値で抽出。
    返り値: {"segments": [{"name", "growth_pct", "basis"}]}
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    names = "\n".join(f"- {n}" for n in segment_names)
    text = (industry_text or "")[:12000]

    prompt = (
        "以下は、ある企業の業界市場動向の分析テキストです。\n"
        "この内容をもとに、次の各セグメントについて『業界の成長率（年率%）の見通し』を"
        "数値で抽出してください。\n"
        "- テキストにそのセグメントの具体的な成長率（例: WFE +20%）があればその数値を使う。\n"
        "- 直接の記載がなければ、最も近い業界の数値や全体見通しから推定する。\n"
        "- growth_pct は％の数値のみ（例: 20）。basis に根拠（どの業界見通しを使ったか）。\n\n"
        "【対象セグメント】\n"
        f"{names}\n\n"
        "【業界市場動向の分析テキスト】\n"
        f"{text}\n"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _SEGGROWTH_SCHEMA}},
    )
    out = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(out)

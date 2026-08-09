"""
IRページからPDFを取得し、売上高・受注高・受注残高を抽出するモジュール。
- 指定した期・Qに対応するPDFを自動選択
- 売上高・受注高は四半期単独値を抽出
- 受注残高は本文テキストの「受注残高はXXX億円」形式にも対応
"""

import re
import io
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import pdfplumber

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# 数値抽出で読むPDFの最大ページ数。受注状況は末尾ページに載るため十分に確保する
# （訂正版は表紙が付いてページ数が増える）。
MAX_EXTRACT_PAGES = 45

SALES_KEYWORDS   = ["売上高", "売上収益", "営業収益"]
ORDERS_KEYWORDS  = ["受注高", "受注額"]
BACKLOG_KEYWORDS = ["受注残高", "受注残"]

QUARTER_TITLE_MAP = {
    1: ["第1四半期", "第一四半期", "1q", "1Q", "第１四半期"],
    2: ["第2四半期", "第二四半期", "2q", "2Q", "第２四半期"],
    3: ["第3四半期", "第三四半期", "3q", "3Q", "第３四半期"],
    4: ["通期", "第4四半期", "第四四半期", "4q", "4Q", "年度"],
}

SINGLE_Q_KEYWORDS = [
    "当第", "当四半期", "当3ヵ月", "当3か月", "当3ケ月",
    "当３ヵ月", "当３か月", "３ヶ月間", "3ヶ月間",
]

# ──────────────────────────────────────────────
# 自社サイト直置き型（TDNET経由でないため直接URLを管理する銘柄）
# JavaScriptで動的にPDFリンクを表示するサイトはスクレイピングで拾えないため、
# ここに銘柄コードをキーにしてPDF URLリストを直接登録する。
# ──────────────────────────────────────────────
DIRECT_IR_PDF_URLS: dict[str, list[dict]] = {
    "6266": [  # タツモ（12月決算）
        {"title": "2026年12月期 第1四半期決算短信",
         "url": "https://tazmo.co.jp/wp/wp-content/uploads/2026/05/fy2025_q1.pdf"},
        {"title": "2025年12月期 通期決算短信（訂正）",
         "url": "https://tazmo.co.jp/wp/wp-content/uploads/2026/03/correction_fy2025_q4.pdf"},
        {"title": "2025年12月期 第3四半期決算短信",
         "url": "https://tazmo.co.jp/wp/wp-content/uploads/2025/11/2025%E5%B9%B412%E6%9C%88%E6%9C%9F-%E7%AC%AC%EF%BC%93%E5%9B%9B%E5%8D%8A%E6%9C%9F%E6%B1%BA%E7%AE%97%E7%9F%AD%E4%BF%A1%E3%80%94%E6%97%A5%E6%9C%AC%E5%9F%BA%E6%BA%96%E3%80%95%EF%BC%88%E9%80%A3%E7%B5%90%EF%BC%89.pdf"},
        {"title": "2025年12月期 第2四半期決算短信",
         "url": "https://tazmo.co.jp/wp/wp-content/uploads/2025/07/2025%E5%B9%B412%E6%9C%88%E6%9C%9F-%E7%AC%AC%EF%BC%92%E5%9B%9B%E5%8D%8A%E6%9C%9F%EF%BC%88%E4%B8%AD%E9%96%93%E6%9C%9F%EF%BC%89%E6%B1%BA%E7%AE%97%E7%9F%AD%E4%BF%A1%E3%80%94%E6%97%A5%E6%9C%AC%E5%9F%BA%E6%BA%96%E3%80%95%EF%BC%88%E9%80%A3%E7%B5%90%EF%BC%89.pdf"},
        {"title": "2025年12月期 第1四半期決算短信",
         "url": "https://tazmo.co.jp/wp/wp-content/uploads/2025/05/2025%E5%B9%B412%E6%9C%88%E6%9C%9F-%E7%AC%AC%EF%BC%91%E5%9B%9B%E5%8D%8A%E6%9C%9F%E6%B1%BA%E7%AE%97%E7%9F%AD%E4%BF%A1%E3%80%94%E6%97%A5%E6%9C%AC%E5%9F%BA%E6%BA%96%E3%80%95%EF%BC%88%E9%80%A3%E7%B5%90%EF%BC%89.pdf"},
        {"title": "2024年12月期 通期決算短信",
         "url": "https://tazmo.co.jp/wp/wp-content/uploads/2025/02/2024%E5%B9%B412%E6%9C%88%E6%9C%9F%E6%B1%BA%E7%AE%97%E7%9F%AD%E4%BF%A1%E3%80%94%E6%97%A5%E6%9C%AC%E5%9F%BA%E6%BA%96%E3%80%95%EF%BC%88%E9%80%A3%E7%B5%90%EF%BC%89.pdf"},
    ]
}

# TDNET形式: 1401YYYYMMDD数字.pdf
_DATE_PAT = re.compile(r"1401(\d{4})(\d{2})(\d{2})\d+\.pdf", re.IGNORECASE)

# WordPress形式: /wp-content/uploads/YYYY/MM/filename.pdf
_WP_DATE_PAT = re.compile(r"/uploads/(\d{4})/(\d{2})/", re.IGNORECASE)


def _filing_date_from_url(url: str) -> str:
    """URLのファイル名から提出日を抽出する（TDNET形式・WP形式両対応）"""
    m = _DATE_PAT.search(url)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}提出"
    m = _WP_DATE_PAT.search(url)
    if m:
        return f"{m.group(1)}/{m.group(2)}提出"
    return ""


def fetch_pdf_links(ir_url: str, doc_type: str, ticker: str = "") -> list[dict]:
    # 直接URLリストが登録されている銘柄はそれを返す（スクレイピング不要）
    if ticker and ticker in DIRECT_IR_PDF_URLS:
        return DIRECT_IR_PDF_URLS[ticker]

    try:
        res = requests.get(ir_url, headers=HEADERS, timeout=15)
        res.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"IRページの取得に失敗しました: {e}")

    soup = BeautifulSoup(res.text, "html.parser")
    base = f"{urlparse(ir_url).scheme}://{urlparse(ir_url).netloc}"

    pdf_links = []
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        full_url = urljoin(base, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        base_title = a.get_text(strip=True) or href.split("/")[-1]
        date_label = _filing_date_from_url(full_url)
        title = f"{base_title}　[{date_label}]" if date_label else base_title

        pdf_links.append({"title": title, "url": full_url})
    return pdf_links


# Q&A・説明会資料など除外するキーワード
_EXCLUDE_KEYWORDS = ["qa ", "q&a", "質疑応答", "説明会", "presentation", "補足説明",
                     "briefing", "conference"]

def _is_excluded(link: dict) -> bool:
    text = (link["title"] + " " + link["url"]).lower()
    return any(ex in text for ex in _EXCLUDE_KEYWORDS)


def filter_pdf_by_quarter(pdf_links: list[dict], quarter: int) -> list[dict]:
    """Q&A・説明会資料を除外した上でキーワードマッチングする。"""
    keywords = QUARTER_TITLE_MAP.get(quarter, [])
    # Q&A等を除外
    candidates = [l for l in pdf_links if not _is_excluded(l)]
    # まずは既存キーワードでマッチ
    matched = [
        l for l in candidates
        if any(kw.lower() in l["title"].lower() or kw.lower() in l["url"].lower()
               for kw in keywords)
    ]
    # 通期資料が 'FY202X' や 'FY202X.YY' の形式で存在する場合もQ4候補とする
    if not matched:
        fy_pattern = re.compile(r"FY\s?\d{4}|FY\s?\d{4}\.\d{2}", re.IGNORECASE)
        for l in candidates:
            if fy_pattern.search(l["title"]) or fy_pattern.search(l["url"]):
                matched.append(l)
    # マッチなければ除外済み候補を全部返す（auto_select_pdf側でフィルタリング）
    return matched if matched else candidates


def expected_filing_year(fiscal_year: int, quarter: int,
                         fiscal_end_month: int) -> int:
    """
    期・Q・決算月から、PDFの提出年（カレンダー年）を計算する。

    例: アルバック（決算月=7、7月期）
      2025期1Q（8〜10月）→ 提出 2024年11月 → 提出年=2024
      2025期2Q（11〜1月）→ 提出 2025年2月  → 提出年=2025
      2025期3Q（2〜4月） → 提出 2025年5月  → 提出年=2025
      2025期4Q（5〜7月） → 提出 2025年9月  → 提出年=2025
    """
    # 期首月（fiscal_end_month の翌月）
    start_month = (fiscal_end_month % 12) + 1
    # 四半期末月（期首から3Q月後）
    q_end_month = ((start_month - 1 + quarter * 3 - 1) % 12) + 1
    # 提出月（四半期末の翌月か2ヶ月後）
    filing_month = (q_end_month % 12) + 1

    # 期首がカレンダー年をまたぐか判定
    # fiscal_year は期末のカレンダー年
    start_year = fiscal_year - 1 if start_month > fiscal_end_month else fiscal_year

    # Q末のカレンダー年
    q_end_year = start_year
    if start_month + quarter * 3 - 1 > 12:
        q_end_year += (start_month + quarter * 3 - 2) // 12

    # 提出年（filing_monthがq_end_monthより小さい＝月をまたいで翌年になった場合）
    if filing_month > q_end_month:
        filing_year = q_end_year      # 同年内に提出
    else:
        filing_year = q_end_year + 1  # 翌年1月提出（Q末=12月の場合）

    return filing_year


def auto_select_pdf(pdf_links: list[dict], fiscal_year: int,
                    quarter: int, fiscal_end_month: int) -> int:
    """
    期・Q・決算月から最も適切なPDFのインデックスを返す。
    URLに含まれる提出年が一致するものを優先する。
    """
    target_year = expected_filing_year(fiscal_year, quarter, fiscal_end_month)
    target_str = str(target_year)

    # 1) 提出年が一致するファイルを優先
    for i, link in enumerate(pdf_links):
        m = _DATE_PAT.search(link["url"])
        if m and m.group(1) == target_str:
            return i
        m2 = _WP_DATE_PAT.search(link["url"])
        if m2 and m2.group(1) == target_str:
            return i

    # 2) タイトル/URLに「決算短信」やtanshinが含まれるものを優先
    for i, link in enumerate(pdf_links):
        txt = (link.get("title", "") + " " + link.get("url", "")).lower()
        if "決算短信" in txt or "tanshin" in txt or "決算" in txt:
            return i

    # 3) 実際にPDFを軽く解析して、売上/受注/受注残の抽出に成功する候補をスコアリング
    best_i = 0
    best_score = -1
    # 上位N件のみチェックして速度を確保
    for i, link in enumerate(pdf_links[:8]):
        try:
            pdf_bytes = download_pdf(link["url"])
            ex = extract_financials_from_pdf(pdf_bytes, quarter=quarter)
            score = 0
            if ex.get("sales") is not None:
                score += 2
            if ex.get("orders") is not None:
                score += 2
            if ex.get("backlog") is not None:
                score += 1
            # ターゲット年がタイトルに含まれるとボーナス
            if target_str in (link.get("title", "") + link.get("url", "")):
                score += 1
            if score > best_score:
                best_score = score
                best_i = i
        except Exception:
            continue

    return best_i


def download_pdf(url: str) -> bytes:
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        res.raise_for_status()
        return res.content
    except Exception as e:
        raise RuntimeError(f"PDFのダウンロードに失敗しました: {e}")


def _clean_num(text: str):
    text = re.sub(r"[,，\s　]", "", str(text))
    text = text.replace("△", "-").replace("▲", "-")
    try:
        v = float(text)
        return v if v != 0 else None
    except ValueError:
        return None


# 金額単位を百万円に換算する乗数（千円→0.001、億円→100、百万円→1）
_UNIT_DECL_MILLION = re.compile(r"単位[：: ]*百万円|[（(]\s*百万円\s*[）)]")
_UNIT_DECL_THOUSAND = re.compile(r"単位[：: ]*千円|[（(]\s*千円\s*[）)]")
_UNIT_DECL_OKU = re.compile(r"単位[：: ]*億円|[（(]\s*億円\s*[）)]")


def _unit_scale(text) -> float | None:
    """
    テキスト中の「単位宣言」から、金額を百万円に換算する乗数を返す。不明ならNone。
    本文の金額表記（例:「9百万円」）に誤反応しないよう、（単位：〇〇）や（〇〇）の
    宣言パターンだけを見る。
    """
    if not text:
        return None
    t = str(text)
    if _UNIT_DECL_MILLION.search(t):
        return 1.0
    if _UNIT_DECL_THOUSAND.search(t):
        return 0.001
    if _UNIT_DECL_OKU.search(t):
        return 100.0
    return None


def _tables_text(tables) -> str:
    """テーブル群の全セルを1つの文字列に連結（単位宣言の検出用）。"""
    out = []
    for table in tables or []:
        for row in table or []:
            for c in row:
                if c:
                    out.append(str(c))
    return " ".join(out)


def _from_table(tables: list, keywords: list[str], prefer_single_q: bool = False,
                default_scale: float = 1.0) -> float | None:
    """
    テーブルから値を取得する（戻り値は百万円に換算済み）。
    キーワードが先頭セルにある行の2番目のセル（今期値）を優先的に返す。
    prefer_single_q=True のとき、ヘッダで当Q列を探して優先する。
    default_scale: その表から単位宣言を検出できなかった場合に使う換算乗数。
    """
    for table in tables:
        if not table:
            continue

        # この表の単位（無ければ呼び出し側の既定スケール）
        scale = _unit_scale(_tables_text([table]))
        if scale is None:
            scale = default_scale

        # 当Q列インデックスを探す
        single_q_col = None
        if prefer_single_q and table:
            header = [str(c or "") for c in table[0]]
            for ci, cell in enumerate(header):
                if any(kw in cell for kw in SINGLE_Q_KEYWORDS):
                    single_q_col = ci
                    break

        for row in table:
            if not row:
                continue
            cells = [str(c or "").strip() for c in row]

            # キーワードが先頭セルにある場合
            # 決算短信の標準フォーマット: [ラベル, 前期Q, 当期Q, 増減率]
            # → index=2 が当期Q値
            if cells and any(kw in cells[0] for kw in keywords):
                # 当Q列ヘッダが特定されていればそこを優先
                if single_q_col and single_q_col < len(cells):
                    v = _clean_num(cells[single_q_col])
                    if v is not None and abs(v) > 10:
                        return v * scale
                # index=2（当期Q）を優先、なければindex=1
                for idx in [2, 1]:
                    if len(cells) > idx:
                        v = _clean_num(cells[idx])
                        if v is not None and abs(v) > 10:
                            return v * scale
                # それでも取れなければ、行内の他のセルを順にチェック
                for idx, cell in enumerate(cells[1:], start=1):
                    v = _clean_num(cell)
                    if v is not None and abs(v) > 10:
                        return v * scale

            # キーワードが行のどこかにある場合（フォールバック）
            elif any(any(kw in c for kw in keywords) for c in cells):
                for ci, cell in enumerate(cells):
                    if any(kw in cell for kw in keywords):
                        for ni in range(ci + 1, len(cells)):
                            v = _clean_num(cells[ni])
                            if v is not None and abs(v) > 10:
                                return v * scale

    return None


def _from_text_amount(lines: list[str], keywords: list[str],
                      default_scale: float = 1.0) -> float | None:
    """
    テキスト行からキーワードに続く金額を抽出する（戻り値は百万円に換算済み）。
    行内にキーワードが含まれ、キーワードの後ろに続く数値を返す。
    default_scale: 金額を百万円へ換算する乗数（呼び出し側でページ単位から算出）。
    """
    for line in lines:
        text = str(line or "").strip()
        if not text:
            continue
        for kw in keywords:
            if kw not in text:
                continue
            suffix = text.split(kw, 1)[1]
            m = re.search(r"([-−△▲]?[\d,，]+(?:\.\d+)?)", suffix)
            if m:
                v = _clean_num(m.group(1))
                if v is not None and abs(v) > 10:
                    return v * default_scale
            # それでも取れなければ行全体から最初の数値を探す
            m = re.search(r"([-−△▲]?[\d,，]+(?:\.\d+)?)", text)
            if m:
                v = _clean_num(m.group(1))
                if v is not None and abs(v) > 10:
                    return v * default_scale
    return None


def _from_text_inline(lines: list[str], keywords: list[str]) -> float | None:
    """
    テキスト行からキーワードに続く金額を抽出し、セグメント合計を返す。

    対応フォーマット（百万円に統一して合算）:
      ① 「受注残高は1,134億76百万円」  → 113,400 + 76 = 113,476
      ② 「受注残高は1,038.78億円」     → 103,878
      ③ 「受注残高は50,916百万円」      → 50,916
    """
    # ① X億Y百万円（例: 1,134億76百万円）
    pat1 = re.compile(
        r"(?:" + "|".join(re.escape(k) for k in keywords) + r")"
        r"[はは：:が]?"
        r"([\d,，]+)億([\d,，]+(?:\.\d+)?)百万円"
    )
    # ② X.XX億円（例: 1,038.78億円）
    pat2 = re.compile(
        r"(?:" + "|".join(re.escape(k) for k in keywords) + r")"
        r"[はは：:が]?"
        r"([\d,，]+(?:\.\d+)?)億円"
    )
    # ③ X百万円（例: 50,916百万円）
    pat3 = re.compile(
        r"(?:" + "|".join(re.escape(k) for k in keywords) + r")"
        r"[はは：:が]?"
        r"([\d,，]+(?:\.\d+)?)百万円"
    )

    total = 0.0
    found = False
    full_text = "\n".join(lines)

    for m in pat1.finditer(full_text):
        oku  = _clean_num(m.group(1))  # 億の部分
        hyak = _clean_num(m.group(2))  # 百万の部分
        if oku is not None:
            total += oku * 100 + (hyak or 0)
            found = True

    if not found:
        for m in pat2.finditer(full_text):
            v = _clean_num(m.group(1))
            if v is not None:
                total += v * 100
                found = True

    if not found:
        for m in pat3.finditer(full_text):
            v = _clean_num(m.group(1))
            if v is not None:
                total += v
                found = True

    return round(total) if found else None


def _from_section_table(pages_data: list[dict], keywords: list[str],
                        end_keywords: list[str] = None,
                        default_scale: float = 1.0) -> float | None:
    """
    タツモ型：テキスト内の見出し（「1. 受注高」など）から次の見出しまでのセクションを切り出し、
    その中の「合計」行の当期値（2番目の数値）を返す（戻り値は百万円に換算済み）。

    例: 「受注高\n...合計 4,430,568 16,058,967 362.5\n受注残高\n...」
    → 受注高セクションの合計行から 16,058,967 を取得

    pages_data: [{"text": ページテキスト, "tables": [テーブルリスト]}, ...]
    end_keywords: セクション終端を示すキーワード（省略時はページ末尾まで）
    default_scale: セクションから単位宣言を検出できない場合の換算乗数。
    """
    full_text = "\n".join(p["text"] for p in pages_data)

    # セクション開始位置（最初に出現するキーワード）
    start_pos = -1
    for kw in keywords:
        p = full_text.find(kw)
        if p != -1 and (start_pos == -1 or p < start_pos):
            start_pos = p
    if start_pos == -1:
        return None

    # セクション終了位置（次の見出しキーワード）
    end_pos = len(full_text)
    if end_keywords:
        for kw in end_keywords:
            p = full_text.find(kw, start_pos + 1)
            if p != -1 and p < end_pos:
                end_pos = p

    section = full_text[start_pos:end_pos]
    # このセクションの単位（無ければ既定スケール）
    scale = _unit_scale(section)
    if scale is None:
        scale = default_scale

    # 「合計」行から当期値を抽出（カンマ区切りの数値列）
    for line in section.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("合計"):
            continue
        nums = re.findall(r"[\d,]+(?:\.\d+)?", stripped)
        vals = []
        for n in nums:
            try:
                v = float(n.replace(",", ""))
                if v > 100:  # 前年比（%）などの小さい値を除外
                    vals.append(v)
            except ValueError:
                pass
        if len(vals) >= 2:
            return vals[1] * scale  # index=1が当期値（index=0は前期値）

    return None


# AI抽出で優先的に読ませたいページのキーワード（受注状況は短信の末尾ページに
# あることが多く、先頭から切ると欠落するため、該当ページを前方に寄せる）
_AI_PRIORITY_KW = ["受注残", "受注高", "受注状況", "生産、受注", "売上高",
                   "四半期連結損益計算書", "連結損益計算書", "経営成績", "販売実績"]


_FISCAL_YEAR_PAT = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月期")
_QUARTER_PAT = re.compile(r"第\s*([1-4１-４一二三四])\s*四半期")
_ZEN_NUM = {"１": "1", "２": "2", "３": "3", "４": "4",
            "一": "1", "二": "2", "三": "3", "四": "4"}


def collect_financials(links, targets, api_key=None, company_name=""):
    """指定期間(targets=[(fy,q),...])の売上高・受注高・受注残高(累計)を一括取得する。

    URL名の四半期表記に頼らず、**各PDFの中身から期・Qを判定**して該当スロットに割り当てる。
    これにより、ファイル名が日付だけの短信（例: 20250212kessantan.pdf）でも正しく対応づく。
    返り値: {(fy,q): {"sales","orders","backlog"}}（累計・百万円）
    """
    import re as _re
    want = set(targets)
    fys = [fy for fy, _ in targets] or [0]
    lo, hi = min(fys) - 1, max(fys) + 1
    out, seen = {}, set()
    for link in (links or []):
        if len(out) >= len(want):
            break
        url = link.get("url", "")
        if not url.lower().endswith(".pdf") or url in seen:
            continue
        # URLに年があれば範囲でざっくり絞る（無ければ通す）
        ym = _re.search(r"(20\d\d)", url)
        if ym and not (lo <= int(ym.group(1)) <= hi + 1):
            continue
        seen.add(url)
        try:
            b = download_pdf(url)
            fy, q = detect_fiscal_period_from_pdf(b)
            if fy is None or q is None or (fy, q) not in want or (fy, q) in out:
                continue
            ex = extract_financials_from_pdf(
                b, quarter=q, api_key=api_key, company_name=company_name)
            if any(ex.get(k) is not None for k in ("sales", "orders", "backlog")):
                out[(fy, q)] = ex
        except Exception:
            continue
    return out


def detect_fiscal_period_from_pdf(pdf_bytes: bytes):
    """
    決算短信PDFの**タイトル行**から (期, Q) を推定する。
    - 期(fiscal_year) = 「20XX年M月期」のXX（期末のカレンダー年）
    - Q = タイトルの「第N四半期」→N。タイトルに四半期表記が無ければ通期とみなしQ=4。
    本文の配当欄「第N四半期末」や業績予想欄「第2四半期（累計）」に誤反応しないよう、
    Q判定は**タイトル行のみ**を見る。判定できない項目は None。
    """
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:2]:
                text += (page.extract_text() or "") + "\n"
    except Exception:
        return None, None

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    title_line = next((ln for ln in lines
                       if "決算短信" in ln or "四半期報告" in ln), "")
    fy_line = next((ln for ln in lines if "月期" in ln), "")

    fy = None
    m = _FISCAL_YEAR_PAT.search(fy_line) or _FISCAL_YEAR_PAT.search(text)
    if m:
        fy = int(m.group(1))

    q = None
    mq = _QUARTER_PAT.search(title_line)
    if mq:
        q = int(_ZEN_NUM.get(mq.group(1), mq.group(1)))
    elif title_line:
        # タイトルに四半期表記が無い＝通期決算短信
        q = 4

    return fy, q


def _table_caption(page, bbox) -> str:
    """表の直上（約48pt）にある見出し行を返す。
    例: '③受注残高（単位：百万円）'。見出しが表の外にある様式で、
    その表が何の表か（受注高/受注残高/売上高）をAIが判断できるようにする。
    銘柄ごとに様式が違うため、決め打ちせず"直上の行"を汎用的に拾う。
    """
    try:
        x0, top, x1, bottom = bbox
        band_top = max(0, top - 48)
        if top - band_top < 2:
            return ""
        region = page.within_bbox((0, band_top, page.width, top))
        cap = (region.extract_text() or "").strip()
    except Exception:
        return ""
    lines = [l.strip() for l in cap.split("\n") if l.strip()]
    return " ".join(lines[-2:]) if lines else ""


def _decode_cid_digits(cell) -> str:
    """壊れた埋め込みフォント（ToUnicode無し）の (cid:N) を数字に復号する。
    多くの日本の決算短信PDFで、数字グリフが (cid:19)〜(cid:28)＝0〜9、(cid:15)＝',' に対応する。
    日本語ラベルは復号できないが、数値だけは確実に取れる。
    """
    def rep(m):
        n = int(m.group(1))
        if 19 <= n <= 28:
            return str(n - 19)
        if n == 15:
            return ","
        return ""
    return re.sub(r"\(cid:(\d+)\)", rep, str(cell or ""))


def _looks_cid_broken(pages_data: list[dict]) -> bool:
    """本文が (cid:...) だらけ＝フォント破損で通常のテキスト抽出が効かないPDFか判定。"""
    joined = "".join((p.get("text") or "") for p in pages_data)
    if not joined:
        return False
    return joined.count("(cid:") >= 50


def _extract_broken_font(pages_data: list[dict]):
    """壊れフォントの短信『補足情報（受注高・売上高・受注残高）』を構造で抽出。
    各表は「セグメント3行＋合計行 × 前期/当期2列」。合計行(最終行)の当期(右端)を数字デコードで取る。
    短信の記載順『受注高→売上高→受注残高』を前提に3値を返す（百万円）。
    """
    for p in pages_data:
        seg_totals = []
        for table in (p.get("tables") or []):
            if not table or len(table) < 3:
                continue
            nums = []
            for c in table[-1]:  # 最終行＝合計行
                for m in re.findall(r"\d[\d,]*", _decode_cid_digits(c)):
                    v = m.replace(",", "")
                    if v.isdigit():
                        nums.append(int(v))
            # 合計行が「前期・当期」の2つの大きな数値＝補足のセグメント合計表
            if len(nums) >= 2 and nums[-1] >= 1000 and nums[-2] >= 1000:
                seg_totals.append(nums[-1])  # 当期（右端）
        if len(seg_totals) >= 3:
            return {"orders": seg_totals[0], "sales": seg_totals[1],
                    "backlog": seg_totals[2]}
    return None


def _from_captioned_table(pages_data: list[dict], caption_kw: str,
                          default_scale: float = 1.0):
    """見出し（キャプション）で表を特定し、『合計/計』行 ×『当期』列の値を返す（百万円）。
    AI無し（残高ゼロ）でも、日本製鋼所型のセグメント別短表を確定的に取るための本命。

    caption_kw: 表の見出しに含まれる語（'受注高' / '売上高' / '受注残高'）。
      ※'受注高'は'受注残高'に部分一致しない（間に'残'が入る）ので取り違えない。
    """
    for p in pages_data:
        caps = p.get("captions") or []
        for ti, table in enumerate(p.get("tables") or []):
            cap = caps[ti] if ti < len(caps) else ""
            if not cap or caption_kw not in cap or not table:
                continue
            # 単位：見出し → ページ → 既定
            scale = _unit_scale(cap) or p.get("scale") or default_scale or 1.0
            # 『当期』列のインデックスを見出し行から特定（当第N四半期/当中間/当連結会計期間等）
            col_idx = None
            header = table[0] if table else []
            for ci, cell in enumerate(header):
                s = str(cell or "")
                if "当" in s and any(k in s for k in ("期", "四半期", "中間", "年", "会計")):
                    col_idx = ci
            # 『合計/計』行を探す
            for row in table:
                first = str(row[0] or "").replace(" ", "").replace("　", "")
                if not (first in ("合計", "計") or first.startswith("合計")):
                    continue
                row_nums = [n for cell in row for n in _parse_nums(cell)]
                if col_idx is not None and col_idx < len(row):
                    # 当期列が見出しで特定できた表（前/当の2列表）＝本命
                    nums = _parse_nums(row[col_idx])
                    if nums:
                        return nums[0] * scale
                elif len(row_nums) == 1:
                    # 数値が1つだけ（当期のみの表）なら取り違えの恐れなし
                    return row_nums[0] * scale
                # それ以外（当期列を特定できず数値が複数）は取り違えの恐れがあるので
                # この表は採用せず次の候補表へ（例: 報告セグメント別P/L表を誤採用しない）
                break
    return None


def _from_orders_results_table(pages_data: list[dict], want: str,
                               default_scale: float = 1.0):
    """『受注実績』表から『合計/計』行の該当列を返す（百万円）。

    受注高と受注残高が**同じ表の別々の列**に並ぶ様式（アドテック型など、
    表の見出しが『受注実績』で受注高/受注残高がキャプションでなく列見出しになる短信）に対応。
    _from_captioned_table は『受注高』というキャプションの表を探すため、この様式では空振りする。

    want: 'orders'（受注高列）/ 'backlog'（受注残高列）。
      受注高列は '受注高' を含み '受注残高' を含まない列で一意に特定でき、
      受注残高列は '受注残高' を含む列で一意に特定できる（'受注高'は'受注残高'に部分一致しない）。
    単位は列見出し（例:『受注高（百万円）』『受注高（千円）』）→ ページ → 既定の順で判定。
    """
    for p in pages_data:
        for table in (p.get("tables") or []):
            if not table:
                continue
            # 受注高・受注残高の両方を列見出しに持つ表だけを対象にする（受注実績表の特定）
            hdr = None
            for row in table[:3]:
                cells = [str(c or "") for c in row]
                if any("受注高" in c for c in cells) and any("受注残高" in c for c in cells):
                    hdr = cells
                    break
            if hdr is None:
                continue
            if want == "backlog":
                col = next((i for i, c in enumerate(hdr) if "受注残高" in c), None)
            else:
                col = next((i for i, c in enumerate(hdr)
                            if "受注高" in c and "受注残高" not in c), None)
            if col is None:
                continue
            scale = _unit_scale(hdr[col]) or p.get("scale") or default_scale or 1.0
            for row in table:
                first = str(row[0] or "").replace(" ", "").replace("　", "")
                if first in ("合計", "計") or first.startswith("合計"):
                    nums = _parse_nums(str(row[col] or "")) if col < len(row) else []
                    if nums:
                        return nums[0] * scale
                    break  # 合計行はあったが数値が取れない → この表は諦め次の表へ
    return None


def _pages_to_text(pages_data: list[dict], prioritize: bool = True) -> str:
    """
    AI抽出用に、本文テキスト＋テーブル（'|'区切り行）を連結して返す。
    prioritize=True のとき、受注・売上に関するキーワードを多く含むページを前方に並べ替え、
    末尾での切り捨て（トークン制限）で受注状況が欠落するのを防ぐ。
    """
    rendered = []
    for pi, p in enumerate(pages_data):
        chunk = [f"--- p{pi+1} ---", p.get("text", "")]
        caps = p.get("captions") or []
        for ti, table in enumerate(p.get("tables", []) or []):
            cap = caps[ti] if ti < len(caps) else ""
            if cap:
                # 表が何の表かを示す直上見出し（例: ③受注残高）を表に貼り付ける
                chunk.append(f"[この表の見出し] {cap}")
            for row in table:
                cells = [str(c or "").strip() for c in row]
                if any(cells):
                    chunk.append(" | ".join(cells))
        rendered.append("\n".join(chunk))

    if prioritize:
        # キーワード出現数が多いページほど前に（同数は元の順序を維持＝安定ソート）
        order = sorted(range(len(rendered)),
                       key=lambda i: -sum(rendered[i].count(k)
                                          for k in _AI_PRIORITY_KW))
        rendered = [rendered[i] for i in order]

    return "\n\n".join(rendered)


def extract_financials_from_pdf(pdf_bytes: bytes, quarter: int = None,
                                api_key: str = None,
                                company_name: str = "") -> dict:
    """
    PDFから売上高・受注高（累計）・受注残高（期末）を抽出する（単位: 百万円）。

    api_key が指定された場合は **AI（Claude）で本文全体を読んで抽出** し、
    AIが取れなかった項目だけ従来の正規表現抽出でフォールバックする。
    api_key が無い環境では従来通り正規表現のみで抽出する。
    """
    result = {
        "sales": None, "orders": None, "backlog": None,
        "pages_tried": 0, "note": "", "source": "regex",
    }
    pages_data = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        result["pages_tried"] = len(pdf.pages)
        all_lines = []
        all_tables = []
        # 受注状況（受注高・受注残高）は決算短信の末尾ページに載ることが多い。
        # 訂正版は表紙が付いてページ数が増える（例: タツモ訂正版26p、受注状況は26p目）ため、
        # ここを25pで切ると受注が丸ごと欠落する。十分な上限にする。
        for page in pdf.pages[:MAX_EXTRACT_PAGES]:
            text = page.extract_text() or ""
            # find_tables で表オブジェクトを取り、各表の直上見出し(caption)も拾う。
            # 見出しが表の外にある様式（例: ③受注残高）でも表の種別が分かるようにする。
            tables, captions = [], []
            try:
                for t in (page.find_tables() or []):
                    rows = t.extract()
                    if rows:
                        tables.append(rows)
                        captions.append(_table_caption(page, t.bbox))
            except Exception:
                tables = page.extract_tables() or []
                captions = [""] * len(tables)
            all_lines.extend(text.split("\n"))
            all_tables.extend(tables)
            pages_data.append({"text": text, "tables": tables, "captions": captions})

    # 各ページの単位スケール（百万円への乗数）を事前計算。
    # ページ本文の単位宣言（（単位：千円）等）→ 無ければその表のセルから検出。
    for p in pages_data:
        p["scale"] = (_unit_scale(p["text"])
                      or _unit_scale(_tables_text(p["tables"])))
    # 文書全体の既定スケール（最初に単位宣言が見つかったページのもの）
    doc_scale = next((p["scale"] for p in pages_data if p["scale"]), 1.0)

    # ── 正規表現抽出（単位換算込み。AI併用時はフォールバックとして使う） ──
    # ページ単位で単位を判定して百万円に正規化する（会社ごとの千円/百万円表記に対応）。
    # 探索順は「全ページの表 → 本文 → セクション合計」。本文（定性情報）を先に見ると
    # 「売上高は354億…」等の narrative を誤って拾うため、必ず表を優先する。
    def _tables_scan(keywords):
        for p in pages_data:
            ds = p["scale"] or doc_scale
            v = _from_table(p["tables"], keywords, False, default_scale=ds)
            if v is not None:
                return v
        return None

    def _text_scan(keywords):
        for p in pages_data:
            ds = p["scale"] or doc_scale
            v = _from_text_amount(p["text"].split("\n"), keywords, default_scale=ds)
            if v is not None:
                return v
        return None

    def _regex_sales():
        # 見出し付き表（（２）売上高 → 合計×当期）を最優先。無ければ従来経路。
        v = _from_captioned_table(pages_data, "売上高", doc_scale)
        if v is not None:
            return v
        v = _tables_scan(SALES_KEYWORDS)
        return v if v is not None else _text_scan(SALES_KEYWORDS)

    def _regex_orders():
        # 『受注実績』表（受注高・受注残高が同一表の別列）を最優先。アドテック型はこれで確定。
        v = _from_orders_results_table(pages_data, "orders", doc_scale)
        if v is not None:
            return v
        # 見出し付き表（（１）受注高 → 合計×当期）。日本製鋼所型はこれで確定。
        v = _from_captioned_table(pages_data, "受注高", doc_scale)
        if v is not None:
            return v
        v = _tables_scan(ORDERS_KEYWORDS)
        if v is None:
            v = _text_scan(ORDERS_KEYWORDS)
        if v is None:
            v = _from_section_table(pages_data, ORDERS_KEYWORDS,
                                    end_keywords=BACKLOG_KEYWORDS,
                                    default_scale=doc_scale)
        return v

    def _regex_backlog():
        # 『受注実績』表（受注高・受注残高が同一表の別列）を最優先。アドテック型はこれで確定。
        v = _from_orders_results_table(pages_data, "backlog", doc_scale)
        if v is not None:
            return v
        # 見出し付き表（（３）受注残高 → 合計×当期）。
        v = _from_captioned_table(pages_data, "受注残高", doc_scale)
        if v is not None:
            return v
        v = _from_text_inline(all_lines, BACKLOG_KEYWORDS)  # 既に百万円換算済み
        if v is None:
            v = _tables_scan(BACKLOG_KEYWORDS)
        if v is None:
            v = _from_section_table(pages_data, BACKLOG_KEYWORDS,
                                    default_scale=doc_scale)
        return v

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

    # ── 正規表現フォールバック ──
    # AI成功時は「AIが取れなかった＝資料に無い」とみなし、正規表現の生値では埋めない。
    # （正規表現は単位換算しないため、AIの百万円値と混ざると桁が1000倍ずれる。
    #   取れない項目はNoneのままにして手動入力を促す方が安全。）
    # AIを使わない（キー無し）場合のみ、従来どおり正規表現で抽出する。
    if not ai_ok:
        if result["sales"] is None:
            result["sales"] = _regex_sales()
        if result["orders"] is None:
            result["orders"] = _regex_orders()
        if result["backlog"] is None:
            result["backlog"] = _regex_backlog()

    # ── 壊れフォント（(cid:...)だらけ）で何も取れない短信の救済 ──
    # 数字グリフを復号し、補足情報の3表（受注高/売上高/受注残高）を構造で取る。
    if (result["sales"] is None and result["orders"] is None
            and result["backlog"] is None and _looks_cid_broken(pages_data)):
        bf = _extract_broken_font(pages_data)
        if bf:
            result["sales"] = bf["sales"]
            result["orders"] = bf["orders"]
            result["backlog"] = bf["backlog"]
            result["source"] = "cid_decode"
            result["note"] = "壊れフォントを数字デコードで抽出（補足情報の合計×当期）"

    if not result["note"]:
        result["note"] = "累計値を抽出（Q2以降は呼び出し側で単独Q換算）"
    return result


# ──────────────────────────────────────────────
# 短信サマリー（最新Q連結業績・通期予想）の抽出
# ──────────────────────────────────────────────

def _parse_nums(cell) -> list:
    """セル文字列から数値リストを返す。△/▲は負、カンマ除去。
    例: '百万円 191,631 187,726' → [191631.0, 187726.0]
        '％ △29.1 1.7'           → [-29.1, 1.7]
    """
    s = str(cell or "").replace("△", "-").replace("▲", "-")
    s = s.replace(",", "").replace("，", "")
    return [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", s)]


def latest_tanshin_pdf(pdf_links: list[dict]) -> dict | None:
    """提出日（URLの日付）が最も新しい決算短信PDFを返す（Q&A等は除外）。"""
    cand = [l for l in pdf_links if not _is_excluded(l)]
    if not cand:
        return None
    def key(l):
        m = _DATE_PAT.search(l["url"])
        if m:
            return int(m.group(1) + m.group(2) + m.group(3))
        m2 = _WP_DATE_PAT.search(l["url"])
        if m2:
            return int(m2.group(1) + m2.group(2) + "01")
        return 0
    return max(cand, key=key)


def extract_summary_from_pdf(pdf_bytes: bytes) -> dict:
    """
    決算短信1ページ目のサマリーから、最新Q連結業績と通期予想を抽出する。
    """
    result = {"quarter": {}, "forecast": {},
              "period_label": "", "forecast_label": ""}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        tables = []
        for page in pdf.pages[:2]:
            tables.extend(page.extract_tables() or [])

    for t in tables:
        if not t or len(t) < 2:
            continue
        header = [str(c or "") for c in t[0]]
        if not (any("売上高" in h for h in header) and
                any("営業利益" in h for h in header)):
            continue

        colmap = {}
        for i, h in enumerate(header):
            if "売上高" in h:
                colmap["sales"] = i
            elif "営業利益" in h:
                colmap["op"] = i
            elif "経常利益" in h:
                colmap["ord"] = i
            elif ("１株" in h or "1株" in h) and "利益" in h:
                colmap["eps"] = i
            elif "純利益" in h:
                colmap["net"] = i

        for row in t[1:]:
            label = str(row[0] or "").strip()
            if not label:
                continue
            vals = {}
            for key, ci in colmap.items():
                nums = _parse_nums(row[ci]) if ci < len(row) else []
                vals[key] = nums[0] if nums else None
                if key != "eps":
                    pn = _parse_nums(row[ci + 1]) if ci + 1 < len(row) else []
                    vals[key + "_pct"] = pn[0] if pn else None

            if "通期" in label or "予想" in label:
                result["forecast"] = vals
                result["forecast_label"] = label
            elif "四半期" in label:
                if not result["quarter"]:
                    result["quarter"] = vals
                    result["period_label"] = label.split()[0] if label.split() else label

    return result


# ──────────────────────────────────────────────
# 決算説明資料からセグメント別（品目別）受注高・売上高を抽出
# ──────────────────────────────────────────────

SEGMENT_NAMES = [
    "半導体及び電子部品製造装置",
    "ディスプレイ・エネルギー関連製造装置",
    "一般産業用装置",
    "コンポーネント",
    "マテリアル",
    "その他",
]


def _parse_fy_q_from_url(url: str):
    """説明資料ファイル名から (年度, Q) を推定。例: '26.06Q3...' → (2026, 3)"""
    m = re.search(r"(\d{2})\.\d{2}Q(\d)", url)
    if m:
        return 2000 + int(m.group(1)), int(m.group(2))
    m = re.search(r"Q(\d)[_%\s0-9]*FY(\d{4})", url, re.IGNORECASE)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"FY(\d{4})", url, re.IGNORECASE)
    if m:
        return int(m.group(1)), 4
    return None, None


def latest_presentation_pdf(pdf_links: list[dict]) -> dict | None:
    """最新の決算説明資料（Presentation）PDFを返す。Script/QA等は除外。"""
    best, best_key = None, (-1, -1)
    skip_kw = ["script", "scripts", "qa", "q&a", "質疑", "原稿"]
    for l in pdf_links:
        u = l["url"].lower()
        t = l["title"]
        if "presentation" not in u and "資料" not in t and "material" not in u:
            continue
        if any(k in u for k in skip_kw):
            continue
        fy, q = _parse_fy_q_from_url(l["url"])
        if fy is None:
            continue
        if (fy, q) > best_key:
            best_key, best = (fy, q), l
    return best


def fetch_product_categories(ir_url: str, product_url: str = "") -> dict:
    """
    会社サイトの製品/事業ページから取扱製品カテゴリを列挙する。
    """
    from urllib.parse import urljoin, urlparse

    hub = product_url.strip() if product_url else None

    if not hub:
        res = requests.get(ir_url, headers=HEADERS, timeout=20)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")

        HUB_PATTERNS = [("/business/", ["事業領域", "事業", "business"]),
                        ("/products/", ["製品", "product"])]
        for path, kws in HUB_PATTERNS:
            for a in soup.find_all("a", href=True):
                full = urljoin(ir_url, a["href"])
                text = a.get_text(strip=True)
                if path in full and (full.rstrip("/").endswith(path.rstrip("/"))
                                     or any(k in (text + full).lower() or k in text for k in kws)):
                    hub = full
                    break
            if hub:
                break

    if not hub:
        return {"source": "", "items": []}

    hres = requests.get(hub, headers=HEADERS, timeout=20)
    hres.encoding = hres.apparent_encoding
    hsoup = BeautifulSoup(hres.text, "html.parser")
    base_dir = "/" + urlparse(hub).path.strip("/").split("/")[0]

    def _clean_path(u):
        p = urlparse(u).path
        p = re.sub(r"/index\.html?$", "", p, flags=re.IGNORECASE)
        return p.rstrip("/")

    hub_path = _clean_path(hub)
    items, seen = [], set()
    SKIP_NAME = ["page top", "ページトップ", "検索", "search", "日", "en",
                 "事業領域", "製品紹介", "トップ"]
    for a in hsoup.find_all("a", href=True):
        full = urljoin(hub, a["href"])
        name = a.get_text(strip=True)
        if not name or len(name) < 2:
            continue
        if "#" in a["href"]:
            continue
        cpath = _clean_path(full)
        if not cpath.startswith(base_dir + "/") or cpath == hub_path:
            continue
        rel = cpath[len(base_dir) + 1:]
        if "/" in rel:
            continue
        if any(s == name.lower() or s in name for s in SKIP_NAME):
            continue
        if name in seen:
            continue
        seen.add(name)
        items.append({"name": name, "url": full})

    return {"source": hub, "items": items}


def extract_presentation_text(pdf_bytes: bytes, max_pages: int = 15) -> str:
    """決算説明資料の本文テキストを連結して返す（AI分析の材料用）。"""
    parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pi, page in enumerate(pdf.pages[:max_pages]):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(f"--- p{pi+1} ---\n{text}")
    return "\n\n".join(parts)


def extract_order_commentary(pdf_bytes: bytes) -> dict:
    """
    決算説明資料の見出しコメントから、受注高・売上高の増加要因の文を抽出する。
    """
    SEG_HINT = ["半導体", "ディスプレイ", "一般産業", "コンポーネント",
                "マテリアル", "レアアース", "電子部品"]
    FACTOR_HINT = ["増加", "伸長", "好調", "拡大", "牽引", "最高", "構成比",
                   "増", "上方修正", "回復"]

    found = {"orders": [], "sales": []}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:12]:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                for key, head in [("orders", "受注高"), ("sales", "売上高")]:
                    m = re.match(rf"{head}\s*[：:]\s*(.+)", line)
                    if not m:
                        continue
                    body = m.group(1).strip()
                    if not any(f in body for f in FACTOR_HINT):
                        continue
                    if body in found[key]:
                        continue
                    found[key].append(body)

    for key in found:
        found[key].sort(key=lambda s: (0 if any(h in s for h in SEG_HINT) else 1))
    return found


def extract_segments_from_presentation(pdf_bytes: bytes,
                                       orders_total: float,
                                       sales_total: float,
                                       tol: float = 3) -> dict:
    """
    決算説明資料の積み上げグラフから受注高・売上高のセグメント別内訳を抽出する。
    """
    out = {"orders": None, "sales": None}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    for cell in row:
                        nums = _parse_nums(cell)
                        if len(nums) != 7:
                            continue
                        total, segs = nums[0], nums[1:]
                        if abs(sum(segs) - total) > tol:
                            continue
                        mapped = dict(zip(SEGMENT_NAMES, list(reversed(segs))))
                        if orders_total and abs(total - orders_total) <= tol \
                                and out["orders"] is None:
                            out["orders"] = mapped
                        elif sales_total and abs(total - sales_total) <= tol \
                                and out["sales"] is None:
                            out["sales"] = mapped
    return out

"""
決算短信 収集アプリ（IRBANK方式・証券コードを入れるだけ）
────────────────────────────────────────────────────────
証券コードを入れると、IR資料まとめサイト IRBANK（irbank.net）を参照して
2022期1Q〜最新Qまでの決算短信PDFを見つけ、コード別フォルダに保存する。

・IRページのURLを探して貼る必要は無い（コードだけでOK）。
・数値の抽出はしない（＝桁ズレ等の失敗要因が無い）。見つけて保存するだけ。
・タイトルから期・Qを判定して {期}_Q{n}.pdf で保存。
・取れた一覧と「欠けている期」を表示するので、抜けは手動で補える。

※IRBANK は第三者のIR資料まとめサイトです。個人利用の範囲で、過度な連続
　アクセスをしないよう、取得の間に短い待ちを入れています。

起動:  python -m streamlit run tanshin_collector.py
"""

import os
import re
import time
import unicodedata
from pathlib import Path

import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

import ir_scraper
import database

BASE_DIR = Path(__file__).parent
OUT_ROOT = BASE_DIR / "決算短信PDF"

# ★★ 保存先フォルダ（ここに入れる）★★
# ここに書いたフォルダに、銘柄ごとの短信PDFを保存します。
# フォルダを移動したときは、この1行だけ書き換えてください。
# 空文字 "" にすると、自動判定（銘柄フォルダが一番多い決算短信PDF）に戻ります。
FIXED_OUT_ROOT = r"C:\新高値ブレイク投資塾\重要フォルダ\上原@勉強会\上原さん流業績予想\業績予想アプリ\決算短信PDF"
IRBANK = "https://irbank.net"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# タイトルから期・Qを判定
_FY_PAT = re.compile(r"(20\d{2})\s*年\s*\d{1,2}\s*月期")
_Q_PAT = re.compile(r"第\s*([1-4１-４一二三四])\s*四半期")
_ZEN = {"１": "1", "２": "2", "３": "3", "４": "4",
        "一": "1", "二": "2", "三": "3", "四": "4"}
# IRBANKのTDNET書類IDリンク（1401 + 提出日時 + 連番）
_ID_PAT = r"/(1401\d{12,16})"
# 詳細ページ内のPDF実URL（f.irbank.net にホスト）
_PDF_URL_PAT = re.compile(r"https?://f\.irbank\.net/pdf/\d+/\d+\.pdf")

Q_LABEL = {1: "1Q", 2: "2Q", 3: "3Q", 4: "通期(4Q)"}


def _safe_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip() or "unknown"


def _out_root() -> Path:
    """保存先の「決算短信PDF」フォルダを決める。
    まず FIXED_OUT_ROOT（上で指定した固定フォルダ）を最優先で使う。
    それが空、または見つからない場合だけ、自動判定
    （このファイルの近くで銘柄フォルダが最も多い決算短信PDF）にする。"""
    # 1) 明示指定の固定フォルダを最優先
    if FIXED_OUT_ROOT:
        p = Path(FIXED_OUT_ROOT)
        try:
            if p.is_dir():
                return p
            if p.parent.is_dir():       # 親フォルダがあれば作ってそこに入れる
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            pass
    # 2) フォールバック：自動判定（銘柄フォルダが一番多い決算短信PDF）
    candidates = []
    for base in (BASE_DIR, BASE_DIR.parent, BASE_DIR.parent.parent):
        cand = base / "決算短信PDF"
        if cand.is_dir():
            try:
                n = sum(1 for d in cand.iterdir() if d.is_dir())
            except Exception:
                n = 0
            candidates.append((n, cand))
    if candidates:
        # 銘柄フォルダ数が最も多い候補を採用（同数なら自分に近い方＝先頭）
        candidates.sort(key=lambda t: t[0], reverse=True)
        return candidates[0][1]
    return OUT_ROOT


def _resolve_out_dir(code: str) -> Path:
    """コードの保存フォルダを返す。今まで通り『コード+会社名』にする。
    - 既にコードで始まるフォルダ（例: 6141DMG森精機）があればそれを再利用
    - 無ければ、登録DBの会社名を付けて {コード}{会社名}
    - 会社名が分からなければ {コード} のみ
    """
    root = _out_root()
    root.mkdir(parents=True, exist_ok=True)
    code = str(code)
    # 既存の「コードで始まる」フォルダを再利用（今までのフォルダにそのまま入れる）
    if root.exists():
        for d in sorted(root.iterdir()):
            if d.is_dir() and d.name.startswith(code):
                return d
    # 会社名を付けて新規（登録DBから引く）
    name = ""
    try:
        st = database.get_stock(code)
        if st and st.get("name"):
            name = st["name"]
    except Exception:
        name = ""
    folder = _safe_name(f"{code}{name}") if name else _safe_name(code)
    return root / folder


def _parse_period(title: str):
    """短信タイトルから (期, Q) を判定。四半期表記が無ければ通期＝Q4。"""
    fy = None
    m = _FY_PAT.search(title)
    if m:
        fy = int(m.group(1))
    q = None
    mq = _Q_PAT.search(title)
    if mq:
        q = int(_ZEN.get(mq.group(1), mq.group(1)))
    elif "短信" in title:
        q = 4  # 四半期表記なし＝通期決算短信
    return fy, q


def list_tanshin(code: str) -> list[dict]:
    """IRBANKの銘柄ページから、決算短信の一覧（書類ID・タイトル・期・Q）を返す。"""
    r = requests.get(f"{IRBANK}/{code}", headers=HEADERS, timeout=20)
    r.encoding = "utf-8"
    if r.status_code != 200:
        raise RuntimeError(f"IRBANKページ取得に失敗 (HTTP {r.status_code})")
    soup = BeautifulSoup(r.text, "html.parser")

    out, seen = [], set()
    id_re = re.compile(rf"/{re.escape(code)}{_ID_PAT}")
    for a in soup.find_all("a", href=True):
        m = id_re.search(a["href"])
        if not m:
            continue
        did = m.group(1)
        title = a.get_text(strip=True)
        if "短信" not in title or did in seen:
            continue
        seen.add(did)
        fy, q = _parse_period(title)
        out.append({
            "id": did, "title": title, "fy": fy, "q": q,
            "filing": did[4:12],              # YYYYMMDD（提出日）
            "corrected": "訂正" in title,
        })
    return out


def detail_pdf_url(code: str, doc_id: str) -> str | None:
    """IRBANKの書類詳細ページから、決算短信PDFの実URL(f.irbank.net)を取り出す。"""
    d = requests.get(f"{IRBANK}/{code}/{doc_id}", headers=HEADERS, timeout=20)
    d.encoding = "utf-8"
    if d.status_code != 200:
        return None
    m = _PDF_URL_PAT.search(d.text)
    return m.group(0) if m else None


def collect_tanshin(code: str, start_fy: int, progress=None) -> dict:
    """
    IRBANK経由で決算短信PDFを収集して保存する。
    返り値: {"saved":[...], "errors":[...], "no_list":bool, "n_candidates":int, "out_dir":str}
      saved 各要素: {"fy","q","title","id","filing","corrected","url","path"}
    """
    try:
        items = list_tanshin(code)
    except Exception as e:
        return {"saved": [], "errors": [f"IRBANK一覧の取得に失敗: {e}"],
                "no_list": True, "n_candidates": 0}

    # 期・Qが判定でき、開始期以降のものだけ
    items = [x for x in items if x["fy"] and x["q"] and x["fy"] >= start_fy]

    # (期,Q)ごとに最新提出（＝訂正版があればそちら）を採用
    picked: dict[tuple, dict] = {}
    for x in items:
        key = (x["fy"], x["q"])
        prev = picked.get(key)
        if prev is None or x["filing"] > prev["filing"] \
                or (x["corrected"] and not prev["corrected"]):
            picked[key] = x

    out_dir = _resolve_out_dir(code)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved, errors = [], []
    total = len(picked)
    for i, (key, x) in enumerate(sorted(picked.items())):
        if progress:
            progress(i + 1, total, f"{x['fy']}期 {Q_LABEL[x['q']]}")
        try:
            url = detail_pdf_url(code, x["id"])
            if not url:
                errors.append(f"{x['fy']}期 {Q_LABEL[x['q']]}: PDFリンクが見つからない")
                continue
            pdf_bytes = ir_scraper.download_pdf(url)
        except Exception as e:
            errors.append(f"{x['fy']}期 {Q_LABEL[x['q']]}: 取得失敗 → {e}")
            continue

        suffix = "_訂正" if x["corrected"] else ""
        fname = f"{x['fy']}_Q{x['q']}{suffix}.pdf"
        path = out_dir / fname
        try:
            path.write_bytes(pdf_bytes)
            saved.append({**x, "url": url, "path": str(path)})
        except Exception as e:
            errors.append(f"保存失敗: {fname} → {e}")
        time.sleep(0.3)  # IRBANKへの礼儀（連続アクセスを避ける）

    return {"saved": saved, "errors": errors, "no_list": False,
            "n_candidates": total, "out_dir": str(out_dir)}


def find_gaps(saved: list[dict], start_fy: int) -> list[str]:
    """取得済みの期・Qから、start_fy〜最大期の間で欠けている(期,Q)を返す。"""
    if not saved:
        return []
    got = {(s["fy"], s["q"]) for s in saved}
    max_fy = max(fy for fy, _ in got)
    max_q_in_max_fy = max(q for fy, q in got if fy == max_fy)
    gaps = []
    for fy in range(start_fy, max_fy + 1):
        last_q = max_q_in_max_fy if fy == max_fy else 4
        for q in range(1, last_q + 1):
            if (fy, q) not in got:
                gaps.append(f"{fy}期 {Q_LABEL[q]}")
    return gaps


# ───────────── 保存済みPDFから数値抽出 → CSV ─────────────

_FNAME_PAT = re.compile(r"(\d{4})_Q([1-4])")


def _get_api_key():
    """Claude APIキー（secrets.toml [anthropic] api_key、なければ環境変数）。無ければNone。"""
    try:
        return st.secrets["anthropic"]["api_key"]
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY")


def list_saved_pdfs(code: str) -> dict:
    """保存フォルダのPDFを (期,Q) ごとに1つ返す（訂正版があれば優先）。"""
    folder = _resolve_out_dir(code)
    picked: dict[tuple, Path] = {}
    if not folder.exists():
        return picked
    for p in sorted(folder.glob("*.pdf")):
        m = _FNAME_PAT.search(p.name)
        if not m:
            continue
        key = (int(m.group(1)), int(m.group(2)))
        # 訂正版を優先。無ければ通常版。
        if key not in picked or "訂正" in p.name:
            picked[key] = p
    return picked


def summary_sales_by_year(pdf_bytes: bytes, fy: int):
    """
    決算短信1ページ目の経営成績サマリー表から、**対象年度(fy)の売上高累計**を返す（百万円）。

    サマリー表は「当期／前期」が縦（改行区切り）に並び、先頭列に年度ヘッダが入る:
        cell0 = '2026年3月期\\n2025年3月期'
        売上高セル = '百万円\\n171,765\\n159,653'
    年度ヘッダの並び順で列を選ぶので、当期/前期どちらが先でも取り違えない。
    （従来の正規表現は列位置決め打ちで、一部様式で前期値を誤取得していた）
    """
    import io as _io
    import pdfplumber as _pp
    from ir_scraper import _parse_nums, _unit_scale
    try:
        with _pp.open(_io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:2]:
                for table in (page.extract_tables() or []):
                    if not table or len(table) < 2:
                        continue
                    # 売上高（or 売上収益/営業収益）の列を見出し行から特定
                    scol = None
                    for ci, c in enumerate(table[0]):
                        s = str(c or "")
                        if "売上高" in s or "売上収益" in s or "営業収益" in s:
                            scol = ci
                            break
                    if scol is None:
                        continue
                    for row in table[1:]:
                        c0 = str(row[0] or "")
                        years = [int(m) for m in re.findall(r"(20\d{2})\s*年", c0)]
                        if fy not in years:
                            continue
                        cell = str(row[scol] or "") if scol < len(row) else ""
                        nums = _parse_nums(cell)
                        if len(nums) == len(years):   # 年数と値数が一致＝整列できる
                            scale = _unit_scale(cell) or _unit_scale(c0) or 1.0
                            return nums[years.index(fy)] * scale
    except Exception:
        return None
    return None


def _to_single(cumulative, fy, q, col, buf):
    """累計値を単独Q値に換算。Q1は累計＝単独。前Qが1つでも欠けたらNone。"""
    if cumulative is None:
        return None
    if q == 1:
        return cumulative
    prior = 0.0
    for pq in range(1, q):
        pv = buf.get((fy, pq), {}).get(col)
        if pv is None:
            return None
        prior += pv
    return cumulative - prior


def extract_to_rows(code: str, use_ai: bool, progress=None) -> list[dict]:
    """保存済みPDFから売上高・受注高（単独Q）・受注残高（期末）を抽出して行リストを返す。"""
    api_key = _get_api_key() if use_ai else None
    stock = database.get_stock(code)
    company = stock["name"] if stock else ""

    pdfs = list_saved_pdfs(code)
    buf: dict[tuple, dict] = {}   # 単独Q換算用バッファ
    rows = []
    total = len(pdfs)
    for i, (key, path) in enumerate(sorted(pdfs.items())):
        fy, q = key
        if progress:
            progress(i + 1, total, f"{fy}期 {Q_LABEL[q]}")
        try:
            pdf_bytes = path.read_bytes()
            ex = ir_scraper.extract_financials_from_pdf(
                pdf_bytes, quarter=q, api_key=api_key, company_name=company)
        except Exception as e:
            pdf_bytes = None
            ex = {"sales": None, "orders": None, "backlog": None,
                  "source": "error", "note": str(e)}

        # 売上高は「年度整列方式」を本命にする（当期/前期の取り違えを防ぐ）。
        # 取れなければ従来抽出の値にフォールバック。
        sales_cum = None
        if pdf_bytes is not None:
            sales_cum = summary_sales_by_year(pdf_bytes, fy)
        if sales_cum is None:
            sales_cum = ex.get("sales")
        elif ex.get("source") == "regex":
            ex["source"] = "regex(年度整列)"

        s_single = _to_single(sales_cum, fy, q, "sales", buf)
        o_single = _to_single(ex.get("orders"), fy, q, "orders", buf)
        buf[key] = {"sales": s_single, "orders": o_single}

        bb = round(o_single / s_single, 2) if (o_single and s_single) else None

        note = ex.get("note", "") or ""
        if ex.get("sales") is not None and s_single is None:
            note = ("前四半期が未抽出のため単独Q換算できず（累計のまま）。 " + note).strip()

        rows.append({
            "期": fy, "Q": q,
            "売上高": None if s_single is None else round(s_single),
            "受注高": None if o_single is None else round(o_single),
            "受注残高": None if ex.get("backlog") is None else round(ex["backlog"]),
            "B/Bレシオ": bb,
            "抽出元": ex.get("source", ""),
            "備考": note,
        })
    return rows


# ─────────────────────────────── UI ───────────────────────────────

st.set_page_config(page_title="決算短信 収集", page_icon="📄", layout="wide")
st.title("📄 決算短信 収集アプリ")
st.caption("証券コードを入れるだけで、2022期1Q〜最新Qの決算短信PDFを集めてコード別フォルダに保存します（数値抽出はしません）。")

database.init_db()

col1, col2 = st.columns([1, 1])
with col1:
    code = st.text_input("証券コード", value="", placeholder="例: 3569").strip()
with col2:
    start_fy = st.number_input("開始期（この期以降を収集）", min_value=2010,
                               max_value=2100, value=2022, step=1)

stock = database.get_stock(code) if code else None
if stock:
    st.info(f"登録銘柄: **{stock['name']}**")

st.caption("※ IR資料まとめサイト IRBANK（irbank.net）を参照します。個人利用の範囲でご利用ください。")

if st.button("🔍 決算短信を収集", type="primary", disabled=not code):
    bar = st.progress(0.0, text="IRBANKを検索中…")

    def _prog(i, total, label):
        bar.progress(min(i / max(total, 1), 1.0), text=f"[{i}/{total}] 取得中: {label}")

    with st.spinner("決算短信を収集しています…"):
        res = collect_tanshin(code, int(start_fy), progress=_prog)
    bar.empty()

    if res["no_list"]:
        st.error(
            "IRBANKからこの銘柄の一覧を取得できませんでした。\n\n"
            "・証券コードが正しいか確認してください（例: 3569）。\n"
            "・時間をおいて再度お試しください。"
        )
    else:
        saved = res["saved"]
        st.subheader(f"✅ 取得 {len(saved)} 件")
        if saved:
            st.caption(f"保存先フォルダ: `{res['out_dir']}`")
            rows = [{
                "期": s["fy"], "Q": Q_LABEL[s["q"]],
                "訂正": "○" if s["corrected"] else "",
                "提出日": f"{s['filing'][:4]}/{s['filing'][4:6]}/{s['filing'][6:8]}",
                "ファイル": Path(s["path"]).name,
            } for s in saved]
            st.dataframe(rows, use_container_width=True, hide_index=True)

            gaps = find_gaps(saved, int(start_fy))
            if gaps:
                st.warning("**未取得の期**： " + " / ".join(gaps))
            else:
                st.success(f"{start_fy}期〜最新期まで、抜けなく揃いました。")
        else:
            st.info(f"{start_fy}期以降の決算短信が見つかりませんでした。開始期を古くして再度お試しください。")

    if res["errors"]:
        with st.expander(f"⚠️ 警告・スキップ {len(res['errors'])} 件"):
            for e in res["errors"]:
                st.text(f"・{e}")


# ───────────── 数値抽出 → CSV ─────────────
st.divider()
st.header("📊 保存済みPDFから数値を抽出 → CSV")
st.caption("上で収集した（または過去に収集済みの）決算短信PDFから、各Qの売上高・受注高（単独Q）・"
           "受注残高（期末）を抽出します。単位は百万円。売上高・受注高は累計から単独Qに換算済み。")

if code:
    n_saved = len(list_saved_pdfs(code))
    st.caption(f"コード **{code}** の保存済みPDF: **{n_saved} 件**")

use_ai = st.checkbox(
    "AIで抽出する（精度↑・Claude API残高を消費）",
    value=False,
    help="OFFなら正規表現のみ（無料）。受注高・受注残高が取りにくい銘柄はONにすると精度が上がりますが、"
         "Anthropicの残高を消費します。",
)

if st.button("📊 保存済みPDFを解析", disabled=not code):
    if not list_saved_pdfs(code):
        st.error(f"コード {code} の保存済みPDFがありません。先に上で「決算短信を収集」してください。")
    else:
        bar2 = st.progress(0.0, text="解析中…")

        def _prog2(i, total, label):
            bar2.progress(min(i / max(total, 1), 1.0), text=f"[{i}/{total}] 解析中: {label}")

        with st.spinner("PDFから数値を抽出しています…"):
            rows = extract_to_rows(code, use_ai, progress=_prog2)
        bar2.empty()
        st.session_state["extracted_rows"] = rows
        st.session_state["extracted_code"] = code
        # AI（PDF直読み）が使われたか確認。使われていないと受注高がマイナス等になりやすい。
        if use_ai and _get_api_key() is None:
            st.error(
                "『AIで抽出する』はONですが、APIキーが見つかりません。"
                ".streamlit\\secrets.toml に api_key を設定してください。"
                "今回は正規表現で抽出したため、受注高が不正確（マイナス等）になっている場合があります。"
            )
        elif not use_ai:
            st.info(
                "『AIで抽出する』がOFFです。受注高は正規表現抽出のため不正確になりやすい"
                "（マイナス等）。精度を上げるにはONにして解析し直してください（Claude API使用）。"
            )

# 抽出結果の表示・編集・ダウンロード（再実行をまたいで保持）
if st.session_state.get("extracted_rows") and st.session_state.get("extracted_code") == code:
    st.markdown("**抽出結果（時系列は横。数値は直接編集できます。おかしい値は手で直してからDLしてください）**")
    base_df = (pd.DataFrame(st.session_state["extracted_rows"])
               .sort_values(["期", "Q"]).reset_index(drop=True))
    base_df["時期"] = base_df["期"].astype(str) + "期 " + base_df["Q"].astype(str) + "Q"

    # 欠損と、受注高マイナス（抽出ミスの疑い）をチェック
    n_miss = int(base_df[["売上高", "受注高", "受注残高"]].isna().any(axis=1).sum())
    neg_labels = base_df.loc[
        pd.to_numeric(base_df["受注高"], errors="coerce") < 0, "時期"].tolist()

    # 時系列を横に：列＝各期Q（左→右で新しく）、行＝指標
    order = base_df["時期"].tolist()
    metrics = ["売上高", "受注高", "受注残高", "B/Bレシオ"]
    tdf = base_df.set_index("時期")[metrics].T[order]

    edited = st.data_editor(tdf, use_container_width=True)

    if neg_labels:
        st.error("⚠️ 受注高がマイナスの期があります（" + " / ".join(neg_labels) + "）。"
                 "抽出ミスの可能性が高いです。『AIで抽出する』をONにして解析し直すか、"
                 "原本PDFを見て手で修正してください。")
    if n_miss:
        st.warning(f"抽出できなかった項目が {n_miss} 期分あります。表を直接編集して補ってください"
                   "（受注高・受注残高が無い会社もあります）。")

    # 抽出元・備考は横持ちに混ぜず、参考として下に表示
    with st.expander("抽出元・備考（各期の読み取り根拠）"):
        st.dataframe(base_df[["時期", "抽出元", "備考"]],
                     use_container_width=True, hide_index=True)

    csv_bytes = edited.to_csv().encode("utf-8-sig")  # 先頭列に指標名(index)を残す・BOM付き
    st.download_button(
        "📥 CSVをダウンロード（時系列・横）", csv_bytes,
        file_name=f"{code}_業績_売上受注受注残_時系列.csv", mime="text/csv",
        type="primary",
    )
    st.caption("※ 単位は百万円。売上高・受注高は単独Q、受注残高は期末残高。B/Bレシオ＝受注高÷売上高。")

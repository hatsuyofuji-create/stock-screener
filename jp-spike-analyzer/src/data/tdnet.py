# -*- coding: utf-8 -*-
"""
適時開示（TDnet）の取得と蓄積。

■ 公式ソース（日次クロール）
  JPX の TDnet 適時開示情報閲覧サービスは、日付ごとの一覧ページ
    https://www.release.tdnet.info/inbs/I_list_{page:03d}_{YYYYMMDD}.html
  を公開している（直近1か月分のみ）。毎営業日これを読み、全銘柄ぶんを
  db/tdnet/YYYY-MM.csv に貯める。貯めた分は1か月を過ぎても手元に残る。

■ 蓄積（TdnetStore）
  columns: date, time, code, name, title, url, source, tag
    - code   は 4桁に正規化（TDnet は 5桁 "72030"）
    - source は official / backfill / mock
    - tag    は見出しから自動付与（決算短信・業績修正・自己株 …）
  重複は (date, code, title) で除く。
"""

from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from .provider import normalize_code

TDNET_BASE = "https://www.release.tdnet.info/inbs/"
_TIMEOUT = 30
_MAX_PAGES = 40  # 1日あたり最大 40ページ × 100件
COLUMNS = ["date", "time", "code", "name", "title", "url", "source", "tag"]

# 見出し → 種別タグ。上から順に最初に当たったものを採用する。
_TAG_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("決算短信", ("決算短信",)),
    ("業績修正", ("業績予想の修正", "業績予想及び配当予想の修正", "業績予想と実績値との差異", "上方修正", "下方修正", "業績予想の変更")),
    ("配当", ("配当予想", "剰余金の配当", "配当方針", "増配", "減配", "復配")),
    ("自己株", ("自己株式", "自社株", "自己株券")),
    ("株式分割", ("株式分割", "株式併合")),
    ("TOB", ("公開買付", "TOB")),
    ("M&A", ("株式取得", "子会社化", "吸収合併", "株式交換", "株式移転", "事業譲受", "買収", "会社分割", "完全子会社")),
    ("資本提携", ("資本業務提携", "資本提携", "業務提携")),
    ("増資", ("第三者割当", "新株式発行", "公募増資", "新株予約権", "転換社債", "CB", "資金調達")),
    ("大株主", ("主要株主", "親会社", "筆頭株主")),
    ("上場", ("上場市場", "市場区分", "市場変更", "上場廃止", "上場維持基準")),
    ("株主優待", ("株主優待",)),
    ("特別損益", ("特別利益", "特別損失", "減損", "貸倒")),
    ("契約・受注", ("契約締結", "受注", "採択", "承認取得", "販売開始", "共同開発", "ライセンス")),
    ("株価照会", ("株価の動向", "報道", "一部報道", "憶測")),
    ("役員", ("代表取締役", "役員の異動", "人事")),
    ("訂正", ("訂正", "一部訂正")),
    ("月次", ("月次", "売上高速報", "売上速報")),
    ("株主総会", ("株主総会", "招集")),
    ("ガバナンス", ("コーポレート・ガバナンス", "コーポレートガバナンス", "独立役員")),
]


def tag_title(title: str) -> str:
    """見出しから種別タグを返す。当たらなければ 'その他'。"""
    t = str(title)
    for tag, kws in _TAG_RULES:
        if any(k in t for k in kws):
            return tag
    return "その他"


# ------------------------------------------------------------------ 公式クロール

def parse_list_page(html: str | bytes, day: date) -> list[dict]:
    """TDnet 一覧ページの HTML を行のリストに変換する（テスト可能な純関数）。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.find_all("tr"):
        title_td = tr.find("td", class_=re.compile(r"kjTitle"))
        code_td = tr.find("td", class_=re.compile(r"kjCode"))
        if title_td is None or code_td is None:
            continue
        a = title_td.find("a")
        title = (a.get_text(" ", strip=True) if a else title_td.get_text(" ", strip=True))
        href = a.get("href", "") if a else ""
        url = href if href.startswith("http") else (TDNET_BASE + href if href else "")
        time_td = tr.find("td", class_=re.compile(r"kjTime"))
        name_td = tr.find("td", class_=re.compile(r"kjName"))
        rows.append({
            "date": pd.Timestamp(day),
            "time": time_td.get_text(strip=True) if time_td else "",
            "code": normalize_code(code_td.get_text(strip=True)),
            "name": name_td.get_text(" ", strip=True) if name_td else "",
            "title": title,
            "url": url,
            "source": "official",
            "tag": tag_title(title),
        })
    return rows


def fetch_official_day(day: date, session: requests.Session | None = None, sleep: float = 0.5) -> pd.DataFrame:
    """指定日の TDnet 一覧を全ページ読む。休場日や1か月より前は空の DataFrame。"""
    s = session or requests.Session()
    ymd = day.strftime("%Y%m%d")
    out: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        url = f"{TDNET_BASE}I_list_{page:03d}_{ymd}.html"
        r = s.get(url, timeout=_TIMEOUT)
        if r.status_code == 404:
            break
        if r.status_code >= 400:
            raise RuntimeError(f"TDnet {r.status_code} {url}")
        rows = parse_list_page(r.content, day)
        if not rows:
            break
        out.extend(rows)
        time.sleep(sleep)
    return pd.DataFrame(out, columns=COLUMNS)


# ------------------------------------------------------------------ 蓄積

class TdnetStore:
    """db/tdnet/YYYY-MM.csv の読み書き。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path(__file__).resolve().parents[2] / "db" / "tdnet")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, month: pd.Timestamp) -> Path:
        return self.root / f"{month.strftime('%Y-%m')}.csv"

    def _read(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            df = pd.DataFrame(columns=COLUMNS)
            df["date"] = pd.to_datetime(df["date"])
            return df
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = ""
        df["date"] = pd.to_datetime(df["date"])
        return df[COLUMNS]

    def upsert(self, rows: pd.DataFrame) -> int:
        """行を追加（重複は date+code+title で除去）。追加された件数を返す。"""
        if rows is None or rows.empty:
            return 0
        rows = rows.copy()
        rows["date"] = pd.to_datetime(rows["date"]).dt.normalize()
        rows["code"] = rows["code"].map(normalize_code)
        if "tag" not in rows.columns or rows["tag"].eq("").any():
            rows["tag"] = rows["title"].map(tag_title)
        added = 0
        for month, part in rows.groupby(rows["date"].dt.to_period("M")):
            path = self._path(month.to_timestamp())
            cur = self._read(path)
            before = len(cur)
            merged = pd.concat([cur, part[COLUMNS]], ignore_index=True)
            merged["date"] = pd.to_datetime(merged["date"])
            merged = merged.drop_duplicates(subset=["date", "code", "title"], keep="first")
            merged = merged.sort_values(["date", "time", "code"]).reset_index(drop=True)
            added += len(merged) - before
            out = merged.copy()
            out["date"] = out["date"].dt.strftime("%Y-%m-%d")
            out.to_csv(path, index=False, encoding="utf-8")
        return added

    def load(self, code: str | None, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """期間内（と銘柄）の開示を返す。"""
        frames = []
        for m in pd.period_range(start.to_period("M"), end.to_period("M"), freq="M"):
            frames.append(self._read(self._path(m.to_timestamp())))
        if not frames:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.concat(frames, ignore_index=True)
        df = df[(df["date"] >= start.normalize()) & (df["date"] <= end.normalize())]
        if code:
            df = df[df["code"] == normalize_code(code)]
        return df.sort_values(["date", "time"]).reset_index(drop=True)

    def coverage(self) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
        """公式クロールで貯まっている最古日と最新日。"""
        dates = []
        for p in sorted(self.root.glob("*.csv")):
            df = self._read(p)
            off = df[df["source"] == "official"]
            if not off.empty:
                dates.append((off["date"].min(), off["date"].max()))
        if not dates:
            return None, None
        return min(d[0] for d in dates), max(d[1] for d in dates)

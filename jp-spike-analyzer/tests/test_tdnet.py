from datetime import date
from pathlib import Path

import pandas as pd

from src.data import tdnet, tdnet_backfill

HTML = """
<table id="main-list-table">
<tr class="oddnew-L">
 <td class="kjTime">15:30</td><td class="kjCode">72030</td><td class="kjName">トヨタ自動車</td>
 <td class="kjTitle"><a href="140120260826512345.pdf" target="_blank">業績予想の修正（上方修正）に関するお知らせ</a></td>
 <td class="kjXbrl"></td><td class="kjPlace">東</td><td class="kjHistroy"></td>
</tr>
<tr class="evennew-L">
 <td class="kjTime">16:00</td><td class="kjCode">99840</td><td class="kjName">ソフトバンクグループ</td>
 <td class="kjTitle"><a href="140120260826512346.pdf">自己株式立会外買付取引（ＴｏＳＴＮｅＴ－３）による自己株式の取得結果</a></td>
 <td class="kjXbrl"></td><td class="kjPlace">東</td><td class="kjHistroy"></td>
</tr>
<tr><td>ヘッダ行など無関係</td></tr>
</table>
"""


def test_parse_list_page():
    rows = tdnet.parse_list_page(HTML, date(2026, 8, 26))
    assert len(rows) == 2
    assert rows[0]["code"] == "7203"
    assert rows[0]["tag"] == "業績修正"
    assert rows[0]["url"].startswith("https://www.release.tdnet.info/inbs/1401")
    assert rows[1]["code"] == "9984"
    assert rows[1]["tag"] == "自己株"


def test_tag_title():
    assert tdnet.tag_title("2027年３月期 第１四半期決算短信〔日本基準〕（非連結）") == "決算短信"
    assert tdnet.tag_title("剰余金の配当（増配）に関するお知らせ") == "配当"
    assert tdnet.tag_title("株式会社Xによる当社株式に対する公開買付けの開始") == "TOB"
    assert tdnet.tag_title("コーポレート・ガバナンスに関する報告書") == "ガバナンス"
    assert tdnet.tag_title("なんでもない件") == "その他"


def test_store_upsert_and_load(tmp_path: Path):
    store = tdnet.TdnetStore(root=tmp_path)
    rows = pd.DataFrame(tdnet.parse_list_page(HTML, date(2026, 8, 26)))
    assert store.upsert(rows) == 2
    assert store.upsert(rows) == 0  # 重複は増えない
    got = store.load("7203", pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"))
    assert len(got) == 1 and got["title"].iloc[0].startswith("業績予想")
    assert (tmp_path / "2026-08.csv").exists()
    lo, hi = store.coverage()
    assert lo == pd.Timestamp("2026-08-26") == hi


def test_backfill_parse_items():
    payload = {"items": [{"Tdnet": {
        "pubdate": "2026-02-25 16:45:00", "company_code": "72030", "company_name": "トヨタ自動車",
        "title": "自己株式の取得及び自己株式立会外買付取引（ToSTNeT-3）による自己株式の買付けに関するお知らせ",
        "document_url": "https://www.release.tdnet.info/inbs/x.pdf"}}]}
    df = tdnet_backfill.parse_items(payload)
    assert df.iloc[0]["code"] == "7203"
    assert df.iloc[0]["time"] == "16:45"
    assert df.iloc[0]["source"] == "backfill"
    assert df.iloc[0]["tag"] == "自己株"

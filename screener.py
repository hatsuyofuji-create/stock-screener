# -*- coding: utf-8 -*-
"""
=====================================================================
 株スクリーナー本体
 条件: 前営業日までの過去3年が安値基準で30%以内
       ＋ 当日の出来高が前日比5倍以上
       ＋ 当日が陽線(始値 < 終値)
=====================================================================
 ※ 設定を変えたいときは、すぐ下の【設定】の数字だけ書き換えればOK
"""

import time
from datetime import date
import pandas as pd
import yfinance as yf

# ============== 【設定】ここの数字だけ変えればOK ==============
TEST_MODE    = True    # ← まずは True のまま(少数の銘柄で動作確認)。
                       #   うまく動いたら False に変えると「東証の全銘柄」を調べます。
RANGE_PCT    = 30.0    # 過去3年の値幅(%以内)
VOL_MULTIPLE = 5.0     # 出来高が前日の何倍以上か
YEARS        = 3       # 過去何年を見るか
# ============================================================

# 動作確認用の銘柄(本番=全銘柄になるので、ここは確認用の少数だけ)
TEST_TICKERS = [
    "3103", "7203", "6758", "9984", "8306", "6501", "9432", "4063",
    "8035", "6098", "9433", "7974", "6902", "4502", "6594", "7267",
    "8058", "6367", "4901", "6273",
]


def normalize(df):
    """yfinanceの返し方の違いを吸収して、列を Open/High/Low/Close/Volume にそろえる"""
    if df is None or len(df) == 0:
        return None
    # 列が2段になっている場合は1段に潰す
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    need = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in need):
        return None
    return df[need].dropna()


def judge(df):
    """1銘柄を判定する(検証済みのロジック)"""
    if len(df) < 2:
        return False, None
    today = df.iloc[-1]
    yday  = df.iloc[-2]

    is_yousen = today["Close"] > today["Open"]                       # 陽線か

    if yday["Volume"] <= 0:
        return False, None
    vol_ratio = today["Volume"] / yday["Volume"]                     # 出来高倍率
    vol_ok = vol_ratio >= VOL_MULTIPLE

    past = df.iloc[:-1].tail(YEARS * 250)                            # 当日を除く過去3年
    lo, hi = past["Low"].min(), past["High"].max()
    band = (hi - lo) / lo * 100 if lo > 0 else float("inf")          # 値幅%
    range_ok = band <= RANGE_PCT

    hit = bool(is_yousen and vol_ok and range_ok)
    return hit, {
        "close": float(today["Close"]),
        "ratio": float(vol_ratio),
        "lo": float(lo), "hi": float(hi), "band": float(band),
    }


def get_tickers():
    """調べる銘柄のリストを返す"""
    if TEST_MODE:
        return TEST_TICKERS
    # 本番: 東証の上場銘柄一覧(JPX公式Excel)から全コードを取得
    url = ("https://www.jpx.co.jp/markets/statistics-equities/misc/"
           "tvdivq0000001vg2-att/data_j.xls")
    j = pd.read_excel(url)
    j = j[j["市場・商品区分"].astype(str).str.contains("内国株式", na=False)]
    return [str(c) for c in j["コード"].tolist()]


def main():
    tickers = get_tickers()
    print(f"調べる銘柄数: {len(tickers)}")
    hits = []

    for i, code in enumerate(tickers, 1):
        try:
            raw = yf.download(f"{code}.T", period=f"{YEARS}y", interval="1d",
                              progress=False, auto_adjust=False, threads=False)
            df = normalize(raw)
            if df is None:
                continue
            ok, d = judge(df)
            if ok:
                hits.append((code, d))
                print(f"  ◎ ヒット: {code}")
        except Exception:
            pass            # 取得できない銘柄は静かにスキップ
        if i % 200 == 0:
            print(f"  ...{i}/{len(tickers)} 件チェック済み")
        time.sleep(0.2)     # サーバーに負担をかけないよう少し待つ

    write_html(hits)
    print(f"完了。該当 {len(hits)} 件。docs/index.html に結果を保存しました。")


def write_html(hits):
    """結果ページ(docs/index.html)を書き出す"""
    import os
    os.makedirs("docs", exist_ok=True)

    if hits:
        rows = ""
        for code, d in hits:
            rows += (f'<tr><td class="code">{code}</td>'
                     f'<td class="num">{d["close"]:.0f}円</td>'
                     f'<td class="num up">{d["ratio"]:.1f}倍</td>'
                     f'<td class="num">{d["band"]:.1f}%</td>'
                     f'<td class="num">{d["lo"]:.0f}〜{d["hi"]:.0f}円</td></tr>')
    else:
        rows = '<tr><td colspan="5" class="empty">本日の該当はありませんでした</td></tr>'

    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>本日のスクリーニング結果</title><style>
body{{font-family:-apple-system,"Hiragino Sans","Meiryo",sans-serif;background:#0f1115;color:#e7e9ee;margin:0;padding:20px;}}
.wrap{{max-width:820px;margin:0 auto;}}
h1{{font-size:20px;margin:0 0 4px;}}
.sub{{color:#8b93a7;font-size:13px;margin-bottom:18px;}}
.card{{background:#171a21;border:1px solid #262b36;border-radius:14px;overflow:hidden;}}
table{{width:100%;border-collapse:collapse;font-size:14px;}}
th{{text-align:left;background:#1c2029;color:#9aa3b5;font-weight:600;padding:11px 12px;font-size:12px;border-bottom:1px solid #262b36;}}
td{{padding:12px;border-bottom:1px solid #21262f;}}
tr:last-child td{{border-bottom:none;}}
.code{{font-weight:700;color:#7cc4ff;}}
.num{{text-align:right;font-variant-numeric:tabular-nums;}}
.up{{color:#ff6b7a;font-weight:700;}}
.empty{{text-align:center;color:#8b93a7;padding:26px;}}
.cond{{margin-top:14px;color:#8b93a7;font-size:12px;line-height:1.7;}}
</style></head><body><div class="wrap">
<h1>📈 本日のスクリーニング結果</h1>
<div class="sub">{date.today().strftime('%Y年%m月%d日')} 更新 ／ 該当 {len(hits)} 件</div>
<div class="card"><table>
<tr><th>コード</th><th>株価</th><th>出来高</th><th>3年の値幅</th><th>3年レンジ</th></tr>
{rows}
</table></div>
<div class="cond">抽出条件: 前営業日までの過去3年が安値基準で{RANGE_PCT:.0f}%以内 ／ 当日の出来高が前日比{VOL_MULTIPLE:.0f}倍以上 ／ 当日が陽線</div>
</div></body></html>"""

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()

"""株価データの取得・キャッシュ・CSV読み込みを担当するモジュール。

外部に公開するのは :func:`load_prices` のみ。戻り値は
インデックスが ``DatetimeIndex``（昇順・重複なし）、値が終値（float）の
``pandas.Series`` で、欠損・非数値はすべて除去済み。
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# よく使うティッカーはキャッシュファイル名を読みやすい別名にする
TICKER_SLUGS = {
    "^N225": "nikkei",
    "^TPX": "topix",
    "^GSPC": "sp500",
}

# CSV の列名ゆらぎ対応（_normalize_key() を通した後の文字列で比較する）
DATE_COLUMN_CANDIDATES = (
    "date", "datetime", "day", "time", "timestamp",
    "日付", "年月日", "日時", "取引日", "基準日",
)
CLOSE_COLUMN_CANDIDATES = (
    "close", "closeprice", "closingprice", "adjclose", "adjustedclose", "price",
    "終値", "終値調整値", "調整後終値", "調整済み終値", "株価", "価格", "終り値",
)


class DataError(RuntimeError):
    """データの取得・解析に失敗したことを表す例外。"""


def _normalize_key(name: object) -> str:
    """列名を比較用に正規化する（小文字化・空白/記号除去・全角英数の半角化）。"""
    s = str(name)
    # 全角英数字と全角スペースを半角へ
    s = s.translate(str.maketrans(
        "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ　",
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz ",
    ))
    s = s.lower().strip()
    return re.sub(r"[\s_\-\.\(\)（）\[\]]", "", s)


def _slugify_ticker(ticker: str) -> str:
    """ティッカーをキャッシュファイル名に使える文字列に変換する。"""
    if ticker in TICKER_SLUGS:
        return TICKER_SLUGS[ticker]
    slug = re.sub(r"[^0-9A-Za-z]+", "", ticker).lower()
    return slug or "ticker"


def cache_path(cache_dir: Path, ticker: str, day: date | None = None) -> Path:
    """``data/nikkei_YYYYMMDD.csv`` 形式のキャッシュパスを返す。"""
    day = day or date.today()
    return Path(cache_dir) / f"{_slugify_ticker(ticker)}_{day:%Y%m%d}.csv"


def _to_numeric(series: pd.Series) -> pd.Series:
    """カンマ区切り・通貨記号付きの文字列列を float に変換する（不正値は NaN）。"""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype("string")
        .str.replace(r"[,\s円¥￥$]", "", regex=True)
        .str.replace("−", "-", regex=False)   # U+2212 マイナス記号
        .replace({"": None, "-": None, "--": None, "―": None, "N/A": None, "nan": None})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _to_datetime(series: pd.Series) -> pd.Series:
    """「2024年1月5日」「2024/01/05」などを含む列を datetime に変換する。"""
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")
    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(r"[年月]", "/", regex=True)
        .str.replace("日", "", regex=False)
        .str.replace(r"/+$", "", regex=True)
    )
    return pd.to_datetime(cleaned, errors="coerce", format="mixed")


def _tidy(dates: pd.Series, closes: pd.Series, source: str) -> pd.Series:
    """日付と終値の組を検証・整形して Series を作る。"""
    frame = pd.DataFrame({"date": _to_datetime(dates), "close": _to_numeric(closes)})
    frame = frame.dropna()
    frame = frame[frame["close"] > 0]
    if frame.empty:
        raise DataError(
            f"{source} から有効な価格データを1件も読み取れませんでした。"
            "日付列と終値列が正しいかご確認ください。"
        )
    frame = frame.sort_values("date").drop_duplicates(subset="date", keep="last")
    prices = frame.set_index("date")["close"].astype(float)
    prices.index = prices.index.normalize()
    prices.name = "close"
    return prices


def _pick_column(
    frame: pd.DataFrame, candidates: tuple[str, ...], exclude: tuple[str, ...] = ()
) -> str | None:
    """候補名に一致する列を探す。

    候補は優先順に並んでいる前提で、候補側を外側のループにする
    （列側を外側にすると、たとえば yfinance が書き出す ``Price`` 列が
    ``Close`` より先に「終値らしい列」として拾われてしまう）。
    """
    normalized = {col: _normalize_key(col) for col in frame.columns if col not in exclude}
    for candidate in candidates:                      # 完全一致を優先
        for col, key in normalized.items():
            if key == candidate:
                return col
    for candidate in candidates:                      # 次に部分一致
        for col, key in normalized.items():
            if candidate in key:
                return col
    return None


def load_csv(csv_path: str | Path) -> pd.Series:
    """任意の CSV から日付・終値を読み込む。

    ``Date``/``日付``、``Close``/``終値`` などの列名ゆらぎ、カンマ入り数値、
    yfinance が書き出す 2〜3 行のヘッダ（Ticker 行など）に対応する。
    """
    path = Path(csv_path)
    if not path.exists():
        raise DataError(f"CSV が見つかりません: {path}")

    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - pandas 側の詳細はそのまま見せる
        raise DataError(f"CSV を読み込めませんでした: {path} ({exc})") from exc

    if frame.empty:
        raise DataError(f"CSV が空です: {path}")

    # 日付列を先に確定し、終値列の候補からは除外する
    date_col = _pick_column(frame, DATE_COLUMN_CANDIDATES)
    if date_col is None:
        date_col = frame.columns[0]
        logger.warning("日付列を特定できなかったため 1 列目 '%s' を使用します。", date_col)
    close_col = _pick_column(frame, CLOSE_COLUMN_CANDIDATES, exclude=(date_col,))

    # 終値列も特定できない場合は「数値化できる最後の列」で救済する
    if close_col is None:
        numeric_cols = [c for c in frame.columns if c != date_col and _to_numeric(frame[c]).notna().any()]
        if not numeric_cols:
            raise DataError(
                f"終値列を特定できませんでした: {path}\n"
                f"見つかった列: {list(frame.columns)}\n"
                "Close / 終値 のいずれかの列名にしてください。"
            )
        close_col = numeric_cols[-1]
        logger.warning("終値列を特定できなかったため '%s' を使用します。", close_col)

    logger.info("CSV を読み込みます: %s（日付列='%s', 終値列='%s'）", path, date_col, close_col)
    return _tidy(frame[date_col], frame[close_col], source=str(path))


def _download(ticker: str) -> pd.Series:
    """yfinance で全期間の日足終値を取得する。"""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise DataError(
            "yfinance がインストールされていません。"
            "`pip install -r requirements.txt` を実行してください。"
        ) from exc

    logger.info("yfinance から %s の日足を取得します（全期間）...", ticker)
    try:
        frame = yf.download(ticker, period="max", interval="1d",
                            auto_adjust=False, progress=False, threads=False)
    except Exception as exc:
        raise DataError(
            f"{ticker} の取得に失敗しました: {exc}\n"
            "ネットワーク接続を確認するか、--csv でローカルの CSV を指定してください。"
        ) from exc

    if frame is None or frame.empty:
        raise DataError(
            f"{ticker} のデータを取得できませんでした（0 件）。\n"
            "ネットワーク接続とティッカー名を確認するか、--csv でローカルの CSV を指定してください。"
        )

    # yfinance は単一ティッカーでも MultiIndex 列を返すことがある
    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.droplevel(-1, axis=1)
    if "Close" not in frame.columns:
        raise DataError(f"取得結果に Close 列がありません: {list(frame.columns)}")

    close = frame["Close"]
    if isinstance(close, pd.DataFrame):  # 同名列が重複した場合の保険
        close = close.iloc[:, 0]
    return _tidy(pd.Series(frame.index), pd.Series(close.to_numpy()), source=ticker)


def load_prices(
    ticker: str = "^N225",
    csv_path: str | Path | None = None,
    cache_dir: str | Path = "data",
    refresh: bool = False,
) -> pd.Series:
    """終値の時系列を返す。

    Args:
        ticker: yfinance のティッカー（既定 ``^N225``）。
        csv_path: 指定した場合は yfinance を使わず CSV から読み込む。
        cache_dir: 取得結果を保存するディレクトリ。
        refresh: True なら当日キャッシュがあっても再取得する。

    Returns:
        日付をインデックスとする終値の ``pandas.Series``。
    """
    if csv_path is not None:
        return load_csv(csv_path)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_dir, ticker)

    if path.exists() and not refresh:
        logger.info("同日のキャッシュを使用します: %s（--refresh で再取得）", path)
        return load_csv(path)

    prices = _download(ticker)
    frame = prices.rename("Close").rename_axis("Date").reset_index()
    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d")
    frame.to_csv(path, index=False)
    logger.info("キャッシュを保存しました: %s", path)
    return prices

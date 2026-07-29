# -*- coding: utf-8 -*-
"""
YahooProvider: yfinance で終値（調整後）を取得する本番プロバイダ。

- 依存: yfinance（requirements.txt）。未インストール時は分かりやすく案内する。
- 取得は日次・調整後終値。取引所をまたぐため、日付は各シンボルの営業日で返し、
  突き合わせ（共通日付の抽出）は analysis.align に任せる。
- 簡易キャッシュ（プロセス内 dict）で同一 (symbol, period) の再取得を避ける。
"""

from __future__ import annotations

from .provider import PriceProvider


class YahooProvider(PriceProvider):
    name = "yahoo"

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[list[str], list[float]]] = {}

    def get_close_history(self, symbol: str, period: str) -> tuple[list[str], list[float]]:
        key = (symbol, period)
        if key in self._cache:
            return self._cache[key]
        try:
            import yfinance as yf
        except ImportError as e:  # pragma: no cover - 依存未導入時の案内
            raise RuntimeError(
                "yfinance が未インストールです。`pip install -r requirements.txt` を実行してください。"
            ) from e

        df = yf.download(
            symbol, period=period, interval="1d",
            auto_adjust=True, progress=False, threads=False,
        )
        if df is None or df.empty:
            raise RuntimeError(f"データを取得できませんでした: {symbol}")

        # yfinance の列は単一/複数シンボルで形が変わるため Close を頑健に取り出す
        close = df["Close"]
        if hasattr(close, "columns"):  # DataFrame（複数列）なら最初の列
            close = close.iloc[:, 0]
        close = close.dropna()

        dates = [d.date().isoformat() for d in close.index]
        closes = [float(v) for v in close.values]
        self._cache[key] = (dates, closes)
        return dates, closes

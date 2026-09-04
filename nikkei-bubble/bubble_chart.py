#!/usr/bin/env python3
"""日経平均バブルチャート（LPPLS信頼度指標）を描画する CLI。

ディディエ・ソネット教授らの LPPLS（Log-Periodic Power Law Singularity /
対数周期べき乗則特異点）モデルを、日経平均株価の対数価格に多数の窓で
当てはめ、「バブル的パターン（超指数的上昇＋対数周期振動）」が検出された
窓の割合を信頼度指標として可視化する。

  上段: 終値（対数軸）＋ ポジティブバブル信頼度（赤バー＝バブルシグナル）
  下段: ネガティブバブル信頼度（紺バー＝バブル終了シグナル）

使い方の詳細は README.md を参照。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

import data as data_mod
from data import DataError

logger = logging.getLogger("bubble_chart")

DEFAULT_TICKER = "^N225"
DEFAULT_START = "2023-06-01"
DEFAULT_WINDOW = 252          # 最大窓（営業日）≒ 1 年
DEFAULT_SMALLEST_WINDOW = 60  # 最小窓（営業日）≒ 3 か月
DEFAULT_OUTER = 5             # 指標を計算する日付の間隔
DEFAULT_INNER = 5             # 窓を縮小する刻み
DEFAULT_SEARCHES = 25         # 1 フィットあたりの初期値ランダム探索回数

CHART_TITLE = "日経平均バブルチャート（LPPLS信頼度指標）"
POS_COLOR = "#d1252b"   # バブルシグナル（赤）
NEG_COLOR = "#1f3864"   # バブル終了シグナル（紺）
PRICE_COLOR = "#111111"
SIGNAL_AXIS_TOP = 0.6   # 信頼度軸の既定上限


# --------------------------------------------------------------------------
# LPPLS 指標の計算
# --------------------------------------------------------------------------
def slice_for_computation(
    prices: pd.Series, start: pd.Timestamp | None, end: pd.Timestamp | None, window: int
) -> pd.Series:
    """指標を ``start`` から出せるよう、窓 1 本分の助走期間を足して切り出す。

    LPPLS 信頼度は「窓の右端」の日付に対して求まるため、``start`` 時点の値を
    得るには ``start`` より前に ``window`` 本の観測が必要になる。
    """
    if end is not None:
        prices = prices[prices.index <= end]
    if start is None:
        return prices

    pos = int(prices.index.searchsorted(start))
    if pos >= len(prices):
        raise DataError(
            f"--start {start:%Y-%m-%d} 以降のデータがありません"
            f"（データ最終日 {prices.index[-1]:%Y-%m-%d}）。"
        )
    begin = pos - (window - 1)
    if begin < 0:
        logger.warning(
            "助走データが %d 本不足しています。指標の開始日は %s より後ろにずれます。",
            -begin, start.date(),
        )
        begin = 0
    return prices.iloc[begin:]


def compute_indicators(
    prices: pd.Series,
    window: int = DEFAULT_WINDOW,
    smallest_window: int = DEFAULT_SMALLEST_WINDOW,
    outer_increment: int = DEFAULT_OUTER,
    inner_increment: int = DEFAULT_INNER,
    max_searches: int = DEFAULT_SEARCHES,
    workers: int | None = None,
) -> pd.DataFrame:
    """入れ子窓の LPPLS フィットから信頼度指標を計算する。

    Returns:
        ``date`` / ``price`` / ``pos_conf`` / ``neg_conf`` を持つ DataFrame。
    """
    from matplotlib.dates import date2num, num2date

    try:
        from lppls import lppls as lppls_mod
    except ImportError as exc:  # pragma: no cover
        raise DataError(
            "lppls がインストールされていません。"
            "`pip install -r requirements.txt` を実行してください。"
        ) from exc

    if smallest_window >= window:
        raise DataError(
            f"--smallest-window ({smallest_window}) は --window ({window}) より小さくしてください。"
        )
    if len(prices) <= window:
        raise DataError(
            f"データ本数が足りません（{len(prices)} 本 ≤ 最大窓 {window} 本）。\n"
            "--start を早めるか --window を小さくしてください。"
        )

    workers = workers or os.cpu_count() or 1
    n_outer = (len(prices) - window) // outer_increment + 1
    n_inner = max(1, (window - smallest_window + inner_increment - 1) // inner_increment)
    logger.info(
        "LPPLS 計算開始: 観測 %d 本 / 窓 %d→%d / outer=%d / inner=%d / searches=%d / workers=%d",
        len(prices), window, smallest_window, outer_increment, inner_increment,
        max_searches, workers,
    )
    logger.info("推定フィット回数: 約 %s 回（時間がかかる処理です）", f"{n_outer * n_inner:,}")

    observations = np.array([
        date2num(prices.index.to_pydatetime()),
        np.log(prices.to_numpy(dtype=float)),
    ])

    model = lppls_mod.LPPLS(observations=observations)
    fits = model.mp_compute_nested_fits(
        workers=workers,
        window_size=window,
        smallest_window_size=smallest_window,
        outer_increment=outer_increment,
        inner_increment=inner_increment,
        max_searches=max_searches,
    )
    raw = model.compute_indicators(fits)

    result = pd.DataFrame({
        "date": pd.to_datetime([num2date(t).date() for t in raw["time"]]),
        "price": np.exp(raw["price"].to_numpy(dtype=float)),
        "pos_conf": raw["pos_conf"].to_numpy(dtype=float),
        "neg_conf": raw["neg_conf"].to_numpy(dtype=float),
    })
    logger.info(
        "指標を %d 点計算しました（%s 〜 %s）",
        len(result), result["date"].iloc[0].date(), result["date"].iloc[-1].date(),
    )
    return result


def save_indicators(indicators: pd.DataFrame, path: Path) -> None:
    """指標を CSV に保存する（``--replot`` での再描画用）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = indicators.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False, float_format="%.6f")
    logger.info("指標を保存しました: %s", path)


def load_indicators(path: Path) -> pd.DataFrame:
    """``--replot`` 用に保存済みの指標 CSV を読み込む。"""
    if not path.exists():
        raise DataError(
            f"指標 CSV が見つかりません: {path}\n"
            "--replot を外して一度計算を実行してください。"
        )
    frame = pd.read_csv(path, parse_dates=["date"])
    logger.info("保存済みの指標を読み込みました: %s（%d 点）", path, len(frame))
    return frame


# --------------------------------------------------------------------------
# 描画
# --------------------------------------------------------------------------
def _bar_width_days(dates: pd.Series) -> float:
    """指標点の間隔からバーの太さ（日数）を決める。"""
    if len(dates) < 2:
        return 3.0
    step = float(np.median(np.diff(dates.to_numpy()).astype("timedelta64[D]").astype(float)))
    return max(1.0, step * 0.9)


def _log_axis_ticks(ax, vmin: float, vmax: float) -> None:
    """対数軸に「35,000」形式のカンマ区切り目盛りを設定する。"""
    import matplotlib.ticker as mticker

    ratio = vmax / max(vmin, 1e-9)
    if ratio < 1.5:
        substep = 0.1
    elif ratio < 3.0:
        substep = 0.25
    elif ratio < 6.0:
        substep = 0.5
    else:
        substep = 1.0
    ax.yaxis.set_major_locator(
        mticker.LogLocator(base=10.0, subs=np.arange(1.0, 10.0, substep))
    )
    ax.yaxis.set_minor_locator(mticker.NullLocator())
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))


def plot_chart(
    prices: pd.Series,
    indicators: pd.DataFrame,
    out_png: Path,
    source_label: str = DEFAULT_TICKER,
    show: bool = False,
) -> Path:
    """上下 2 段（価格＋バブルシグナル / バブル終了シグナル）の PNG を書き出す。"""
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import japanize_matplotlib  # noqa: F401  日本語フォントを登録する副作用が目的

    fig, (ax_price, ax_neg) = plt.subplots(
        2, 1, figsize=(14, 8.5), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
    )

    # --- 上段: 終値（対数軸） ------------------------------------------------
    ax_price.plot(prices.index, prices.to_numpy(), color=PRICE_COLOR, linewidth=1.3,
                  label="終値", zorder=3)
    ax_price.set_yscale("log")
    _log_axis_ticks(ax_price, float(prices.min()), float(prices.max()))
    ax_price.set_ylabel("株価（円・対数軸）")
    ax_price.grid(True, which="major", axis="both", alpha=0.25, linestyle=":")

    # --- 上段: ポジティブバブル信頼度（右軸・赤バー） -------------------------
    width = _bar_width_days(indicators["date"])
    ax_pos = ax_price.twinx()
    ax_pos.bar(indicators["date"], indicators["pos_conf"], width=width,
               color=POS_COLOR, alpha=0.85, label="バブルシグナル", zorder=1)
    ax_pos.set_ylim(0, max(SIGNAL_AXIS_TOP, float(indicators["pos_conf"].max()) * 1.15))
    ax_pos.set_ylabel("バブルシグナル（LPPLS信頼度）", color=POS_COLOR)
    ax_pos.tick_params(axis="y", colors=POS_COLOR)

    # 価格の折れ線をバーより手前に描く
    ax_price.set_zorder(ax_pos.get_zorder() + 1)
    ax_price.patch.set_visible(False)

    handles = [ax_price.lines[0], ax_pos.containers[0]]
    ax_price.legend(handles, [h.get_label() for h in handles], loc="upper left", framealpha=0.9)

    # --- 下段: ネガティブバブル信頼度（紺バー） ------------------------------
    ax_neg.bar(indicators["date"], indicators["neg_conf"], width=width,
               color=NEG_COLOR, alpha=0.9, label="バブル終了シグナル")
    ax_neg.set_ylim(0, max(SIGNAL_AXIS_TOP, float(indicators["neg_conf"].max()) * 1.15))
    ax_neg.set_ylabel("バブル終了シグナル", color=NEG_COLOR, fontsize=9)
    ax_neg.tick_params(axis="y", colors=NEG_COLOR)
    ax_neg.grid(True, axis="y", alpha=0.25, linestyle=":")
    ax_neg.legend(loc="upper left", framealpha=0.9)

    ax_neg.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=12))
    ax_neg.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m"))
    for label in ax_neg.get_xticklabels():
        label.set_rotation(30)
        label.set_horizontalalignment("right")

    fig.suptitle(CHART_TITLE, fontsize=17, y=0.965)
    ax_price.set_title(
        f"{source_label}  {prices.index[0]:%Y/%m/%d} 〜 {prices.index[-1]:%Y/%m/%d}"
        f"（終値 {prices.iloc[-1]:,.0f} 円）",
        fontsize=10, color="#555555", loc="left",
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    logger.info("チャートを保存しました: %s", out_png)

    if show:
        plt.show()
    plt.close(fig)
    return out_png


# --------------------------------------------------------------------------
# セルフテスト（合成バブルデータ）
# --------------------------------------------------------------------------
def make_synthetic_bubble(
    n: int = 250,
    tc_offset_days: float = 8.0,
    m: float = 0.4,
    omega: float = 8.0,
    B: float = -0.05,
    C: float = 0.004,
    phi: float = 1.0,
    A: float = np.log(30000.0),
    noise: float = 0.002,
    seed: int = 20240101,
) -> pd.Series:
    """LPPLS 式そのままの合成バブルを作る（臨界点はデータ末尾の直後）。

        ln p = A + B(tc-t)^m + C(tc-t)^m cos(ω ln(tc-t) − φ)

    既定パラメータは lppls パッケージの品質フィルタ
    （減衰率 D = m|B| / (ω|C|) = 0.625 > 0.5、2 < ω < 15、0 < m < 1）を満たす。
    """
    from matplotlib.dates import date2num

    dates = pd.bdate_range(end=pd.Timestamp("2024-12-31"), periods=n)
    t = np.asarray(date2num(dates.to_pydatetime()), dtype=float)
    tc = t[-1] + tc_offset_days
    dt = tc - t

    log_price = A + (dt ** m) * (B + C * np.cos(omega * np.log(dt) - phi))
    log_price += np.random.default_rng(seed).normal(0.0, noise, size=n)
    return pd.Series(np.exp(log_price), index=dates, name="close")


def run_selftest(args: argparse.Namespace) -> int:
    """合成バブルで pos_conf が末尾で立ち上がることを確認する。"""
    threshold = args.selftest_threshold
    prices = make_synthetic_bubble()
    logger.info(
        "合成バブルを生成しました: %d 本（%s 〜 %s, %.0f → %.0f）",
        len(prices), prices.index[0].date(), prices.index[-1].date(),
        prices.iloc[0], prices.iloc[-1],
    )

    indicators = compute_indicators(
        prices,
        window=args.selftest_window,
        smallest_window=args.selftest_smallest_window,
        outer_increment=10,
        inner_increment=5,
        max_searches=args.searches,
        workers=args.workers,
    )

    tail = indicators.tail(3)
    print()
    print("--- 末尾 5 点の信頼度 ---")
    for _, row in indicators.tail(5).iterrows():
        print(f"  {row['date']:%Y-%m-%d}  price={row['price']:9,.0f}  "
              f"pos_conf={row['pos_conf']:.3f}  neg_conf={row['neg_conf']:.3f}")

    best = float(tail["pos_conf"].max())
    passed = best > threshold
    print()
    print(f"末尾 3 点の pos_conf 最大値 = {best:.3f}（判定閾値 > {threshold:.2f}）")
    print(f"SELFTEST: {'PASS' if passed else 'FAIL'}")
    if not passed:
        print(
            "  合成バブルの臨界点付近でバブルシグナルが立ちませんでした。\n"
            "  lppls のバージョンやフィルタ条件の変更が原因の可能性があります。",
            file=sys.stderr,
        )
    return 0 if passed else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="日経平均バブルチャート（LPPLS信頼度指標）を生成します。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    src = parser.add_argument_group("データ")
    src.add_argument("--ticker", default=DEFAULT_TICKER, help="yfinance のティッカー")
    src.add_argument("--csv", default=None, metavar="PATH",
                     help="yfinance の代わりに読み込む CSV（Date/日付・Close/終値 列）")
    src.add_argument("--data-dir", default="data", help="キャッシュ CSV の保存先")
    src.add_argument("--refresh", action="store_true", help="当日キャッシュを無視して再取得する")

    rng = parser.add_argument_group("期間")
    rng.add_argument("--start", default=DEFAULT_START, help="チャート・指標の開始日 (YYYY-MM-DD)")
    rng.add_argument("--end", default=None, help="終了日 (YYYY-MM-DD)。既定は直近")

    lp = parser.add_argument_group("LPPLS パラメータ")
    lp.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="最大窓（営業日）")
    lp.add_argument("--smallest-window", type=int, default=DEFAULT_SMALLEST_WINDOW,
                    help="最小窓（営業日）")
    lp.add_argument("--outer", type=int, default=DEFAULT_OUTER,
                    help="outer_increment: 指標を計算する日付の間隔")
    lp.add_argument("--inner", type=int, default=DEFAULT_INNER,
                    help="inner_increment: 窓の縮小刻み")
    lp.add_argument("--searches", type=int, default=DEFAULT_SEARCHES,
                    help="max_searches: 1 フィットあたりの探索回数")
    lp.add_argument("--workers", type=int, default=os.cpu_count(), help="並列プロセス数")

    out = parser.add_argument_group("出力")
    out.add_argument("--output-dir", default="output", help="PNG と指標 CSV の出力先")
    out.add_argument("--out-png", default=None, help="PNG の出力パス（既定 <output-dir>/nikkei_bubble_chart.png）")
    out.add_argument("--out-csv", default=None, help="指標 CSV の出力パス（既定 <output-dir>/indicators.csv）")
    out.add_argument("--replot", action="store_true",
                     help="LPPLS を再計算せず、保存済みの指標 CSV から描き直す")
    out.add_argument("--show", action="store_true", help="画面にも表示する")

    test = parser.add_argument_group("セルフテスト")
    test.add_argument("--selftest", action="store_true",
                      help="合成バブルでバブルシグナルが立つかを検証して PASS/FAIL を表示する")
    test.add_argument("--selftest-threshold", type=float, default=0.3,
                      help="セルフテストの合格ライン（末尾 3 点の pos_conf 最大値）")
    test.add_argument("--selftest-window", type=int, default=120, help="セルフテストの最大窓")
    test.add_argument("--selftest-smallest-window", type=int, default=60,
                      help="セルフテストの最小窓")

    parser.add_argument("--quiet", action="store_true", help="ログを警告以上のみにする")
    return parser


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    out_png = Path(args.out_png) if args.out_png else output_dir / "nikkei_bubble_chart.png"
    out_csv = Path(args.out_csv) if args.out_csv else output_dir / "indicators.csv"

    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) if args.end else None

    prices = data_mod.load_prices(
        ticker=args.ticker, csv_path=args.csv, cache_dir=args.data_dir, refresh=args.refresh,
    )
    logger.info(
        "価格データ: %d 本（%s 〜 %s）",
        len(prices), prices.index[0].date(), prices.index[-1].date(),
    )

    if args.replot:
        indicators = load_indicators(out_csv)
    else:
        target = slice_for_computation(prices, start, end, args.window)
        indicators = compute_indicators(
            target,
            window=args.window,
            smallest_window=args.smallest_window,
            outer_increment=args.outer,
            inner_increment=args.inner,
            max_searches=args.searches,
            workers=args.workers,
        )
        save_indicators(indicators, out_csv)

    # --replot では別条件で計算した指標が渡り得るので、表示期間で絞り直す
    if start is not None:
        indicators = indicators[indicators["date"] >= start]
    if end is not None:
        indicators = indicators[indicators["date"] <= end]
    if indicators.empty:
        raise DataError("表示期間に該当する指標がありません。--start / --end を見直してください。")
    indicators = indicators.reset_index(drop=True)

    # 描画に使う価格は「指標の開始日」と --start の遅い方から
    disp_start = max([d for d in (start, indicators["date"].iloc[0]) if d is not None])
    disp = prices[prices.index >= disp_start]
    if end is not None:
        disp = disp[disp.index <= end]
    if disp.empty:
        raise DataError("描画対象の期間に価格データがありません。--start / --end を見直してください。")

    source_label = Path(args.csv).name if args.csv else args.ticker
    plot_chart(disp, indicators, out_png, source_label=source_label, show=args.show)

    latest = indicators.iloc[-1]
    print()
    print(f"最新の指標（{latest['date']:%Y-%m-%d}）: "
          f"バブルシグナル={latest['pos_conf']:.3f} / バブル終了シグナル={latest['neg_conf']:.3f}")
    print(f"チャート : {out_png}")
    print(f"指標 CSV : {out_csv}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )
    if not args.show:
        matplotlib.use("Agg")

    try:
        return run_selftest(args) if args.selftest else run(args)
    except DataError as exc:
        print(f"\nエラー: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("\n中断しました。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

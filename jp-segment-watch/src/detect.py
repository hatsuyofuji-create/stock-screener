# -*- coding: utf-8 -*-
"""
新セグメント検知と履歴の入出力。

やりたいこと:
  「過去1年になかったセグメントが新しく増えた銘柄」を拾う。
  有価証券報告書は年1回なので、ある銘柄の“今回の有報のセグメント集合”を、
  同じ銘柄の“1つ前（=約1年前）の有報のセグメント集合”と比べ、
  今回だけにある名前があれば「新セグメント出現」とみなす。

履歴（db/segments.csv）:
  銘柄ごと・有報ごとに1行。segments は '|' 区切りで保存。
  これをリポジトリにコミットして貯めていくことで、次回以降の比較材料になる。

検知結果（db/new_segments.csv）:
  新セグメントが出た銘柄だけを追記していく（人が後で振り返れるように）。
"""

from __future__ import annotations

import csv
from pathlib import Path

SEG_SEP = "|"

HISTORY_FIELDS = [
    "detected_date",   # この行を記録した日
    "docID",
    "ticker",
    "secCode",
    "edinetCode",
    "filerName",
    "periodEnd",       # 会計期間の末日（比較の基準）
    "submitDate",
    "n_segments",
    "segments",        # '|' 区切り
]

HIT_FIELDS = [
    "detected_date",
    "ticker",
    "filerName",
    "periodEnd",
    "prior_periodEnd",
    "new_segments",        # 今回増えたセグメント（'|'区切り）
    "current_segments",    # 今回の全セグメント（'|'区切り）
    "docID",
]


def join_segments(segs: list[str]) -> str:
    return SEG_SEP.join(segs)


def split_segments(text: str) -> list[str]:
    return [s for s in (text or "").split(SEG_SEP) if s]


# --------------------------------------------------------------------- 履歴 I/O
def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_history(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HISTORY_FIELDS})


def append_hits(path: Path, hits: list[dict]) -> None:
    if not hits:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HIT_FIELDS)
        if not exists:
            w.writeheader()
        for h in hits:
            w.writerow({k: h.get(k, "") for k in HIT_FIELDS})


# ----------------------------------------------------------------------- 検知
def _company_key(row: dict) -> str:
    """同一企業の名寄せキー。EDINETコード優先、無ければ証券コード。"""
    return row.get("edinetCode") or row.get("secCode") or row.get("ticker") or ""


def find_prior(history: list[dict], company_key: str, period_end: str) -> dict | None:
    """
    同じ企業で period_end より前（=過去）の有報のうち、最も新しいものを返す。
    無ければ None（＝初回で比較対象なし）。
    """
    prior = None
    for row in history:
        if _company_key(row) != company_key:
            continue
        pe = row.get("periodEnd", "")
        if pe and pe < period_end:
            if prior is None or pe > prior.get("periodEnd", ""):
                prior = row
    return prior


def detect_new_segments(
    prior: dict | None, current_segments: list[str]
) -> list[str]:
    """
    prior（過去の有報の履歴行）に対し、current にだけあるセグメント名を返す。
    prior が無い、または prior にセグメント記録が無い場合は [] （初回は判定しない）。
    """
    if not prior:
        return []
    prior_segs = set(split_segments(prior.get("segments", "")))
    if not prior_segs:
        return []
    return sorted(set(current_segments) - prior_segs)


def process(
    docmetas: list[dict],
    history: list[dict],
    fetch_segments,
    *,
    today: str,
    log=print,
) -> tuple[list[dict], list[dict]]:
    """
    docmetas を順に処理して、更新後の履歴と、新セグメント検知ヒットを返す。

    引数:
      docmetas       : EDINET から得た有報メタデータの一覧（各 dict）
      history        : 既存の履歴行（load_history の戻り）
      fetch_segments : docmeta -> list[str]（セグメント名一覧を返す関数）
      today          : 記録日（YYYY-MM-DD）

    ふるまい:
      - 既に履歴にある docID はスキップ（再取得・重複通知を防ぐ）。
      - periodEnd 昇順で処理する。こうすると同一 run 内に “1年前→今回” が
        両方含まれるとき、先に過去を記録してから今回で差分が取れる。
    """
    known_docids = {r.get("docID") for r in history}
    updated = list(history)
    hits: list[dict] = []

    todo = [d for d in docmetas if d.get("docID") not in known_docids]
    todo.sort(key=lambda d: d.get("periodEnd", ""))  # 過去→今回の順

    for meta in todo:
        try:
            segs = fetch_segments(meta)
        except Exception as e:  # 1銘柄の失敗で全体を止めない
            log(f"[skip] {meta.get('ticker')} {meta.get('filerName')}: {e}")
            continue

        ckey = _company_key(meta)
        prior = find_prior(updated, ckey, meta.get("periodEnd", ""))
        new_segs = detect_new_segments(prior, segs)

        row = {
            "detected_date": today,
            "docID": meta.get("docID", ""),
            "ticker": meta.get("ticker", ""),
            "secCode": meta.get("secCode", ""),
            "edinetCode": meta.get("edinetCode", ""),
            "filerName": meta.get("filerName", ""),
            "periodEnd": meta.get("periodEnd", ""),
            "submitDate": meta.get("submitDate", ""),
            "n_segments": len(segs),
            "segments": join_segments(segs),
        }
        updated.append(row)

        mark = ""
        if new_segs:
            mark = f"  ★新セグメント: {', '.join(new_segs)}"
            hits.append({
                "detected_date": today,
                "ticker": meta.get("ticker", ""),
                "filerName": meta.get("filerName", ""),
                "periodEnd": meta.get("periodEnd", ""),
                "prior_periodEnd": prior.get("periodEnd", "") if prior else "",
                "new_segments": join_segments(new_segs),
                "current_segments": join_segments(segs),
                "docID": meta.get("docID", ""),
            })
        log(f"[{meta.get('ticker')}] {meta.get('filerName')} "
            f"seg={len(segs)}{mark}")

    return updated, hits

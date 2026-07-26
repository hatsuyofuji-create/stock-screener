# -*- coding: utf-8 -*-
"""検知ロジック（src/detect.py）の単体テスト。ネットワーク不要。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import detect  # noqa: E402


def _meta(doc_id, ticker, edinet, period_end, submit):
    return {
        "docID": doc_id, "ticker": ticker, "secCode": ticker + "0",
        "edinetCode": edinet, "filerName": f"会社{ticker}",
        "periodEnd": period_end, "submitDate": submit, "docTypeCode": "120",
    }


def test_detect_new_segment_within_single_run():
    """同一runに“1年前→今回”があれば、増えたセグメントを1件検知する。"""
    docs = [
        _meta("D-2025", "7203", "E1", "2025-03-31", "2025-06-20"),  # 新しい方を先に置く
        _meta("D-2024", "7203", "E1", "2024-03-31", "2024-06-20"),
    ]
    segmap = {"D-2024": ["自動車", "金融"], "D-2025": ["自動車", "金融", "新モビリティ"]}

    updated, hits = detect.process(
        docs, [], lambda m: list(segmap[m["docID"]]), today="2025-06-25", log=lambda *_: None
    )
    assert len(updated) == 2
    assert len(hits) == 1
    assert detect.split_segments(hits[0]["new_segments"]) == ["新モビリティ"]
    assert hits[0]["prior_periodEnd"] == "2024-03-31"
    assert hits[0]["ticker"] == "7203"


def test_no_hit_when_unchanged():
    """セグメントが変わらなければ検知しない。"""
    docs = [
        _meta("E-2024", "6758", "E2", "2024-03-31", "2024-06-21"),
        _meta("E-2025", "6758", "E2", "2025-03-31", "2025-06-21"),
    ]
    segmap = {"E-2024": ["ゲーム", "音楽"], "E-2025": ["音楽", "ゲーム"]}  # 順序違いは同一
    _, hits = detect.process(
        docs, [], lambda m: list(segmap[m["docID"]]), today="2025-06-25", log=lambda *_: None
    )
    assert hits == []


def test_first_filing_is_baseline_only():
    """比較対象（過去の有報）が無い初回は検知しない（ベースライン記録のみ）。"""
    docs = [_meta("F-2025", "9999", "E9", "2025-03-31", "2025-06-25")]
    updated, hits = detect.process(
        docs, [], lambda m: ["A事業", "B事業"], today="2025-06-25", log=lambda *_: None
    )
    assert len(updated) == 1 and hits == []


def test_uses_prior_from_stored_history():
    """過去分が履歴CSV側にある場合でも、今回の有報と比較して検知できる。"""
    history = [{
        "detected_date": "2024-06-25", "docID": "G-2024", "ticker": "4000",
        "secCode": "40000", "edinetCode": "E4", "filerName": "会社4000",
        "periodEnd": "2024-03-31", "submitDate": "2024-06-20",
        "n_segments": "2", "segments": detect.join_segments(["医薬", "診断"]),
    }]
    docs = [_meta("G-2025", "4000", "E4", "2025-03-31", "2025-06-20")]
    _, hits = detect.process(
        docs, history, lambda m: ["医薬", "診断", "ヘルスケアIT"],
        today="2025-06-25", log=lambda *_: None,
    )
    assert len(hits) == 1
    assert detect.split_segments(hits[0]["new_segments"]) == ["ヘルスケアIT"]


def test_already_processed_docid_skipped():
    """既に履歴にある docID は再処理・再検知しない。"""
    history = [{
        "docID": "H-2025", "ticker": "5000", "edinetCode": "E5",
        "periodEnd": "2025-03-31", "segments": detect.join_segments(["X"]),
    }]
    docs = [_meta("H-2025", "5000", "E5", "2025-03-31", "2025-06-20")]
    called = []
    updated, hits = detect.process(
        docs, history, lambda m: called.append(m) or ["X", "Y"],
        today="2025-06-25", log=lambda *_: None,
    )
    assert called == []           # fetch されない
    assert len(updated) == 1      # 追加されない
    assert hits == []


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()

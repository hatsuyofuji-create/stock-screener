# -*- coding: utf-8 -*-
"""
セグメント抽出パーサ（src/segments.py）を、合成 XBRL 一式で検証する。
ネットワーク不要。`python -m pytest` でも `python tests/test_segments.py` でも動く。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.segments import parse_segments_from_zip  # noqa: E402
from tests.fixtures import build_zip  # noqa: E402


def test_extracts_extension_segments_and_labels():
    """会社独自セグメントの日本語ラベルが取れ、標準の合計メンバーは除外される。"""
    zip_bytes = build_zip([
        ("ElectronicsReportableSegmentsMember", "電子機器事業"),
        ("SoftwareReportableSegmentsMember", "ソフトウェア事業"),
    ], include_total=True)
    segs = parse_segments_from_zip(zip_bytes)
    assert segs == ["ソフトウェア事業", "電子機器事業"], segs  # ソート済み
    assert "報告セグメント計" not in segs  # 標準合計メンバーは除外


def test_reportable_segments_axis_variant():
    """軸名が ReportableSegmentsAxis でも 'segment' を含むので拾える。"""
    zip_bytes = build_zip(
        [("EnergyReportableSegmentsMember", "エネルギー事業")],
        axis="jpcrp_cor:ReportableSegmentsAxis", include_total=False,
    )
    assert parse_segments_from_zip(zip_bytes) == ["エネルギー事業"]


def test_label_fallback_to_humanized_local_name():
    """ラベルが引けない場合でも Local 名から素の名前を復元する。"""
    # ラベルにヒットしないよう、わざとラベル無しのZIPを別途作るのは煩雑なので、
    # ここでは _resolve_label / _humanize を直接確認する。
    from src.segments import _humanize, _resolve_label
    assert _humanize("NewBusinessReportableSegmentsMember") == "NewBusiness"
    # ラベル辞書が空 → Local 名から復元
    assert _resolve_label(
        "jpcrp030000-asr_E01234-000:NewBusinessSegmentMember", {}
    ) == "NewBusiness"


def test_generic_labels_excluded():
    """調整額など一般名称はセグメントとして扱わない。"""
    zip_bytes = build_zip([
        ("AbcReportableSegmentsMember", "調整額"),   # 拡張だが一般名称 → 除外
        ("XyzReportableSegmentsMember", "半導体事業"),
    ], include_total=False)
    assert parse_segments_from_zip(zip_bytes) == ["半導体事業"]


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()

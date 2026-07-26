# -*- coding: utf-8 -*-
"""
テスト用の合成 XBRL 一式（ZIP）を組み立てるヘルパ。

本物の EDINET 有報 ZIP の構造を最小限まねる:
  XBRL/PublicDoc/<name>.xbrl      … インスタンス（セグメント軸のメンバー入り）
  XBRL/PublicDoc/<name>_lab.xml   … 日本語ラベルリンクベース

これにより parse_segments_from_zip を“実物と同じ経路”で検証できる
（ネットワーク不要）。
"""

from __future__ import annotations

import io
import zipfile

# 拡張（会社独自）名前空間プレフィックス。EDINETコードを含むのが本物の目印。
_EXT = "jpcrp030000-asr_E01234-000"

_INSTANCE_TMPL = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl
    xmlns:xbrli="http://www.xbrl.org/2003/instance"
    xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
    xmlns:jpcrp_cor="http://disclosure.edinet-fsa.go.jp/taxonomy/jpcrp/2023-12-01/jpcrp_cor"
    xmlns:jppfs_cor="http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs/2023-12-01/jppfs_cor"
    xmlns:{ext}="http://disclosure.edinet-fsa.go.jp/taxonomy/jpcrp030000-asr/2023-12-01/{ext}">
  {contexts}
  {facts}
</xbrli:xbrl>
"""

_CONTEXT_TMPL = """
  <xbrli:context id="{cid}">
    <xbrli:entity>
      <xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E01234-000</xbrli:identifier>
      <xbrli:segment>
        <xbrldi:explicitMember dimension="{axis}">{member}</xbrldi:explicitMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-04-01</xbrli:startDate><xbrli:endDate>2025-03-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
"""

_LAB_TMPL = """<?xml version="1.0" encoding="UTF-8"?>
<link:linkbase
    xmlns:link="http://www.xbrl.org/2003/linkbase"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xml="http://www.w3.org/XML/1998/namespace">
  <link:labelLink xlink:type="extended" xlink:role="http://www.xbrl.org/2003/role/link">
    {entries}
  </link:labelLink>
</link:linkbase>
"""

_LAB_ENTRY_TMPL = """
    <link:loc xlink:type="locator" xlink:href="dummy.xsd#{elem_id}" xlink:label="loc_{key}"/>
    <link:labelArc xlink:type="arc"
        xlink:arcrole="http://www.xbrl.org/2003/arcrole/concept-label"
        xlink:from="loc_{key}" xlink:to="lab_{key}"/>
    <link:label xlink:type="resource" xlink:label="lab_{key}"
        xlink:role="http://www.xbrl.org/2003/role/label" xml:lang="ja">{text}</link:label>
"""


def build_zip(segments: list[tuple[str, str]], *,
              axis: str = "jpcrp_cor:OperatingSegmentsAxis",
              include_total: bool = True) -> bytes:
    """
    segments: [(member_local_name, japanese_label), ...]（会社独自の報告セグメント）
    include_total: True なら標準の「報告セグメント計」メンバーも混ぜる
                   （抽出時に除外されるべきノイズ）。
    戻り値: XBRL 一式 ZIP のバイト列。
    """
    contexts = []
    lab_entries = []
    for i, (local, label) in enumerate(segments):
        member = f"{_EXT}:{local}"
        elem_id = f"{_EXT}_{local}"          # EDINET 慣例の要素ID（QNameの ':'→'_'）
        contexts.append(_CONTEXT_TMPL.format(cid=f"C{i}", axis=axis, member=member))
        lab_entries.append(_LAB_ENTRY_TMPL.format(key=f"seg{i}", elem_id=elem_id, text=label))

    if include_total:
        # 標準タクソノミの合計メンバー（拡張ではない＝抽出対象外になるべき）
        total_member = "jpcrp_cor:ReportableSegmentsTotalMember"
        contexts.append(_CONTEXT_TMPL.format(cid="CT", axis=axis, member=total_member))
        lab_entries.append(_LAB_ENTRY_TMPL.format(
            key="total", elem_id="jpcrp_cor_ReportableSegmentsTotalMember", text="報告セグメント計"))

    instance = _INSTANCE_TMPL.format(
        ext=_EXT, contexts="".join(contexts),
        facts='<jppfs_cor:NetSales contextRef="C0" unitRef="JPY" decimals="-6">100</jppfs_cor:NetSales>',
    )
    lab = _LAB_TMPL.format(entries="".join(lab_entries))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        base = "XBRL/PublicDoc/jpcrp030000-asr-001_E01234-000_2025-03-31_01_2025-06-20"
        zf.writestr(base + ".xbrl", instance)
        zf.writestr(base + "_lab.xml", lab)
        zf.writestr(base + "_lab-en.xml", "<x/>")  # 英語ラベル（選ばれないこと確認用）
    return buf.getvalue()

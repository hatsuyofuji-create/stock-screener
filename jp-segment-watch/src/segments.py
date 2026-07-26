# -*- coding: utf-8 -*-
"""
XBRL（EDINET 有価証券報告書の ZIP）から「事業セグメント名」の集合を取り出す。

■ セグメントは XBRL でどう表現されるか
  セグメント別の数値は、コンテキストに “セグメント軸” の明示メンバー
  （explicitMember）が付いた形で入っている。例:

    <xbrldi:explicitMember dimension="jpcrp_cor:OperatingSegmentsAxis">
      jpcrp030000-asr_E01234-000:ElectronicsReportableSegmentsMember
    </xbrldi:explicitMember>

  - dimension … セグメントの軸。要素名に "Segment" を含む（会社により
                OperatingSegmentsAxis / ReportableSegmentsAxis 等）。
  - メンバー本体（テキスト）… 各セグメント。報告セグメントは会社独自の
                拡張要素（名前空間プレフィックスに EDINETコード _Exxxxx-000 を
                含む）。合計・調整額・全社などは標準タクソノミ（jpXXX_cor）の
                メンバーで来ることが多い。

  セグメントの“名前”（例: 電子機器事業）は本体には無く、ラベルリンクベース
  （*_lab.xml）の標準ラベル（role=label, xml:lang="ja"）から引く。

■ 本モジュールの方針
  1. インスタンス（*.xbrl）から、セグメント軸に紐づくメンバーを全部集める。
  2. 会社独自メンバー（拡張名前空間）だけを“実セグメント”として残す
     （標準メンバーの合計・調整額・全社などは自然に外れる）。
  3. ラベルリンクベースから日本語名を引く。引けなければ要素IDから復元。
  4. 明らかな非セグメント名（合計・調整額 等）は保険で除外。

  ねらいは厳密な会計集計ではなく「セグメント名の集合を年ごとに安定して
  得る」こと。年次で集合を比較して“増えた名前”を拾うのが目的。
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

# セグメント名として扱わない一般名称（拡張名前空間フィルタの保険）。
# 「その他」は実際の報告セグメントであり得るので除外しない。
_GENERIC_LABELS = {
    "合計",
    "報告セグメント計",
    "報告セグメント合計",
    "調整額",
    "消去又は全社",
    "全社",
    "セグメント間取引消去",
    "連結",
    "個別",
    "連結財務諸表計上額",
}

# 標準タクソノミの名前空間プレフィックス（会社独自＝拡張ではない印）。
_STD_PREFIXES = ("jpcrp", "jppfs", "jpdei", "jpigp", "jpctl", "jplvh", "jpsps")


def _localname(tag: str) -> str:
    """'{ns}Local' or 'prefix:Local' から Local だけ取り出す。"""
    if "}" in tag:
        tag = tag.rsplit("}", 1)[1]
    if ":" in tag:
        tag = tag.rsplit(":", 1)[1]
    return tag


def _is_extension_member(qname: str) -> bool:
    """メンバー QName が会社独自（拡張）なら True。標準タクソノミなら False。"""
    prefix = qname.split(":", 1)[0] if ":" in qname else ""
    if not prefix:
        return False
    # 拡張プレフィックスは EDINETコード（_E数字-数字）を含むのが目印
    if re.search(r"_E\d{5}-\d{3}", prefix):
        return True
    # 念のため：標準プレフィックスで始まるものは拡張ではない
    return not prefix.startswith(_STD_PREFIXES)


def parse_segments_from_zip(zip_bytes: bytes) -> list[str]:
    """
    XBRL 一式 ZIP（EDINET type=1）から事業セグメント名の一覧（ソート済み）を返す。
    セグメントが取れない／単一セグメントの場合は空リスト。
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        inst_name = _pick_instance(names)
        if inst_name is None:
            return []
        instance = zf.read(inst_name)
        lab_name = _pick_label(names)
        labels = _parse_labels(zf.read(lab_name)) if lab_name else {}

    member_qnames = _collect_segment_members(instance)
    out: set[str] = set()
    for qname in member_qnames:
        if not _is_extension_member(qname):
            continue  # 標準メンバー（合計・調整額・全社 等）は落とす
        name = _resolve_label(qname, labels)
        if not name or name in _GENERIC_LABELS:
            continue
        out.add(name)
    return sorted(out)


# --------------------------------------------------------------- ZIP 内ファイル選択
def _pick_instance(names: list[str]) -> str | None:
    """本文（PublicDoc）配下の XBRL インスタンス（*.xbrl）を選ぶ。"""
    cands = [
        n for n in names
        if n.lower().endswith(".xbrl") and _in_publicdoc(n)
    ]
    if not cands:
        cands = [n for n in names if n.lower().endswith(".xbrl")]
    if not cands:
        return None
    # 有報本文は jpcrp...asr... が付く。無ければ最初の候補。
    for n in cands:
        base = n.rsplit("/", 1)[-1].lower()
        if base.startswith("jpcrp") and "asr" in base:
            return n
    return cands[0]


def _pick_label(names: list[str]) -> str | None:
    """日本語ラベルリンクベース（*_lab.xml。*_lab-en.xml は除外）を選ぶ。"""
    cands = [
        n for n in names
        if n.lower().endswith("_lab.xml") and _in_publicdoc(n)
    ]
    if not cands:
        cands = [n for n in names if n.lower().endswith("_lab.xml")]
    return cands[0] if cands else None


def _in_publicdoc(name: str) -> bool:
    return "/publicdoc/" in name.lower() or name.lower().startswith("publicdoc/")


# ------------------------------------------------------- インスタンスからメンバー収集
def _collect_segment_members(instance_bytes: bytes) -> set[str]:
    """
    インスタンス中の explicitMember のうち、dimension（軸）名に 'segment' を
    含むものの本体（メンバー QName 文字列）を集めて返す。
    """
    members: set[str] = set()
    # iterparse でメモリを抑えつつ explicitMember だけ拾う
    for _event, elem in ET.iterparse(io.BytesIO(instance_bytes), events=("end",)):
        if _localname(elem.tag) != "explicitMember":
            continue
        dim = elem.get("dimension") or ""
        if "segment" not in _localname(dim).lower():
            elem.clear()
            continue
        text = (elem.text or "").strip()
        if text:
            members.add(text)
        elem.clear()
    return members


# ----------------------------------------------------------- ラベルリンクベース解決
_XLINK = "{http://www.w3.org/1999/xlink}"
_XMLLANG = "{http://www.w3.org/XML/1998/namespace}lang"
_ROLE_LABEL = "http://www.xbrl.org/2003/role/label"


def _parse_labels(lab_bytes: bytes) -> dict[str, str]:
    """
    ラベルリンクベースを解析し、要素ID（loc の href フラグメント）→ 日本語標準
    ラベル の対応を返す。
    構造: loc(xlink:label→href#id) / labelArc(from→to) / label(xlink:label,role,lang).
    """
    try:
        root = ET.fromstring(lab_bytes)
    except ET.ParseError:
        return {}

    loc_to_id: dict[str, str] = {}     # locのxlink:label -> 要素ID(フラグメント)
    arcs: list[tuple[str, str]] = []   # (from, to)
    # labelのxlink:label -> {(role,lang): text}
    label_text: dict[str, dict[tuple[str, str], str]] = {}

    for elem in root.iter():
        ln = _localname(elem.tag)
        if ln == "loc":
            href = elem.get(f"{_XLINK}href") or ""
            xlabel = elem.get(f"{_XLINK}label") or ""
            if "#" in href and xlabel:
                loc_to_id[xlabel] = href.rsplit("#", 1)[1]
        elif ln == "labelArc":
            frm = elem.get(f"{_XLINK}from") or ""
            to = elem.get(f"{_XLINK}to") or ""
            if frm and to:
                arcs.append((frm, to))
        elif ln == "label":
            xlabel = elem.get(f"{_XLINK}label") or ""
            role = elem.get(f"{_XLINK}role") or ""
            lang = elem.get(_XMLLANG) or ""
            if xlabel:
                label_text.setdefault(xlabel, {})[(role, lang)] = (elem.text or "").strip()

    # from(loc) -> to(label) を辿って 要素ID -> 日本語標準ラベル を作る
    id_to_label: dict[str, str] = {}
    for frm, to in arcs:
        elem_id = loc_to_id.get(frm)
        if not elem_id:
            continue
        texts = label_text.get(to)
        if not texts:
            continue
        text = _prefer_ja_label(texts)
        if text:
            id_to_label[elem_id] = text
    return id_to_label


def _prefer_ja_label(texts: dict[tuple[str, str], str]) -> str:
    """標準ラベル(role=label)・日本語を優先して1つ選ぶ。"""
    # 1) 標準ラベル × 日本語
    for (role, lang), t in texts.items():
        if role == _ROLE_LABEL and lang == "ja" and t:
            return t
    # 2) 日本語ならなんでも
    for (role, lang), t in texts.items():
        if lang == "ja" and t:
            return t
    # 3) 標準ラベルならなんでも
    for (role, lang), t in texts.items():
        if role == _ROLE_LABEL and t:
            return t
    # 4) 最後の手段
    for t in texts.values():
        if t:
            return t
    return ""


def _resolve_label(qname: str, labels: dict[str, str]) -> str:
    """
    メンバー QName（prefix:Local）を日本語名に解決する。
    要素ID は EDINET 慣例で prefix と Local を '_' で繋いだ形（= QName の ':' を '_' に）。
    見つからなければ Local 名末尾一致で救済、それも無ければ Local から復元。
    """
    if qname in labels:  # 稀に QName そのものがキーのことがある
        return labels[qname]
    elem_id = qname.replace(":", "_", 1)
    if elem_id in labels:
        return labels[elem_id]
    # 末尾一致（プレフィックスの綴れ違いを救済）
    local = qname.split(":", 1)[1] if ":" in qname else qname
    suffix = "_" + local
    for key, val in labels.items():
        if key.endswith(suffix):
            return val
    # ラベルが無ければ Local 名から人間可読名を復元
    return _humanize(local)


def _humanize(local: str) -> str:
    """
    'ElectronicsReportableSegmentsMember' のような Local 名から、後ろの定型語を
    落として素の名前を返す（ラベルが引けなかったときの保険）。
    """
    for suf in ("ReportableSegmentsMember", "OperatingSegmentsMember",
                "SegmentsMember", "SegmentMember", "Member"):
        if local.endswith(suf):
            local = local[: -len(suf)]
            break
    return local or ""

# -*- coding: utf-8 -*-
"""
=====================================================================
 短信PDFの取得（TDnet / 会社IR）
=====================================================================
 決算短信PDFの配布元は TDnet(適時開示情報)です。J-Quantsは短信PDF自体は
 配布しません。ここでは:
   1) download_pdf(url, dest) : URLからPDFを保存する（確実に動く土台）
   2) TDnet からの自動検索は「方針メモ」を残しつつ、環境依存が大きいため
      まずは手動DL or URL指定で運用し、後から自動化する構成にしています。

 自動取得を本格化するときの方針:
   - TDnet「適時開示情報閲覧サービス」(www.release.tdnet.info) は日付単位で
     開示一覧(I-list)を返す。J-Quants /fins/announcement で開示日を特定し、
     その日の一覧から対象銘柄の「決算短信」PDFリンクを拾うのが定石。
   - 直近30日程度しか遡れない点、HTML構造が変わりうる点に注意（要保守）。
   - 過去分は EDINET(四半期/半期報告書, 公式API) や会社IRページも併用する。
=====================================================================
"""

from __future__ import annotations
import os
import time

import requests


def download_pdf(url: str, dest: str, retries: int = 4) -> str:
    """URLからPDFをダウンロードして dest に保存し、そのパスを返す。"""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    delay = 2.0
    last: Exception | None = None
    headers = {"User-Agent": "jp-order-tracker/0.1 (+research use)"}
    for _ in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "")
            if "pdf" not in ctype.lower() and not r.content[:4] == b"%PDF":
                raise RuntimeError(f"PDFではないレスポンス (Content-Type={ctype})")
            with open(dest, "wb") as f:
                f.write(r.content)
            return dest
        except requests.RequestException as e:
            last = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"PDFのダウンロードに失敗: {url} ({last})")

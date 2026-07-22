# -*- coding: utf-8 -*-
"""
LINE 通知（Messaging API）。

LINE Notify は終了済みのため、公式アカウントの Messaging API で push する。
必要な環境変数:
  - LINE_CHANNEL_ACCESS_TOKEN
  - LINE_USER_ID（自分のユーザーID Uxxxx…）

どちらか未設定なら、送信せずコンソール出力にフォールバックする
（鍵が無い間も pipeline は止まらない）。
"""

from __future__ import annotations

import os

import requests

_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_TIMEOUT = 15


def notify(message: str) -> bool:
    """
    LINE に message を push する。
    戻り値: 実際に送信できたら True、フォールバック（コンソール）なら False。
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("LINE_USER_ID", "").strip()

    if not (token and user_id):
        print("[LINE未設定→コンソール出力]\n" + message)
        return False

    try:
        r = requests.post(
            _PUSH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"to": user_id, "messages": [{"type": "text", "text": message}]},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        print("[LINE送信OK]")
        return True
    except Exception as e:  # 通知失敗で pipeline を止めない
        print(f"[LINE送信失敗→コンソール出力] {e}\n{message}")
        return False

"""
銘柄名の登録DB（簡易版）。

★注意★ これは「一式で動かすための簡易版」です。
　上原さんの手元に**本物の database.py**（登録済み銘柄名などが入ったもの）があれば、
　このファイルを本物に差し替えてください。中身が空でもアプリは動きます
　（その場合、会社名は空欄になり、AIへのヒントに使われないだけです）。

tanshin_collector.py が使う関数は次の2つだけ:
  - init_db()        … 起動時にテーブルを用意する
  - get_stock(code)  … コードから {"code","name"} を返す（無ければ None）
おまけで add_stock(code, name) も用意（銘柄名を登録したいとき用）。
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "stocks.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS stocks ("
            "  code TEXT PRIMARY KEY,"
            "  name TEXT"
            ")"
        )


def get_stock(code):
    """コードから {'code','name'} を返す。未登録なら None。"""
    if not code:
        return None
    with _conn() as c:
        row = c.execute(
            "SELECT code, name FROM stocks WHERE code = ?", (str(code),)
        ).fetchone()
        return dict(row) if row else None


def add_stock(code, name):
    """銘柄名を登録/更新する（任意）。"""
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO stocks (code, name) VALUES (?, ?)",
            (str(code), name),
        )

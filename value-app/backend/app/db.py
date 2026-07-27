"""DB 接続（仕様書 2章：SQLite 初期 → 将来 PostgreSQL）。"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# デフォルトはリポジトリ内の SQLite ファイル。DATABASE_URL 環境変数で上書き可能。
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(os.path.dirname(__file__)), "value_app.db"),
)

# SQLite の場合のみ check_same_thread=False（FastAPI のマルチスレッド対応）。
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依存性注入用の DB セッション。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """全テーブルを作成する。"""
    from . import models  # noqa: F401  (モデル登録のため import)
    Base.metadata.create_all(bind=engine)

"""测试辅助：为流程/端点测试提供隔离且已注资的 Credits 环境。

Credits v1 起 `standard_song` 定价 30，POST /generate 会真实扣费。若仍走默认
`credits_service.SessionLocal`（开发库 music_platform.db，且无 user_credits 表），
流程测试会被判成 insufficient_credits 并污染开发库。这里把 SessionLocal 指向临时
SQLite 建表并给指定用户注资，让流程测试继续只测自己关心的东西。
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.services import credits_service

DEFAULT_GRANT = 100_000


def install_credits_env(monkeypatch, tmp_path, users: Iterable[str], grant: int = DEFAULT_GRANT):
    """建临时 Credits 库（含 user_credits / credits_transactions）并为用户注资。"""
    eng = create_engine(
        f"sqlite:///{tmp_path / 'credits.env.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(credits_service, "SessionLocal", sessionmaker(bind=eng))
    for u in users:
        credits_service.add_credits(u, grant, "admin_adjustment", description="test grant")
    return eng

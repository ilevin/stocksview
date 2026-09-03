"""数据库连接与初始化：SQLite 自动建库；结构升级自 v0.03 起由 Alembic 负责。"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    """sqlite:///./data/market.db 形式的相对路径：确保目录存在，否则建库会失败。"""
    if not url.startswith("sqlite:///"):
        return
    db_path = url.removeprefix("sqlite:///")
    if db_path and db_path != ":memory:":
        parent = Path(db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(url: str):
    _ensure_sqlite_dir(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        # v0.03：让外键约束真正生效（如 watchlist.tag_id 的 RESTRICT 删除保护）。
        # 全库既有外键仅 watchlist / index_watchlist -> instrument，不存在删除
        # instrument 的代码路径，开启 enforcement 不影响既有行为（design D4）。
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def init_db(engine) -> None:
    """建表（幂等）。模型必须先导入注册到 Base.metadata。"""
    import app.models  # noqa: F401  确保模型注册

    Base.metadata.create_all(bind=engine)
    logger.info("数据库表已就绪")


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def check_database(session: Session) -> bool:
    try:
        session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("数据库健康检查失败")
        return False

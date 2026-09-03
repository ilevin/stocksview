"""Alembic 迁移集成测试（v0.03 design D5/D6/D7）。

覆盖：
- v0.02 库（有表、无 alembic_version 记录）stamp 基线后无损升级到 v0.03；
- 未 stamp 直接 upgrade head 应失败且数据不变；
- 空库 upgrade head 全链；
- upgrade head 产物与模型 create_all 产物 schema 一致（防迁移与模型漂移）；
- batch 重建后 watchlist 唯一约束保留。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V002_TABLES = {
    "instrument",
    "watchlist",
    "index_watchlist",
    "quote_snapshot",
    "fundamental_snapshot",
    "app_setting",
    "trading_calendar",
}
V003_NEW_TABLES = {"tag", "job_status", "watchlist_tag"}


def _alembic_config(db_path: Path) -> Config:
    """programmatic API：注入临时库 url，不依赖 CWD 的 config.yaml。"""
    cfg = Config()
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _make_v002_db(db_path: Path) -> None:
    """构造 v0.02 库：跑到基线后删除版本表，模拟“有 v0.02 表、无版本记录”。"""
    command.upgrade(_alembic_config(db_path), "0001_v002_baseline")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE alembic_version"))
    engine.dispose()


def _seed_v002_data(db_path: Path) -> None:
    """向 v0.02 库写入各类代表性数据，用于升级后无损断言。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO instrument (instrument_id, symbol, name, market, asset_type,"
                " exchange, currency, is_active, created_at, updated_at)"
                " VALUES ('CN:STOCK:600519', '600519', '贵州茅台', 'CN', 'STOCK', NULL, 'CNY', 1,"
                " '2026-08-01 00:00:00', '2026-08-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO instrument (instrument_id, symbol, name, market, asset_type,"
                " exchange, currency, is_active, created_at, updated_at)"
                " VALUES ('CN:INDEX:000001', '000001', '上证指数', 'CN', 'INDEX', NULL, 'CNY', 1,"
                " '2026-08-01 00:00:00', '2026-08-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO watchlist (instrument_id, sort_order, created_at)"
                " VALUES ('CN:STOCK:600519', 10, '2026-08-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO index_watchlist (instrument_id, sort_order, created_at)"
                " VALUES ('CN:INDEX:000001', 10, '2026-08-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO quote_snapshot (instrument_id, price, change_percent, source,"
                " source_timestamp, fetched_at, created_at)"
                " VALUES ('CN:STOCK:600519', 1500.0, 1.25, 'tencent', NULL,"
                " '2026-08-20 09:31:00', '2026-08-20 09:31:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO fundamental_snapshot (instrument_id, trade_date, pe_ttm, pb, source,"
                " fetched_at, created_at)"
                " VALUES ('CN:STOCK:600519', '2026-08-19', 25.5, 8.2, 'tushare',"
                " '2026-08-20 09:00:00', '2026-08-20 09:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO trading_calendar (market, trade_date, is_open)"
                " VALUES ('CN', '2026-08-20', 1)"
            )
        )
    engine.dispose()


def test_v002_db_stamp_then_upgrade_preserves_data(tmp_path):
    """v0.02 库：stamp 基线 -> upgrade head，四类数据无损、tag_id 全 NULL、新表就绪。"""
    db = tmp_path / "market.db"
    _make_v002_db(db)
    _seed_v002_data(db)

    cfg = _alembic_config(db)
    command.stamp(cfg, "0001_v002_baseline")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db}")
    insp = sa.inspect(engine)
    tables = set(insp.get_table_names()) - {"alembic_version"}
    assert V002_TABLES | V003_NEW_TABLES == tables

    with engine.connect() as conn:
        # 原有数据完整保留
        assert conn.execute(sa.text("SELECT name FROM instrument WHERE instrument_id='CN:STOCK:600519'")).scalar() == "贵州茅台"
        assert conn.execute(sa.text("SELECT count(*) FROM watchlist")).scalar() == 1
        assert conn.execute(sa.text("SELECT count(*) FROM index_watchlist")).scalar() == 1
        assert conn.execute(sa.text("SELECT price FROM quote_snapshot")).scalar() == 1500.0
        assert conn.execute(sa.text("SELECT pe_ttm FROM fundamental_snapshot")).scalar() == 25.5
        assert conn.execute(sa.text("SELECT count(*) FROM trading_calendar")).scalar() == 1
        # 既有自选默认无标签（v0.02 库无标签数据 -> 关联表为空）
        assert conn.execute(sa.text("SELECT count(*) FROM watchlist_tag")).scalar() == 0
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "0003_v003b"

        # batch 重建后唯一约束仍在
        uq = {c["name"]: c["column_names"] for c in insp.get_unique_constraints("watchlist")}
        assert uq.get("uq_watchlist_instrument") == ["instrument_id"]
    engine.dispose()


def test_v002_db_upgrade_without_stamp_fails_and_keeps_data(tmp_path):
    """未 stamp 直接 upgrade head：基线建表失败、流程终止且数据无损。"""
    db = tmp_path / "market.db"
    _make_v002_db(db)
    _seed_v002_data(db)

    with pytest.raises(Exception):
        command.upgrade(_alembic_config(db), "head")

    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ))}
        # 基线建表失败即止：不落版本记录、不产生 v0.03 新表、数据无损
        if "alembic_version" in tables:  # 失败前 alembic 可能已建空版本表
            assert conn.execute(sa.text("SELECT count(*) FROM alembic_version")).scalar() == 0
        assert "tag" not in tables and "job_status" not in tables
        assert conn.execute(sa.text("SELECT count(*) FROM instrument")).scalar() == 2
        assert conn.execute(sa.text("SELECT count(*) FROM watchlist")).scalar() == 1
    engine.dispose()


def test_empty_db_upgrade_head_full_chain(tmp_path):
    """空库 upgrade head：全链执行，产出 v0.03 完整结构。"""
    db = tmp_path / "market.db"
    command.upgrade(_alembic_config(db), "head")

    engine = create_engine(f"sqlite:///{db}")
    insp = sa.inspect(engine)
    tables = set(insp.get_table_names()) - {"alembic_version"}
    assert V002_TABLES | V003_NEW_TABLES == tables
    assert "tag_id" not in {c["name"] for c in insp.get_columns("watchlist")}
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "0003_v003b"
    engine.dispose()


def test_v003_single_tag_data_migrated_to_association_table(tmp_path):
    """0003 搬迁：v0.03a 的 watchlist.tag_id 单标签数据无损进入 watchlist_tag。"""
    db = tmp_path / "migrate.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "0002_v003")

    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO instrument (instrument_id, symbol, name, market, asset_type,"
                " exchange, currency, is_active, created_at, updated_at)"
                " VALUES ('CN:STOCK:600519', '600519', '贵州茅台', 'CN', 'STOCK', NULL, 'CNY', 1,"
                " '2026-08-01 00:00:00', '2026-08-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO tag (id, name, created_at, updated_at)"
                " VALUES (1, '高股息', '2026-09-01 00:00:00', '2026-09-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO watchlist (instrument_id, sort_order, created_at, tag_id)"
                " VALUES ('CN:STOCK:600519', 10, '2026-08-01 00:00:00', 1)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO watchlist (instrument_id, sort_order, created_at, tag_id)"
                " VALUES ('CN:INDEX:000001', 20, '2026-08-01 00:00:00', NULL)"
            )
        )
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT watchlist_id, tag_id FROM watchlist_tag")).fetchall()
        assert rows == [(1, 1)]  # 仅有标签的行搬迁；tag_id NULL 的行不产生关联
    insp = sa.inspect(engine)
    assert "tag_id" not in {c["name"] for c in insp.get_columns("watchlist")}
    engine.dispose()


def test_upgraded_schema_matches_models(tmp_path):
    """upgrade head 产物与模型 create_all 产物一致（列名/类型/可空、索引、唯一约束）。"""
    migrated_db = tmp_path / "migrated.db"
    command.upgrade(_alembic_config(migrated_db), "head")

    models_db = tmp_path / "models.db"
    models_engine = create_engine(f"sqlite:///{models_db}")
    import app.models  # noqa: F401
    from app.db import Base

    Base.metadata.create_all(models_engine)

    migrated_engine = create_engine(f"sqlite:///{migrated_db}")
    m_insp, c_insp = sa.inspect(migrated_engine), sa.inspect(models_engine)

    def _schema(insp):
        tables = sorted(set(insp.get_table_names()) - {"alembic_version"})
        result = {}
        for tbl in tables:
            cols = {
                c["name"]: (str(c["type"]), c["nullable"])
                for c in insp.get_columns(tbl)
            }
            indexes = {
                i["name"]: (tuple(i["column_names"]), i["unique"])
                for i in insp.get_indexes(tbl)
            }
            uqs = {
                c["name"]: tuple(c["column_names"])
                for c in insp.get_unique_constraints(tbl)
            }
            result[tbl] = (cols, indexes, uqs)
        return result

    assert _schema(m_insp) == _schema(c_insp), "迁移产物与模型 create_all 产物存在漂移"
    migrated_engine.dispose()
    models_engine.dispose()


def test_delete_referenced_tag_blocked_by_db(tmp_path):
    """PRAGMA foreign_keys=ON 生效：DB 层 RESTRICT 阻止删除被引用标签（经 watchlist_tag 关联）。"""
    from sqlalchemy.exc import IntegrityError

    from app.db import create_db_engine, init_db, make_session_factory
    from app.models import Instrument, Tag, Watchlist, WatchlistTag

    db = tmp_path / "guard.db"
    engine = create_db_engine(f"sqlite:///{db}")
    init_db(engine)
    factory = make_session_factory(engine)

    with factory() as session:
        session.add(
            Instrument(
                instrument_id="CN:STOCK:600519",
                symbol="600519",
                name="贵州茅台",
                market="CN",
                asset_type="STOCK",
                currency="CNY",
            )
        )
        tag = Tag(name="高股息")
        session.add(tag)
        session.flush()
        row = Watchlist(instrument_id="CN:STOCK:600519", sort_order=0)
        session.add(row)
        session.flush()
        session.add(WatchlistTag(watchlist_id=row.id, tag_id=tag.id))
        session.commit()

    with factory() as session:
        tag = session.query(Tag).one()
        session.delete(tag)
        with pytest.raises(IntegrityError):
            session.flush()
    engine.dispose()

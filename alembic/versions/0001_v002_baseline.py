"""v0.02 基线：v0.02 正式发布时的数据库结构。

基线内容逐表对照线上 v0.02 库（data/market.db）的实际 DDL 生成：
约束名（uq_*）、索引名（ix_*）、外键（匿名，与 create_all 产物一致）均保持一致。
已有 v0.02 库升级时先 `alembic stamp 0001_v002_baseline` 打标，再 upgrade head。

Revision ID: 0001_v002_baseline
Revises:
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_v002_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("asset_type", sa.String(length=8), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instrument_instrument_id", "instrument", ["instrument_id"], unique=True
    )

    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id", name="uq_watchlist_instrument"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.instrument_id"]),
    )

    op.create_table(
        "index_watchlist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id", name="uq_index_watchlist_instrument"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.instrument_id"]),
    )

    op.create_table(
        "quote_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("change_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("volume_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("previous_close", sa.Numeric(20, 6), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_snapshot_instrument_id", "quote_snapshot", ["instrument_id"], unique=False)

    op.create_table(
        "fundamental_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("pe_ttm", sa.Numeric(12, 4), nullable=True),
        sa.Column("pb", sa.Numeric(12, 4), nullable=True),
        sa.Column("dividend_yield_ttm", sa.Numeric(12, 4), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id", "trade_date", name="uq_fundamental_instrument_date"),
    )
    op.create_index(
        "ix_fundamental_snapshot_instrument_id", "fundamental_snapshot", ["instrument_id"], unique=False
    )

    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "trading_calendar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "trade_date", name="uq_calendar_market_date"),
    )


def downgrade() -> None:
    op.drop_table("trading_calendar")
    op.drop_table("app_setting")
    op.drop_index("ix_fundamental_snapshot_instrument_id", table_name="fundamental_snapshot")
    op.drop_table("fundamental_snapshot")
    op.drop_index("ix_quote_snapshot_instrument_id", table_name="quote_snapshot")
    op.drop_table("quote_snapshot")
    op.drop_table("index_watchlist")
    op.drop_table("watchlist")
    op.drop_index("ix_instrument_instrument_id", table_name="instrument")
    op.drop_table("instrument")

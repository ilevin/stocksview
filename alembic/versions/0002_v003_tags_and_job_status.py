"""v0.03：新增 tag、job_status 表，watchlist 增加 tag_id 外键。

- tag / job_status 为新表（create_table）；
- watchlist.tag_id 经 batch_alter_table（表重建）添加，保留既有数据与
  uq_watchlist_instrument 唯一约束（SQLite 结构变更统一 batch 模式，技术方案 §18）；
- 既有 Watchlist 行 tag_id 保持 NULL（默认无标签）。

Revision ID: 0002_v003
Revises: 0001_v002_baseline
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_v003"
down_revision: Union[str, None] = "0001_v002_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_tag_name"),
    )

    op.create_table(
        "job_status",
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("job_name"),
    )

    with op.batch_alter_table("watchlist") as batch:
        batch.add_column(sa.Column("tag_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_watchlist_tag_id_tag", "tag", ["tag_id"], ["id"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    with op.batch_alter_table("watchlist") as batch:
        batch.drop_column("tag_id")

    op.drop_table("job_status")
    op.drop_table("tag")

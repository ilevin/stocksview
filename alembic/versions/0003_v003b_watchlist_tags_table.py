"""v0.03b：条目与标签改为多对多（需求修订，见 design D2 修订）。

- 新增 watchlist_tag 关联表（watchlist_id CASCADE / tag_id RESTRICT / 联合唯一）；
- 既有 watchlist.tag_id 单标签数据搬入关联表（每行一条关联，零丢失）；
- batch 移除 watchlist.tag_id 列与外键。

Revision ID: 0003_v003b
Revises: 0002_v003
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_v003b"
down_revision: Union[str, None] = "0002_v003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("watchlist_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watchlist_id", "tag_id", name="uq_watchlist_tag"),
        sa.ForeignKeyConstraint(
            ["watchlist_id"],
            ["watchlist.id"],
            ondelete="CASCADE",
            name="fk_watchlist_tag_watchlist_id",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tag.id"], ondelete="RESTRICT", name="fk_watchlist_tag_tag_id"
        ),
    )
    # 既有单标签数据搬迁：tag_id 非空的每个自选行生成一条关联
    op.execute(
        "INSERT INTO watchlist_tag (watchlist_id, tag_id) "
        "SELECT id, tag_id FROM watchlist WHERE tag_id IS NOT NULL"
    )
    with op.batch_alter_table("watchlist") as batch:
        batch.drop_constraint("fk_watchlist_tag_id_tag", type_="foreignkey")
        batch.drop_column("tag_id")


def downgrade() -> None:
    # 有损降级：一个条目多个标签时仅保留 id 最小的标签
    with op.batch_alter_table("watchlist") as batch:
        batch.add_column(sa.Column("tag_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_watchlist_tag_id_tag", "tag", ["tag_id"], ["id"], ondelete="RESTRICT"
        )
    op.execute(
        "UPDATE watchlist SET tag_id = "
        "(SELECT MIN(tag_id) FROM watchlist_tag WHERE watchlist_tag.watchlist_id = watchlist.id)"
    )
    op.drop_table("watchlist_tag")

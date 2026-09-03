"""自选条目与标签的多对多关联模型（v0.03b 需求修订：一个条目可关联多个标签）。

- watchlist_id ON DELETE CASCADE：删除自选条目时自动清理关联；
- tag_id ON DELETE RESTRICT：被引用的标签由业务层计数检查拦截删除，
  此处为数据库层兜底（PRAGMA foreign_keys=ON 生效）。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WatchlistTag(Base):
    __tablename__ = "watchlist_tag"
    __table_args__ = (UniqueConstraint("watchlist_id", "tag_id", name="uq_watchlist_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("watchlist.id", ondelete="CASCADE", name="fk_watchlist_tag_watchlist_id"),
    )
    tag_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tag.id", ondelete="RESTRICT", name="fk_watchlist_tag_tag_id"),
    )

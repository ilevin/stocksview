"""标签模型：股票 / ETF 自选条目的用户自定义分类（v0.03）。

标签先在标签管理中创建，再关联到 Watchlist 条目（tag_id 可空）；
存在引用时禁止删除（业务层计数检查 + 数据库 RESTRICT 外键双层保护）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tag(Base):
    """标签；name 全库唯一，去除首尾空格后非空且不超过 50 字符（由 TagService 校验）。"""

    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("name", name="uq_tag_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

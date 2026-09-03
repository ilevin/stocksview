"""自选列表模型：股票/ETF 自选与指数配置彼此独立。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Watchlist(Base):
    """股票 / ETF 自选（仅 STOCK / ETF）。标签关联见 watchlist_tag（多对多，v0.03b）。"""

    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("instrument_id", name="uq_watchlist_instrument"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(64), ForeignKey("instrument.instrument_id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IndexWatchlist(Base):
    """首页指数行情区配置（仅 INDEX）。"""

    __tablename__ = "index_watchlist"
    __table_args__ = (UniqueConstraint("instrument_id", name="uq_index_watchlist_instrument"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(64), ForeignKey("instrument.instrument_id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

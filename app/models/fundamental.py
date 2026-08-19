"""估值快照模型：最近一次估值（主要 A 股股票；指数与 ETF 不写入）。"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FundamentalSnapshot(Base):
    __tablename__ = "fundamental_snapshot"
    __table_args__ = (
        UniqueConstraint("instrument_id", "trade_date", name="uq_fundamental_instrument_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(64), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    pe_ttm: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    pb: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    dividend_yield_ttm: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(32))  # tushare
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

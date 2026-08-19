"""交易日历缓存表：结果缓存到 SQLite，禁止每 60 秒请求日历数据源。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TradingCalendarDay(Base):
    __tablename__ = "trading_calendar"
    __table_args__ = (
        UniqueConstraint("market", "trade_date", name="uq_calendar_market_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(8))  # CN / HK
    trade_date: Mapped[date] = mapped_column(Date)
    is_open: Mapped[bool] = mapped_column(Boolean)

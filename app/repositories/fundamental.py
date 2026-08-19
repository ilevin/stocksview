"""估值快照仓储。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fundamental import FundamentalSnapshot


class FundamentalRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(self, snapshot: FundamentalSnapshot) -> None:
        existing = self.session.scalar(
            select(FundamentalSnapshot).where(
                FundamentalSnapshot.instrument_id == snapshot.instrument_id,
                FundamentalSnapshot.trade_date == snapshot.trade_date,
            )
        )
        if existing is not None:
            existing.pe_ttm = snapshot.pe_ttm
            existing.pb = snapshot.pb
            existing.dividend_yield_ttm = snapshot.dividend_yield_ttm
            existing.source = snapshot.source
            if snapshot.fetched_at is not None:
                existing.fetched_at = snapshot.fetched_at
        else:
            self.session.add(snapshot)
        self.session.flush()

    def latest(self, instrument_id: str) -> FundamentalSnapshot | None:
        return self.session.scalar(
            select(FundamentalSnapshot)
            .where(FundamentalSnapshot.instrument_id == instrument_id)
            .order_by(FundamentalSnapshot.trade_date.desc())
            .limit(1)
        )

    def latest_many(self, instrument_ids: list[str]) -> dict[str, FundamentalSnapshot]:
        result: dict[str, FundamentalSnapshot] = {}
        if not instrument_ids:
            return result
        rows = self.session.scalars(
            select(FundamentalSnapshot).where(
                FundamentalSnapshot.instrument_id.in_(instrument_ids)
            )
        ).all()
        for row in rows:
            current = result.get(row.instrument_id)
            if current is None or row.trade_date > current.trade_date:
                result[row.instrument_id] = row
        return result

    def has_data_for_date(self, trade_date: date) -> bool:
        count = self.session.scalar(
            select(func.count(FundamentalSnapshot.id)).where(
                FundamentalSnapshot.trade_date == trade_date
            )
        )
        return bool(count)

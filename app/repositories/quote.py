"""行情快照仓储：upsert 幂等 + 最近快照查询（缓存回退用）。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.quote import QuoteSnapshot


class QuoteSnapshotRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(self, snapshot: QuoteSnapshot) -> None:
        existing = self.latest(snapshot.instrument_id)
        if existing is not None:
            existing.price = snapshot.price
            existing.change_percent = snapshot.change_percent
            existing.volume_ratio = snapshot.volume_ratio
            existing.previous_close = snapshot.previous_close
            existing.source = snapshot.source
            existing.source_timestamp = snapshot.source_timestamp
            if snapshot.fetched_at is not None:
                existing.fetched_at = snapshot.fetched_at
        else:
            self.session.add(snapshot)
        self.session.flush()

    def latest(self, instrument_id: str) -> QuoteSnapshot | None:
        return self.session.scalar(
            select(QuoteSnapshot)
            .where(QuoteSnapshot.instrument_id == instrument_id)
            .order_by(QuoteSnapshot.fetched_at.desc(), QuoteSnapshot.id.desc())
            .limit(1)
        )

    def latest_many(self, instrument_ids: list[str]) -> dict[str, QuoteSnapshot]:
        """每个 instrument 的最近一条快照（内存缓存预热 / API 回退）。"""
        result: dict[str, QuoteSnapshot] = {}
        if not instrument_ids:
            return result
        rows = self.session.scalars(
            select(QuoteSnapshot).where(QuoteSnapshot.instrument_id.in_(instrument_ids))
        ).all()
        for row in rows:
            current = result.get(row.instrument_id)
            if current is None or (row.fetched_at, row.id) > (current.fetched_at, current.id):
                result[row.instrument_id] = row
        return result

    def count(self) -> int:
        return self.session.scalar(select(func.count(QuoteSnapshot.id))) or 0

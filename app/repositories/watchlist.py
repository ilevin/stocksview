"""自选 / 指数配置仓储：两套列表结构一致，用泛型基类避免重复（不加抽象层）。"""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.instrument import Instrument
from app.models.watchlist import IndexWatchlist, Watchlist

T = TypeVar("T", bound=Watchlist | IndexWatchlist)


class BaseWatchlistRepository(Generic[T]):
    model: type[T]

    def __init__(self, session: Session):
        self.session = session

    def list_ordered(self) -> list[tuple[T, Instrument]]:
        stmt = (
            select(self.model, Instrument)
            .join(Instrument, self.model.instrument_id == Instrument.instrument_id)
            .order_by(self.model.sort_order, self.model.id)
        )
        return list(self.session.execute(stmt).all())

    def get(self, instrument_id: str) -> T | None:
        return self.session.scalar(
            select(self.model).where(self.model.instrument_id == instrument_id)
        )

    def exists(self, instrument_id: str) -> bool:
        return self.get(instrument_id) is not None

    def add(self, instrument_id: str, sort_order: int = 0) -> T:
        row = self.model(instrument_id=instrument_id, sort_order=sort_order)
        self.session.add(row)
        self.session.flush()
        return row

    def remove(self, instrument_id: str) -> bool:
        row = self.get(instrument_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.flush()
        return True

    def reorder(self, orders: dict[str, int]) -> None:
        for instrument_id, sort_order in orders.items():
            row = self.get(instrument_id)
            if row is not None:
                row.sort_order = sort_order
        self.session.flush()

    def next_sort_order(self) -> int:
        rows = self.session.scalars(select(self.model)).all()
        return max((r.sort_order for r in rows), default=0) + 10


class WatchlistRepository(BaseWatchlistRepository[Watchlist]):
    model = Watchlist


class IndexWatchlistRepository(BaseWatchlistRepository[IndexWatchlist]):
    model = IndexWatchlist

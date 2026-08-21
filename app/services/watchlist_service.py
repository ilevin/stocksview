"""自选 / 指数配置业务服务（增删查排序 + 名称自动识别）。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.instrument import Instrument
from app.providers.base import InstrumentNameProvider
from app.repositories.instrument import InstrumentRepository
from app.repositories.watchlist import (
    BaseWatchlistRepository,
    IndexWatchlistRepository,
    WatchlistRepository,
)
from app.services.instrument_id import (
    MARKET_CURRENCY,
    InvalidInstrumentError,
    build_instrument_id,
)

logger = logging.getLogger(__name__)

_HK_INDEX_CODE_HINT = (
    "。港股指数代码为字母缩写，常见如 HSI（恒生指数）、"
    "HSCEI（国企指数）、HSTECH（恒生科技指数），请核对后重试"
)


def _unknown_symbol_detail(market: str, asset_type: str, symbol: str) -> str:
    """识别失败的报错文案；港股指数附常见代码指引。"""
    detail = f"无法识别证券: {market}/{asset_type}/{symbol}"
    if market.upper() == "HK" and asset_type == "INDEX":
        detail += _HK_INDEX_CODE_HINT
    return detail


class ServiceError(Exception):
    """业务错误基类。"""


class DuplicateItemError(ServiceError):
    """重复添加。"""


class InstrumentNotFoundError(ServiceError):
    """证券无法识别。"""


class InvalidTypeError(ServiceError):
    """资产类型不允许进入该列表。"""


class BaseWatchlistService:
    """股票/ETF 自选与指数配置共用的服务逻辑。"""

    allowed_asset_types: frozenset[str]

    def __init__(self, session: Session, name_provider: InstrumentNameProvider):
        self.session = session
        self.name_provider = name_provider
        self.instrument_repo = InstrumentRepository(session)
        self.repo = self._make_repo(session)

    def _make_repo(self, session: Session) -> BaseWatchlistRepository:
        raise NotImplementedError

    def list(self) -> list[tuple[Instrument, int]]:
        return [(inst, row.sort_order) for row, inst in self.repo.list_ordered()]

    def add(self, *, symbol: str, market: str, asset_type: str) -> str:
        """返回 instrument_id；失败抛出业务异常。"""
        asset_type = asset_type.upper()
        if asset_type not in self.allowed_asset_types:
            raise InvalidTypeError(
                f"asset_type 仅允许 {'/'.join(sorted(self.allowed_asset_types))}，收到 {asset_type}"
            )
        # 港股指数代码为字母缩写（如 HSTECH），统一大写；A股/港股股票与 ETF 代码均为数字
        symbol = symbol.strip().upper()
        instrument_id = build_instrument_id(market, asset_type, symbol)
        if self.repo.exists(instrument_id):
            raise DuplicateItemError(f"已在列表中: {instrument_id}")

        name = self.name_provider.get_name(market.upper(), asset_type, symbol)
        if not name:
            raise InstrumentNotFoundError(_unknown_symbol_detail(market, asset_type, symbol))

        self.instrument_repo.upsert(
            instrument_id=instrument_id,
            symbol=symbol,
            name=name,
            market=market.upper(),
            asset_type=asset_type,
            currency=MARKET_CURRENCY[market.upper()],
        )
        self.repo.add(instrument_id, sort_order=self.repo.next_sort_order())
        self.session.commit()
        logger.info("已添加自选: %s (%s)", instrument_id, name)
        return instrument_id

    def remove(self, instrument_id: str) -> bool:
        removed = self.repo.remove(instrument_id)
        self.session.commit()
        if removed:
            logger.info("已删除自选: %s", instrument_id)
        return removed

    def reorder(self, orders: dict[str, int]) -> None:
        self.repo.reorder(orders)
        self.session.commit()
        logger.info("已调整自选排序: %s", list(orders.items()))


class WatchlistService(BaseWatchlistService):
    allowed_asset_types = frozenset({"STOCK", "ETF"})

    def _make_repo(self, session: Session) -> WatchlistRepository:
        return WatchlistRepository(session)


class IndexWatchlistService(BaseWatchlistService):
    allowed_asset_types = frozenset({"INDEX"})

    def _make_repo(self, session: Session) -> IndexWatchlistRepository:
        return IndexWatchlistRepository(session)

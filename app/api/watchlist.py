"""股票/ETF 自选 API。"""

from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas import (
    OrderUpdateRequest,
    WatchlistAddRequest,
    WatchlistItem,
    WatchlistListResponse,
)
from app.services.watchlist_service import (
    DuplicateItemError,
    IndexWatchlistService,
    InstrumentNotFoundError,
    InvalidInstrumentError,
    InvalidTypeError,
    WatchlistService,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def get_watchlist_service(request: Request) -> Iterator[WatchlistService]:
    with request.app.state.session_factory() as session:
        yield WatchlistService(session, request.app.state.name_provider)


def get_index_watchlist_service(request: Request) -> Iterator[IndexWatchlistService]:
    with request.app.state.session_factory() as session:
        yield IndexWatchlistService(session, request.app.state.name_provider)


def _error_status(exc: Exception) -> int:
    if isinstance(exc, DuplicateItemError):
        return 409
    if isinstance(exc, (InstrumentNotFoundError,)):
        return 404
    if isinstance(exc, (InvalidTypeError, InvalidInstrumentError)):
        return 422
    return 500


def _trigger_refresh_if_open(request: Request, instrument_id: str, market: str) -> None:
    """添加自选时，若该市场正在交易则触发一次该资产行情更新（PRD 17.4）。"""
    refresher = getattr(request.app.state, "refresh_service", None)
    session_service = getattr(request.app.state, "session_service", None)
    if refresher is None or session_service is None:
        return
    if not session_service.should_refresh(market):
        return
    try:
        refresher.refresh_instruments_now([instrument_id])
    except Exception:  # 刷新失败不影响添加
        pass


@router.get("", response_model=WatchlistListResponse)
def list_watchlist(service: WatchlistService = Depends(get_watchlist_service)):
    items = [
        WatchlistItem(
            instrument_id=inst.instrument_id,
            symbol=inst.symbol,
            name=inst.name,
            market=inst.market,
            asset_type=inst.asset_type,
            sort_order=sort_order,
        )
        for inst, sort_order in service.list()
    ]
    return WatchlistListResponse(items=items)


@router.post("", response_model=WatchlistItem, status_code=201)
def add_watchlist(
    body: WatchlistAddRequest,
    request: Request,
    service: WatchlistService = Depends(get_watchlist_service),
):
    try:
        instrument_id = service.add(
            symbol=body.symbol, market=body.market, asset_type=body.asset_type
        )
    except Exception as exc:
        raise HTTPException(status_code=_error_status(exc), detail=str(exc)) from exc

    _trigger_refresh_if_open(request, instrument_id, body.market)
    inst = service.instrument_repo.get(instrument_id)
    sort_order = service.repo.get(instrument_id).sort_order
    return WatchlistItem(
        instrument_id=inst.instrument_id,
        symbol=inst.symbol,
        name=inst.name,
        market=inst.market,
        asset_type=inst.asset_type,
        sort_order=sort_order,
    )


@router.delete("/{instrument_id}", status_code=204)
def delete_watchlist(
    instrument_id: str, service: WatchlistService = Depends(get_watchlist_service)
):
    if not service.remove(instrument_id):
        raise HTTPException(status_code=404, detail=f"自选中不存在: {instrument_id}")


@router.put("/order", response_model=WatchlistListResponse)
def reorder_watchlist(
    body: OrderUpdateRequest, service: WatchlistService = Depends(get_watchlist_service)
):
    service.reorder({item.instrument_id: item.sort_order for item in body.items})
    return list_watchlist(service)

"""估值刷新任务：每日收盘后一次 + 启动时当天无数据补一次（PRD 第 14 节）。"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from app.config import AppConfig
from app.repositories.fundamental import FundamentalRepository
from app.services.market_session_service import MarketStatus, now_beijing

logger = logging.getLogger(__name__)

# 收盘后多久开始当日估值更新
_AFTER_CLOSE_DELAY = timedelta(minutes=30)
_CHECK_INTERVAL_SECONDS = 30 * 60  # 每 30 分钟检查一次是否需要更新


class FundamentalRefreshJob:
    def __init__(self, config, session_factory, provider, session_service, calendar_repo_factory):
        self.config = config
        self.session_factory = session_factory
        self.provider = provider
        self.session_service = session_service
        self.calendar_repo_factory = calendar_repo_factory
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="fundamental-refresh")
            logger.info("估值刷新任务已启动")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self._maybe_run)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("估值刷新任务异常")
            await asyncio.sleep(_CHECK_INTERVAL_SECONDS)

    def _latest_trade_date(self):
        """最近的 CN 交易日（含今天，若今天是交易日且已收盘）。"""
        today = now_beijing().date()
        with self.calendar_repo_factory() as repo:
            for back in range(7):
                day = today - timedelta(days=back)
                if repo.get("CN", day) is True:
                    # 今天是交易日但要收盘后才取当日数据
                    if day == today:
                        close_time = now_beijing().replace(hour=15, minute=30, second=0, microsecond=0)
                        if now_beijing() < close_time:
                            continue
                    return day
        return None

    def _maybe_run(self) -> None:
        if not self.config.has_tushare_token:
            return
        trade_date = self._latest_trade_date()
        if trade_date is None:
            return
        with self.session_factory() as session:
            if FundamentalRepository(session).has_data_for_date(trade_date):
                return  # 当天已有估值数据
        self.run_once(trade_date)

    def run_once(self, trade_date=None) -> dict:
        """执行一次估值刷新，返回 {success, updated, failed}。"""
        from app.repositories.watchlist import WatchlistRepository

        trade_date = trade_date or self._latest_trade_date()
        with self.session_factory() as session:
            instruments = [inst for _, inst in WatchlistRepository(session).list_ordered()]

        fundamentals = self.provider.get_fundamentals(instruments, trade_date)
        updated = len(fundamentals)
        failed = len([i for i in instruments if i.market == "CN" and i.asset_type == "STOCK"]) - updated
        if failed < 0:
            failed = 0

        from app.models.fundamental import FundamentalSnapshot

        with self.session_factory() as session:
            repo = FundamentalRepository(session)
            for fund in fundamentals.values():
                repo.upsert(
                    FundamentalSnapshot(
                        instrument_id=fund.instrument_id,
                        trade_date=fund.trade_date,
                        pe_ttm=fund.pe_ttm,
                        pb=fund.pb,
                        dividend_yield_ttm=fund.dividend_yield_ttm,
                        source=fund.source,
                    )
                )
            session.commit()
        logger.info("估值刷新完成: trade_date=%s updated=%d failed=%d", trade_date, updated, failed)
        return {"success": failed == 0 and updated > 0, "updated": updated, "failed": failed}

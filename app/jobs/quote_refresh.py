"""后台行情刷新任务：FastAPI lifespan 启动的 60 秒 asyncio 循环。

Provider 均为同步实现（akshare/httpx），通过 asyncio.to_thread 调用，
避免阻塞事件循环。单轮异常只记日志，绝不让主进程退出。
"""

from __future__ import annotations

import asyncio
import logging

from app.config import AppConfig
from app.services.refresh_service import RefreshService

logger = logging.getLogger(__name__)


class QuoteRefreshJob:
    def __init__(self, config: AppConfig, refresh_service: RefreshService):
        self.refresh_seconds = config.quote.refresh_seconds
        self.refresh_service = refresh_service
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="quote-refresh")
            logger.info("行情刷新任务已启动（周期 %d 秒）", self.refresh_seconds)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("行情刷新任务已停止")

    async def _run(self) -> None:
        while True:
            try:
                result = await asyncio.to_thread(self.refresh_service.tick)
                logger.info(
                    "行情刷新完成: updated=%d failed=%d markets=%s",
                    result.updated, result.failed, result.markets,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("后台行情刷新任务异常")
            await asyncio.sleep(self.refresh_seconds)

"""Tushare 估值 Provider 与刷新任务单测（mock，不依赖真实 Token）。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import AppConfig, TushareConfig
from app.db import init_db
from app.jobs.fundamental_refresh import FundamentalRefreshJob
from app.models.fundamental import FundamentalSnapshot
from app.models.instrument import Instrument
from app.providers.fundamental.tushare import TushareFundamentalProvider, to_ts_code
from app.repositories.fundamental import FundamentalRepository
from app.repositories.instrument import InstrumentRepository
from app.repositories.watchlist import WatchlistRepository
from app.services.market_session_service import MarketSessionService

SHANGHAI = ZoneInfo("Asia/Shanghai")
MAOTAI = Instrument(
    instrument_id="CN:STOCK:600519", symbol="600519", name="贵州茅台",
    market="CN", asset_type="STOCK", currency="CNY",
)
TENCENT = Instrument(
    instrument_id="HK:STOCK:00700", symbol="00700", name="腾讯控股",
    market="HK", asset_type="STOCK", currency="HKD",
)


class FakePro:
    """mock tushare pro.daily_basic。"""

    def __init__(self, df):
        self.df = df

    def daily_basic(self, **kwargs):
        if "trade_date" in kwargs:
            return self.df
        # 按 ts_code 查询：返回该代码的行
        code = kwargs.get("ts_code")
        rows = self.df[self.df["ts_code"] == code]
        return rows if len(rows) else pd.DataFrame(columns=self.df.columns)


def _df():
    return pd.DataFrame(
        [
            {"ts_code": "600519.SH", "trade_date": "20260818", "pe_ttm": 21.31, "pb": 7.21, "dv_ttm": 3.12},
            {"ts_code": "000001.SZ", "trade_date": "20260818", "pe_ttm": "-", "pb": "", "dv_ttm": None},
        ]
    )


@pytest.fixture()
def provider_with_token(monkeypatch):
    config = AppConfig(tushare=TushareConfig(token="fake-token-for-test"))
    provider = TushareFundamentalProvider(config)
    monkeypatch.setattr(provider, "_pro", lambda: FakePro(_df()))
    return provider


def test_to_ts_code():
    assert to_ts_code("600519") == "600519.SH"
    assert to_ts_code("000001") == "000001.SZ"
    assert to_ts_code("300750") == "300750.SZ"


def test_fundamentals_parsed_and_cleaned(provider_with_token):
    result = provider_with_token.get_fundamentals(
        [MAOTAI, TENCENT], trade_date=date(2026, 8, 18)
    )
    # 港股不请求、不写估值
    assert "HK:STOCK:00700" not in result
    fund = result["CN:STOCK:600519"]
    assert fund.pe_ttm == 21.31
    assert fund.pb == 7.21
    assert fund.dividend_yield_ttm == 3.12
    assert fund.source == "tushare"
    assert fund.trade_date == date(2026, 8, 18)


def test_dirty_values_become_none(monkeypatch):
    config = AppConfig(tushare=TushareConfig(token="fake-token-for-test"))
    provider = TushareFundamentalProvider(config)
    df = pd.DataFrame(
        [{"ts_code": "000001.SZ", "trade_date": "20260818", "pe_ttm": "-", "pb": "nan", "dv_ttm": None}]
    )
    monkeypatch.setattr(provider, "_pro", lambda: FakePro(df))
    result = provider.get_fundamentals(
        [Instrument(instrument_id="CN:STOCK:000001", symbol="000001", name="平安银行",
                    market="CN", asset_type="STOCK", currency="CNY")],
        trade_date=date(2026, 8, 18),
    )
    fund = result["CN:STOCK:000001"]
    assert fund.pe_ttm is None and fund.pb is None and fund.dividend_yield_ttm is None


def test_no_token_returns_empty():
    config = AppConfig()  # 无 Token
    provider = TushareFundamentalProvider(config)
    assert provider.get_fundamentals([MAOTAI], trade_date=date(2026, 8, 18)) == {}


def test_request_failure_returns_empty(monkeypatch):
    config = AppConfig(tushare=TushareConfig(token="fake-token-for-test"))
    provider = TushareFundamentalProvider(config)

    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(provider, "_pro", boom)
    assert provider.get_fundamentals([MAOTAI], trade_date=date(2026, 8, 18)) == {}


# ---- FundamentalRefreshJob ----


@pytest.fixture()
def job_env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as s:
        irepo = InstrumentRepository(s)
        irepo.upsert(instrument_id="CN:STOCK:600519", symbol="600519", name="贵州茅台",
                     market="CN", asset_type="STOCK", currency="CNY")
        irepo.upsert(instrument_id="HK:STOCK:00700", symbol="00700", name="腾讯控股",
                     market="HK", asset_type="STOCK", currency="HKD")
        WatchlistRepository(s).add("CN:STOCK:600519", 10)
        WatchlistRepository(s).add("HK:STOCK:00700", 20)
        s.commit()

    config = AppConfig(tushare=TushareConfig(token="fake-token-for-test"))
    provider = TushareFundamentalProvider(config)
    monkeypatch.setattr(provider, "_pro", lambda: FakePro(_df()))

    from contextlib import contextmanager

    from app.repositories.trading_calendar import TradingCalendarRepository

    @contextmanager
    def calendar_repo():
        with factory() as s:
            yield TradingCalendarRepository(s)

    job = FundamentalRefreshJob(
        config, factory, provider, MarketSessionService(_AlwaysTrading()), calendar_repo
    )
    return {"job": job, "factory": factory}


class _AlwaysTrading:
    def is_trading_day(self, market, day):
        return True


def test_job_run_once_saves_snapshots(job_env):
    job = job_env["job"]
    result = job.run_once(trade_date=date(2026, 8, 18))
    assert result["updated"] == 1  # 只有 A股股票
    with job_env["factory"]() as s:
        fund = FundamentalRepository(s).latest("CN:STOCK:600519")
        assert fund is not None
        assert float(fund.pe_ttm) == 21.31
        assert float(fund.dividend_yield_ttm) == 3.12
        # 港股无估值
        assert FundamentalRepository(s).latest("HK:STOCK:00700") is None


def test_job_skips_when_data_exists(job_env):
    job = job_env["job"]
    job.run_once(trade_date=date(2026, 8, 18))
    # 再次运行：快照按 (instrument_id, trade_date) 幂等覆盖，不重复
    job.run_once(trade_date=date(2026, 8, 18))
    with job_env["factory"]() as s:
        count = len(s.query(FundamentalSnapshot).all())
        assert count == 1

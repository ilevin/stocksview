"""行情 Provider 注册表：按 (market, asset_type) 从配置选择数据源实现。"""

from __future__ import annotations

from app.config import AppConfig
from app.models.instrument import Instrument
from app.providers.base import QuoteProvider
from app.providers.quote.akshare import AkshareQuoteProvider
from app.providers.quote.tencent import TencentQuoteProvider

# 数据源名称 -> Provider 类（新增数据源只需在此登记）
_PROVIDERS: dict[str, type] = {
    "akshare": AkshareQuoteProvider,
    "tencent": TencentQuoteProvider,
}


class QuoteProviderRegistry:
    """按市场+资产类型分派到配置声明的 Provider。"""

    def __init__(self, config: AppConfig):
        self._single: dict[str, QuoteProvider] = {}
        quote_cfg = config.providers.quote
        for field_name in (
            "cn_stock", "cn_etf", "hk_stock", "hk_etf", "cn_index", "hk_index",
        ):
            source = getattr(quote_cfg, field_name).lower()
            provider_cls = _PROVIDERS.get(source)
            if provider_cls is None:
                raise ValueError(f"未知的行情数据源: {source}（可选: {sorted(_PROVIDERS)}）")
            if source not in self._single:
                self._single[source] = provider_cls()
        self._registry = {}  # (market, asset_type) -> provider 实例
        for (market, asset_type), field_name in {
            ("CN", "STOCK"): "cn_stock",
            ("CN", "ETF"): "cn_etf",
            ("HK", "STOCK"): "hk_stock",
            ("HK", "ETF"): "hk_etf",
            ("CN", "INDEX"): "cn_index",
            ("HK", "INDEX"): "hk_index",
        }.items():
            source = getattr(quote_cfg, field_name).lower()
            self._registry[(market, asset_type)] = self._single[source]

    def provider_for(self, market: str, asset_type: str) -> QuoteProvider | None:
        return self._registry.get((market, asset_type))

    def get_quotes(self, instruments: list[Instrument]) -> dict:
        """按 (market, asset_type) 分组调用对应 Provider 并合并结果。"""
        import logging

        result = {}
        groups: dict[tuple[str, str], list[Instrument]] = {}
        for inst in instruments:
            groups.setdefault((inst.market, inst.asset_type), []).append(inst)
        for key, group in groups.items():
            provider = self.provider_for(*key)
            if provider is None:
                continue
            try:
                result.update(provider.get_quotes(group))
            except Exception:
                # 单个 Provider 失败不影响其他数据源，保留已有缓存
                logging.getLogger(__name__).exception(
                    "行情 Provider 失败: market=%s asset_type=%s", *key
                )
        return result

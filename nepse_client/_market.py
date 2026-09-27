"""Market data, indices, top tens and depth. endpoints (mixin for NepseClient)."""

from __future__ import annotations

from typing import Optional


class MarketMixin:
    # -- market status / summary / ticker --------------------------------
    def market_status(self) -> dict:
        """Market open state (homepage + every page reads this)."""
        return self.get_json("/api/nots/nepse-data/market-open")  # type: ignore[return-value]

    def market_summary(self) -> list:
        """Homepage summary tiles [{detail, value}]."""
        return self.get_json("/api/nots/market-summary/")  # type: ignore[return-value]

    def market_summary_history(self) -> list:
        """Daily history [{businessDate, totalTurnover, ...}]."""
        return self.get_json("/api/nots/market-summary-history")  # type: ignore[return-value]

    def ticker(self, index_id: int = 58) -> list:
        """Live ticker strip [{symbol, ltp, ...}] (every page load)."""
        return self.get_json(f"/api/nots/securityDailyTradeStat/{index_id}")  # type: ignore[return-value]

    def live_market(self) -> list:
        """Full live snapshot (356 rows: OHLC, volumes, per-security indexId).

        The Live Market *page* redirects to `/` while the market is closed,
        but the API itself answers 200 regardless — verified live.
        """
        return self.get_json("/api/nots/lives-market")  # type: ignore[return-value]

    def nepse_indices(self) -> list:
        """Index snapshot [{index, close, change, perChange, ...}]."""
        return self.get_json("/api/nots/nepse-index")  # type: ignore[return-value]

    def sub_indices(self) -> list:
        """Sub-index snapshot [{id, index, change, currentValue}]."""
        return self.get_json("/api/nots")  # type: ignore[return-value]

    def indices_list(self) -> list:
        """Index directory [{id, indexCode, indexName, ...}]."""
        return self.get_json("/api/nots/index")  # type: ignore[return-value]

    def index_history(self, index_id: int = 58, page: int = 1,
                      size: int = 20) -> dict:
        """Datewise index OHLC (Indices page; page is 1-based like the UI)."""
        path = f"/api/nots/index/history/{index_id}?&size={size}"
        if page > 1:
            path = f"/api/nots/index/history/{index_id}?page={page - 1}&size={size}"
        return self.get_json(path)  # type: ignore[return-value]

    def sector_summary(self, business_date: Optional[str] = None) -> list:
        """Sector turnover (Sector Summary page; date 'yyyy-MM-dd')."""
        path = "/api/nots/sectorwise"
        if business_date:
            path += f"?businessDate={business_date}"
        return self.get_json(path)  # type: ignore[return-value]

    # -- top tens ------------------------------------------------------------
    def _top_ten(self, kind: str, full: bool = False) -> list:
        return self.get_json(f"/api/nots/top-ten/{kind}?all={str(full).lower()}")  # type: ignore[return-value]

    def top_gainers(self, full: bool = False) -> list:
        """Top gainers [{symbol, ltp, pointChange, percentageChange, ...}]."""
        return self._top_ten("top-gainer", full)

    def top_losers(self, full: bool = False) -> list:
        """Top losers (same shape as gainers)."""
        return self._top_ten("top-loser", full)

    def top_turnover(self, full: bool = False) -> list:
        """Top by turnover."""
        return self._top_ten("turnover", full)

    def top_traded_shares(self, full: bool = False) -> list:
        """Top by shares traded."""
        return self._top_ten("trade", full)

    def top_transactions(self, full: bool = False) -> list:
        """Top by transaction count."""
        return self._top_ten("transaction", full)

    def top_active(self, full: bool = False) -> list:
        """Most active scrips (trade quantity)."""
        return self._top_ten("trade-qty", full)

    # -- supply / demand / depth ----------------------------------------------
    def supply_demand(self, full: bool = False) -> dict:
        """Top supply/demand {supplyList, demandList}."""
        return self.get_json(  # type: ignore[return-value]
            f"/api/nots/nepse-data/supplydemand?all={str(full).lower()}")

    def market_depth(self, security_id: int) -> dict:
        """Order book {totalBuyQty, totalSellQty, marketDepth{...}}."""
        return self.get_json(f"/api/nots/nepse-data/marketdepth/{security_id}")  # type: ignore[return-value]

    def odd_lot_depth(self, security_id: int) -> dict:
        """Odd-lot order book (same shape as market_depth)."""
        return self.get_json(f"/api/nots/nepse-data/marketdepth-ol/{security_id}")  # type: ignore[return-value]

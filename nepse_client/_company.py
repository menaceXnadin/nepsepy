"""Per-security data and company tabs. endpoints (mixin for NepseClient)."""

from __future__ import annotations

from typing import Optional


class CompanyMixin:
    # -- per-security data (GET; mirrors company tabs) --------------------------
    def security_detail(self, security_id: int) -> dict:
        """{securityData, securityMcsData} (Market Depth page header)."""
        return self.get_json(f"/api/nots/security/{security_id}")  # type: ignore[return-value]

    def security_profile(self, security_id: int) -> dict:
        return self.get_json(f"/api/nots/security/profile/{security_id}")  # type: ignore[return-value]

    def board_of_directors(self, security_id: int) -> list:
        return self.get_json(f"/api/nots/security/boardOfDirectors/{security_id}")  # type: ignore[return-value]

    def corporate_actions(self, security_id: int) -> list:
        """Bonus/cash/right [{fiscalYear, bonusPercentage, ...}]."""
        return self.get_json(f"/api/nots/security/corporate-actions/{security_id}")  # type: ignore[return-value]

    def financial_reports(self, security_id: int) -> list:
        return self.get_json(f"/api/nots/application/reports/{security_id}")  # type: ignore[return-value]

    def agm(self, security_id: int) -> list:
        return self.get_json(f"/api/nots/application/agm/{security_id}")  # type: ignore[return-value]

    def security_company_news(self, security_id: int) -> list:
        return self.get_json(f"/api/nots/application/company-news/{security_id}")  # type: ignore[return-value]

    def market_security(self, security_id: int) -> dict:
        """Flat daily-trade snapshot + nested security (Listing Information)."""
        return self.get_json(f"/api/nots/market/security/{security_id}")  # type: ignore[return-value]

    def security_market_picture(self, security_id: int) -> dict:
        """Compact quote {receivedDateTime, securityId, lastTradedPrice,
        openPrice, highPrice, lowPrice} (site's getSecurityDetailsFromMarketPicture)."""
        return self.get_json(f"/api/nots/security-detail/{security_id}")  # type: ignore[return-value]

    def dividends(self, security_id: int) -> list:
        """Dividend applications/news for a security (site's getSecurityDividendNewsById)."""
        return self.get_json(f"/api/nots/application/dividend/{security_id}")  # type: ignore[return-value]

    def book_close(self, news_id: int) -> dict:
        """Book-closure news by id (site's getSecurityBookCloseNewsById).

        NOTE: currently HTTP 404 for every id tried (security ids and
        company-news ids alike), so this is mapped-but-dead like
        security_floorsheet() until the backend serves it again.
        """
        return self.get_json(f"/api/nots/news/book-close/{news_id}")  # type: ignore[return-value]

    def security_price_history(self, security_id: int, page: int = 1,
                               size: int = 20,
                               business_date: Optional[str] = None) -> dict:
        """Price History tab (Spring page of OHLCV rows; page 1-based)."""
        query = f"?&size={size}"
        if business_date:
            query += f"&businessDate={business_date}"
        if page > 1:
            query = f"?page={page - 1}&size={size}" + (
                f"&businessDate={business_date}" if business_date else "")
        return self.get_json(f"/api/nots/market/security/price/{security_id}{query}")  # type: ignore[return-value]

    def stock_trading_history(self, security_id: int, page: int = 1,
                              size: int = 20,
                              start: Optional[str] = None,
                              end: Optional[str] = None) -> dict:
        """Stock Trading page (page 1-based; dates 'yyyy-MM-dd')."""
        query = f"?&size={size}"
        if start:
            query += f"&startDate={start}"
        if end:
            query += f"&endDate={end}"
        if page > 1:
            query = f"?page={page - 1}&size={size}" + (
                f"&startDate={start}" if start else "") + (
                    f"&endDate={end}" if end else "")
        return self.get_json(f"/api/nots/market/history/security/{security_id}{query}")  # type: ignore[return-value]

    def trading_average(self, n_days: int = 120,
                        business_date: Optional[str] = None,
                        stock_id: Optional[int] = None) -> list:
        """N-day average price per security (Trading Average page)."""
        path = f"/api/nots/nepse-data/trading-average?nDays={n_days}"
        if business_date:
            path += f"&businessDate={business_date}"
        if stock_id is not None:
            path += f"&stockId={stock_id}"
        return self.get_json(path)  # type: ignore[return-value]

    def market_cap_history(self, page: int = 1) -> list:
        """Daily market caps [{businessDate, marCap, ...}] (filter client-side)."""
        path = "/api/nots/nepse-data/marcapbydate/?"
        if page > 1:
            path = f"/api/nots/nepse-data/marcapbydate/?page={page - 1}"
        return self.get_json(path)  # type: ignore[return-value]

    # -- signed POST: company data --------------------------------------------------
    def company_info(self, security_id: int) -> dict:
        """Company header {securityDailyTradeDto, security, ...} (detail page)."""
        return self.post_json(f"/api/nots/security/{security_id}",  # type: ignore[return-value]
                              {"id": self._signed("raw")})

    def company_graph(self, security_id: int) -> list:
        """Company OHLC history [{businessDate, openPrice, ...}] (chart tab)."""
        return self.post_json(f"/api/nots/market/graphdata/{security_id}",  # type: ignore[return-value]
                              {"id": self._signed("raw")})

    def company_graph_intraday(self, security_id: int) -> list:
        """Company intraday LTP (Charts Company tab, 1D range)."""
        return self.post_json(f"/api/nots/market/graphdata/daily/{security_id}",  # type: ignore[return-value]
                              {"id": self._signed("raw")})

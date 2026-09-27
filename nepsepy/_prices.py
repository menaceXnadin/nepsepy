"""Signed price, floorsheet and graph POSTs. endpoints (mixin for NepseClient)."""

from __future__ import annotations

from typing import Optional


class PricesMixin:
    # -- signed POST: today price ----------------------------------------------
    def today_price(self, page: int = 1, size: int = 20,
                    security_id: Optional[int] = None,
                    business_date: Optional[str] = None,
                    sort_by: str = "", sort_order: str = "") -> dict:
        """Today's Price table (Spring page; page 1-based like the UI)."""
        query = f"?&size={size}"
        if security_id is not None:
            query += f"&securityId={security_id}"
        if business_date:
            query += f"&businessDate={business_date}"
        if sort_by:
            query += f"&sort={sort_by},{sort_order}"
        if page > 1:
            query = query.replace("?", f"?page={page - 1}", 1)
        return self.post_json(  # type: ignore[return-value]
            f"/api/nots/nepse-data/today-price{query}",
            {"id": self._signed("b")})

    def today_price_all(self, business_date: Optional[str] = None) -> list:
        """Full Today's Price list behind the CSV export."""
        path = "/api/nots/nepse-data/todays-price/"
        if business_date:
            path += f"?businessDate={business_date}"
        return self.post_json(path, {"id": self._signed("b")})  # type: ignore[return-value]

    # -- signed POST: floorsheet -------------------------------------------------
    def floorsheets(self, page: int = 1, size: int = 20,
                    contract_no: Optional[int] = None,
                    stock_id: Optional[int] = None,
                    buyer_broker: Optional[int] = None,
                    seller_broker: Optional[int] = None,
                    sort_by: str = "contractId",
                    sort_order: str = "desc") -> dict:
        """Floor Sheet page ({totalAmount, totalQty, totalTrades, floorsheets};
        page 1-based like the UI)."""
        query = f"?&size={size}"
        if stock_id is not None:
            query += f"&stockId={stock_id}"
        if contract_no is not None:
            query += f"&contractNo={contract_no}"
        if buyer_broker is not None:
            query += f"&buyerBroker={buyer_broker}"
        if seller_broker is not None:
            query += f"&sellerBroker={seller_broker}"
        query += f"&sort={sort_by},{sort_order}"
        if page > 1:
            query = query.replace("?", f"?page={page - 1}", 1)
        return self.post_json(  # type: ignore[return-value]
            f"/api/nots/nepse-data/floorsheet{query}",
            {"id": self._signed("c")})

    def security_floorsheet(self, security_id: int,
                            business_date: Optional[str] = None,
                            page: int = 1, size: int = 20,
                            sort_by: str = "contractId",
                            sort_order: str = "asc") -> dict:
        """Per-security Floor Sheet tab (company modal).

        Mirrors the site's own tab request:
        ``POST /api/nots/security/floorsheet/{id}?[&businessDate=]...``.
        ``business_date`` defaults to the market ``asOf`` day like the UI.

        NOTE: the server currently answers nginx ``403 Forbidden`` to this
        request — including requests made by the genuine site itself —
        so this method exists for the day they fix it server-side. Until
        then it raises ``AuthExpiredError("access rejected with HTTP 403")``
        after the normal single refresh + retry. The checksum variant is
        likewise unverified; it follows the sibling floorsheet endpoint
        (variant C).
        """
        if business_date is None:
            business_date = str(self.market_status().get("asOf", ""))[:10]
        query = f"?businessDate={business_date}&size={size}"
        query += f"&sort={sort_by},{sort_order}"
        if page > 1:
            query = query.replace("?", f"?page={page - 1}", 1)
        return self.post_json(  # type: ignore[return-value]
            f"/api/nots/security/floorsheet/{security_id}{query}",
            {"id": self._signed("c")})

    # -- signed POST: index graphs -----------------------------------------------
    def index_intraday(self, index_id: int = 58) -> list:
        """Intraday index chart [[epochSeconds, value]] (homepage graph)."""
        return self.post_json(f"/api/nots/graph/index/{index_id}",  # type: ignore[return-value]
                              {"id": self._signed("a")})

    def index_range(self, index_code: int, start: str, end: str) -> list:
        """Index chart over a range (Charts 1W/1M/1Q/1Y; dates 'yyyy-MM-dd')."""
        return self.post_json(  # type: ignore[return-value]
            f"/api/nots/graph/index?indexCode={index_code}"
            f"&startDate={start}&endDate={end}",
            {"id": self._signed("a")})

"""Securities directory and listings. endpoints (mixin for NepseClient)."""

from __future__ import annotations

from typing import Optional


class SecuritiesMixin:
    # -- securities directory ----------------------------------------------
    def securities(self) -> list:
        """All securities [{securityId, securityName, securitySymbol}]."""
        return self.get_json("/api/nots/securities")  # type: ignore[return-value]

    def companies(self) -> list:
        """Non-delisted companies (selectors site-wide)."""
        return self.get_json("/api/nots/security?nonDelisted=true")  # type: ignore[return-value]

    def companies_list(self) -> list:
        """Listed companies directory."""
        return self.get_json("/api/nots/company/list")  # type: ignore[return-value]

    def companies_paged(self, page: int = 1) -> dict:
        """Combined directory {companies: Spring page, securities: 938 flat}.

        (Site's getListsOfCompanies(); page 1-based like the UI.)"""
        path = "/api/nots/company/"
        if page > 1:
            path += f"?page={page - 1}"
        return self.get_json(path)  # type: ignore[return-value]

    def margin_companies(self) -> list:
        """Margin-tradable companies."""
        return self.get_json("/api/nots/company/margin-list")  # type: ignore[return-value]

    def sectors(self) -> dict:
        """Sector directory {sectors[{id, sectorDescription, regulatoryBody}]}."""
        return self.get_json("/api/nots/sector")  # type: ignore[return-value]

    def debentures(self, instrument_type: str = "govBonds") -> list:
        """Listed debentures/bonds (Listing menu page; ``?type=`` required).

        Verified against the live page dropdown: ``"govBonds"`` (default,
        68 government bonds) and ``"debenture"`` (77 corporate debentures).
        Unknown values fall back to the bond list server-side.
        """
        return self.get_json(  # type: ignore[return-value]
            f"/api/nots/company/debentureAndBond?type={instrument_type}")

    def companies_non_promoter(self) -> list:
        """Non-promoter securities [{id, symbol, securityName, ...}].

        Filter source on the Listed Securities / Margin Securities pages
        (``security?nonPromoter=true`` — 649 rows, flatter than companies()).
        """
        return self.get_json("/api/nots/security?nonPromoter=true")  # type: ignore[return-value]

    def share_groups(self) -> list:
        """Share groups [{id, name}] — names A/Z/B/G drive classification()."""
        return self.get_json("/api/nots/security/shareGroup/")  # type: ignore[return-value]

    def classification(self, page: int = 1, size: int = 20,
                       share_group: Optional[str] = None) -> dict:
        """Company Classification page (Spring page; page 1-based like the UI;
        share_group is the A/Z/B/G letter — verified exhaustive: 31/107/108/34)."""
        query = f"?&size={size}"
        if share_group is not None:
            query += f"&shareGroup={share_group}"
        if page > 1:
            query = query.replace("?", f"?page={page - 1}", 1)
        # type: ignore[return-value]
        return self.get_json(f"/api/nots/security/classification{query}")

    def promoters(self, page: int = 1, size: int = 20) -> dict:
        """Promoter Share page (Spring page, 289 rows; page 1-based)."""
        path = "/api/nots/security/promoters?&size=" + str(size)
        if page > 1:
            path = f"/api/nots/security/promoters?page={page - 1}&size={size}"
        return self.get_json(path)  # type: ignore[return-value]

    def report_types(self) -> list:
        """Report directory (Reports menu: Weekly/Monthly/Annual/AGM/Other)."""
        return self.get_json("/api/nots/report/report-types")  # type: ignore[return-value]

    def reports_by_category(self, category_id: int, page: int = 1,
                            size: int = 20) -> dict:
        """Report files by category (Reports pages; category id = report
        type id 1..5; page 1-based like the UI; category 5 is empty)."""
        path = f"/api/web/report/reportByCategory/{category_id}?"
        if page > 1 or size != 20:
            path = (f"/api/web/report/reportByCategory/{category_id}?"
                    f"page={page - 1}&size={size}")
        return self.get_json(path)  # type: ignore[return-value]

    def events(self, page: int = 1, size: int = 20) -> dict:
        """Events page (Spring page; site grid uses size=6)."""
        path = "/api/web/event?&size=" + str(size)
        if page > 1:
            path = f"/api/web/event?page={page - 1}&size={size}"
        return self.get_json(path)  # type: ignore[return-value]

    def margin_trades(self, business_date: Optional[str] = None) -> dict:
        """Margin Trades page ({content Spring page, totalAmountInvested}).

        ``business_date`` defaults to the market ``asOf`` day. NOTE: the
        site itself calls this endpoint with an empty query and gets HTTP
        500 back; ``?businessDate=`` answers 200 (empty as of 2026-09-24).
        """
        if business_date is None:
            business_date = str(self.market_status().get("asOf", ""))[:10]
        return self.get_json(  # type: ignore[return-value]
            f"/api/margin/trades-report?businessDate={business_date}")

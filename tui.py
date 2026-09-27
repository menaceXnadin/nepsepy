"""Terminal UI to browse every endpoint in docs/nepse-api-catalog.md.

Stdlib only. Run:  python tui.py
Data summaries only; token material is never printed.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from nepsepy import NepseClient

TODAY = date.today().isoformat()
DISPLAY_ROWS = 15


def safe(text: object) -> str:
    """Render text without crashing Windows console encodings (cp1252)."""
    s = str(text)
    enc = sys.stdout.encoding or "utf-8"
    try:
        s.encode(enc)
        return s
    except UnicodeEncodeError:
        return s.encode(enc, errors="replace").decode(enc)

TOP_KINDS = [
    ("gainers", "Top gainers"), ("losers", "Top losers"),
    ("turnover", "Top turnover"), ("shares", "Top traded shares"),
    ("transactions", "Top transactions"), ("active", "Most active"),
]

TP_SORTS = ["symbol", "closePrice", "openPrice", "highPrice", "lowPrice",
            "totalTradedQuantity", "totalTradedValue", "totalTrades",
            "lastUpdatedPrice", "previousDayClosePrice", "averageTradedPrice",
            "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "marketCapitalization"]

FS_SORTS = ["contractid", "symbol", "buyer", "seller", "quantity", "rate",
            "amount"]


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return val or default


def pause() -> None:
    try:
        input("-- Enter for menu --")
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)


def save_blob(filename: str, blob: object) -> None:
    """Write a bytes payload (captcha/file/CSV) to disk."""
    data = bytes(blob) if isinstance(blob, (bytes, bytearray)) else blob
    if not isinstance(data, (bytes, bytearray)):
        print(f"unexpected payload: {type(blob).__name__}")
        pause()
        return
    with open(filename, "wb") as fh:
        fh.write(data)
    print(f"saved {len(data)} bytes -> {filename}")
    pause()


def pick(options: list[tuple[str, str]], title: str) -> str:
    print(f"\n== {title} ==")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {i}. {label}")
    print("  0. back")
    while True:
        choice = ask("choice", "0")
        if choice.isdigit() and 0 <= int(choice) <= len(options):
            if choice == "0":
                return ""
            return options[int(choice) - 1][0]
        print("invalid choice")


def show(title: str, rows: object, cols: list[str]) -> None:
    print(f"\n-- {title} --")
    if isinstance(rows, dict):
        for key, val in rows.items():
            if isinstance(val, (list, dict)):
                print(f"{key}: <{type(val).__name__} len="
                      f"{len(val) if hasattr(val, '__len__') else '?'}>")
            else:
                print(f"{key}: {safe(val)}")
        pause()
        return
    if not isinstance(rows, list) or not rows:
        print("(empty — market may be closed)")
        pause()
        return
    print(f"{len(rows)} rows")
    widths = {c: max(len(c), *(len(safe(r.get(c, ''))) for r in rows
                                if isinstance(r, dict))) for c in cols}
    print(" | ".join(c.ljust(widths[c]) for c in cols))
    for i, row in enumerate(rows):
        if i and i % DISPLAY_ROWS == 0:
            try:
                more = input(f"-- {i}/{len(rows)}, Enter=more, q=menu: ")
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if more.strip().lower() == "q":
                return
        if isinstance(row, dict):
            print(" | ".join(safe(row.get(c, "")).ljust(widths[c])
                             for c in cols))
        else:
            print(safe(row))
    pause()


class TUI:
    def __init__(self) -> None:
        self.client = NepseClient()
        self._companies: list[dict] | None = None

    def close(self) -> None:
        self.client.close()

    def resolve(self, symbol: str) -> int:
        """Symbol -> security id using the site's own company list."""
        if self._companies is None:
            self._companies = self.client.companies()
        for row in self._companies:
            if isinstance(row, dict) and \
                    str(row.get("symbol", "")).upper() == symbol.upper():
                return int(row["id"])
        raise ValueError(f"unknown symbol: {symbol}")

    def symbol_or_id(self) -> int:
        raw = ask("symbol or id", "ACLBSL")
        return int(raw) if raw.isdigit() else self.resolve(raw)

    # -- sections ---------------------------------------------------------
    def market(self) -> None:
        while True:
            key = pick([("status", "Market status"), ("sum", "Summary"),
                        ("hist", "Summary history"), ("tick", "Ticker"),
                        ("live", "Live snapshot")],
                       "Market")
            if not key:
                return
            if key == "status":
                show("market status", self.client.market_status(), [])
            elif key == "sum":
                show("market summary",
                     self.client.market_summary(), ["detail", "value"])
            elif key == "hist":
                show("summary history", self.client.market_summary_history(),
                     ["businessDate", "totalTurnover", "totalTradedShares",
                      "totalTransactions", "tradedScrips"])
            elif key == "tick":
                show("ticker", self.client.ticker(),
                     ["symbol", "lastTradedPrice", "totalTradeQuantity"])
            else:
                show("live snapshot", self.client.live_market(),
                     ["symbol", "lastTradedPrice", "previousClose",
                      "percentageChange", "totalTradeQuantity"])

    def tops(self) -> None:
        while True:
            key = pick(TOP_KINDS, "Top tens")
            if not key:
                return
            full = ask("full list? y/N", "N").lower() == "y"
            method = {"gainers": self.client.top_gainers,
                      "losers": self.client.top_losers,
                      "turnover": self.client.top_turnover,
                      "shares": self.client.top_traded_shares,
                      "transactions": self.client.top_transactions,
                      "active": self.client.top_active}[key]
            rows = method(full=full)
            cols = ["symbol", "lastTradedPrice", "pointChange",
                    "percentageChange"]
            if rows and isinstance(rows[0], dict):
                extra = [k for k in rows[0] if k not in cols
                         and k not in ("securityName", "securityId", "cp",
                                       "ltp")]
                cols += extra[:3]
            show(f"top {key} (full={full})", rows, cols)

    def today_price(self) -> None:
        page = int(ask("page", "1"))
        size = int(ask("size", "20"))
        sidx = pick([(s, s) for s in ["(none)"] + TP_SORTS], "Sort column")
        order = ""
        if sidx and sidx != "(none)":
            order = ask("order asc/desc", "desc")
        sym = ask("symbol filter (blank=none)")
        dt = ask("business date yyyy-mm-dd (blank=latest)")
        rows = self.client.today_price(
            page=page, size=size,
            sort_by="" if sidx in ("", "(none)") else sidx,
            sort_order=order,
            security_id=self.resolve(sym) if sym else None,
            business_date=dt or None)
        show("today price", rows.get("content", []),
             ["symbol", "closePrice", "openPrice", "highPrice", "lowPrice",
              "totalTradedQuantity", "totalTrades"])

    def floorsheet(self) -> None:
        page = int(ask("page", "1"))
        contract = ask("contract no (blank=none)")
        sym = ask("stock symbol (blank=none)")
        buyer = ask("buyer broker code (blank=none)")
        seller = ask("seller broker code (blank=none)")
        sidx = pick([(s, s) for s in FS_SORTS], "Sort column")
        order = ask("order asc/desc", "desc") if sidx else "desc"
        data = self.client.floorsheets(
            page=page, contract_no=int(contract) if contract else None,
            stock_id=self.resolve(sym) if sym else None,
            buyer_broker=int(buyer) if buyer else None,
            seller_broker=int(seller) if seller else None,
            sort_by=sidx or "contractId", sort_order=order or "desc")
        print(f"trades={data.get('totalTrades')} "
              f"qty={data.get('totalQty')} amount={data.get('totalAmount')}")
        show("floorsheet", data.get("floorsheets", {}).get("content", []),
             ["contractId", "stockSymbol", "contractQuantity", "contractRate",
              "contractAmount", "buyerBrokerName", "sellerBrokerName"])

    def depth(self) -> None:
        sid = self.symbol_or_id()
        odd = ask("odd lot? y/N", "N").lower() == "y"
        data = self.client.odd_lot_depth(sid) if odd \
            else self.client.market_depth(sid)
        print(f"buyQty={data.get('totalBuyQty')} "
              f"sellQty={data.get('totalSellQty')}")
        md = data.get("marketDepth", {})
        side = pick([("buy", "Buy side"), ("sell", "Sell side")], "Side")
        if not side:
            return
        show(f"{'odd-lot ' if odd else ''}{side} depth",
             md.get("buyMarketDepthList" if side == "buy"
                    else "sellMarketDepthList", []),
             ["orderBookOrderPrice", "quantity", "orderCount"])

    def indices(self) -> None:
        while True:
            key = pick([("snap", "Index snapshot"), ("sub", "Sub indices"),
                        ("list", "Index directory"),
                        ("hist", "Datewise index history"),
                        ("intra", "Intraday chart"),
                        ("range", "Range chart")], "Indices")
            if not key:
                return
            if key == "snap":
                show("nepse indices", self.client.nepse_indices(),
                     ["index", "close", "change", "perChange"])
            elif key == "sub":
                show("sub indices", self.client.sub_indices(),
                     ["id", "index", "change", "currentValue"])
            elif key == "list":
                show("index directory", self.client.indices_list(),
                     ["id", "indexCode", "indexName"])
            elif key == "hist":
                iid = int(ask("index id", "58"))
                page = int(ask("page", "1"))
                data = self.client.index_history(iid, page=page)
                show("index history", data.get("content", []),
                     ["businessDate", "openIndex", "highIndex", "lowIndex",
                      "closingIndex", "percentageChange"])
            elif key == "intra":
                iid = int(ask("index id", "58"))
                pts = self.client.index_intraday(iid)
                print(f"{len(pts)} points, last={pts[-1] if pts else None}")
                pause()
            else:
                iid = int(ask("index id", "58"))
                days = int(ask("days back", "7"))
                end = date.today().isoformat()
                start = (date.today() - timedelta(days=days)).isoformat()
                pts = self.client.index_range(iid, start, end)
                print(f"{len(pts)} points, last={pts[-1] if pts else None}")
                pause()

    def company(self) -> None:
        sid = self.symbol_or_id()
        while True:
            key = pick([("info", "Info header"), ("graph", "OHLC graph"),
                        ("intra", "Intraday LTP"),
                        ("price", "Price history"),
                        ("hist", "Trading history"),
                        ("snap", "Market snapshot"),
                        ("pic", "Market picture quote"),
                        ("div", "Dividends"),
                        ("profile", "Profile"), ("board", "Board"),
                        ("actions", "Corporate actions"),
                        ("fin", "Financials"), ("agm", "AGM"),
                        ("news", "Company news"),
                        ("book", "Book close (dead backend)")], "Company")
            if not key:
                return
            if key == "info":
                show("company info", self.client.company_info(sid), [])
            elif key == "graph":
                show("company graph", self.client.company_graph(sid),
                     ["businessDate", "openPrice", "highPrice", "lowPrice",
                      "closePrice", "totalTradedQuantity"])
            elif key == "intra":
                rows = self.client.company_graph_intraday(sid)
                print(f"{len(rows)} rows, last={rows[-1] if rows else None}")
                pause()
            elif key == "price":
                page = int(ask("page", "1"))
                data = self.client.security_price_history(sid, page=page)
                show("price history", data.get("content", []),
                     ["businessDate", "openPrice", "highPrice", "lowPrice",
                      "closePrice", "totalTradedQuantity"])
            elif key == "hist":
                start = ask("start yyyy-mm-dd (blank=none)")
                end = ask("end yyyy-mm-dd (blank=none)")
                data = self.client.stock_trading_history(
                    sid, start=start or None, end=end or None)
                show("trading history", data.get("content", []),
                     ["businessDate", "closePrice", "highPrice", "lowPrice",
                      "totalTradedQuantity"])
            elif key == "profile":
                show("profile", self.client.security_profile(sid), [])
            elif key == "snap":
                show("market snapshot", self.client.market_security(sid),
                     [])
            elif key == "pic":
                show("market picture", self.client.security_market_picture(sid),
                     [])
            elif key == "div":
                show("dividends", self.client.dividends(sid),
                     ["id", "applicationType", "applicationStatus"])
            elif key == "board":
                show("board", self.client.board_of_directors(sid),
                     ["name", "position", "appointmentDate"])
            elif key == "actions":
                show("corporate actions",
                     self.client.corporate_actions(sid),
                     ["fiscalYear", "bonusPercentage", "cashDividend",
                      "rightPercentage"])
            elif key == "fin":
                show("financials", self.client.financial_reports(sid),
                     ["id", "fiscalYear"])
            elif key == "agm":
                show("agm", self.client.agm(sid), ["id"])
            elif key == "book":
                nid = ask("book-close news id")
                print("note: backend 404s even for the site itself")
                show("book close", self.client.book_close(nid), [])
            else:
                show("company news",
                     self.client.security_company_news(sid),
                     ["id", "newsHeadline"])

    def company_lists(self) -> None:
        while True:
            key = pick([("flat", "Listed companies (flat)"),
                        ("paged", "Listed securities (paged)"),
                        ("margin", "Margin-tradable companies"),
                        ("nonpromo", "Non-promoter securities")],
                       "Company lists")
            if not key:
                return
            if key == "flat":
                show("listed companies", self.client.companies_list(),
                     ["id", "symbol", "securityName", "companyName"])
            elif key == "paged":
                page = int(ask("page", "1"))
                data = self.client.companies_paged(page=page)
                spr = data.get("companies", {}) \
                    if isinstance(data, dict) else {}
                secs = data.get("securities", []) \
                    if isinstance(data, dict) else []
                print(f"companies total={spr.get('totalElements')} "
                      f"+ {len(secs)} securities flat")
                show("listed companies (paged)", spr.get("content", []),
                     ["id", "companyShortName", "companyName"])
            elif key == "margin":
                show("margin companies", self.client.margin_companies(),
                     ["id", "symbol", "securityName", "companyName"])
            else:
                show("non-promoter", self.client.companies_non_promoter(),
                     ["id", "symbol", "securityName"])

    def summaries(self) -> None:
        while True:
            key = pick([("sector", "Sector summary"),
                        ("sectors", "Sector directory"),
                        ("groups", "Share groups"),
                        ("codir", "Company lists"),
                        ("class", "Classification"),
                        ("promo", "Promoter shares"),
                        ("margin", "Margin trades"),
                        ("deb", "Debentures/bonds"),
                        ("avg", "Trading average"),
                        ("marcap", "Market cap history")], "Summaries")
            if not key:
                return
            if key == "sector":
                dt = ask("business date (blank=latest)")
                show("sectors",
                     self.client.sector_summary(business_date=dt or None),
                     ["sectorName", "turnOverValues", "turnOverVolume",
                      "totalTransaction"])
            elif key == "avg":
                ndays = int(ask("n days", "120"))
                sym = ask("symbol (blank=all)")
                show("trading average",
                     self.client.trading_average(
                         n_days=ndays,
                         stock_id=self.resolve(sym) if sym else None),
                     ["symbol", "closingPriceAverage", "weightedAverage",
                      "closePrice", "totalTrades"])
            elif key == "sectors":
                show("sector directory",
                     self.client.sectors().get("sectors", []),
                     ["id", "sectorDescription", "regulatoryBody"])
            elif key == "groups":
                show("share groups", self.client.share_groups(),
                     ["id", "name"])
            elif key == "codir":
                self.company_lists()
            elif key == "class":
                sg = ask("share group A/Z/B/G (blank=all)").upper()
                page = int(ask("page", "1"))
                data = self.client.classification(
                    page=page, share_group=sg or None)
                print(f"total={data.get('totalElements')}")
                show("classification", data.get("content", []),
                     ["symbol", "isin", "listingDate", "permittedToTrade"])
            elif key == "promo":
                page = int(ask("page", "1"))
                data = self.client.promoters(page=page)
                print(f"total={data.get('totalElements')}")
                show("promoters", data.get("content", []),
                     ["symbol", "isin", "listingDate"])
            elif key == "margin":
                dt = ask("business date (blank=market asOf)")
                data = self.client.margin_trades(business_date=dt or None)
                print(f"total={data.get('totalElements')} "
                      f"invested={data.get('totalAmountInvested')}")
                show("margin trades", data.get("content", []),
                     ["businessDate", "symbol", "quantity"])
            elif key == "deb":
                typ = ask("type govBonds/debenture", "govBonds")
                rows = self.client.debentures(typ)
                if rows and isinstance(rows[0], dict) \
                        and "debentureName" in rows[0]:
                    cols = ["id", "debentureName", "debentureSymbol",
                            "couponRate", "listingDate", "maturityDate"]
                else:  # government bonds carry no separate symbol field
                    cols = ["id", "bondName", "couponRate", "listingDate",
                            "maturityDate"]
                show("debentures/bonds", rows, cols)
            else:
                show("market cap", self.client.market_cap_history(),
                     ["businessDate", "marCap", "senMarCap", "floatMarCap",
                      "senFloatMarCap"])

    def files(self) -> None:
        while True:
            key = pick([("captcha", "Captcha challenge + image"),
                        ("export", "Stock trading CSV export"),
                        ("notice", "Notice file download"),
                        ("appl", "Application file download"),
                        ("img", "Security image"),
                        ("secfile", "Security file")],
                       "Files & captcha")
            if not key:
                return
            if key == "captcha":
                ch = self.client.captcha_challenge()
                show("captcha challenge", ch, [])
                cid = ch.get("id") if isinstance(ch, dict) else None
                cid = ask("challenge id", str(cid or ""))
                out = ask("save image as", "captcha.jpg")
                save_blob(out, self.client.captcha_image(cid))
            elif key == "export":
                sid = self.symbol_or_id()
                start = ask("start yyyy-mm-dd (blank=none)")
                end = ask("end yyyy-mm-dd (blank=none)")
                out = ask("save csv as", "trading.csv")
                save_blob(out, self.client.export_stock_csv(
                    sid, start=start or None, end=end or None))
            elif key == "notice":
                name = ask("notice file name")
                out = ask("save as", name.rsplit("/", 1)[-1] or "notice.pdf")
                save_blob(out, self.client.fetch_notice_file(name))
            elif key == "appl":
                eid = ask("encrypted id")
                out = ask("save as", "application.pdf")
                save_blob(out, self.client.fetch_application_file(eid))
            elif key == "img":
                loc = ask("image file_location")
                out = ask("save as", loc.rsplit("/", 1)[-1] or "image.jpg")
                save_blob(out, self.client.security_image(loc))
            else:
                loc = ask("security file_location")
                out = ask("save as", loc.rsplit("/", 1)[-1] or "file.pdf")
                save_blob(out, self.client.security_file(loc))

    def news(self) -> None:
        while True:
            key = pick([("notices", "Notices"), ("discl", "Disclosures"),
                        ("feed", "Company news feed"),
                        ("holiday", "Holidays"), ("brokers", "Brokers"),
                        ("reports", "Report types"),
                        ("events", "Events"),
                        ("about", "About/contact"),
                        ("listing", "Listing info"),
                        ("officer", "Info officer")],
                       "News & reference")
            if not key:
                return
            if key == "notices":
                page = int(ask("page", "1"))
                data = self.client.notices(page=page)
                show("notices", data.get("content", []),
                     ["id", "noticeHeading", "noticeExpiryDate"])
            elif key == "discl":
                data = self.client.disclosures()
                sub = pick([("ex", "Exchange messages"),
                            ("cn", "Company news")], "Disclosures")
                if sub == "ex":
                    show("exchange messages", data.get("exchangeMessages",
                                                       []),
                         ["id", "messageTitle", "expiryDate"])
                elif sub == "cn":
                    show("company news", data.get("companyNews", []),
                         ["id", "newsHeadline"])
            elif key == "feed":
                sym = ask("filter symbol (blank=none)").upper()
                rows = self.client.company_news_list()
                if sym:
                    rows = [r for r in rows
                            if isinstance(r, dict) and r.get("symbol") == sym]
                show("company news feed", rows,
                     ["id", "symbol", "newsHeadline", "publishedDate"])
            elif key == "holiday":
                year = ask("year", "2027")
                show("holidays", self.client.holidays(int(year)),
                     ["holidayDate", "holidayDescription"])
            elif key == "reports":
                show("report types", self.client.report_types(),
                     ["id", "typeName", "description"])
                cid = ask("browse category id (blank=skip)")
                if cid:
                    page = int(ask("page", "1"))
                    data = self.client.reports_by_category(int(cid), page=page)
                    print(f"total={data.get('totalElements')}")
                    show("reports", data.get("content", []),
                         ["id", "filename", "description", "publishedDate"])
            elif key == "listing":
                show("listing info", self.client.listing_info(), [])
            elif key == "about":
                sub = pick([("intro", "Introductions"),
                            ("struct", "Structure"),
                            ("contact", "Contact info")], "About")
                if sub == "intro":
                    data = self.client.about_introduction()
                    print(f"total={data.get('totalElements')}")
                    show("introductions", data.get("content", []), ["id"])
                elif sub == "struct":
                    data = self.client.about_structure()
                    print(f"total={data.get('totalElements')}")
                    show("structure", data.get("content", []), ["id"])
                elif sub == "contact":
                    show("contact info", self.client.contact_info(), [])
            elif key == "events":
                page = int(ask("page", "1"))
                data = self.client.events(page=page)
                print(f"total={data.get('totalElements')}")
                show("events", data.get("content", []),
                     ["id", "eventHeading"])
            elif key == "officer":
                show("info officer", self.client.info_officer(), [])
            else:
                name = ask("broker name search (blank=all)")
                data = self.client.brokers(
                    criteria={"memberName": name} if name else None)
                show("brokers", data.get("content", []),
                     ["memberCode", "memberName"])

    def run(self) -> None:
        print("Bootstrapping public session ...")
        self.client.bootstrap()
        print(self.client.describe_state())
        sections = [("mkt", "Market status/summary/ticker", self.market),
                    ("top", "Top tens", self.tops),
                    ("tp", "Today price", self.today_price),
                    ("fs", "Floor sheet", self.floorsheet),
                    ("depth", "Market depth", self.depth),
                    ("idx", "Indices & charts", self.indices),
                    ("co", "Company", self.company),
                     ("sum", "Directories & summaries", self.summaries),
                     ("news", "News/notices/holidays/brokers", self.news),
                     ("files", "Files, CSV export & captcha", self.files)]
        try:
            while True:
                key = pick([(k, label) for k, label, _ in sections],
                           "NEPSE explorer")
                if not key:
                    print("bye")
                    return
                for k, _, fn in sections:
                    if k == key:
                        try:
                            fn()
                        except ValueError as exc:
                            print(f"input error: {exc}")
                        except Exception as exc:  # keep the TUI alive
                            print(f"{type(exc).__name__}: {exc}")
                        break
        finally:
            self.close()


if __name__ == "__main__":
    TUI().run()

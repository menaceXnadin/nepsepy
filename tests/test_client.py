"""Unit tests. Fake tokens/indexes only — no live credentials anywhere."""

import asyncio

import httpx
import pytest

from nepsepy import AsyncNepseClient, NepseClient
from nepsepy.auth import ProveResponse, TokenState
from nepsepy.exceptions import (AuthExpiredError, BootstrapError,
                                PublicEndpointError, RateLimitedError)
from nepsepy.wasm import strip_at_indexes

FAKE_ACCESS = "ACCESS-0123456789-fake-token-abcdef"
FAKE_REFRESH = "REFRESH-9876543210-fake-token-ghijkl"


def fake_prove(access=FAKE_ACCESS, refresh=FAKE_REFRESH):
    return {"serverTime": 1, "salt": "x", "accessToken": access,
            "refreshToken": refresh, "salt1": 11, "salt2": 22, "salt3": 33,
            "salt4": 44, "salt5": 55, "isDisplayActive": False,
            "popupDocFor": ""}


class FakeCleaner:
    """Deterministic stand-in for css.wasm (fixed fake indexes)."""
    ACCESS_IDX = (2, 5, 8, 11, 14)
    REFRESH_IDX = (1, 4, 7, 10, 13)

    def access_indexes(self, *salts):
        return self.ACCESS_IDX

    def refresh_indexes(self, *salts):
        return self.REFRESH_IDX

    def clean_access(self, raw, salts):
        return strip_at_indexes(raw, self.ACCESS_IDX)

    def clean_refresh(self, raw, salts):
        return strip_at_indexes(raw, self.REFRESH_IDX)


def make_client(handler, **kw):
    kw.setdefault("min_interval", 0)
    client = NepseClient(transport=httpx.MockTransport(handler), **kw)
    client._cleaner = FakeCleaner()  # never touch real wasm in unit tests
    return client


# -- async client ----------------------------------------------------------

def test_async_client_awaits_endpoint_methods():
    calls = {"prove": 0, "data": 0}

    def handler(request):
        if request.url.path == "/api/authenticate/prove":
            calls["prove"] += 1
            return httpx.Response(200, json=fake_prove())
        calls["data"] += 1
        return httpx.Response(200, json={"isOpen": "CLOSE"})

    async def run():
        async with AsyncNepseClient(
                transport=httpx.MockTransport(handler), min_interval=0) as client:
            client._client._cleaner = FakeCleaner()
            return await client.market_status()

    assert asyncio.run(run()) == {"isOpen": "CLOSE"}
    assert calls == {"prove": 1, "data": 1}


def test_async_client_refreshes_once():
    calls = {"prove": 0, "refresh": 0, "data": 0}

    async def run():
        async with AsyncNepseClient(
                transport=httpx.MockTransport(_refresh_handler(calls, [401, 200])),
                min_interval=0) as client:
            client._client._cleaner = FakeCleaner()
            return await client.market_summary()

    assert asyncio.run(run()) == []
    assert calls == {"prove": 1, "refresh": 1, "data": 2}


# -- transformation -------------------------------------------------------

def test_strip_removes_chars_at_indexes():
    token = "0123456789ABCDEFGHIJ"
    assert strip_at_indexes(token, (2, 5, 8, 11, 14)) == "0134679ACDFGHIJ"


def test_strip_rejects_bad_indexes():
    with pytest.raises(Exception):
        strip_at_indexes("0123456789ABCDEFGHIJ", (2, 5, 8))  # not 5
    with pytest.raises(Exception):
        strip_at_indexes("0123456789ABCDEFGHIJ", (2, 5, 8, 11, 99))  # oob
    with pytest.raises(Exception):
        strip_at_indexes("0123456789ABCDEFGHIJ", (14, 11, 8, 5, 2))  # unsorted


# -- malformed prove -------------------------------------------------------

@pytest.mark.parametrize("payload", [
    None, [], "nope",
    {},
    fake_prove(access="short"),
    dict(fake_prove(), salt3="not-an-int"),
    {k: v for k, v in fake_prove().items() if k != "salt5"},
])
def test_malformed_prove_rejected(payload):
    with pytest.raises(BootstrapError):
        ProveResponse.from_dict(payload)


# -- redaction ---------------------------------------------------------------

def test_tokens_never_echoed():
    prove = ProveResponse.from_dict(fake_prove())
    assert FAKE_ACCESS not in repr(prove)
    state = TokenState(access=FAKE_ACCESS, refresh=FAKE_REFRESH)
    assert FAKE_ACCESS not in repr(state)
    assert FAKE_REFRESH not in repr(state)
    try:
        ProveResponse.from_dict(fake_prove(access=12345))
    except BootstrapError as exc:
        assert "12345" not in str(exc)


def test_describe_state_redacted():
    def handler(request):
        return httpx.Response(200, json=fake_prove())

    client = make_client(handler)
    client.bootstrap()
    desc = client.describe_state()
    assert FAKE_ACCESS not in desc and FAKE_REFRESH not in desc
    client.close()


# -- authorization header -----------------------------------------------------

def test_auth_header_shape():
    state = TokenState(access="FAKE-CLEANED", refresh="R")
    assert state.auth_header() == {"Authorization": "Salter FAKE-CLEANED"}
    with pytest.raises(BootstrapError):
        TokenState(access="", refresh="R").auth_header()


def test_salter_header_sent_redacted_check():
    seen = {}

    def handler(request):
        if request.url.path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=[{"symbol": "X"}])

    client = make_client(handler)
    resp = client.get("/api/nots/securityDailyTradeStat/58")
    assert resp.status_code == 200
    assert seen["auth"].startswith("Salter ")
    assert seen["auth"] == f"Salter {strip_at_indexes(FAKE_ACCESS, (2, 5, 8, 11, 14))}"
    client.close()


# -- endpoint guardrails -------------------------------------------------------

def test_non_public_paths_blocked():
    def handler(request):
        if request.url.path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        return httpx.Response(200, json=[])

    client = make_client(handler)
    for bad in ("/api/cms/notice/downloadNotice/1", "/cms/x",
                "/api/authenticate/login", "/api/other/thing", "relative"):
        with pytest.raises(PublicEndpointError):
            client.get(bad)
        with pytest.raises(PublicEndpointError):
            client.post(bad, {"id": 1})
    # exact no-trailing-slash UI path is allowed
    assert client.get("/api/nots").status_code == 200
    client.close()


# -- 401 refresh: at most once ----------------------------------------------------

def _refresh_handler(calls, data_statuses):
    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            calls["prove"] += 1
            return httpx.Response(200, json=fake_prove())
        if path == "/api/authenticate/refresh-token":
            calls["refresh"] += 1
            assert request.method == "POST"
            return httpx.Response(200, json=fake_prove())
        calls["data"] += 1
        return httpx.Response(data_statuses[min(calls["data"] - 1,
                                                len(data_statuses) - 1)],
                              json=[])
    return handler


def test_401_refresh_then_retry_once():
    calls = {"prove": 0, "refresh": 0, "data": 0}
    client = make_client(_refresh_handler(calls, [401, 200]))
    resp = client.get("/api/nots/market-summary/")
    assert resp.status_code == 200
    assert calls == {"prove": 1, "refresh": 1, "data": 2}
    client.close()


def test_double_401_raises_without_loop():
    calls = {"prove": 0, "refresh": 0, "data": 0}
    client = make_client(_refresh_handler(calls, [401, 401]))
    with pytest.raises(AuthExpiredError):
        client.get("/api/nots/market-summary/")
    assert calls["refresh"] == 1 and calls["data"] == 2
    client.close()


# -- 429 handling ------------------------------------------------------------------

def test_429_raises_without_retry_loop():
    calls = {"n": 0}

    def handler(request):
        if request.url.path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={})

    client = make_client(handler)
    with pytest.raises(RateLimitedError):
        client.get("/api/nots/market-summary/")
    assert calls["n"] == 1  # no evasion loop
    client.close()


def test_prove_429_surfaced():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "0"}, json={})

    client = make_client(handler)
    client._cleaner = None
    with pytest.raises(RateLimitedError):
        client.bootstrap()
    client.close()


# -- checksums (pure math, fake salts) -----------------------------------------

def test_checksum_base_and_variants():
    from nepsepy import checksum_a, checksum_b, checksum_c
    from nepsepy.checksum import base, sign
    # locks the DUMMY row the live site used on 2026-09-27 (market id 80)
    assert base(80, 27) == 291
    salts = (11, 22, 33, 44, 55)
    # 291 % 10 == 1 -> hi branch in every variant
    assert sign(291, salts, 27, 5, 3, 1) == 291 + 44 * 27 - 33  # A
    assert sign(291, salts, 27, 5, 1, 3) == 291 + 22 * 27 - 11  # B
    assert sign(291, salts, 27, 4, 1, 3) == 291 + 22 * 27 - 11  # C
    assert checksum_a(291, salts, 27) == 1446
    assert checksum_b(291, salts, 27) == 874
    assert checksum_c(291, salts, 27) == 874
    # lo branch: value ending in 7
    assert sign(297, salts, 27, 5, 3, 1) == 297 + 22 * 27 - 11
    assert sign(297, salts, 27, 4, 1, 3) == 297 + 44 * 27 - 33


# -- signed POST wiring (MockTransport, fake salts) ------------------------------

def _signed_client(monkeypatch, seen):
    import nepsepy.client as client_mod

    monkeypatch.setattr(client_mod, "_ck_day", lambda: 27)

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            seen["mopen"] += 1
            return httpx.Response(200, json={"isOpen": "CLOSE",
                                             "asOf": "2026-09-24T15:00:00",
                                             "id": 80})
        if request.method == "POST":
            import json as _json
            seen["posts"].append((path, str(request.url.query),
                                  _json.loads(request.content.decode())))
            return httpx.Response(200, json={"content": [], "totalPages": 1,
                                             "totalElements": 0, "number": 0,
                                             "size": 20})
        return httpx.Response(200, json=[])

    seen["mopen"] = 0
    seen["posts"] = []
    return make_client(handler)


def test_signed_posts_send_expected_ids_and_paths(monkeypatch):
    seen: dict = {}
    client = _signed_client(monkeypatch, seen)
    # fake salts (11,22,33,44,55): base(80,27)=291 -> A=1446 B=C=874
    client.today_price()
    client.floorsheets(contract_no=2026092405016843)
    client.index_intraday(58)
    client.company_info(2790)
    by_path = {p: (q, b) for p, q, b in seen["posts"]}
    assert by_path["/api/nots/nepse-data/today-price"][1] == {"id": 874}
    fs_q = by_path["/api/nots/nepse-data/floorsheet"][0]
    assert "2026092405016843" in fs_q and "sort=contractId" in fs_q
    assert by_path["/api/nots/nepse-data/floorsheet"][1] == {"id": 874}
    assert by_path["/api/nots/graph/index/58"][1] == {"id": 1446}
    assert by_path["/api/nots/security/2790"][1] == {"id": 291}
    assert seen["mopen"] == 1  # market id fetched once, then cached
    client.close()


def test_security_floorsheet_mirrors_site_tab_request(monkeypatch):
    seen: dict = {}
    client = _signed_client(monkeypatch, seen)
    client.security_floorsheet(2790, business_date="2026-09-24")
    by_path = {p: (q, b) for p, q, b in seen["posts"]}
    q, b = by_path["/api/nots/security/floorsheet/2790"]
    assert "businessDate=2026-09-24" in q
    assert "sort=contractId,asc" in q
    assert b == {"id": 874}  # variant C, like the main floorsheet
    client.close()


def test_ui_page_numbers_map_to_zero_based(monkeypatch):
    import nepsepy.client as client_mod

    monkeypatch.setattr(client_mod, "_ck_day", lambda: 27)
    seen = {"gets": [], "posts": []}

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            return httpx.Response(200, json={"id": 80})
        if request.method == "POST":
            seen["posts"].append((path, request.url.query.decode("ascii")))
            return httpx.Response(200, json={"content": []})
        seen["gets"].append((path, request.url.query.decode("ascii")))
        return httpx.Response(200, json={"content": []})

    client = make_client(handler)
    client.today_price(page=1)
    client.today_price(page=2)
    client.index_history(index_id=57, page=1)
    client.index_history(index_id=57, page=3)
    client.notices(page=1)
    client.notices(page=2)
    gets = seen["gets"]
    posts = seen["posts"]
    tp = [q for p, q in posts if p == "/api/nots/nepse-data/today-price"]
    assert "page=" not in tp[0]       # UI page 1 -> no page param
    assert "page=1" in tp[1]          # UI page 2 -> api page 1
    ih = [q for p, q in gets if p == "/api/nots/index/history/57"]
    assert ih[0] == "&size=20"
    assert "page=2" in ih[1]          # UI page 3 -> api page 2
    nn = [q for p, q in gets if p == "/api/nots/news/notice/all"]
    assert nn[0] == "page=0"
    assert nn[1] == "page=1"
    client.close()


def test_post_401_refreshes_only_once(monkeypatch):
    import nepsepy.client as client_mod

    monkeypatch.setattr(client_mod, "_ck_day", lambda: 27)
    calls = {"prove": 0, "refresh": 0, "post": 0}

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            calls["prove"] += 1
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            return httpx.Response(200, json={"id": 80})
        if path == "/api/authenticate/refresh-token":
            calls["refresh"] += 1
            return httpx.Response(200, json=fake_prove())
        calls["post"] += 1
        if calls["post"] == 1:
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"content": []})

    client = make_client(handler)
    data = client.today_price()
    assert data == {"content": []}
    assert calls == {"prove": 1, "refresh": 1, "post": 2}
    client.close()


# -- brokers / filters / sort passthrough ---------------------------------------

def test_brokers_list_search_and_dealers():
    seen = {}

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            return httpx.Response(200, json={"id": 80})
        seen["last"] = (request.method, path, request.url.query.decode())
        if request.method == "POST":
            import json as _json
            seen["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"content": [], "totalElements": 0})

    client = make_client(handler)
    client.brokers()
    assert seen["last"] == ("GET", "/api/nots/member", "&size=20")
    client.brokers(page=3, size=50)
    assert seen["last"] == ("GET", "/api/nots/member", "page=2&size=50")
    client.brokers(criteria={"memberName": "Kumari"})
    assert seen["last"][0] == "POST"
    # site always sends the full criteria object with defaults
    assert seen["body"]["memberName"] == "Kumari"
    assert seen["body"]["provinceId"] == 0
    assert seen["body"]["memberCode"] == ""
    client.dealers(page=2)
    assert seen["last"] == ("GET", "/api/nots/member/dealer",
                            "page=1&size=20")
    client.close()


def test_sort_and_filter_query_passthrough(monkeypatch):
    import nepsepy.client as client_mod

    monkeypatch.setattr(client_mod, "_ck_day", lambda: 27)
    seen = []

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            return httpx.Response(200, json={"id": 80})
        seen.append((request.method, path, request.url.query.decode()))
        return httpx.Response(200, json={"content": []})

    client = make_client(handler)
    client.today_price(sort_by="closePrice", sort_order="desc")
    client.floorsheets(sort_by="rate", sort_order="asc")
    client.today_price(business_date="2026-09-24", security_id=2790)
    client.security_price_history(2790, business_date="2026-09-24")
    client.stock_trading_history(2790, start="2026-09-01", end="2026-09-24")
    client.trading_average(n_days=30, stock_id=2790)
    client.sector_summary(business_date="2026-09-24")
    queries = [q for _, _, q in seen]
    assert "sort=closePrice%2Cdesc" in queries[0] or \
        "sort=closePrice,desc" in queries[0]
    assert "sort=rate%2Casc" in queries[1] or "sort=rate,asc" in queries[1]
    assert "businessDate=2026-09-24" in queries[2]
    assert "securityId=2790" in queries[2]
    assert "businessDate=2026-09-24" in queries[3]
    assert "startDate=2026-09-01" in queries[4]
    assert "endDate=2026-09-24" in queries[4]
    assert "nDays=30" in queries[5] and "stockId=2790" in queries[5]
    assert "businessDate=2026-09-24" in queries[6]
    client.close()


def test_second_pass_endpoints_hit_expected_paths():
    seen = []

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            return httpx.Response(200, json={"id": 80})
        seen.append((request.method, path, request.url.query.decode()))
        if path == "/api/nots/sector":
            return httpx.Response(200, json={"sectors": []})
        return httpx.Response(200, json={"content": [], "totalElements": 0})

    client = make_client(handler)
    client.sectors()
    client.debentures("bond")
    client.share_groups()
    client.classification(page=2, size=5, share_group="A")
    client.promoters()
    client.report_types()
    client.market_security(2790)
    client.security_market_picture(2790)
    client.dividends(2790)
    client.book_close(70749)
    client.listing_info()
    client.info_officer()
    got = {(m, p) for m, p, _ in seen}
    assert ("GET", "/api/nots/sector") in got
    assert ("GET", "/api/nots/company/debentureAndBond") in got
    assert ("GET", "/api/nots/security/shareGroup/") in got
    assert ("GET", "/api/nots/security/classification") in got
    assert ("GET", "/api/nots/security/promoters") in got
    assert ("GET", "/api/nots/report/report-types") in got
    assert ("GET", "/api/nots/market/security/2790") in got
    assert ("GET", "/api/nots/security-detail/2790") in got
    assert ("GET", "/api/nots/application/dividend/2790") in got
    assert ("GET", "/api/nots/news/book-close/70749") in got
    assert ("GET", "/api/web/listing-info") in got
    assert ("GET", "/api/web/info-officer") in got
    queries = {p: q for _, p, q in seen}
    assert "type=bond" in queries["/api/nots/company/debentureAndBond"]
    assert "page=1" in queries["/api/nots/security/classification"]
    assert "shareGroup=A" in queries["/api/nots/security/classification"]
    client.close()


def test_third_pass_endpoints_hit_expected_paths():
    seen = []

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            return httpx.Response(200, json={"id": 80, "asOf": "2026-09-24T15:00:00"})
        seen.append((request.method, path, request.url.query.decode()))
        return httpx.Response(200, json={"content": [], "totalElements": 0})

    client = make_client(handler)
    client.reports_by_category(1)
    client.reports_by_category(2, page=3, size=5)
    client.events()
    client.events(page=2)
    client.margin_trades(business_date="2026-09-24")
    client.margin_trades()  # defaults to market asOf
    client.companies_non_promoter()
    client.debentures()  # default mirrors the page dropdown
    got = {(m, p) for m, p, _ in seen}
    assert ("GET", "/api/web/report/reportByCategory/1") in got
    assert ("GET", "/api/web/report/reportByCategory/2") in got
    assert ("GET", "/api/web/event") in got
    assert ("GET", "/api/margin/trades-report") in got
    assert ("GET", "/api/nots/security") in got
    assert ("GET", "/api/nots/company/debentureAndBond") in got
    queries = {p: q for _, p, q in seen}
    assert "page=2" in queries["/api/web/report/reportByCategory/2"]
    assert "page=1" in queries["/api/web/event"]
    assert queries["/api/margin/trades-report"] == "businessDate=2026-09-24"
    assert "nonPromoter=true" in queries["/api/nots/security"]
    assert "type=govBonds" in queries["/api/nots/company/debentureAndBond"]
    client.close()


def test_fourth_pass_excluded_endpoints_hit_expected_paths():
    seen = []

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            return httpx.Response(200, json={"id": 80, "asOf": "2026-09-24T15:00:00"})
        seen.append((request.method, path, request.url.query.decode()))
        if path == "/api/web/about-us/introduction":
            return httpx.Response(200, json={"content": [], "totalElements": 0})
        return httpx.Response(200, json=[], headers={"content-type": "application/json"})

    client = make_client(handler)
    assert client.live_market() == []
    client.companies_paged()
    client.companies_paged(page=2)
    client.about_introduction()
    client.about_structure(page=2)
    client.contact_info()
    client.captcha_challenge()
    got = {(m, p) for m, p, _ in seen}
    assert ("GET", "/api/nots/lives-market") in got
    assert ("GET", "/api/nots/company/") in got
    assert ("GET", "/api/web/about-us/introduction") in got
    assert ("GET", "/api/web/about-us/structure") in got
    assert ("GET", "/api/web/about-us/contact-info") in got
    assert ("GET", "/api/web/captcha/id") in got
    queries = {p: q for _, p, q in seen}
    assert "page=1" in queries["/api/nots/company/"]
    assert "page=1" in queries["/api/web/about-us/structure"]
    # binary download methods return raw bytes through the same paths
    client.close()


def test_binary_downloads_return_bytes(monkeypatch):
    import nepsepy.client as client_mod

    monkeypatch.setattr(client_mod, "_ck_day", lambda: 27)
    seen = []

    def handler(request):
        path = request.url.path
        if path == "/api/authenticate/prove":
            return httpx.Response(200, json=fake_prove())
        if path == "/api/nots/nepse-data/market-open":
            return httpx.Response(200, json={"id": 80})
        seen.append((request.method, path, request.url.query.decode()))
        return httpx.Response(200, content=b"BINARY",
                              headers={"content-type": "application/octet-stream"})

    client = make_client(handler)
    assert client.captcha_image("abc") == b"BINARY"
    assert client.fetch_application_file("enc") == b"BINARY"
    assert client.fetch_notice_file("f.pdf") == b"BINARY"
    assert client.export_stock_csv(2790) == b"BINARY"
    assert client.security_image("loc") == b"BINARY"
    assert client.security_file("loc") == b"BINARY"
    got = {(m, p) for m, p, _ in seen}
    assert ("GET", "/api/web/captcha/image/abc") in got
    assert ("GET", "/api/nots/application/fetchFiles") in got
    assert ("GET", "/api/nots/news/notice/fetchFiles/f.pdf") in got
    assert ("GET", "/api/nots/market/export/2790") in got
    assert ("GET", "/api/nots/security/getImage") in got
    assert ("GET", "/api/nots/security/fetchFiles") in got
    client.close()

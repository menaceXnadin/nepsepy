"""News, calendar, captcha, files and reference data. endpoints (mixin for NepseClient)."""

from __future__ import annotations

from typing import Optional


class NewsMixin:
    # -- news / notices / calendar -----------------------------------------------------
    def notices(self, page: int = 1) -> dict:
        """Notices (Spring page; page 1-based like the UI)."""
        return self.get_json(f"/api/nots/news/notice/all?page={page - 1}")  # type: ignore[return-value]

    def disclosures(self) -> dict:
        """Homepage disclosures {exchangeMessages, companyNews}."""
        return self.get_json("/api/nots/news/companies/disclosure")  # type: ignore[return-value]

    def company_news_list(self) -> list:
        """Corporate disclosures feed (8836 rows at capture time)."""
        return self.get_json("/api/nots/news/media/company-news")  # type: ignore[return-value]

    def news_alerts(self, page: int = 1) -> list:
        if page <= 1:
            return self.get_json("/api/nots/news/media/news-and-alerts")  # type: ignore[return-value]
        return self.get_json(f"/api/nots/news/media/news-and-alerts/?page={page - 1}")  # type: ignore[return-value]

    def press_releases(self, page: int = 1) -> list:
        if page <= 1:
            return self.get_json("/api/nots/news/press-release")  # type: ignore[return-value]
        return self.get_json(f"/api/nots/news/press-release?page={page - 1}")  # type: ignore[return-value]

    def investor_awareness(self) -> list:
        return self.get_json("/api/nots/news/media/investor-awareness")  # type: ignore[return-value]

    def holiday_years(self) -> list:
        return self.get_json("/api/nots/holiday/year")  # type: ignore[return-value]

    def holidays(self, year: int) -> list:
        """Market holidays [{holidayDate, holidayDescription}]."""
        return self.get_json(f"/api/nots/holiday/list?year={year}")  # type: ignore[return-value]

    def menu(self) -> list:
        return self.get_json("/api/web/menu/")  # type: ignore[return-value]

    def listing_info(self) -> dict:
        """Listing Information page content {headline, body} (web CMS)."""
        return self.get_json("/api/web/listing-info")  # type: ignore[return-value]

    def info_officer(self) -> dict:
        """Information officer contact (web CMS)."""
        return self.get_json("/api/web/info-officer")  # type: ignore[return-value]

    def about_introduction(self, page: Optional[int] = None) -> dict:
        """About-Us introductions (Spring page; site passes ?page=0-based
        only past the first page)."""
        path = "/api/web/about-us/introduction"
        if page is not None and page > 1:
            path += f"?page={page - 1}"
        return self.get_json(path)  # type: ignore[return-value]

    def about_structure(self, page: Optional[int] = None) -> dict:
        """About-Us org structure (same paging as introduction)."""
        path = "/api/web/about-us/structure"
        if page is not None and page > 1:
            path += f"?page={page - 1}"
        return self.get_json(path)  # type: ignore[return-value]

    def contact_info(self) -> dict:
        """Contact-Us info {contact, id} (web CMS)."""
        return self.get_json("/api/web/about-us/contact-info")  # type: ignore[return-value]

    # -- captcha (suggestion-box flow; read-only steps only) -------------------
    def captcha_challenge(self) -> dict:
        """Captcha challenge {id} (public; image/reload hang off the id)."""
        return self.get_json("/api/web/captcha/id")  # type: ignore[return-value]

    def captcha_image(self, challenge_id: str) -> bytes:
        """Captcha image bytes (octet-stream). NOTE: the reload sibling
        (web/captcha/reload/{id}) currently 500s server-side."""
        return self.get(
            f"/api/web/captcha/image/{challenge_id}").content

    # -- file downloads (binary; verified live) --------------------------------
    def fetch_application_file(self, encrypted_id: str) -> bytes:
        """Application/AGM report file (PDF bytes; id from e.g. disclosures)."""
        return self.get(  # type: ignore[return-value]
            f"/api/nots/application/fetchFiles?encryptedId={encrypted_id}").content

    def fetch_notice_file(self, file_name: str) -> bytes:
        """Notice attachment bytes (fileName from notices())."""
        return self.get(  # type: ignore[return-value]
            f"/api/nots/news/notice/fetchFiles/{file_name}").content

    def export_stock_csv(self, security_id: int,
                         start: Optional[str] = None,
                         end: Optional[str] = None) -> bytes:
        """Stock Trading CSV export (site's export path; dates 'yyyy-MM-dd')."""
        path = f"/api/nots/market/export/{security_id}"
        query = "&".join(
            [f"startDate={start}" for _ in [0] if start] +
            [f"endDate={end}" for _ in [0] if end])
        if query:
            path += "?" + query
        return self.get(path).content

    def security_image(self, file_location: str) -> bytes:
        """Security image envelope (logos, board portraits) — raw body.

        The response is JSON ``{"content": "<base64>"}``, NOT raw image
        bytes. To process: parse the JSON, take ``["content"]``, strip
        whitespace, pad to a multiple of 4 (``+= "=" * (-len(s) % 4)``),
        then base64-decode — you get JPEG/PNG bytes (magic ``ffd8ff``).
        For web display the site's own bundle prefixes the string as
        ``"data:image/PNG;base64," + content`` straight into an <img>.
        ``fileLocation`` from e.g. ``security_profile()["logoFilePath"]``
        (verified: BARUN logo decodes to a 25 KB JPEG).
        NOTE: returns the raw envelope; decoding is left to the caller.
        """
        return self.get(  # type: ignore[return-value]
            f"/api/nots/security/getImage?fileLocation={file_location}").content

    def security_file(self, file_location: str) -> bytes:
        """Security file bytes (same fileLocation scheme) — raw bytes.

        Unlike security_image(), this one returns the file directly
        (verified: BARUN logo path yields ``image/jpeg`` + JFIF magic,
        no envelope). Save the body as-is.
        """
        return self.get(  # type: ignore[return-value]
            f"/api/nots/security/fetchFiles?fileLocation={file_location}").content

    # -- brokers / dealers (reference data) --------------------------------------
    def brokers(self, page: int = 1, size: int = 20,
                criteria: Optional[dict] = None) -> dict:
        """Broker directory (Spring page; page 1-based like the UI).

        criteria mirrors the Brokers search form: memberName,
        contactPerson, contactNumber, memberCode, provinceId, districtId,
        municipalityId. The site always sends the full object with
        defaults, so missing keys are filled the same way.
        """
        if page > 1:
            path = f"/api/nots/member?page={page - 1}&size={size}"
        else:
            path = f"/api/nots/member?&size={size}"
        if criteria:
            body = {"memberName": "", "contactPerson": "",
                    "contactNumber": "", "memberCode": "", "provinceId": 0,
                    "districtId": 0, "municipalityId": 0}
            body.update(criteria)
            return self.post_json(path, body)  # type: ignore[return-value]
        return self.get_json(path)  # type: ignore[return-value]

    def dealers(self, page: int = 1, size: int = 20,
                criteria: Optional[dict] = None) -> dict:
        """Dealer directory (same shape/conventions as brokers)."""
        if page > 1:
            path = f"/api/nots/member/dealer?page={page - 1}&size={size}"
        else:
            path = f"/api/nots/member/dealer?&size={size}"
        if criteria:
            body = {"memberName": "", "contactPerson": "",
                    "contactNumber": "", "memberCode": "", "provinceId": 0,
                    "districtId": 0, "municipalityId": 0}
            body.update(criteria)
            return self.post_json(path, body)  # type: ignore[return-value]
        return self.get_json(path)  # type: ignore[return-value]

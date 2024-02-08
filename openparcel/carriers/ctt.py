#!/usr/bin/env python3

from openparcel.carriers.base import BrowserBaseCarrier


class CarrierCTT(BrowserBaseCarrier):
    uid = 'ctt'
    name = 'CTT'
    tracking_url_base = \
        'https://appserver.ctt.pt/CustomerArea/PublicArea_Detail?' \
        'ObjectCodeInput=${tracking_code}&SearchInput=${tracking_code}'
    accent_color = '#DE0024'

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)

    def fetch(self):
        try:
            self._fetch_page()
            self.page.wait.title_change('Detalhe', timeout=5, raise_err=True)
            self._wait_page_complete(
                '[data-block="TrackTrace.TT_Timeline_New"] '
                '[data-block="CustomerArea.AC_TimelineItemCustom"]')
            self._create_resp_dict(
                self.page.run_js_loaded(self._get_scraping_js(), as_expr=True))
        finally:
            # Quit the browser.
            self._close_page()

        return self._resp_dict

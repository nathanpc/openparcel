#!/usr/bin/env python3

from DrissionPage.errors import WaitTimeoutError

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
            try:
                self.page.wait.title_change('Detalhe', raise_err=True,
                                            timeout=self._timeout(10))
                self._wait_page_complete(
                    '[data-block="TrackTrace.TT_Timeline_New"] '
                    '[data-block="CustomerArea.AC_TimelineItemCustom"]',
                    timeout=self._timeout(10))
            except WaitTimeoutError as e:
                self._scrape_check_error()
                raise e
            self._scrape()
        finally:
            # Quit the browser.
            self._close_page()

        return self._resp_dict

#!/usr/bin/env python3

from DrissionPage.errors import WaitTimeoutError

from openparcel.carriers.base import BrowserBaseCarrier


class CarrierDPDPT(BrowserBaseCarrier):
    uid = 'dpd-pt'
    name = 'DPD (PT)'
    tracking_url_base = 'https://tracking.dpd.pt/en/getting-parcel/' \
                        'track-trace?reference=${tracking_code}'
    accent_color = '#DC1332'

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)

    def fetch(self):
        try:
            # Load the page in the browser.
            self._fetch_page()

            try:
                self._wait_title_change('Track & Trace', raise_err=True,
                                        timeout=10)
                self._scrape_check_error()
                self._wait_page_complete('#content .table-responsive')
            except WaitTimeoutError as e:
                self._scrape_check_error()
                raise e

            # Finally scrape it.
            self._scrape()
        finally:
            # Quit the browser.
            self._close_page()

        return self._resp_dict

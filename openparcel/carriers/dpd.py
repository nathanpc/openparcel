#!/usr/bin/env python3

from DrissionPage.errors import WaitTimeoutError

from openparcel.carriers.base import BrowserBaseCarrier


class CarrierDPDPT(BrowserBaseCarrier):
    uid = 'dpd-pt'
    name = 'DPD (PT)'
    tracking_url_base = 'https://tracking.dpd.pt/en/getting-parcel/' \
                        'track-trace?reference=${tracking_code}'
    accent_color = '#DC1332'
    outdated_period_days: int = 30 * 2

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)

    def fetch(self):
        try:
            # Load the page in the browser.
            self._fetch_page()

            try:
                # Wait for it to actually load something we can work with.
                self._wait_title_change('Track & Trace', timeout=5)
                self._wait_page_complete(['#content .table-responsive',
                                          '#content strong'], timeout=8)
                self._scrape_check_error()
            except WaitTimeoutError as e:
                self._scrape_check_error()
                raise e

            # Finally scrape it.
            self._scrape()
        finally:
            # Quit the browser.
            self._close_page()

        return self._resp_dict

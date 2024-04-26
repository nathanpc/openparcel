#!/usr/bin/env python3

from DrissionPage.errors import WaitTimeoutError

from openparcel.carriers.base import BrowserBaseCarrier


class CarrierDHL(BrowserBaseCarrier):
    uid = 'dhl'
    name = 'DHL'
    tracking_url_base = 'https://www.dhl.com/us-en/home/tracking.html?' \
                        'tracking-id=${tracking_code}&submit=1'
    accent_color = '#FFCC00'
    outdated_period_days: int = 30 * 3

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)

    def fetch(self):
        try:
            self._fetch_page()
            self._load_scraping_js()

            # Wait for the page to load
            try:
                self._wait_page_complete(
                    ['.c-tracking-result--checkpoint',
                     '.c-tracking-result--status-shipment-undefined'],
                    timeout=10)
                self._scrape_check_error()
            except WaitTimeoutError:
                # Looks like we need to bypass their anti-scraping measures.
                self._scrape_check_error()
                button = self.page.ele('css:.c-voc-tracking-bar--button'
                                       '.js--tracking--input-submit')
                self.debug_print('Clicking the Track button...')
                button.click(timeout=10)

            # Finally scrape it.
            self._load_scraping_js()
            self._wait_page_complete(
                ['.c-tracking-result--checkpoint',
                 '.c-tracking-result--status-shipment-undefined'], timeout=8)
            self._scrape()
        finally:
            # Quit the browser.
            self._close_page()

        return self._resp_dict

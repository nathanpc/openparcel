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
    outdated_period_days: int = 30 * 2

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)

    def fetch(self):
        try:
            # Load the website.
            self._fetch_page()
            self._load_scraping_js()

            try:
                # Wait for their shitty UI framework to populate the page.
                self._wait_page_complete(
                    ['[data-block="TrackTrace.TT_Timeline_New"] '
                     '[data-block="CustomerArea.AC_TimelineItemCustom"]',
                     '#feedbackMessageContainer',
                     '[data-block="TrackTrace.TT_ObjectErrorCard"]'],
                    timeout=18)
                self._scrape_check_error()
            except WaitTimeoutError as e:
                self._scrape_check_error()
                raise e

            # Finally we have possibly reached the tracking history page.
            self._wait_page_complete(
                '[data-block="TrackTrace.TT_Timeline_New"] '
                '[data-block="CustomerArea.AC_TimelineItemCustom"]',
                timeout=10)
            self._scrape()
        finally:
            # Quit the browser.
            self._close_page()

        return self._resp_dict

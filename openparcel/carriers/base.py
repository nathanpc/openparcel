#!/usr/bin/env python3

from os.path import abspath, dirname, exists
from string import Template
from typing import Optional

from DrissionPage import ChromiumPage

from openparcel.exceptions import TrackingCodeNotFound, ScrapingJsNotFound


class BaseCarrier:
    """Base class for all carriers in the system."""
    uid: str = None
    name: str = None
    tracking_url_base: str = None
    accent_color: str = '#D6BC9C'

    def __init__(self, tracking_code: str = None):
        self.tracking_url: Template = Template(self.tracking_url_base)
        self.tracking_code: str = tracking_code
        self._resp_dict: Optional[dict] = None

    def get_tracking_url(self) -> str:
        """Gets the tracking URL for the carrier based on the available
        information."""
        # Check if we have a tracking code to substitute with.
        if self.tracking_code is None:
            raise TrackingCodeNotFound('No tracking code was supplied')

        return self.tracking_url.substitute({
            'tracking_code': self.tracking_code
        })

    def fetch(self) -> dict:
        """Fetches tracking updates from the carrier's tracking website."""
        raise NotImplementedError

    def _create_resp_dict(self, json_resp: dict):
        """Creates the response dictionary with all the information gathered
        for the parcel."""
        self._resp_dict = json_resp
        self._resp_dict['accentColor'] = self.accent_color


class BrowserBaseCarrier(BaseCarrier):
    """Base class for carriers that require the use of a full web browser to
    scrape."""

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)

        from DrissionPage import ChromiumPage
        self.page: Optional[ChromiumPage] = None

    def _fetch_page(self):
        """Sets up the scraping web browser and begins fetching the carrier's
        tracking page."""
        # Get a new browser for us to play around with if needed.
        if self.page is None:
            self.page = ChromiumPage()

        # Get the tracking website.
        self.page.get(self.get_tracking_url())
        self.page.run_js_loaded(self._get_scraping_js('utils'), as_expr=True)

    def _close_page(self):
        """Closes the scraping web browser instance and cleans up any temporary
        resources."""
        self.page.close()
        self.page = None

    def _get_scraping_js(self, name: str = None) -> str:
        """Gets the Javascript script to run in order to scrape the web page."""
        # Build the file path.
        if name is None:
            name = self.uid
        filepath = (dirname(dirname(dirname(abspath(__file__)))) +
                    f'/scrapers/{name}.js')

        # Check if the file exists.
        if not exists(filepath):
            raise ScrapingJsNotFound(filepath)

        # Read the contents of the script file.
        with open(filepath, mode='r', encoding='utf-8') as f:
            return f.read()

    def _wait_page_complete(self, elem: str):
        """Waits until a page is completely loaded, including garbage that was
        loaded in via shitty frameworks such as React. This method will use some
        hacks to determine when a specific element (selected using a Javascript
        query string) has been loaded into the DOM."""
        self.page.run_js_loaded(f'OpenParcel.notifyElementLoaded(\'{elem}\');')
        alert_text = self.page.handle_alert(accept=True, timeout=5)

        # Check if the dialog box was actually the one we were expecting.
        if alert_text != "READY!":
            raise TimeoutError('Alert from waiting for page to finish loading'
                               f'didn\'t contain magic phrase. Got: {alert_text}')

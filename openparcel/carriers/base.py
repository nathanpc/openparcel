#!/usr/bin/env python3

import datetime

from os.path import abspath, dirname, exists
from string import Template
from typing import Optional

from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.errors import WaitTimeoutError

from openparcel.exceptions import (TrackingCodeNotFound, ScrapingJsNotFound,
                                   ScrapingReturnedError)


class BaseCarrier:
    """Base class for all carriers in the system."""
    uid: str = None
    name: str = None
    tracking_url_base: str = None
    accent_color: str = '#D6BC9C'
    outdated_period_secs: int = 60 * 60 * 24 * 30 * 6

    def __init__(self, tracking_code: str = None):
        self.tracking_url: Template = Template(self.tracking_url_base)
        self.tracking_code: str = tracking_code
        self.cached: bool = False
        self.created: datetime.datetime = datetime.datetime.now(datetime.UTC)
        self.last_updated: datetime.datetime = self.created
        self.db_id: Optional[int] = None
        self.parcel_name: Optional[str] = None
        self.archived: bool = False
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

    def is_outdated(self) -> bool:
        """Checks if the parcel is outdated given its creation date."""
        return ((datetime.datetime.now(datetime.UTC) - self.created) >
                datetime.timedelta(seconds=self.outdated_period_secs))

    def from_cache(self, db_id: int, cache: dict, created: datetime.datetime,
                   last_updated: datetime.datetime, parcel_name: str = None,
                   archived: bool = False):
        """Populates the object with data from a cached object."""
        self._resp_dict = cache
        self.db_id = db_id
        self.parcel_name = parcel_name
        self.archived = archived
        self.cached = True
        self.created = created
        self.last_updated = last_updated

    def get_resp_dict(self, extra: dict = None) -> dict:
        """Creates the response dictionary with all the information gathered
        for the parcel."""
        resp = self._resp_dict

        # Add additional information to object.
        resp['id'] = self.db_id
        resp['name'] = self.parcel_name
        resp['cached'] = self.cached
        resp['archived'] = self.archived
        resp['carrier'] = {
            'id': self.uid,
            'name': self.name
        }
        resp['accentColor'] = self.accent_color
        resp['created'] = self.created.isoformat()
        resp['lastUpdated'] = self.last_updated.isoformat()
        resp['outdated'] = self.is_outdated()

        # Append any extras.
        if extra is not None:
            resp |= extra

        return resp

    def _scrape(self):
        """Scrapes the tracking information and stores the results
        internally."""
        raise NotImplementedError


class BrowserBaseCarrier(BaseCarrier):
    """Base class for carriers that require the use of a full web browser to
    scrape."""

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)
        self.page: Optional[ChromiumPage] = None

    def _scrape(self, func_name: str = 'scrape'):
        # Get the scraped response.
        self._resp_dict = self.page.run_js_loaded(f'{func_name}();',
                                                  as_expr=True)

        # Check if we caught an error.
        if self._resp_dict is not None and 'error' in self._resp_dict:
            raise ScrapingReturnedError(self._resp_dict['error'])

    def _scrape_check_error(self, load_scripts: bool = True):
        """Scrapes the page for errors and raises and exception if needed."""
        if load_scripts:
            self._load_scraping_js()

        self._scrape(func_name='errorCheck')

    def _fetch_page(self):
        """Sets up the scraping web browser and begins fetching the carrier's
        tracking page."""
        # Get a new browser for us to play around with if needed.
        if self.page is None:
            opts = ChromiumOptions()
            opts.auto_port()
            opts.set_argument('--ignore-certificate-errors')
            opts.set_argument('--disable-web-security')

            self.page = ChromiumPage(addr_or_opts=opts)

        # Get the tracking website.
        self.page.get(self.get_tracking_url())
        self._load_scraping_js()

    def _close_page(self):
        """Closes the scraping web browser instance and cleans up any temporary
        resources."""
        self.page.close()
        self.page = None

    def _load_scraping_js(self):
        """Loads scraping scripts into the page."""
        self.page.run_js_loaded(self._get_scraping_js('utils'), as_expr=True)
        self.page.run_js_loaded(self._get_scraping_js(), as_expr=True)

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

    def _wait_page_complete(self, elem: str, timeout: float = 5):
        """Waits until a page is completely loaded, including garbage that was
        loaded in via shitty frameworks such as React. This method will use some
        hacks to determine when a specific element (selected using a Javascript
        query string) has been loaded into the DOM."""
        self.page.run_js_loaded(f'OpenParcel.notifyElementLoaded(\'{elem}\');')
        alert_text = self.page.handle_alert(accept=True, timeout=timeout)

        # Check if the dialog box was actually the one we were expecting.
        if alert_text != "READY!":
            raise WaitTimeoutError(
                'Alert from waiting for page to finish loading did not contain '
                f'magic phrase. Got: {alert_text}')

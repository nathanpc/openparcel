#!/usr/bin/env python3

import datetime
import json
import random
import re
import secrets
import traceback

from os.path import abspath, dirname, exists
from string import Template
from typing import Optional, Self

from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage._elements.none_element import NoneElement
from DrissionPage.errors import WaitTimeoutError, JavaScriptError

from openparcel.exceptions import (TrackingCodeNotFound, ScrapingJsNotFound,
                                   ScrapingReturnedError, TrackingCodeInvalid)


class BaseCarrier:
    """Base class for all carriers in the system."""
    uid: str = None
    name: str = None
    tracking_url_base: str = None
    accent_color: str = '#D6BC9C'
    outdated_period_days: int = 30 * 6

    def __init__(self, tracking_code: str = None):
        self.tracking_url: Template = Template(self.tracking_url_base)
        self.tracking_code: str = tracking_code
        self.cached: bool = False
        self.created: datetime.datetime = datetime.datetime.now(datetime.UTC)
        self.last_updated: datetime.datetime = self.created
        self.db_id: Optional[int] = None
        self.slug: Optional[str] = None
        self.parcel_name: Optional[str] = None
        self.archived: bool = False
        self._resp_dict: Optional[dict] = None

        # Check if the tracking code is valid before proceeding.
        if not BaseCarrier.is_tracking_code_valid(self.tracking_code):
            raise TrackingCodeInvalid()

    def get_tracking_url(self) -> str:
        """Gets the tracking URL for the carrier based on the available
        information."""
        # Check if we have a tracking code to substitute with.
        if self.tracking_code is None:
            raise TrackingCodeNotFound('No tracking code was supplied')

        return self.tracking_url.substitute({
            'tracking_code': self.tracking_code
        })

    def set_parcel_id(self, parcel_id: [int | str]):
        """Sets the value of the database parcel ID of the object."""
        self.db_id = int(parcel_id)

    def fetch(self) -> dict:
        """Fetches tracking updates from the carrier's tracking website."""
        raise NotImplementedError

    def created_delta(self) -> datetime.timedelta:
        """Gets the time delta between when the parcel was created and now."""
        return datetime.datetime.now() - self.created

    def is_outdated(self) -> bool:
        """Checks if the parcel is outdated given its creation date."""
        return (self.created_delta() >
                datetime.timedelta(days=self.outdated_period_days))

    def from_cache(self, db_id: int, cache: dict, created: datetime.datetime,
                   last_updated: datetime.datetime, slug: str,
                   parcel_name: str = None, archived: bool = False):
        """Populates the object with data from a cached object."""
        self._resp_dict = cache
        self.set_parcel_id(db_id)
        self.slug = slug
        self.parcel_name = parcel_name
        self.archived = archived
        self.cached = True
        self.created = created
        self.last_updated = last_updated

    def generate_slug(self, force: bool = False) -> str:
        """Generates a unique slug using the available information."""
        # Is the generation part even required?
        if not force and self.slug is not None:
            return self.slug

        # Build the base of the slug.
        clean = re.compile(r'[^A-Za-z0-9]+')
        self.slug = (clean.sub('', self.uid)[:5] + '-' +
                     clean.sub('', self.tracking_code)[:8].lower())

        # Generate the random bit of the slug.
        rand = secrets.token_bytes(random.randint(2, 3))
        self.slug += '-' + rand.hex()

        return self.slug

    @staticmethod
    def is_slug_valid(slug: str) -> bool:
        """Checks if a slug is in a valid format."""
        # Is it too long?
        if len(slug) > 35:
            return False

        # Check if it only contains the characters that we care about.
        return re.match('^[a-z-0-9]+$', slug) is not None

    @staticmethod
    def is_tracking_code_valid(tracking_code: str) -> bool:
        """Checks if a parcel's tracking code is in fact valid (does not
        contain any invalid characters)."""
        return re.search('[^A-Za-z0-9-]+', tracking_code) is None

    def is_similar(self, other: Self):
        """Checks if a parcel is similar to this one. Uses the slug (if
        available) or carrier and tracking code to infer the similarity."""
        if self.slug is not None and other.slug is not None:
            return self.slug == other.slug

        return self.name == other.name and \
            self.tracking_code == other.tracking_code

    def get_resp_dict(self, extra: dict = None, bare: bool = False) -> dict:
        """Creates the response dictionary with all the information gathered
        about the parcel."""
        # Build up the response object.
        resp = self._resp_dict
        if not bare:
            resp.update(self.as_dict())

        # Append any extras.
        if extra is not None:
            resp |= extra

        return resp

    def as_dict(self, internals: bool = False) -> dict:
        """Dictionary representation of this object."""
        return {
            'id': self.slug,
            'name': self.parcel_name,
            'cached': self.cached,
            'archived': self.archived,
            'outdated': self.is_outdated(),
            'carrier': {
                'id': self.uid,
                'name': self.name
            },
            'accentColor': self.accent_color,
            'created': self.created.isoformat(),
            'lastUpdated': self.last_updated.isoformat(),
            'trackingUrl': self.get_tracking_url()
        }

    def _scrape(self):
        """Scrapes the tracking information and stores the results
        internally."""
        raise NotImplementedError


class BrowserBaseCarrier(BaseCarrier):
    """Base class for carriers that require the use of a full web browser to
    scrape."""

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)
        self.proxy: Optional[str] = None
        self.page: Optional[ChromiumPage] = None
        self.base_timeout: float = 10

    def set_proxy(self, proxy: str):
        """Sets the proxy server for the scraping browser."""
        if self.page is not None:
            raise RuntimeError('Cannot set the proxy of a running browser')

        self.proxy = proxy

    def debug_print(self, message: str, fail_silent: bool = False):
        """Prints a message in the scraped page's debug window."""
        try:
            self.page.run_js_loaded(
                f'OpenParcel.debugLog({json.dumps(message)});')
        except JavaScriptError as e:
            if not fail_silent:
                raise e

    def as_dict(self, internals: bool = False) -> dict:
        # Get the basics.
        base = super().as_dict()

        # Include the browser settings.
        if internals:
            base['browser'] = {
                'proxy': self.proxy,
                'base_timeout': self.base_timeout
            }

        return base

    def _scrape(self, statement: str = 'new Carrier().scrape().toJSON()'):
        # Get the scraped response.
        self.debug_print('Scraping for tracking information...')
        self._resp_dict = self.page.run_js_loaded(statement + ';',
                                                  as_expr=True)

        # Check if we caught an error.
        if self._resp_dict is not None and 'error' in self._resp_dict:
            raise ScrapingReturnedError(self._resp_dict['error'])

    def _scrape_check_error(self, load_scripts: bool = True):
        """Scrapes the page for errors and raises and exception if needed."""
        if load_scripts:
            self._load_scraping_js()

        self.debug_print('Scraping for errors...')
        self._scrape(statement='new Carrier().errorCheck()?.toJSON() ?? null')

    def _fetch_page(self, timeout: float = 10):
        """Sets up the scraping web browser and begins fetching the carrier's
        tracking page."""
        # Get a new browser for us to play around with if needed.
        if self.page is None:
            opts = ChromiumOptions()
            opts.auto_port()
            opts.incognito()
            opts.no_imgs()
            opts.ignore_certificate_errors()
            opts.set_timeouts(page_load=self.base_timeout)
            opts.set_retry(3)
            opts.set_argument('--disable-web-security')
            if self.proxy is not None:
                opts.set_proxy(self.proxy)

            self.page = ChromiumPage(addr_or_opts=opts)

        # Get the tracking website.
        self.page.get(self.get_tracking_url(), timeout=self._timeout(timeout),
                      retry=1)
        self._load_scraping_js()

    def _close_page(self):
        """Closes the scraping web browser instance and cleans up any temporary
        resources."""
        self.page.close()
        self.page = None

    def _load_scraping_js(self):
        """Loads scraping scripts into the page."""
        # Check if our token element is present.
        elem = self.page.ele('#op-token-elem', timeout=1)
        if type(elem) is not NoneElement:
            return

        try:
            # Load the necessary scripts.
            self.page.run_js_loaded(self._get_scraping_js('utils'), as_expr=True)
            self.page.run_js_loaded(self._get_scraping_js(), as_expr=True)
            self.page.run_js_loaded('OpenParcel.dropTokenElement();')
            self.debug_print(
                f'Scraping scripts loaded at {datetime.datetime.now().time()}')
        except TimeoutError:
            raise ScrapingReturnedError({
                'code': {'id': 5, 'name': 'ProxyTimeout'},
                'data': {'traceback': traceback.format_exc()}
            })

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

    def _enable_unload_script(self):
        """Enables the detection of redirections or reloads when waiting for
        the page to complete."""
        self._load_scraping_js()
        self.page.run_js_loaded('OpenParcel.notifyUnload();')
        self.debug_print(f'Enabled unload event listener')

    def _disable_unload_script(self):
        """Disables the detection of redirections or reloads when waiting for
        the page to complete."""
        self._load_scraping_js()
        self.page.run_js_loaded('OpenParcel.disableNotifyUnload();')
        self.debug_print(f'Disabled unload event listener')

    def _wait_page_complete(self, elems: list[str] | str, timeout: float = 5,
                            auto_redirect: bool = True) -> int | None:
        """Waits until a page is completely loaded, including garbage that was
        loaded in via shitty frameworks such as React. This method will use some
        hacks to determine when specific elements (selected using a Javascript
        query strings) have been loaded into the DOM."""
        # Set up the Javascript argument.
        args = 'null'
        if isinstance(elems, str):
            args = f'[\'{elems}\']'
        elif hasattr(elems, '__iter__'):
            # Ensure we don't have an empty list.
            if len(elems) == 0:
                raise AssertionError('List of elements to wait for must '
                                     'contain at least a single element')

            # Create the Javascript array.
            args = f'[\'{elems[0]}\''
            for elem in elems[1:]:
                args += f', \'{elem}\''
            args += ']'

        # Run the script and set up the alert event handler.
        self._load_scraping_js()
        self.debug_print('Waiting for elements to load: ' + json.dumps(elems))
        self.page.run_js_loaded(f'OpenParcel.notifyElementLoaded({args});')
        alert_text = self.page.handle_alert(accept=True,
                                            timeout=self._timeout(timeout))
        if alert_text == '':
            # Looks like we are being redirected to another page.
            if not auto_redirect:
                return None

            # Handle the redirection and recurse into it.
            self._load_scraping_js()
            self.debug_print('We have been redirected to another page.')
            return self._wait_page_complete(elems, timeout=timeout,
                                            auto_redirect=True)
        elif isinstance(alert_text, bool) and not alert_text:
            # Sadly the alert never happened.
            self.debug_print('Page wait alert never triggered.',
                             fail_silent=True)
            raise WaitTimeoutError('Page wait alert dialog never triggered and '
                                   'timed out')

        # Check if the dialog box was actually the one we were expecting.
        match = re.match("READY! \\(([0-9]+)\\)", alert_text)
        if match is None:
            self.debug_print('Page wait alert did not match our pattern.',
                             fail_silent=True)
            raise WaitTimeoutError(
                'Alert from waiting for page to finish loading did not contain '
                f'magic phrase. Got: {alert_text}')

        return int(match.groups()[0])

    def _wait_title_change(self, contains: str, timeout: float,
                           raise_err: bool = True):
        """Waits for a page's title to change to something that contains the
        specified string."""
        self._load_scraping_js()
        self.debug_print(f'Waiting for page title to change "{contains}"...')
        self.page.wait.title_change(contains, raise_err=raise_err,
                                    timeout=self._timeout(timeout))

    def _timeout(self, timeout: float) -> float:
        """Calculates a timeout value taking into account the obligatory base
        timeout of our connection or proxy server."""
        return self.base_timeout + timeout

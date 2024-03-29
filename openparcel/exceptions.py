#!/usr/bin/env python3
import logging
import os
import errno
import traceback

from typing import Optional

import DrissionPage.errors

from openparcel.logger import Logger, LoggerNotFound


class TitledException(Exception):
    """An exception that has a title and a message associated with it."""

    def __init__(self, title: str, message: str, status_code: int,
                 logger: Logger = None):
        self.title = title
        self.message = message
        self.status_code = status_code
        self.logger = logger

    def log(self, level: int, action_id: str, context: dict = None):
        """Logs the occurrence of this exception."""
        if self.logger is None:
            raise LoggerNotFound

        self.logger.log(level, action_id,
                        f'{self.title}: {self.message}', context=context)

    def resp_dict(self) -> dict:
        """Returns the equivalent response dictionary for the web service."""
        return {
            'title': self.title,
            'message': self.message
        }


class NotEnoughParameters(TitledException):
    """Not all the required parameters were passed to us."""


class AuthenticationFailed(TitledException):
    """Raised when the user authentication failed for any reason."""


class TrackingCodeNotFound(Exception):
    """No tracking code was supplied, or it doesn't exist."""


class ScrapingJsNotFound(FileNotFoundError):
    """Javascript scraping source file doesn't exist."""

    def __init__(self, filename: str):
        super().__init__(errno.ENOENT, os.strerror(errno.ENOENT),
                         filename)


class ScrapingReturnedError(TitledException):
    """Error raised when the scraping script failed to scrape the website in a
    predictable manner and reported on it."""

    def __init__(self, err_obj: dict):
        self.err_id: int = err_obj['code']['id']
        self.code: str = err_obj['code']['name']
        self.data: Optional[dict] = err_obj['data']
        super().__init__(self._get_title(), self._get_description(), 422)

    def _get_title(self) -> str:
        match self.code:
            case 'ParcelNotFound':
                return 'Parcel not found'
            case 'InvalidTrackingCode':
                return 'Invalid tracking code'
            case 'RateLimiting':
                return 'Too many requests'
            case 'Blocked':
                return 'Blocked by carrier'

        self.status_code = 500
        return 'Unknown error'

    def _get_description(self) -> str:
        match self.code:
            case 'ParcelNotFound':
                return 'The provided tracking code did not match any parcels ' \
                       'in the carrier\'s system.'
            case 'InvalidTrackingCode':
                return 'The provided tracking code is invalid for this carrier.'
            case 'RateLimiting':
                return 'We have reached the request limit of this carrier.'
            case 'Blocked':
                return ('We have been blocked by the carrier for trying to '
                        'scrape their website. Try again later after the'
                        'system\'s proxy list has been refreshed.')

        return 'An unknown, but expected, error occurred while scraping the ' \
               'website.'


class ScrapingBrowserError(TitledException):
    """Error raised when the scraping browser raises an exception and crashes.
    These are usually caused by an unexpected issue while scraping."""

    def __init__(self, err: DrissionPage.errors.BaseError, carrier,
                 logger: Logger):
        super().__init__(
            title='Scraping error',
            message='An error occurred while trying to fetch the tracking '
                    'history from the carrier\'s website.',
            status_code=500, logger=logger)
        self.origin = err
        self.trace: str = traceback.format_exc()
        self.data: dict = carrier.as_dict()

        # Log the incident.
        self.log(logging.ERROR, 'scrape_error', {
            'context': carrier.as_dict(),
            'traceback': self.trace
        })

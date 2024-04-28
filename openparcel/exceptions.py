#!/usr/bin/env python3
import logging
import os
import errno
import traceback

from typing import Optional

import DrissionPage.errors
import mysql.connector.errors

from openparcel.logger import Logger, LoggerNotFound


class TitledException(Exception):
    """An exception that has a title and a message associated with it."""

    def __init__(self, title: str, message: str, status_code: int,
                 logger: Logger = None):
        self.title = title
        self.message = message
        self.status_code = status_code
        self.logger = logger

    def log(self, level: int, action_id: str, message: str = None,
            context: dict = None):
        """Logs the occurrence of this exception."""
        if self.logger is None:
            raise LoggerNotFound

        # Build up the log message if needed.
        if message is None:
            message = f'{self.title}: {self.message}'

        # Log the incident.
        self.logger.log(level, action_id, message, context=context)

    def resp_dict(self, req_uuid: str = None) -> dict:
        """Returns the equivalent response dictionary for the web service."""
        # Build the base response.
        resp = {
            'title': self.title,
            'message': self.message
        }

        # Do we have a UUID to include?
        if req_uuid is not None:
            resp['reqid'] = req_uuid

        return resp


class NotEnoughParameters(TitledException):
    """Not all the required parameters were passed to us."""


class AuthenticationFailed(TitledException):
    """Raised when the user authentication failed for any reason."""


class TrackingCodeInvalid(TitledException):
    """Tracking code contains invalid characters."""

    def __init__(self, title: str = 'Invalid tracking code',
                 message: str = 'The provided tracking code contains invalid '
                                'characters.', logger: Logger = None):
        super().__init__(title, message, 422, logger)


class TrackingCodeNotFound(Exception):
    """No tracking code was supplied, or it doesn't exist."""


class ScrapingJsNotFound(FileNotFoundError):
    """Javascript scraping source file doesn't exist."""

    def __init__(self, filename: str):
        super().__init__(errno.ENOENT, os.strerror(errno.ENOENT),
                         filename)


class ServerOverwhelmedError(TitledException, TimeoutError):
    """Server is currently overwhelmed and some operations or endpoints may not
    be functional."""

    def __init__(self, title: str = 'Service overwhelmed',
                 message: str = 'The service is currently experiencing a lot '
                                'of traffic or is undergoing maintenance. '
                                'Please try again later.',
                 context: dict = None, logger: Logger = None):
        super().__init__(title, message, 503, logger=logger)

        # Log the incident.
        self.log(logging.WARNING, 'server_overwhelmed', context={
            'context': context,
            'traceback': traceback.format_exc()
        })


class DatabaseError(TitledException):
    """A database error occurred that wasn't caught by the server."""

    def __init__(self, exc: mysql.connector.errors.Error,
                 title: str = 'Server database error',
                 message: str = 'Sorry but a server error related to our '
                                'database occurred. We have been notified and '
                                'are currently working on a solution.',
                 context: dict = None, logger: Logger = None):
        super().__init__(title, message, 500, logger=logger)

        # Log the incident.
        self.log(logging.ERROR, 'mysql_error',
                 f'{exc.__class__.__name__}: {exc.msg}',
                 context={
                     'context': context,
                     'mysql_msg': str(exc),
                     'traceback': traceback.format_exc()
                 })


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
            case 'ProxyTimeout':
                return 'Proxy server timeout'

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
            case 'ProxyTimeout':
                return ('The proxy server used to perform the request to the '
                        'carrier took too long to respond. Try again later.')

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
        self.log(logging.ERROR, 'scrape_error', context={
            'context': carrier.as_dict(internals=True),
            'traceback': self.trace
        })

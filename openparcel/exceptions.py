#!/usr/bin/env python3

import os
import errno

from typing import Optional


class TitledException(Exception):
    """An exception that has a title and a message associated with it."""

    def __init__(self, title: str, message: str, status_code: int):
        self.title = title
        self.message = message
        self.status_code = status_code

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
        self.title: str = self._get_title()
        self.message: str = self._get_description()

    def _get_title(self) -> str:
        match self.code:
            case 'ParcelNotFound':
                return 'Parcel not found'
            case 'InvalidTrackingCode':
                return 'Invalid tracking code'

        return 'Unknown error'

    def _get_description(self) -> str:
        match self.code:
            case 'ParcelNotFound':
                return 'The provided tracking code did not match any parcels ' \
                       'in the carrier\'s system.'
            case 'InvalidTrackingCode':
                return 'The provided tracking code is invalid for this carrier.'

        return 'An unknown, but expected, error occurred while scraping the ' \
               'website.'

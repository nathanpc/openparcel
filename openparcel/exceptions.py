#!/usr/bin/env python3

import os
import errno


class TrackingCodeNotFound(Exception):
    """No tracking code was supplied, or it doesn't exist."""


class ScrapingJsNotFound(FileNotFoundError):
    """Javascript scraping source file doesn't exist."""

    def __init__(self, filename: str):
        super().__init__(errno.ENOENT, os.strerror(errno.ENOENT),
                         filename)

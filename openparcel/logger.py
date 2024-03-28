#!/usr/bin/env python3

from __future__ import annotations

import json
import logging
import os

from os.path import dirname, abspath
from logging.handlers import TimedRotatingFileHandler


class Logger:
    """The overarching class that abstracts away the logging details."""

    def __init__(self, system: str, subsystem: str, log_dir: str = None):
        self.subsystem = subsystem
        self.log_dir = log_dir

        # Create a new logger for us to use.
        self.logger = logging.getLogger(system)
        self.logger.setLevel(logging.DEBUG)
        self._setup()

    def for_subsystem(self, subsystem: str) -> Logger:
        """Creates a derived logger for a specific subsystem."""
        return Logger(self.logger.name, subsystem, log_dir=self.log_dir)

    def log(self, level: int, message: str, context: dict = None):
        """Logs something using our logging system."""
        # Merge our extra data into a single dictionary.
        extra = {
            'subsystem': self.subsystem,
            'detail': ''
        }
        if context is not None:
            extra['detail'] = '\n' + json.dumps(context, indent=2)

        # Perform the logging operation.
        self.logger.log(level, message, extra=extra)

    def debug(self, message: str, context: dict = None):
        """Logs a debug level message."""
        self.log(logging.DEBUG, message, context=context)

    def info(self, message: str, context: dict = None):
        """Logs an info level message."""
        self.log(logging.INFO, message, context=context)

    def warning(self, message: str, context: dict = None):
        """Logs a warning level message."""
        self.log(logging.WARNING, message, context=context)

    def error(self, message: str, context: dict = None):
        """Logs an error level message."""
        self.log(logging.ERROR, message, context=context)

    def critical(self, message: str, context: dict = None):
        """Logs a critical level message."""
        self.log(logging.CRITICAL, message, context=context)

    def _setup(self):
        """Sets up the logger for us."""
        # Is this logger already properly set up?
        if self.logger.hasHandlers():
            return

        # Ensure we have a place to put our log files.
        if self.log_dir is None:
            self.log_dir = dirname(dirname(abspath(__file__))) + '/logs'
        os.makedirs(self.log_dir, exist_ok=True)

        # Create a detailed formatter.
        df = logging.Formatter('%(asctime)s [%(levelname)s] {%(subsystem)s} '
                               '%(message)s %(detail)s')

        # Create a simple formatter.
        sf = logging.Formatter('%(asctime)s [%(levelname)s] {%(subsystem)s} '
                               '%(message)s')

        # Create the file handler.
        fh = TimedRotatingFileHandler(dirname(dirname(abspath(__file__))) +
                                      f'/logs/{self.logger.name}.log',
                                      when='W6', utc=True, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(df)
        self.logger.addHandler(fh)

        # Create the console handler.
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        ch.setFormatter(sf)
        self.logger.addHandler(ch)


class LoggerNotFound(RuntimeError):
    """Exception for when a logger isn't defined and we need one."""

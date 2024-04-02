#!/usr/bin/env python3

from __future__ import annotations

import json
import logging
import os

from os.path import dirname, abspath
from logging.handlers import TimedRotatingFileHandler


class Logger:
    """The overarching class that abstracts away the logging details."""

    def __init__(self, system: str, subsystem: str, log_dir: str = None,
                 uuid: str = None):
        self.subsystem = subsystem
        self.log_dir = log_dir
        self.uuid = uuid

        # Create a new logger for us to use.
        self.logger = logging.getLogger(system)
        self.logger.setLevel(logging.DEBUG)
        self._setup()

    def for_subsystem(self, subsystem: str) -> Logger:
        """Creates a derived logger for a specific subsystem."""
        return Logger(self.logger.name, subsystem, log_dir=self.log_dir,
                      uuid=self.uuid)

    def log(self, level: int, action_id: str, message: str,
            context: dict = None):
        """Logs something using our logging system."""
        # Merge our extra data into a single dictionary.
        extra = {
            'subsystem': self.subsystem,
            'action': action_id,
            'detail': ''
        }
        if self.uuid is not None:
            extra['detail'] += f'({self.uuid}) '
        if context is not None:
            extra['detail'] += '\n' + json.dumps(context, indent=2)

        # Perform the logging operation.
        self.logger.log(level, message, extra=extra)

    def debug(self, action_id: str, message: str, context: dict = None):
        """Logs a debug level message."""
        self.log(logging.DEBUG, action_id, message, context=context)

    def info(self, action_id: str, message: str, context: dict = None):
        """Logs an info level message."""
        self.log(logging.INFO, action_id, message, context=context)

    def warning(self, action_id: str, message: str, context: dict = None):
        """Logs a warning level message."""
        self.log(logging.WARNING, action_id, message, context=context)

    def error(self, action_id: str, message: str, context: dict = None):
        """Logs an error level message."""
        self.log(logging.ERROR, action_id, message, context=context)

    def critical(self, action_id: str, message: str, context: dict = None):
        """Logs a critical level message."""
        self.log(logging.CRITICAL, action_id, message, context=context)

    def _setup(self):
        """Sets up the logger for us."""
        # Is this logger already properly set up?
        if self.logger.hasHandlers():
            return

        # Ensure we have a place to put our log files.
        if self.log_dir is None:
            self.log_dir = dirname(dirname(abspath(__file__))) + '/logs'
        os.makedirs(self.log_dir, exist_ok=True)

        # Create our formatters.
        base_format = ('%(asctime)s [%(levelname)s] {%(subsystem)s} '
                       '|%(action)s| %(message)s')
        df = logging.Formatter(f'{base_format} %(detail)s')
        sf = logging.Formatter(base_format)

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

#!/usr/bin/env python3

import asyncio
import threading
import traceback
from enum import Enum

from openparcel.carriers.base import BrowserBaseCarrier
from openparcel.logger import Logger


class ScrapeOperation:
    """An instance of a scraping operation."""

    class State(Enum):
        """The state of the current scraping operation."""
        UNKNOWN, SETUP, FETCHING, FETCHED, SCRAPED, DONE = range(6)

    def __init__(self, base_parcel: BrowserBaseCarrier, logger: Logger):
        self.base_parcel = base_parcel

        self.exception_raised: Exception | None = None
        self.original_traceback: str | None = None
        self.logger = logger

        self.thread: threading.Thread = threading.Thread(
            target=self.fetch,
            name=f'scraper-{base_parcel.tracking_code.lower()}')
        self.state: ScrapeOperation.State = ScrapeOperation.State.SETUP
        self.state_lock = threading.Lock()

    def fetch(self):
        """Fetches a parcel from the carrier and sets any appropriate flags
        internally."""
        self.logger.debug(f'{self.thread.name}.fetch',
                          'Started scraping thread fetch')

        # Try to fetch information about the parcel and capture any exceptions.
        try:
            # Start scraping!
            self.set_state(ScrapeOperation.State.FETCHING)
            self.base_parcel.fetch()
        except Exception as e:
            # Capture the exception state.
            self.original_traceback = traceback.format_exc()
            self.exception_raised = e

            # Log the incident.
            self.logger.warning(f'{self.thread.name}.async_fetch_exception',
                                'An exception occurred while fetching a '
                                'parcel within the scraper\'s thread',
                                {'traceback': self.original_traceback})

        # Flag the fetching as finished.
        self.logger.debug(f'{self.thread.name}.fetched',
                          'Finished scraping fetch from thread')
        self.set_state(ScrapeOperation.State.FETCHED)

    async def run(self):
        """Runs the scraping operation asynchronously."""
        # Start the scraping thread.
        self.thread.start()

        # Check if the operation has finished and flag when it's done.
        while not self.thread.is_alive():
            await asyncio.sleep(1)
        self.thread.join()
        self.logger.debug(f'{self.thread.name}.joined',
                          'Joined scraping thread')
        self.set_state(ScrapeOperation.State.SCRAPED)

        # Raise any exceptions caught inside the thread.
        if self.was_exception_raised():
            raise self.exception_raised

    def merge_resp_into(self, parcel: BrowserBaseCarrier):
        """Since the base parcel contains sensitive information, this method
        only copies over the general information about that was scraped."""
        # TODO: Use the from_cache() method to merge the response into the
        #  other object.
        # TODO: Afterwards set the cached attribute to False.

    def set_state(self, state: State):
        """Sets the current state of the scraping operation."""
        with self.state_lock:
            self.state = state

    def mark_done(self):
        """Marks the current scraping operation as completely finished."""
        self.set_state(ScrapeOperation.State.DONE)

    def is_scrape_done(self) -> bool:
        """Has only the scraping operation finished?"""
        with self.state_lock:
            return self.state >= ScrapeOperation.State.SCRAPED

    def was_exception_raised(self) -> bool:
        """Was as exception raised during the fetch process?"""
        return self.exception_raised is not None

    def is_done(self) -> bool:
        """Has all the necessary processing completed on the base parcel?"""
        with self.state_lock:
            return self.state >= ScrapeOperation.State.DONE


class ScrapingPool:
    """An abstraction over the tool that will be used for scraping a website."""

    def __init__(self, max_instances: int = 5, logger: Logger = None):
        self.max_instances = max_instances
        self.instances: list[ScrapeOperation] = []
        self._instances_lock = asyncio.Lock()

        # Create our logger if needed.
        if logger is None:
            self.logger = Logger('scraping_pool', 'root')
        else:
            self.logger = logger.for_subsystem('scraping_pool')

    async def fetch(self, parcel: BrowserBaseCarrier, timeout: float = 10,
                    local_logger: Logger = None) -> ScrapeOperation:
        """Fetches a parcel asynchronously. Will wait if all instances are
        currently in use."""
        # Ensure we have a logger.
        if local_logger is None:
            local_logger = self.logger

        # TODO: Check if we already have an instance fetching this parcel.

        # Wait until an instance is available.
        try:
            async with asyncio.timeout(timeout):
                while not (await self.is_available()):
                    await asyncio.sleep(.3)
        except TimeoutError:
            local_logger.info('fetch.timeout',
                              f'Fetch operation for parcel {parcel.uid} '
                              f'{parcel.tracking_code} timed out.')
            raise TimeoutError('Could not allocate a scraper instance in time. '
                               'The service is overloaded.')

        # Run scraping operation and remove our own instance when we are done.
        op = ScrapeOperation(parcel, local_logger)
        await self.run_instance(op)

        return op

    async def run_instance(self, op: ScrapeOperation):
        """Add a scrape operation to the instance list, run it, and drop it as
        soon as it's finished doing its job."""
        await self.add_instance(op)
        await op.run()
        await self.drop_instance(op)

    async def add_instance(self, op: ScrapeOperation):
        """Appends a new scraping instance to the instances list."""
        async with self._instances_lock:
            self.instances.append(op)

    async def drop_instance(self, op: ScrapeOperation):
        """Removes a complete scraping instance from the instances list."""
        async with self._instances_lock:
            self.instances.remove(op)

    async def is_available(self) -> bool:
        """Checks if a scraper is currently idling and available to be used."""
        async with self._instances_lock:
            return len(self.instances) < self.max_instances

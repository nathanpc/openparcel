#!/usr/bin/env python3

import sys

from typing import Any

from mysql.connector import MySQLConnection
from requests import HTTPError

import config
import openparcel
from openparcel.proxies import Proxy, FileProxyList
from scripts import Command, Argument, Action


class FetchAction(Action):
    name = 'fetch'
    description = 'Fetches proxies from a proxy list provider'
    arguments = [Argument('provider')]
    default = True

    def __init__(self):
        super().__init__()

    def perform(self, providers: list[str] = None):
        """Fetches all the configured proxy lists."""
        # Get providers from configuration if none were provided.
        if providers is None:
            providers = []
            for provider in config.proxy('api_keys'):
                providers.append(provider.lower())

        # Go through our list of available providers and invoke the requested.
        for name, provider in openparcel.proxies.providers():
            if name in providers:
                try:
                    print(f'Fetching proxies from {name}...')
                    proxies = provider(auto_save=True, conn=self.parent.db_conn)
                    proxies.load()
                    print(f'Finished fetching proxies from {name}.')
                except HTTPError as e:
                    print(f'Failed to fetch proxies from {name}: {e}',
                          file=sys.stderr)

    def parse_arg(self, index: int, value: str) -> Any:
        if index == 0:
            # Convert providers to a proper list.
            return value.lower().split(',')
        
        return super().parse_arg(index, value)


class RefreshAction(Action):
    name = 'refresh'
    description = 'Refreshes the list of cached proxies'

    def __init__(self):
        super().__init__()

    def perform(self):
        for proxy in Proxy.list(self.parent.db_conn):
            # Retest the proxy.
            if not proxy.test():
                proxy.active = False
            proxy.save()


class ImportAction(Action):
    name = 'import'
    description = 'Loads proxies from a file'
    arguments = [Argument('proto', True), Argument('file', True)]

    def __init__(self):
        super().__init__()

    def perform(self, protocol: str, file: str):
        proxies = FileProxyList(protocol, file, conn=self.parent.db_conn)
        proxies.load()


class ProxiesCommand(Command):
    """The proxy management command."""
    name = 'proxy'
    description = 'Manages our proxies and the proxy list'

    def __init__(self, parent: str = None):
        super().__init__(parent)
        self.enable_exit_handler()

        # Connect to the database.
        self.db_conn = MySQLConnection(**config.db_conn())

        # Add default actions.
        self.add_action(FetchAction())
        self.add_action(RefreshAction())
        self.add_action(ImportAction())

    def _exit_handler(self):
        # Ensure we close the database connection.
        if self.db_conn is not None:
            self.db_conn.close()
            self.db_conn = None


if __name__ == '__main__':
    command = ProxiesCommand()
    command.run()

#!/usr/bin/env python3

import sqlite3
import string
import random
import time

import requests
import yaml
import DrissionPage.errors

from os.path import abspath, dirname

from openparcel.carriers import carriers
from openparcel.exceptions import ScrapingReturnedError

# Load the configuration file.
with open(dirname(dirname(abspath(__file__))) + '/config/config.yml', 'r') as s:
    config = yaml.safe_load(s)


class Proxy:
    """A proxy server abstraction."""

    def __init__(self, addr: str, port: int, country: str, speed: int,
                 protocol: str, active: bool = True, db_id: int = None):
        self.db_id: int = db_id
        self.addr: str = addr
        self.port: int = port
        self.country: str = country.upper()
        self.speed: int = speed
        self.protocol: str = protocol.lower()
        self.active: bool = active

    def test(self) -> bool:
        """Perform a cursory test of the proxy server."""
        timing = []

        # Go through available carriers.
        for carrier in carriers():
            # Generate a random tracking code.
            code = ''.join(random.choices(string.ascii_uppercase, k=2) +
                           random.choices(string.digits, k=9) +
                           random.choices(string.ascii_uppercase, k=2))
            start_time = None

            # Fetch the random tracking code to try the proxy out.
            try:
                carrier = carrier(code)
                carrier.set_proxy(self.as_str())
                print(f'Testing proxy {self.as_str()} '
                      f'({round(self.speed / 1000)}) from {self.country} '
                      f'with {carrier.name}...', end=' ')

                start_time = time.time()
                carrier.fetch()
            except ScrapingReturnedError as e:
                speed = round((time.time() - start_time) * 1000)
                timing.append(speed)
                print(f'{speed} ms')
            except DrissionPage.errors.BaseError:
                print('FAILED')
                return False

        # Compute the average time it took to perform the requests.
        self.speed = round(sum(timing) / len(timing))
        print(f'Proxy {self.as_str()} has an average speed of {self.speed}',
              end='\n\n', flush=True)

        return True

    def save(self, conn: sqlite3.Connection):
        """Saves the proxy information to our database."""
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO proxies (addr, port, country, speed, protocol, active)'
            ' VALUES (?, ?, ?, ?, ?, ?)',
            (self.addr, self.port, self.country, self.speed, self.protocol,
             self.active))
        conn.commit()
        self.db_id = cur.lastrowid
        cur.close()

    def as_str(self) -> str:
        """String representation of the proxy, ready to be used."""
        return f'{self.protocol}://{self.addr}:{self.port}'


class ProxyList:
    """Generic proxy list provider class."""

    def __init__(self, url: str):
        self.url: str = url
        self.list: list[Proxy] = []

    def load(self) -> list[Proxy]:
        """Loads the proxy list from its source."""
        self._parse_response(self._fetch())
        return self.list

    def _fetch(self) -> requests.Response:
        """Fetches the proxy list from somewhere."""
        req = requests.get(self.url)
        if req.status_code != 200:
            raise Exception('Proxy list backend API request failed with HTTP '
                            f'status code: {req.status_code}')

        return req

    def _parse_response(self, response: requests.Response):
        """Parses the proxy list response from the backend."""
        raise NotImplementedError


class PubProxy(ProxyList):
    """Proxy list using PubProxy as the backend."""

    def __init__(self, api_key: str = None, country_denylist: list = None):
        # Build up the request URL.
        url = 'http://pubproxy.com/api/proxy?format=json'
        if api_key is not None:
            url += '&api=' + api_key
        url += '&type=http,socks4,socks5'
        url += '&last_check=30'
        url += '&speed=8'
        url += f'&limit={5 if api_key is None else 20}'
        if country_denylist is not None:
            url += '&not_country=' + ','.join(country_denylist)
        url += '&https=true'
        url += '&post=true'
        url += '&user_agent=true'
        url += '&cookies=true'
        url += '&referer=true'

        super().__init__(url)
        self.api_key: str = api_key

    def load(self, num: int = 1) -> list[Proxy]:
        # Load the list multiple times in order to get a good selection.
        for _ in range(num):
            super().load()

        return self.list

    def _parse_response(self, response: requests.Response):
        json = response.json()
        for item in json['data']:
            # Build up the proxy object.
            proxy = Proxy(
                addr=item['ip'],
                port=int(item['port']),
                country=item['country'],
                speed=int(item['speed']) * 1000,
                protocol=item['type'])

            # TODO: Check if we already have this proxy in our database.

            # Test the proxy out before appending it to the list.
            if proxy.test():
                self.list.append(proxy)


if __name__ == '__main__':
    # Connect to the database.
    conn = sqlite3.connect(dirname(dirname(abspath(__file__))) + '/' +
                           config['DB_HOST'])
    conn.execute('PRAGMA foreign_keys = ON')

    # Get a new proxy list.
    proxies = PubProxy()
    proxies.load()

    # Save all the fetched proxies into the database.
    for proxy in proxies.list:
        proxy.save(conn)

    # Ensure we close the database connection.
    conn.close()

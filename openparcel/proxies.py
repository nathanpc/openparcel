#!/usr/bin/env python3

import concurrent.futures
import inspect
import json
import string
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from operator import itemgetter
from threading import Lock
from typing import Mapping, TypeVar, Type

import requests
import DrissionPage.errors
from mysql.connector import MySQLConnection

import config
from openparcel.carriers import carriers
from openparcel.exceptions import ScrapingReturnedError

# Typing hints.
TProxy = TypeVar('TProxy', bound='Proxy')


class Proxy:
    """A proxy server abstraction."""

    def __init__(self, addr: str, port: int, country: str, speed: int,
                 protocol: str, active: bool = True, db_id: int = None,
                 valid_carriers: list[dict] = None,
                 conn: MySQLConnection = None):
        self.db_id: int = db_id
        self.addr: str = addr
        self.port: int = port
        self.country: str = country.upper()
        self.speed: int = speed
        self.protocol: str = protocol.lower()
        self.active: bool = active
        self.valid_carriers: list[dict] = valid_carriers
        self.conn: MySQLConnection = conn

        # Ensure we always have an empty list of valid carriers.
        if self.valid_carriers is None:
            self.valid_carriers = []

    @staticmethod
    def list(conn: MySQLConnection) -> list[TProxy]:
        """Gets the entire list of available proxies."""
        proxies = []

        # Get the list from the database.
        cur = conn.cursor()
        cur.execute('SELECT * FROM proxies WHERE (active = %s)', (True,))
        for row in cur:
            proxies.append(Proxy.from_row(row, conn=conn))
        cur.close()
        return proxies

    @staticmethod
    def from_row(row: tuple, conn: MySQLConnection = None) -> TProxy:
        """Builds up a Proxy object from a database row."""
        return Proxy(db_id=row[0], addr=row[1], port=row[2], country=row[3],
                     speed=row[4], protocol=row[5], active=bool(row[6]),
                     valid_carriers=json.loads(row[7]), conn=conn)

    def test(self) -> bool:
        """Perform a cursory test of the proxy server."""
        # Ensure we have a clean slate.
        self.valid_carriers = []

        # Go through available carriers.
        for carrier in carriers():
            # Generate a random tracking code.
            code = ''.join(random.choices(string.ascii_uppercase, k=2) +
                           random.choices(string.digits, k=9) +
                           random.choices(string.ascii_uppercase, k=2))
            start_time = None

            # Fetch the random tracking code to try the proxy out.
            try:
                # Set up the carrier and proxy settings.
                carrier = carrier(code)
                carrier.set_proxy(self.as_str())
                print(f'Testing proxy {self.as_str()} '
                      f'({round(self.speed / 1000)}) from {self.country} '
                      f'with {carrier.name}...', end=' ')

                # Try to scrape the website.
                start_time = time.time()
                carrier.fetch()

                # By some miracle we've hit a valid tracking code!
                speed = round((time.time() - start_time) * 1000)
                print(f'{speed} ms')
                self.valid_carriers.append({
                    'id': carrier.uid,
                    'timing': speed
                })
            except ScrapingReturnedError as e:
                # Check which kind of scraping error occurred.
                match e.code:
                    case 'RateLimiting' | 'Blocked':
                        # Blocked by the carrier's anti-bot measures.
                        print('BLOCKED')
                        continue
                    case 'ProxyTimeout':
                        # Proxy is complete garbage.
                        print('TIMEOUT')
                        continue
                    case 'ParcelNotFound' | 'InvalidTrackingCode':
                        # Looks like it is a valid proxy!
                        speed = round((time.time() - start_time) * 1000)
                        print(f'{speed} ms')
                        self.valid_carriers.append({
                            'id': carrier.uid,
                            'timing': speed
                        })
                        continue

                # Something unexpected just happened.
                print(f'Unknown scraping error: {e.code}')
            except DrissionPage.errors.BaseError:
                print('FAILED')

        # Is this proxy completely dead?
        if len(self.valid_carriers) == 0:
            return False

        # Compute the average time it took to perform the requests.
        self.speed = round(sum(it['timing'] for it in self.valid_carriers) /
                           len(self.valid_carriers))
        print(f'Proxy {self.as_str()} has an average speed of {self.speed}',
              end='\n\n', flush=True)

        return True

    def is_duplicate(self) -> bool:
        """Checks if we are already in the database."""
        # Ensure we have a database connection.
        if self.conn is None:
            raise AssertionError('Database not available for duplicate check')

        # Check the database if this object is already in it.
        cur = self.conn.cursor()
        cur.execute('SELECT id, active FROM proxies '
                    'WHERE (addr = %s) AND (port = %s) AND (protocol = %s)',
                    (self.addr, self.port, self.protocol))
        row = cur.fetchone()
        cur.close()

        return row is not None

    def save(self):
        """Saves the proxy information to our database."""
        # Ensure we have a database connection.
        if self.conn is None:
            raise AssertionError('Database not available for saving')

        # Check if a refresh failed.
        if len(self.valid_carriers) == 0:
            self.active = False

        # Insert or update database record?
        params = (self.addr, self.port, self.country, self.speed, self.protocol,
                  self.active, json.dumps(self.valid_carriers))
        if self.db_id is not None:
            stmt = ('UPDATE proxies SET  addr = %s, port = %s, country = %s, '
                    ' speed = %s, protocol = %s, active = %s, carriers = %s '
                    'WHERE id = %s')
            params += (self.db_id,)
        else:
            stmt = ('INSERT INTO proxies '
                    '(addr, port, country, speed, protocol, active, carriers) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s)')

        # Insert the object into the database.
        cur = self.conn.cursor()
        cur.execute(stmt, params)
        self.conn.commit()
        if self.db_id is None:
            self.db_id = cur.lastrowid
        cur.close()

    def as_str(self) -> str:
        """String representation of the proxy, ready to be used."""
        return f'{self.protocol}://{self.addr}:{self.port}'


class ProxyList:
    """Generic proxy list provider class."""
    url: str = None

    def __init__(self, api_key: str = None, auto_save: bool = True,
                 conn: MySQLConnection = None,
                 headers: Mapping[str, str | bytes] = None,
                 test_workers: int = 8):
        self.list: list[Proxy] = []
        self.conn: MySQLConnection = conn
        self.auto_save: bool = auto_save
        self.headers: Mapping[str, str | bytes] = headers
        self.num_workers: int = test_workers
        self._lock: Lock = Lock()

        # Import API key from configuration if needed.
        self._import_api_key(self.__class__.__name__, api_key)

    def load(self, parallel: bool = True) -> list[Proxy]:
        """Loads the proxy list from its source."""
        self._parse_response(self._fetch(), parallel=parallel)
        return self.list

    def append(self, server: Proxy) -> bool:
        """Appends a proxy server to the list after performing some checks."""
        # Check if we already have this proxy in our database.
        if server.is_duplicate():
            print(f'Duplicate proxy server {server.protocol}://{server.addr}:'
                  f'{server.port} was ignored.')
            return False

        # Test the proxy out before appending it to the list.
        if server.test():
            # Acquire our process lock and append the server to the list.
            self._lock.acquire()
            self.list.append(server)

            # Automatically save the server to the database if asked for.
            try:
                if self.auto_save:
                    server.save()
            finally:
                self._lock.release()

            return True

        # Looks like this proxy server was a bust.
        return False

    def set_test_workers(self, num_workers: int):
        """Sets the number of proxy testing workers in the pool."""
        self.num_workers = num_workers

    def _fetch(self) -> requests.Response:
        """Fetches the proxy list from somewhere."""
        req = requests.get(self.url, headers=self.headers)
        if req.status_code != 200:
            raise requests.exceptions.HTTPError(
                'Proxy list backend API request failed with HTTP status code ' +
                str(req.status_code))

        return req

    def _parse_response(self, response: requests.Response,
                        parallel: bool = True):
        """Parses the proxy list response from the backend."""
        raise NotImplementedError

    def _import_api_key(self, service_name: str, default: str):
        """Imports an API key from the configuration if one is available."""
        # Import the key from the configuration.
        if default is None:
            self.api_key = config.proxy_api_key(service_name)
            return

        self.api_key = default


class PubProxy(ProxyList):
    """Proxy list using PubProxy as the backend."""
    url: str = 'http://pubproxy.com/api/proxy?format=json'

    def __init__(self, api_key: str = None, country_denylist: list = None,
                 auto_save: bool = True, conn: MySQLConnection = None):
        super().__init__(api_key, auto_save=auto_save, conn=conn)

        # Build up the request URL.
        if self.api_key is not None:
            self.url += '&api=' + self.api_key
        self.url += '&last_check=30'
        self.url += f'&limit={5 if self.api_key is None else 20}'
        if country_denylist is not None:
            self.url += '&not_country=' + ','.join(country_denylist)
        self.url += '&https=true'
        self.url += '&post=true'
        self.url += '&user_agent=true'
        self.url += '&cookies=true'
        self.url += '&referer=true'
        self.common_url = self.url

    def load(self, num: int = 1) -> list[Proxy]:
        # Load the list multiple times in order to get a good selection.
        for _ in range(num):
            for protocol in ('http', 'socks4', 'socks5'):
                self.url = f'{self.common_url}&type={protocol}'
                super().load()

        return self.list

    def _parse_response(self, response: requests.Response,
                        parallel: bool = True):
        resp_json = response.json()
        if parallel:
            with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
                futures = [pool.submit(self._append_item, proxy)
                           for proxy in resp_json['data']]
                concurrent.futures.wait(
                    futures, return_when=concurrent.futures.ALL_COMPLETED)
        else:
            for item in resp_json['data']:
                self._append_item(item)

    def _append_item(self, item: dict):
        """Appends an item returned from the API into the proxy list."""
        with MySQLConnection(**config.db_conn()) as conn:
            self.append(Proxy(
                addr=item['ip'],
                port=int(item['port']),
                country=item['country'],
                speed=int(item['speed']) * 1000,
                protocol=item['type'],
                conn=conn))


class Proxifly(ProxyList):
    """Proxy list using Proxifly as the backend."""
    url: str = 'https://api.proxifly.dev/get-proxy'

    def __init__(self, api_key: str = None, quantity: int = 5,
                 auto_save: bool = True, conn: MySQLConnection = None):
        # Initialize the parent class.
        super().__init__(api_key, conn=conn, auto_save=auto_save,
                         headers={'Content-Type': 'application/json'})

        # Set up the request parameters.
        self.options = {
            'format': 'json',
            'protocol': ['http', 'socks4', 'socks5'],
            'quantity': quantity,
            'https': True,
            'speed': 10000
        }

        # Append the API key if we have one.
        if self.api_key is not None:
            self.options['apiKey'] = self.api_key

    def _fetch(self) -> requests.Response:
        req = requests.post(self.url, data=json.dumps(self.options),
                            headers=self.headers)
        if req.status_code != 200:
            raise requests.exceptions.HTTPError(
                'Proxifly request failed with HTTP status code ' +
                str(req.status_code))

        return req

    def _parse_response(self, response: requests.Response,
                        parallel: bool = True):
        resp_json = response.json()
        if parallel:
            with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
                futures = [pool.submit(self._append_item, proxy)
                           for proxy in resp_json]
                concurrent.futures.wait(
                    futures, return_when=concurrent.futures.ALL_COMPLETED)
        else:
            for item in resp_json:
                self._append_item(item)

    def _append_item(self, item: dict):
        """Appends an item returned from the API into the proxy list."""
        with MySQLConnection(**config.db_conn()) as conn:
            self.append(Proxy(
                addr=item['ip'],
                port=int(item['port']),
                country=item['geolocation']['country'],
                speed=int(item['score']) * 1000,
                protocol=item['protocol'],
                conn=conn))


class OpenProxySpace(ProxyList):
    """Proxy list using Open Proxy Space as the backend."""
    url: str = 'https://api.openproxy.space/premium/json'

    def __init__(self, api_key: str = None, quantity: int = 5,
                 auto_save: bool = True, conn: MySQLConnection = None):
        super().__init__(api_key, auto_save=auto_save, conn=conn)

        # Build up the request URL.
        self.url += (f'?apiKey={self.api_key}&amount={quantity}&smart=1'
                     '&stableAverage=0&status=1&uptime=99')

    @staticmethod
    def proto_from_index(index: int) -> str:
        """Gets the appropriate protocol name from a protocol index."""
        match index:
            case 1:
                return 'http'
            case 2:
                return 'socks4'
            case 3:
                return 'socks5'

        raise ValueError(f'Invalid protocol index: {index}')

    def _parse_response(self, response: requests.Response,
                        parallel: bool = True):
        resp_json = response.json()
        proxies = []

        # Build a flat proxy list.
        for item in resp_json:
            for proto_index in item['protocols']:
                item['proto'] = self.proto_from_index(proto_index)
                proxies.append(item)

        if parallel:
            with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
                futures = [pool.submit(self._append_item, proxy)
                           for proxy in proxies]
                concurrent.futures.wait(
                    futures, return_when=concurrent.futures.ALL_COMPLETED)
        else:
            for item in proxies:
                self._append_item(item)

    def _append_item(self, item: dict):
        """Appends an item returned from the API into the proxy list."""
        with MySQLConnection(**config.db_conn()) as conn:
            self.append(Proxy(
                addr=item['ip'],
                port=int(item['port']),
                country=item['country'],
                speed=int(item['timeout']),
                protocol=item['proto'],
                conn=conn))


class ProxyScrapeFree(ProxyList):
    """Proxy list using ProxyScrape freebies list as the backend."""

    def __init__(self, timeout: int = 8000, auto_save: bool = True,
                 conn: MySQLConnection = None):
        url = ('https://api.proxyscrape.com/v3/free-proxy-list/get?'
               f'request=displayproxies&protocol=all&timeout={timeout}'
               '&proxy_format=protocolipport&format=json')
        super().__init__(auto_save=auto_save, conn=conn)

    def _parse_response(self, response: requests.Response,
                        parallel: bool = True):
        # Sort the response list by timeout.
        resp_json = response.json()
        proxy_list = sorted(resp_json['proxies'],
                            key=itemgetter('average_timeout'))
        alive_proxies = []

        # Filter out dead proxies.
        for item in proxy_list:
            # Ignore dead proxies.
            if not item['alive'] or not item['ssl']:
                continue
            alive_proxies.append(item)

        if parallel:
            with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
                futures = [pool.submit(self._append_item, proxy)
                           for proxy in alive_proxies]
                concurrent.futures.wait(
                    futures, return_when=concurrent.futures.ALL_COMPLETED)
        else:
            for item in alive_proxies:
                self._append_item(item)

    def _append_item(self, item: dict):
        """Appends an item returned from the API into the proxy list."""
        with MySQLConnection(**config.db_conn()) as conn:
            self.append(Proxy(
                addr=item['ip'],
                port=int(item['port']),
                country=item['ip_data']['countryCode'],
                speed=round(item['average_timeout']),
                protocol=item['protocol'],
                conn=conn))


class WebShare(ProxyList):
    """Proxy list using WebShare as the backend."""
    url: str = 'https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1'

    def __init__(self, api_key: str = None, quantity: int = 25,
                 auto_save: bool = True, conn: MySQLConnection = None):
        # Initialize the parent class.
        super().__init__(api_key, conn=conn, auto_save=auto_save)
        self.url += f'&page_size={quantity}'
        self.common_url = self.url

        # Set up the authentication token in the headers.
        self.headers = {'Authorization': f'Token {self.api_key}'}

    def load(self, page: int = 1) -> list[Proxy]:
        self.url = f'{self.common_url}&page={page}'
        return super().load()

    def _parse_response(self, response: requests.Response,
                        parallel: bool = True):
        resp_json = response.json()
        if parallel:
            with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
                futures = [pool.submit(self._append_item, proxy)
                           for proxy in resp_json['results']]
                concurrent.futures.wait(
                    futures, return_when=concurrent.futures.ALL_COMPLETED)
        else:
            for item in resp_json['results']:
                self._append_item(item)

    def _append_item(self, item: dict):
        """Appends an item returned from the API into the proxy list."""
        with MySQLConnection(**config.db_conn()) as conn:
            self.append(Proxy(
                addr=item['proxy_address'],
                port=int(item['port']),
                country=item['country_code'],
                speed=-1,
                protocol='socks5',
                conn=conn))


class FileProxyList(ProxyList):
    """Proxy list from a file."""

    def __init__(self, protocol: str, file: str, auto_save: bool = True,
                 conn: MySQLConnection = None):
        super().__init__(auto_save=auto_save, conn=conn)
        self.protocol = protocol
        self.file = file

    def load(self, parallel: bool = True) -> list[Proxy]:
        proxies = []

        # Read proxies from file.
        with open(self.file, 'r') as f:
            for line in f:
                line = line.split(':')
                proxies.append((line[0], int(line[1])))

        # Generate the proxy list.
        if parallel:
            with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
                futures = [pool.submit(self._append_item, proxy)
                           for proxy in proxies]
                concurrent.futures.wait(
                    futures, return_when=concurrent.futures.ALL_COMPLETED)
        else:
            for item in proxies:
                self._append_item(item)

        return self.list

    def _append_item(self, line: tuple[str, int]):
        """Appends an item returned from the API into the proxy list."""
        with MySQLConnection(**config.db_conn()) as conn:
            self.append(Proxy(
                addr=line[0],
                port=line[1],
                country='ZZ',
                speed=-1,
                protocol=self.protocol,
                conn=conn))


def providers() -> list[tuple[str, Type[ProxyList]]]:
    """Returns a list of the available providers."""
    objs = []

    # Go through our list of classes and only use the ones in the provider list.
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        if (issubclass(obj, ProxyList) and name != 'ProxyList'
                and name != 'FileProxyList'):
            objs.append((name.lower(), obj))

    return objs

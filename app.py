#!/usr/bin/env python3

import asyncio
import datetime
import hashlib
import json
import os
import random
import re
import secrets
import time
from typing import Optional

import DrissionPage.errors
import mysql.connector.errors
from flask import Flask, request, g
from mysql.connector import MySQLConnection
from mysql.connector.pooling import MySQLConnectionPool, PooledMySQLConnection
from werkzeug.exceptions import InternalServerError

import config
import openparcel.carriers as carriers
from openparcel.logger import Logger
from openparcel.carriers import BaseCarrier
from openparcel.exceptions import (NotEnoughParameters, AuthenticationFailed,
                                   TitledException, ScrapingBrowserError,
                                   TrackingCodeInvalid, ServerOverwhelmedError, DatabaseError, TitledInternalServerError)
from openparcel.scraper import ScrapingPool, DuplicateScrapingOperation

# Get our application's logger instance.
root_logger = Logger('flask', 'app')

# Define the global flask application object.
app = Flask(__name__)

# Create MySQL connection pool.
db_conn_pool = MySQLConnectionPool(pool_name='op_main',
                                   pool_size=config.db('pool_size'),
                                   **config.db_conn())

# Create our global scraping browser pool.
scraping_pool = ScrapingPool(
    max_instances=int(config.app('scraper')['max_instances']))


def get_logger(subsystem: str) -> Logger:
    """Gets the logger from the request context. Will not override the subsystem
    if a logger is already in the context."""
    if 'logger' not in g:
        g.logger = root_logger.for_subsystem(subsystem)
    return g.logger


def connect_db() -> MySQLConnection | PooledMySQLConnection:
    """Connects to the database and stores the connection in the global
    application context."""
    if 'db' not in g:
        g.db = db_conn_pool.get_connection()
    return g.db


@app.teardown_appcontext
def app_context_teardown(exception):
    """Event handler when the application context is being torn down."""
    db: MySQLConnection = g.pop('db', None)
    if db is not None and db.is_connected():
        db.commit()
        db.close()


@app.errorhandler(TitledException)
def handle_title_exception(exc: TitledException):
    """Handles uncaught exceptions that were made to provide a response to the
    user."""
    return exc.resp_dict(req_uuid=request_uuid()), exc.status_code


@app.errorhandler(InternalServerError)
def handle_uncaught_exceptions(exc: InternalServerError):
    """Deals with all uncaught exceptions that weren't handled by other error
    handlers."""
    logger = get_logger('internal_server_error')
    return handle_title_exception(TitledInternalServerError(exc, logger=logger))


@app.errorhandler(mysql.connector.errors.Error)
def handle_mysql_exception(exc: mysql.connector.errors.Error):
    """Handles uncaught database exceptions."""
    logger = get_logger('mysql_exception')
    return handle_title_exception(DatabaseError(exc, context={
        'req_uuid': request_uuid()
    }, logger=logger))


def is_authenticated() -> bool:
    """Checks if the user is currently authenticated."""
    return 'user_id' in g


def authenticate(username: str, password: str = None,
                 auth_token: str = None) -> Optional[int]:
    """Authenticates the user based on the provided credentials."""
    # Check if we have cached the user ID and get a logger for us.
    if is_authenticated():
        return user_id()
    logger = get_logger('auth')

    # Perform a bunch of sanity checks.
    if username is None and password is None and auth_token is None:
        raise NotEnoughParameters(
            title='Nothing was provided for authentication',
            message='None of the required parameters were set. Either send the '
                    'username, and password or authentication token.',
            status_code=401)
    elif username is None:
        raise NotEnoughParameters(
            title='Missing username',
            message='In order to authenticate a username and password must be '
                    'supplied.',
            status_code=400)
    elif password is None and auth_token is None:
        raise NotEnoughParameters(
            title='Missing password or authentication token',
            message='In order to authenticate a password or an authentication '
                    'token must be supplied.',
            status_code=400)
    elif username is not None and password is not None and \
            auth_token is not None:
        raise AuthenticationFailed(
            title='Both secrets were provided',
            message='Either password or authentication token must be provided, '
                    'but not both of them.',
            status_code=422)

    # Check the username and get the salt used to generate the password hash.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT salt FROM users WHERE username = %s', (username,))
    row = cur.fetchone()
    if row is None:
        logger.info('auth_failed_username',
                    'User authentication failed due to a wrong username being '
                    f'provided: {username}')
        raise AuthenticationFailed(
            title='Invalid username',
            message='Username is not in our database. Maybe you have'
                    'misspelled it?',
            status_code=401)
    salt = bytes.fromhex(row[0])
    cur.close()

    # Check the credentials against the database.
    cur = conn.cursor()
    if password is not None:
        # Authenticate using a password.
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                            salt, 100_000)
        cur.execute('SELECT id, access_level FROM users '
                    'WHERE (username = %s) AND (password = %s)',
                    (username, password_hash.hex()))
        row = cur.fetchone()
        if row is None:
            logger.info('auth_failed_password',
                        f'User {username} authentication failed due to a wrong '
                        'password.')
            raise AuthenticationFailed(
                title='Wrong password',
                message='Credentials did not match any users in our database. '
                        'Check if you have typed the right password.',
                status_code=401)
    else:
        # Authenticate using the authentication token.
        cur.execute('SELECT auth_tokens.user_id, users.access_level '
                    'FROM auth_tokens '
                    'INNER JOIN users on auth_tokens.user_id = users.id '
                    'WHERE (auth_tokens.token = %s) AND (users.username = %s) '
                    ' AND auth_tokens.active',
                    (auth_token, username))
        row = cur.fetchone()
        if row is None:
            logger.info('auth_failed_token',
                        f'User {username} authentication failed due to a wrong '
                        f'authentication token: {auth_token}')
            raise AuthenticationFailed(
                title='Wrong authentication token',
                message='Credentials did not match anything in our database. '
                        'Check if you have the right authentication token for '
                        'this user.',
                status_code=401)
    cur.close()

    # Caches the user information for the request lifecycle.
    g.username = username
    g.user_id = int(row[0])
    g.user_acl = int(row[1])

    return g.user_id


def http_authenticate(use_secrets: str | tuple[str, ...]) -> Optional[int]:
    """Authentication workflow for an HTTP request."""
    # Check if we have cached the user ID.
    if 'user_id' in g:
        return g.user_id

    # Ensure we build a tuple if a single string was passed for secrets.
    if type(use_secrets) is str:
        use_secrets = (use_secrets,)

    # Get a logger for us.
    logger = get_logger('auth.http')

    # Check if we have the authentication key to work with.
    auth_key = request.args.get('auth')
    if request.method == 'POST':
        auth_key = request.form.get('auth')
    if 'X-Auth-Token' in request.headers:
        auth_key = request.headers['X-Auth-Token']
    if auth_key is None:
        raise NotEnoughParameters(
            title='Missing authentication key',
            message='An authentication key (username and authentication token) '
                    'must be provided to access this resource.',
            status_code=401)

    # Break down the authentication key and perform some general checks.
    auth_key = auth_key.split(':')
    if len(auth_key) != 2 or not auth_key[0].strip() or not auth_key[1].strip():
        logger.info('auth_key_invalid', 'Authentication failed due to an '
                                        'invalid authentication key.')
        raise AuthenticationFailed(
            title='Invalid authentication key',
            message='Format of the provided authentication key is not valid.',
            status_code=200)
    username = auth_key[0].lower()
    secret = auth_key[1]

    # Perform the authentication.
    err = None
    if 'password' in use_secrets:
        try:
            return authenticate(username, password=secret)
        except TitledException as e:
            err = e
    if 'auth_token' in use_secrets:
        try:
            return authenticate(username, auth_token=secret)
        except TitledException as e:
            err = e

    # Raise an exception if something went wrong.
    if err is not None:
        raise err

    # Looks like not a single valid secret was passed into us.
    raise NotImplementedError('Unsupported secret type')


def user_id() -> Optional[int]:
    """Returns currently logged user ID if authenticated. None otherwise."""
    return g.user_id if is_authenticated() else None


def logged_username() -> Optional[str]:
    """Returns currently logged username if authenticated. None otherwise."""
    return g.username if is_authenticated() else None


def user_acl() -> int:
    """Returns the currently logged user access level."""
    # Do we even have a user ID?
    return g.user_acl if is_authenticated() else 0


def is_superuser() -> bool:
    """Checks if the currently authenticated user is an admin."""
    return user_acl() >= 100


def request_uuid() -> str:
    """Returns a UUID that represents the current request. Will be generated if
    needed."""
    if 'req_uuid' not in g:
        # Generate a meaningful UUID to reference the request in the future.
        g.req_uuid = (hex(round(time.time() * 1000))[2:] + '-' +
                      hashlib.md5(request.path.encode()).hexdigest()[-8:] +
                      '-' + hashlib.md5(json.dumps(dict(request.headers))
                                        .encode()).hexdigest()[-12:] + '-' +
                      random.randbytes(2).hex())

    return g.req_uuid


def log_http_request(logger: Logger = None):
    """Logs everything about an HTTP request."""
    # Ensure the logger has our request UUID.
    logger.uuid = request_uuid()

    # Build our machine-readable context for the logs.
    context = {
        'method': request.method,
        'full_path': request.full_path,
        'path': request.path,
        'query_string': request.query_string.decode(),
        'args': request.args,
        'headers': dict(request.headers),
        'form': request.form,
        'remote_addr': request.remote_addr,
        'req_uuid': request_uuid()
    }

    # Remove sensitive information from the context.
    if 'X-Auth-Token' in context['headers']:
        context['headers']['X-Auth-Token'] = '<Withheld for security reasons>'

    # Log the request.
    logger.debug('request',
                 f'{request.method} {request.path} [{request.remote_addr}]',
                 context=context)


def should_refresh_parcel(parcel: BaseCarrier, timediff: float,
                          force: bool = False) -> bool:
    """Checks if a parcel tracking history is old enough to have timed out."""
    timeout = config.app('cache')['refresh_timeout']
    return force or (not parcel.archived and abs(timediff) >= timeout)


@app.route('/')
def hello_world():
    return 'OpenParcel'


@app.route('/ping')
def ping_pong():
    """Provides a rudimentary way to detect the server and its version."""
    resp = app.make_response('PONG')
    resp.headers['X-OpenParcel-Version'] = '0.1.0'

    return resp


@app.route('/track/<carrier_id>/<code>')
async def track(carrier_id: str, code: str, force: bool = False,
                carrier: BaseCarrier = None):
    """Tracks the history of a parcel given a carrier ID and a tracking code."""
    # Get a logger for us.
    logger = get_logger('track.carrier_and_code')
    log_http_request(logger)

    # Check if we are authorized.
    http_authenticate('auth_token')
    if logger.subsystem == 'track.carrier_and_code':
        logger.debug('user_track_parcel',
                     f'User {logged_username()} trying to track parcel '
                     f'{carrier_id} {code}')

    # Check if we have a valid tracking code.
    if not BaseCarrier.is_tracking_code_valid(code):
        raise TrackingCodeInvalid(logger=logger)

    # Get the requested carrier if not provided.
    if carrier is None:
        carrier = carriers.from_id(carrier_id)
        if carrier is None:
            logger.warning('carrier_invalid',
                           f'User {logged_username()} passed an invalid '
                           f'carrier ID: {carrier_id}')
            raise TitledException(
                title='Invalid carrier ID',
                message='Provided carrier ID does not match any of the available '
                        'carriers.',
                status_code=404)
        carrier = carrier(code)

    # Is this a bespoke tracking request?
    conn = connect_db()
    if carrier.db_id is None:
        # Check if it has been previously tracked and isn't outdated.
        cur = conn.cursor()
        cur.execute(
            'SELECT id FROM parcels WHERE (carrier = %s) '
            ' AND (tracking_code = %s) AND (DATEDIFF(NOW(), created) < %s) '
            'ORDER BY created DESC LIMIT 1',
            (carrier_id, code, carrier.outdated_period_days))
        row = cur.fetchone()
        cur.close()

        if row is not None:
            carrier.set_parcel_id(row[0])

        # Check if it has been previously cached.
        cur = conn.cursor()
        cond = '(parcels.id = %s) '
        cond_values = (carrier.db_id,)
        if carrier.db_id is None:
            cond = '(parcels.carrier = %s) AND (parcels.tracking_code = %s) '
            cond_values = (carrier_id, code)
        cur.execute(
            'SELECT parcels.id, parcels.carrier, parcels.tracking_code, '
            ' parcels.slug, parcels.created, history_cache.retrieved, '
            ' history_cache.data, user_parcels.name, user_parcels.archived, '
            ' UNIX_TIMESTAMP(history_cache.retrieved) - UNIX_TIMESTAMP() diff '
            'FROM history_cache '
            'LEFT JOIN parcels ON history_cache.parcel_id = parcels.id '
            'LEFT JOIN user_parcels '
            ' ON (history_cache.parcel_id = user_parcels.parcel_id) '
            ' AND (user_parcels.user_id = %s) '
            f'WHERE {cond} AND (DATEDIFF(NOW(), created) < %s)'
            'ORDER BY history_cache.retrieved DESC LIMIT 1',
            (user_id(),) + cond_values + (carrier.outdated_period_days,))
        row = cur.fetchone()
        cur.close()

        if row is not None:
            carrier.slug = row[3]
            carrier.archived = bool(row[-2]) if row[-2] is not None else False
            carrier.parcel_name = row[-3]

            # Ensure that only the superuser can issue a force from the outside.
            if not force and is_superuser():
                force = request.args.get('force', default=force, type=bool)

            # Check if we should return the cached value.
            if not should_refresh_parcel(carrier, row[-1], force=force):
                carrier.from_cache(
                    db_id=row[0],
                    cache=json.loads(row[6]),
                    slug=row[3],
                    created=row[4],
                    last_updated=row[5],
                    parcel_name=carrier.parcel_name,
                    archived=carrier.archived)
                logger.info('parcel_cached',
                            f'User {logged_username()} requested parcel '
                            f'{carrier.slug} ({carrier.db_id}) and is being '
                            'served a cached version since it is '
                            f'{carrier.created_delta().total_seconds()} secs '
                            f'old.')
                return carrier.get_resp_dict()

            # Store the parcel ID.
            carrier.set_parcel_id(row[0])

    # Fetch tracking history.
    try:
        # Fetch tracking history.
        prefetch_now = datetime.datetime.now(datetime.UTC)
        op = await scraping_pool.fetch(carrier, local_logger=logger)
        cur = conn.cursor()
        now = datetime.datetime.now(datetime.UTC)

        # Log the time it took to fetch the parcel.
        logger.info('parcel_fetch', f'Parcel {carrier_id} {code} fetched in '
                                    f'{(now - prefetch_now).total_seconds()} seconds using '
                                    f'proxy {carrier.proxy}')

        # Is this the first time that we are caching this parcel?
        if carrier.db_id is None:
            # First time we are caching this parcel.
            cur.execute(
                'INSERT INTO parcels (carrier, tracking_code, created, slug) '
                'VALUES (%s, %s, %s, %s)',
                (carrier_id, code, now.isoformat(), carrier.generate_slug()))
            conn.commit()
            carrier.set_parcel_id(cur.lastrowid)
            logger.info('parcel_new', f'New parcel {carrier.slug} '
                                      f'({carrier.db_id}) added to the system.',
                        {'context': carrier.as_dict(internals=True)})

        # Cache the retrieved tracking history.
        cur.execute('INSERT INTO history_cache (parcel_id, retrieved, data) '
                    'VALUES (%s, %s, %s)',
                    (carrier.db_id, now.isoformat(),
                     json.dumps(carrier.get_resp_dict(bare=True))))
        conn.commit()
        cur.close()
        logger.info('parcel_history_new',
                    f'Updated tracking history for parcel {carrier.slug} '
                    f'({carrier.db_id}) by {logged_username()}.')

        # Mark operation as finished and send tracking history to the client.
        op.mark_done()
        return carrier.get_resp_dict()
    except DuplicateScrapingOperation as dup:
        # Looks like another request is already taking care of this for us.
        while not dup.op.is_done():
            await asyncio.sleep(.5)

        # Merge the scraped information from the other operation and return.
        dup.op.merge_resp_into(carrier)
        return carrier.get_resp_dict()
    except DrissionPage.errors.BaseError as e:
        # Probably an error with our scraping stuff.
        raise ScrapingBrowserError(e, carrier, logger=logger)
    except TimeoutError as e:
        # Looks like we are currently overwhelmed.
        raise ServerOverwhelmedError(logger=logger, context={
            'cause': str(e)
        })


@app.route('/track/<parcel_slug>')
async def track_id(parcel_slug: str, force: bool = False):
    """Tracks the history of a parcel given a parcel ID."""
    # Get a logger for us.
    logger = get_logger('track.slug')
    log_http_request(logger)

    # Check if we are authorized.
    http_authenticate('auth_token')
    logger.debug('user_track_parcel',
                 f'User {logged_username()} trying to track a parcel using '
                 f'slug {parcel_slug}')

    # Check if parcel slug is valid.
    if not BaseCarrier.is_slug_valid(parcel_slug):
        logger.info('slug_invalid',
                    f'User {logged_username()} tried to track a parcel using '
                    f'an invalid slug ({parcel_slug}).')
        raise TitledException(
            title='Invalid parcel slug',
            message='Provided parcel slug contains invalid characters or is '
                    'too long.',
            status_code=422)

    # Check if it has been previously cached.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute(
        'SELECT user_parcels.name, user_parcels.archived, parcels.id, '
        ' parcels.carrier, parcels.tracking_code, parcels.slug, '
        ' parcels.created, history_cache.retrieved, history_cache.data, '
        ' (UNIX_TIMESTAMP(history_cache.retrieved) - UNIX_TIMESTAMP()) diff '
        'FROM history_cache '
        'LEFT JOIN user_parcels '
        ' ON user_parcels.parcel_id = history_cache.parcel_id '
        'LEFT JOIN parcels ON parcels.id = history_cache.parcel_id '
        'WHERE (user_parcels.user_id = %s) AND (parcels.slug = %s) '
        'ORDER BY history_cache.retrieved DESC LIMIT 1',
        (user_id(), parcel_slug))
    row = cur.fetchone()
    cur.close()
    if row is None:
        logger.info('slug_not_found',
                    f'User {logged_username()} tried to track a parcel using '
                    f'a slug ({parcel_slug}) that we could not match to them.')
        raise TitledException(
            title='Unknown parcel',
            message='The provided parcel slug does not match with any saved '
                    'parcels for this user.',
            status_code=404)

    # Gather some basic information about the parcel.
    carrier = carriers.from_id(row[3])(str(row[4]))
    carrier.from_cache(
        db_id=row[2],
        cache=json.loads(row[-2]),
        slug=row[5],
        created=row[6],
        last_updated=row[7],
        parcel_name=row[0],
        archived=bool(row[1]))

    # Check if it's outdated or archived and always serve a cached version.
    if (carrier.is_outdated()
            or not should_refresh_parcel(carrier, row[-1], force=force)):
        if carrier.is_outdated():
            status_log = 'outdated'
        else:
            status_log = f'{carrier.created_delta().total_seconds()} secs old'
        logger.info('parcel_cached',
                    f'User {logged_username()} requested parcel {carrier.slug} '
                    f'({carrier.db_id}) and is being served a cached version '
                    f'since it is {status_log}.')

        return carrier.get_resp_dict()

    # Fetch some fresh (or cached) information about this parcel.
    return await track(carrier.uid, carrier.tracking_code, force=force,
                       carrier=carrier)


@app.route('/register', methods=['POST'])
def register():
    """Registers the user in the database."""
    username = request.form['username'].lower()
    password = request.form['password']

    # Get a logger for us.
    logger = get_logger('user_register')
    log_http_request(logger)

    # Check if we are accepting registrations.
    if not config.app('allow_registration'):
        raise TitledException(
            title='Registrations disabled',
            message='Registrations have been disabled by the administrator.',
            status_code=422)

    # Check if we have both username and password.
    if username is None or password is None:
        raise TitledException(
            title='Missing username or password',
            message='In order to register a username and password must be '
                    'supplied.',
            status_code=400)

    # Check if the username is clean.
    if not re.match(r'^[a-z][a-z0-9_]+$', username):
        raise TitledException(
            title='Invalid username',
            message='Username must contain only lowercase letters, numbers, '
                    'and underscores.',
            status_code=422)

    # Check if username is long enough.
    if 30 < len(username) < 3:
        raise TitledException(
            title='Invalid username',
            message='Username must have at least 3 characters and no more than '
                    '30 characters.',
            status_code=422)

    # Check if the password is long enough.
    if 250 < len(password) < 6:
        raise TitledException(
            title='Invalid password',
            message='Password must have at least 6 characters and no more than '
                    '250 characters.',
            status_code=422)

    # Check if the username already exists.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username = %s', (username,))
    if cur.fetchone() is not None:
        raise TitledException(
            title='Username already exists',
            message='Username is already in use. Please select another one.',
            status_code=422)
    cur.close()

    # Hash the password.
    salt = os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                        salt, 100_000)

    # Insert the new user into the database.
    cur = conn.cursor()
    cur.execute('INSERT INTO users (username, password, salt) '
                'VALUES (%s, %s, %s)',
                (username, password_hash.hex(), salt.hex()))
    conn.commit()
    cur.close()

    logger.info('user_new', f'New user registered: {username}')
    return {
        'title': 'Registration successful',
        'message': 'User was successfully registered.'
    }


@app.route('/auth/token/new', methods=['POST'])
def create_auth_token(description: str = None, username: str = None,
                      password: str = None):
    """Creates a new authentication token for a user."""
    # Get a logger for us.
    logger = get_logger('auth_token.new')
    log_http_request(logger)

    # Authenticate using the username and password first.
    if username is None:
        http_authenticate('password')
    else:
        authenticate(username, password)

    # Get the description.
    if description is None:
        if 'description' not in request.form:
            raise TitledException(
                title='Description not provided',
                message='You must provide a description for the authorization '
                        'token that will be generated.',
                status_code=400)
        elif request.form['description'].strip() == '':
            raise TitledException(
                title='Empty description provided',
                message='A meaningful description is required for generating '
                        'an authentication token.',
                status_code=422)

        description = request.form['description'].strip()

    # Ensure the description isn't enormous.
    description = description[:150]

    # Generate the authentication token store it.
    auth_token = secrets.token_hex(20)
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO auth_tokens (token, user_id, description) '
                'VALUES (%s, %s, %s)', (auth_token, user_id(), description))
    conn.commit()
    cur.close()

    logger.info('auth_token_new',
                f'New authentication token generated for {logged_username()}')
    return {
        'description': description,
        'token': auth_token
    }


@app.route('/auth/token/<revoke_token>', methods=['DELETE'])
def revoke_auth_token(revoke_token: str = None, username: str = None,
                      password: str = None, auth_token: str = None):
    """Revokes an authentication token of a user."""
    # Get a logger for us.
    logger = get_logger('auth_token.revoke')
    log_http_request(logger)

    if username is None:
        http_authenticate(('password', 'auth_token'))
    else:
        authenticate(username, password, auth_token)

    # Check if the authentication token to revoke actually exists.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT description, active FROM auth_tokens '
                'WHERE (token = %s) AND (user_id = %s) AND active',
                (revoke_token, user_id()))
    row = cur.fetchone()
    if row is None:
        raise TitledException(
            title='Authentication token not found',
            message='The authentication token provided to be revoked did not '
                    'match anything in our database. Please check if you have '
                    'the right authentication token for this user.',
            status_code=422)
    cur.close()

    # Mark the token as inactive.
    cur = conn.cursor()
    cur.execute('UPDATE auth_tokens SET active = false '
                'WHERE (token = %s) AND (user_id = %s)',
                (revoke_token, user_id()))
    conn.commit()
    cur.close()

    logger.info('auth_token_revoked', f'User {logged_username()} revoked '
                                      f'authentication token {revoke_token}')
    return {
        'title': 'Authentication token revoked',
        'message': f'The authentication token for {row[0]} has been '
                   'successfully revoked.'
    }


@app.route('/save/<carrier_id>/<code>', methods=['POST', 'DELETE'])
def save_parcel(carrier_id: str, code: str, archived: bool = False):
    """Stores a parcel into the user's tracked parcels list."""
    # Get a logger for us.
    logger = get_logger('parcel_save.carrier_and_code')
    log_http_request(logger)

    # Check if we are authorized.
    http_authenticate('auth_token')

    # Check if we have a valid tracking code.
    if not BaseCarrier.is_tracking_code_valid(code):
        raise TrackingCodeInvalid(logger=logger)

    # Get the parcel ID.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT parcels.id, parcels.slug, user_parcels.name '
                'FROM parcels LEFT JOIN user_parcels '
                ' ON (parcels.id = user_parcels.parcel_id) '
                '  AND (user_parcels.user_id = %s) '
                'WHERE (parcels.carrier = %s) AND (parcels.tracking_code = %s)',
                (user_id(), carrier_id, code))
    row = cur.fetchone()
    cur.close()

    # Check if the parcel has been tracked in the past.
    if row is None:
        raise TitledException(
            title='Parcel does not exist',
            message='Parcel was not found in our system. Try tracking it for '
                    ' its first time before attempting to save it.',
            status_code=422)

    # Delegate the operation.
    return save_parcel_id(row[1], row[2], archived, parcel_id=int(row[0]))


@app.route('/save/<parcel_slug>', methods=['POST', 'DELETE'])
def save_parcel_id(parcel_slug: str, name: str = None, archived: bool = False,
                   parcel_id: int = None):
    """Stores a parcel into the user's tracked parcels list."""
    # Get the name of the saved parcel.
    if name is None:
        name = request.form.get('name') or None
    if len(name) > 100:
        raise TitledException(
            title='Invalid name',
            message='Provided parcel name is too long. Parcel names must not'
                    'exceed 100 characters.',
            status_code=422)

    # Get a logger for us.
    logger = get_logger('parcel_save.slug')
    log_http_request(logger)

    # Check if we are authorized.
    http_authenticate('auth_token')

    # Check if parcel slug is valid.
    if not BaseCarrier.is_slug_valid(parcel_slug):
        logger.info('slug_invalid',
                    f'User {logged_username()} tried to save a parcel using '
                    f'an invalid slug ({parcel_slug}).')
        raise TitledException(
            title='Invalid parcel slug',
            message='Provided parcel slug contains invalid characters or is '
                    'too long.',
            status_code=422)

    # Check if the parcel is already in the user's list.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute(
        'SELECT parcels.id, user_parcels.name FROM parcels '
        'INNER JOIN user_parcels ON user_parcels.parcel_id = parcels.id '
        'WHERE (parcels.slug = %s) AND (user_parcels.user_id = %s)',
        (parcel_slug, user_id()))
    row = cur.fetchone()
    if row is not None:
        if request.method == 'POST':
            raise TitledException(
                title='Already saved',
                message='The parcel is already in the user\'s list.',
                status_code=422)
        elif request.method == 'DELETE':
            parcel_id = int(row[0])
            name = row[1]
    elif row is None and request.method == 'DELETE':
        raise TitledException(
            title='Saved parcel does not exist',
            message='The requested parcel is not in the user\'s list.',
            status_code=422)
    cur.close()

    # Handle the operation of removing a parcel from the user's list.
    if request.method == 'DELETE':
        # Remove it from the saved parcels list.
        cur = conn.cursor()
        cur.execute('DELETE FROM user_parcels '
                    'WHERE (parcel_id = %s) AND (user_id = %s)',
                    (parcel_id, user_id()))
        conn.commit()
        cur.close()

        logger.info('user_parcel_removed',
                    f'User {logged_username()} removed parcel {parcel_slug} '
                    f'({parcel_id}) from its tracking list')
        return {
            'title': 'Removed from saved list',
            'message': f'Parcel "{name}" was removed from the user\'s list.'
        }

    # Perform some cursory checks.
    if name is None:
        raise TitledException(
            title='Missing parcel name',
            message='Please supply a parcel name to be stored.',
            status_code=400)

    # Check if the parcel actually exists in the system.
    if parcel_id is None:
        cur = conn.cursor()
        cur.execute('SELECT id FROM parcels WHERE slug = %s', (parcel_slug,))
        row = cur.fetchone()
        if row is None:
            raise TitledException(
                title='Parcel does not exist',
                message='Parcel was not found in our system. Try tracking it '
                        'for its first time before attempting to save it.',
                status_code=422)
        cur.close()
        parcel_id = int(row[0])

    # Store the saved parcel information in the database.
    name = name.strip()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO user_parcels (name, archived, user_id, parcel_id) '
        'VALUES (%s, %s, %s, %s)', (name, archived, user_id(), parcel_id))
    conn.commit()
    cur.close()

    logger.info('user_parcel_saved',
                f'User {logged_username()} added parcel {parcel_slug} '
                f'({parcel_id}) to its tracking list')
    return {
        'title': 'Parcel saved',
        'message': 'The parcel has been successfully added to your tracked '
                   'parcels list.'
    }


@app.route('/archive/<parcel_slug>', methods=['POST', 'DELETE'])
def archive_flag_parcel(parcel_slug: str):
    """Marks a saved parcel as archived or not."""
    # Get a logger for us.
    logger = get_logger('parcel_archive.slug')
    log_http_request(logger)

    # Check if we are authorized.
    http_authenticate('auth_token')

    # Check if parcel slug is valid.
    if not BaseCarrier.is_slug_valid(parcel_slug):
        logger.info('slug_invalid',
                    f'User {logged_username()} tried to archive a parcel using '
                    f'an invalid slug ({parcel_slug}).')
        raise TitledException(
            title='Invalid parcel slug',
            message='Provided parcel slug contains invalid characters or is '
                    'too long.',
            status_code=422)

    # Get the saved parcel.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute(
        'SELECT parcels.id, user_parcels.name, user_parcels.archived '
        'FROM parcels '
        'INNER JOIN user_parcels ON user_parcels.parcel_id = parcels.id '
        'WHERE (parcels.slug = %s) AND (user_parcels.user_id = %s)',
        (parcel_slug, user_id()))
    row = cur.fetchone()
    cur.close()

    # Perform cursory checks.
    if row is None:
        raise TitledException(
            title='Parcel does not exist',
            message='In order to archive a parcel it must be saved first.',
            status_code=422)
    elif request.method == 'POST' and bool(row[2]):
        raise TitledException(
            title='Parcel already archived',
            message='The parcel has already been marked as archived.',
            status_code=422)
    elif request.method == 'DELETE' and not bool(row[2]):
        raise TitledException(
            title='Parcel not yet archived',
            message='The parcel has not been marked as archived previously.',
            status_code=422)

    # Save some variables.
    parcel_id = int(row[0])
    name = row[1]

    # Toggle the parcel's archived flag.
    cur = conn.cursor()
    cur.execute('UPDATE user_parcels SET archived = %s '
                'WHERE (user_id = %s) AND (parcel_id = %s)',
                (request.method == 'POST', user_id(), parcel_id))
    conn.commit()
    cur.close()

    # Respond with a pretty message.
    if request.method == 'POST':
        logger.info('user_parcel_archived',
                    f'User {logged_username()} archived parcel {parcel_slug} '
                    f'({parcel_id})')
        return {
            'title': 'Parcel archived',
            'message': f'{name} has been archived successfully.'
        }
    else:
        logger.info('user_parcel_unarchived',
                    f'User {logged_username()} unarchived parcel {parcel_slug} '
                    f'({parcel_id})')
        return {
            'title': 'Parcel unarchived',
            'message': f'{name} has been unarchived successfully.'
        }


@app.route('/parcels')
def list_parcels():
    """Lists the parcels for a registered user."""
    resp = {
        'parcels': []
    }

    # Get a logger for us.
    logger = get_logger('parcel_list')
    log_http_request(logger)

    # Check if we are authorized.
    http_authenticate('auth_token')

    # Get the list of the user's parcels from the database.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute(
        'SELECT user_parcels.name, user_parcels.archived, parcels.id, '
        ' parcels.carrier, parcels.tracking_code, parcels.slug, '
        ' parcels.created '
        'FROM user_parcels '
        'LEFT JOIN parcels ON parcels.id = user_parcels.parcel_id '
        'WHERE user_parcels.user_id = %s', (user_id(),))
    parcel_rows = cur.fetchall()
    cur.close()

    # Go through the user's parcels appending the tracking history.
    for parcel_row in parcel_rows:
        # Fetch the parcel history.
        cur = conn.cursor()
        cur.execute('SELECT retrieved, data FROM history_cache '
                    'WHERE parcel_id = %s ORDER BY retrieved DESC LIMIT 1',
                    (parcel_row[2],))
        hist_row = cur.fetchone()
        cur.close()

        # Check if there's no tracking history for this parcel.
        if hist_row is None:
            logger.error(
                'no_history',
                f'User parcel ({parcel_row[5]}) has no tracking history',
                {'row': parcel_row})
            continue

        # Build up the tracked object.
        carrier = carriers.from_id(parcel_row[3])(str(parcel_row[4]))
        carrier.from_cache(
            db_id=parcel_row[2],
            cache=json.loads(hist_row[1]),
            slug=parcel_row[5],
            created=parcel_row[6],
            last_updated=hist_row[0],
            parcel_name=parcel_row[0],
            archived=parcel_row[1])

        # Append the object to the list.
        resp['parcels'].append(carrier.get_resp_dict())

    return resp


if __name__ == '__main__':
    app.run(debug=True)

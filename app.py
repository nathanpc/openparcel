#!/usr/bin/env python3

import datetime
import hashlib
import json
import os
import re
import secrets
import sqlite3
from typing import Optional

import DrissionPage.errors
import yaml
from flask import Flask, request, g

import openparcel.carriers as carriers
from openparcel.exceptions import (NotEnoughParameters, AuthenticationFailed,
                                   TitledException, ScrapingBrowserError)

# Check if we have a configuration file present.
config_path = 'config/config.yml'
if not os.path.exists(config_path):
    print(f'Missing the configuration file in "{config_path}". Duplicate the '
          'example file contained in the same folder and change anything you '
          'see fit.')
    exit(1)

# Define the global flask application object.
app = Flask(__name__)
app.config.from_file(config_path, load=yaml.safe_load)


def connect_db() -> sqlite3.Connection:
    """Connects to the database and stores the connection in the global
    application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DB_HOST'])
        g.db.execute('PRAGMA foreign_keys = ON')

    return g.db


@app.teardown_appcontext
def app_context_teardown(exception):
    """Event handler when the application context is being torn down."""
    # Close the database connection.
    db = g.pop('db', None)
    if db is not None:
        db.close()


@app.errorhandler(TitledException)
def handle_title_exception(exc: TitledException):
    """Handles uncaught exceptions that were made to provide a response to the
    user."""
    return exc.resp_dict(), exc.status_code


def is_authenticated() -> bool:
    """Checks if the user is currently authenticated."""
    return 'user_id' in g


def authenticate(username: str, password: str = None,
                 auth_token: str = None) -> Optional[int]:
    """Authenticates the user based on the provided credentials."""
    # Check if we have cached the user ID.
    if 'user_id' in g:
        return g.user_id

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
    cur.execute('SELECT salt FROM users WHERE username = ?', (username,))
    row = cur.fetchone()
    if row is None:
        raise AuthenticationFailed(
            title='Invalid username',
            message='Username is not in our database. Maybe you have misspelt '
                    'it?',
            status_code=401)
    salt = bytes.fromhex(row[0])
    cur.close()

    # Check the credentials against the database.
    cur = conn.cursor()
    row = None
    if password is not None:
        # Authenticate using a password.
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                            salt, 100_000)
        cur.execute('SELECT id FROM users WHERE (username = ?) AND '
                    '(password = ?)', (username, password_hash.hex()))
        row = cur.fetchone()
        if row is None:
            raise AuthenticationFailed(
                title='Wrong password',
                message='Credentials did not match any users in our database. '
                        'Check if you have typed the right password.',
                status_code=401)
    else:
        # Authenticate using the authentication token.
        cur.execute('SELECT auth_tokens.user_id FROM auth_tokens '
                    'INNER JOIN users on auth_tokens.user_id = users.id '
                    'WHERE (auth_tokens.token = ?) AND (users.username = ?) '
                    ' AND auth_tokens.active',
                    (auth_token, username))
        row = cur.fetchone()
        if row is None:
            raise AuthenticationFailed(
                title='Wrong authentication token',
                message='Credentials did not match anything in our database. '
                        'Check if you have the right authentication token for '
                        'this user.',
                status_code=401)
    cur.close()

    # Caches the username and user ID for the request lifecycle.
    g.username = username
    g.user_id = int(row[0])

    return g.user_id


def http_authenticate(use_secrets: str | tuple[str, ...]) -> Optional[int]:
    """Authentication workflow for an HTTP request."""
    if type(use_secrets) is str:
        use_secrets = (use_secrets,)

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
    else:
        raise NotImplementedError('Unsupported secret type')

    # Raise an exception if something went wrong.
    if err is not None:
        raise err


def user_id() -> Optional[int]:
    """Returns the currently logged user ID if authenticated. None otherwise."""
    return g.user_id if is_authenticated() else None


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
def track(carrier_id: str, code: str, force: bool = False):
    """Tracks the history of a parcel given a carrier ID and a tracking code."""
    # Check if we are authorized.
    http_authenticate('auth_token')

    # Get the requested carrier.
    carrier = carriers.from_id(carrier_id)
    if carrier is None:
        raise TitledException(
            title='Invalid carrier ID',
            message='Carrier ID does not match any of the available carriers.',
            status_code=422)
    carrier = carrier(code)

    # Check if it has been previously cached.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT parcels.*, history_cache.*, '
                ' user_parcels.name, user_parcels.archived, '
                ' (unixepoch(history_cache.retrieved) - unixepoch(\'now\')) '
                'FROM history_cache '
                'LEFT JOIN parcels ON history_cache.parcel_id = parcels.id '
                'LEFT JOIN user_parcels '
                ' ON (history_cache.parcel_id = user_parcels.parcel_id)'
                ' AND (user_parcels.user_id = ?)'
                'WHERE (parcels.carrier = ?) AND (parcels.tracking_code = ?) '
                ' AND ((unixepoch(\'now\') - unixepoch(parcels.created)) < ?)'
                'ORDER BY history_cache.retrieved DESC LIMIT 1',
                (user_id(), carrier_id, code,
                 60 * 60 * 24 * app.config['PARCEL_OUTDATED_PERIOD']))
    row = cur.fetchone()
    cur.close()

    # Get the parcel ID if we even have one.
    if row is not None:
        timeout = app.config['CACHE_REFRESH_TIMEOUT']
        force = request.args.get('force', default=force, type=bool)
        archived = row[-2]
        parcel_name = row[-3]

        # Check if we should return the cached value.
        if not force and (abs(row[-1]) <= timeout or archived):
            carrier.from_cache(row[0], json.loads(row[7]),
                               datetime.datetime.fromisoformat(row[6]),
                               parcel_name=parcel_name)
            return carrier.get_resp_dict()

        carrier.db_id = row[0]

    # Fetch tracking history.
    try:
        # Fetch tracking history.
        data = carrier.fetch()
        cur = conn.cursor()
        now = datetime.datetime.now(datetime.UTC)

        # Is this the first time that we are caching this parcel?
        if carrier.db_id is None:
            # First time we are caching this parcel.
            cur.execute('INSERT OR IGNORE INTO parcels (carrier, tracking_code, created)'
                        ' VALUES (?, ?, ?)', (carrier_id, code, now.isoformat()))
            conn.commit()
            carrier.db_id = cur.lastrowid

        # Cache the retrieved tracking history.
        cur.execute('INSERT INTO history_cache (parcel_id, retrieved, data) '
                    'VALUES (?, ?, ?)',
                    (carrier.db_id, now.isoformat(), json.dumps(data)))
        conn.commit()
        cur.close()

        # Send tracking history to the client.
        return carrier.get_resp_dict()
    except DrissionPage.errors.BaseError as e:
        # Probably an error with our scraping stuff.
        raise ScrapingBrowserError(e, carrier_id, code)


@app.route('/register', methods=['POST'])
def register():
    """Registers the user in the database."""
    username = request.form['username'].lower()
    password = request.form['password']

    # Check if we are accepting registrations.
    if not app.config['ALLOW_REGISTRATION']:
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
    if not re.match(r'^[a-z0-9_]+$', username):
        raise TitledException(
            title='Invalid username',
            message='Username must contain only lowercase letters, numbers, '
                    'and underscore.',
            status_code=422)

    # Check if the password is long enough.
    if len(password) < 6:
        raise TitledException(
            title='Invalid password',
            message='Password must have at least 6 characters.',
            status_code=422)

    # Check if the username already exists.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username = ?', (username,))
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
    cur.execute('INSERT INTO users (username, password, salt) VALUES (?, ?, ?)',
                (username, password_hash.hex(), salt.hex()))
    conn.commit()
    cur.close()

    return {
        'title': 'Registration successful',
        'message': 'User was successfully registered.'
    }


@app.route('/auth/token/new', methods=['POST'])
def create_auth_token(description: str = None, username: str = None,
                      password: str = None):
    """Creates a new authentication token for a user."""
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

    # Generate the authentication token store it.
    auth_token = secrets.token_hex(20)
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO auth_tokens (token, user_id, description) '
                'VALUES (?, ?, ?)', (auth_token, user_id(), description))
    conn.commit()
    cur.close()

    return {
        'description': description,
        'token': auth_token
    }


@app.route('/auth/token/<revoke_token>', methods=['DELETE'])
def revoke_auth_token(revoke_token: str = None, username: str = None,
                      password: str = None, auth_token: str = None):
    """Revokes an authentication token of a user."""
    if username is None:
        http_authenticate(('password', 'auth_token'))
    else:
        authenticate(username, password, auth_token)

    # Check if the authentication token to revoke actually exists.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT description, active FROM auth_tokens '
                'WHERE (token = ?) AND (user_id = ?) AND active',
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
                'WHERE (token = ?) AND (user_id = ?)',
                (revoke_token, user_id()))
    conn.commit()
    cur.close()

    return {
        'title': 'Authentication token revoked',
        'message': f'The authentication token for {row[0]} has been '
                   'successfully revoked.'
    }


@app.route('/save/<carrier_id>/<code>', methods=['POST', 'DELETE'])
def save_parcel(carrier_id: str, code: str, name: str = None,
                delivered: bool = False):
    """Stores a parcel into the user's tracked parcels list."""
    name = request.form.get('name') if name is None else None
    # TODO: Fix this implementation. Name is currently ignored.

    # Check if we are authorized.
    http_authenticate('auth_token')

    # Get the parcel ID.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT parcels.id, user_parcels.name FROM parcels '
                'LEFT JOIN user_parcels '
                'ON (parcels.id = user_parcels.parcel_id) '
                'AND (user_parcels.user_id = ?) '
                'WHERE (parcels.carrier = ?) AND (parcels.tracking_code = ?)',
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
    parcel_id = row[0]
    name = row[1]
    return save_parcel_id(parcel_id, name, delivered, skip_id_check=True)


@app.route('/save/<parcel_id>', methods=['POST', 'DELETE'])
def save_parcel_id(parcel_id: int, name: str = None,
                   archived: bool = False, skip_id_check: bool = False):
    """Stores a parcel into the user's tracked parcels list."""
    if name is None:
        name = request.form.get('name') or None

    # Check if we are authorized.
    http_authenticate('auth_token')

    # Check if the parcel is already in the user's list.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT name FROM user_parcels '
                'WHERE (parcel_id = ?) AND (user_id = ?)',
                (parcel_id, user_id()))
    row = cur.fetchone()
    if row is not None:
        if request.method == 'POST':
            raise TitledException(
                title='Already saved',
                message='The parcel is already in the user\'s list.',
                status_code=422)
        elif request.method == 'DELETE':
            name = row[0]
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
                    'WHERE (parcel_id = ?) AND (user_id = ?)',
                    (parcel_id, user_id()))
        conn.commit()
        cur.close()

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

    # Check if the parcel ID actually exists in the system.
    if not skip_id_check:
        cur = conn.cursor()
        cur.execute('SELECT id FROM parcels WHERE id = ?', (parcel_id,))
        row = cur.fetchone()
        if row is None:
            raise TitledException(
                title='Parcel does not exist',
                message='Parcel was not found in our system. Try tracking it '
                        'for its first time before attempting to save it.',
                status_code=422)
        cur.close()

    # Store the saved parcel information in the database.
    name = name.strip()
    cur = conn.cursor()
    cur.execute('INSERT INTO user_parcels (name, archived, user_id, parcel_id) '
                'VALUES (?, ?, ?, ?)',
                (name, archived, user_id(), parcel_id))
    conn.commit()
    cur.close()

    return {
        'title': 'Parcel saved',
        'message': 'The parcel has been successfully added to your tracked '
                   'parcels list.'
    }


@app.route('/archive/<parcel_id>', methods=['POST', 'DELETE'])
def archive_flag_parcel(parcel_id: int):
    """Marks a saved parcel as archived or not."""
    # Check if we are authorized.
    http_authenticate('auth_token')

    # Get the saved parcel.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT parcel_id, name, archived FROM user_parcels '
                'WHERE (user_id = ?) AND (parcel_id = ?)',
                (user_id(), parcel_id))
    row = cur.fetchone()
    cur.close()

    # Perform cursory checks.
    if row is None:
        raise TitledException(
            title='Parcel does not exist',
            message='In order to archive a parcel it must be saved first.',
            status_code=422)
    elif request.method == 'POST' and row[2]:
        raise TitledException(
            title='Parcel already archived',
            message='The parcel has already been marked as archived.',
            status_code=422)
    elif request.method == 'DELETE' and not row[2]:
        raise TitledException(
            title='Parcel not yet archived',
            message='The parcel has not been marked as archived previously.',
            status_code=422)

    # Toggle the parcel's delivered flag.
    cur = conn.cursor()
    cur.execute('UPDATE user_parcels SET archived = ? '
                'WHERE (user_id = ?) AND (parcel_id = ?)',
                (request.method == 'POST', user_id(), parcel_id))
    conn.commit()
    cur.close()

    # Respond with a pretty message.
    if request.method == 'POST':
        return {
            'title': 'Parcel archived',
            'message': f'{row[1]} has been archived successfully.'
        }
    else:
        return {
            'title': 'Parcel no longer archived',
            'message': f'{row[1]} has been unarchived successfully.'
        }


@app.route('/parcels')
def list_parcels():
    """Lists the parcels for a registered user."""
    resp = {
        'parcels': []
    }

    # Check if we are authorized.
    http_authenticate('auth_token')

    # Get the list from the database.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT * FROM '
                '(SELECT user_parcels.name, parcels.carrier,'
                ' parcels.tracking_code, history_cache.* FROM user_parcels '
                'LEFT JOIN parcels '
                'ON parcels.id = user_parcels.parcel_id '
                'LEFT JOIN history_cache '
                'ON history_cache.parcel_id = user_parcels.parcel_id '
                'WHERE user_parcels.user_id = ? '
                'ORDER BY history_cache.retrieved DESC) AS sq '
                'GROUP BY sq.parcel_id;', (user_id(),))
    for row in cur.fetchall():
        # Build up the tracked object.
        carrier = carriers.from_id(row[1])(row[2])
        carrier.from_cache(row[4], json.loads(row[6]),
                           datetime.datetime.fromisoformat(row[5]),
                           parcel_name=row[0])

        # Append the object to the list.
        resp['parcels'].append(carrier.get_resp_dict())
    cur.close()

    return resp


if __name__ == '__main__':
    app.run(debug=True)

#!/usr/bin/env python3

import os
import re
import yaml
import json
import sqlite3
import datetime
import traceback
import DrissionPage.errors

from flask import Flask, request, session, g

import openparcel.carriers as carriers

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


@app.route('/')
def hello_world():
    return 'OpenParcel'


@app.route('/track/<carrier_id>/<code>')
def track(carrier_id: str, code: str, force: bool = False):
    """Tracks the history of a parcel given a carrier ID and a tracking code."""
    # Get the requested carrier.
    carrier = carriers.from_id(carrier_id)
    if carrier is None:
        return {
            'title': 'Invalid carrier ID',
            'message': 'Carrier ID doesn\'t match any of the available '
                       'carriers.'
        }, 422
    carrier = carrier(code)

    # Check if it has been previously cached.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT parcels.*, history_cache.*, '
                '(unixepoch(history_cache.retrieved) - unixepoch(\'now\')) '
                'FROM history_cache LEFT JOIN parcels '
                'ON history_cache.parcel_id = parcels.id '
                'WHERE (parcels.carrier = ?) AND (parcels.tracking_code = ?) '
                'ORDER BY history_cache.retrieved DESC LIMIT 1',
                (carrier_id, code))
    row = cur.fetchone()

    # Get the parcel ID if we even have one.
    parcel_id = None
    if row is not None:
        parcel_id = row[0]

        # Check if we should return the cached value.
        force = request.args.get('force', default=force)
        if abs(row[-1]) <= app.config['CACHE_REFRESH_TIMEOUT'] and not force:
            carrier.from_cache(json.loads(row[7]),
                               datetime.datetime.fromisoformat(row[6]))
            return carrier.get_resp_dict()

    # Fetch tracking history.
    try:
        # Fetch tracking history.
        data = carrier.fetch()
        cur = conn.cursor()
        now = datetime.datetime.now(datetime.UTC)

        # Is this the first time that we are caching this parcel?
        if parcel_id is None:
            # First time we are caching this parcel.
            cur.execute('INSERT OR IGNORE INTO parcels (carrier, tracking_code, created)'
                        ' VALUES (?, ?, ?)', (carrier_id, code, now.isoformat()))
            conn.commit()
            parcel_id = cur.lastrowid

        # Cache the retrieved tracking history.
        cur.execute('INSERT INTO history_cache (parcel_id, retrieved, data) '
                    'VALUES (?, ?, ?)',
                    (parcel_id, now.isoformat(), json.dumps(data)))
        conn.commit()
        cur.close()

        # Send tracking history to the client.
        return carrier.get_resp_dict()
    except DrissionPage.errors.BaseError as e:
        # Probably an error with our scraping stuff.
        return {
            'title': 'Scraping error',
            'message': 'An error occurred while trying to fetch the tracking '
                       'history from the carrier\'s website.',
            'trace': traceback.format_exc()
        }, 500


@app.route('/register', methods=['POST'])
def register():
    """Registers the user in the database."""
    username = request.form['username'].lower()
    password = request.form['password']

    # Check if we are accepting registrations.
    if not app.config['ALLOW_REGISTRATION']:
        return {
            'title': 'Registrations disabled',
            'message': 'Registrations have been disabled by the administrator.'
        }, 422

    # Check if we have both username and password.
    if username is None or password is None:
        return {
            'title': 'Missing username or password',
            'message': 'In order to register a username and password must be '
                       'supplied.'
        }, 400

    # Check if the username is clean.
    if not re.match(r'^[a-z0-9_]+$', username):
        return {
            'title': 'Invalid username',
            'message': 'Username must contain only lowercase letters, numbers, '
                       'and underscore.'
        }, 422

    # Check if the password is long enough.
    if len(password) < 6:
        return {
            'title': 'Invalid password',
            'message': 'Password must have at least 6 characters.'
        }, 422

    # Check if the username already exists.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cur.fetchone() is not None:
        return {
            'title': 'Username already exists',
            'message': 'Username is in use by another user. Please select '
                       'another one.'
        }, 422
    cur.close()

    # Insert the new user into the database.
    cur = conn.cursor()
    cur.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                (username, password))
    conn.commit()

    # Log the user in for convenience.
    login(username, cur.lastrowid)
    cur.close()

    return {
        'title': 'Registration successful',
        'message': 'User was successfully registered and is already logged in.'
    }


@app.route('/login', methods=['POST'])
def login(username: str = None, user_id: int = None):
    """Logs the use into the system."""
    # Check if we are just setting the authentication session keys.
    if username is not None and user_id is not None:
        session['username'] = username
        session['user_id'] = user_id

    # Check if we have a username and password.
    username = request.form['username'].lower()
    password = request.form['password']
    if username is None or password is None:
        return {
            'title': 'Missing username or password',
            'message': 'In order to login a username and password must be '
                       'supplied.'
        }, 400

    # Check if we are already logged in.
    if 'user_id' in session:
        message = 'The user is already logged into the system.'
        if username != session['username']:
            message = 'Another user is currently logged in. Please log out ' \
                      'first.'
        return {
            'title': 'User already logged in',
            'message': message
        }, 422

    # Check the credentials against the database.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE (username = ?) AND '
                '(password = ?)', (username, password))
    row = cur.fetchone()
    if row is None:
        return {
            'title': 'Invalid username or password',
            'message': 'Credentials didn\'t match any users in our database.'
        }, 401

    # Sets the session authentication keys.
    user_id = row[0]
    session['username'] = username
    session['user_id'] = user_id

    return {
        'title': 'Logged in',
        'message': f'User {username} successfully logged in.'
    }


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Logs out the user."""
    # Check if there's even a logged user.
    if 'user_id' not in session:
        return {
            'title': 'Logout unsuccessful',
            'message': 'No user was previously logged in.'
        }, 422

    # Remove the authentication keys.
    session.pop('user_id', None)
    username = session.pop('username', None)

    return {
        'title': 'Logout successful',
        'message': f'User {username} was logged out.'
    }


@app.route('/parcels')
def list_parcels():
    """Lists the parcels for a registered user."""
    # Check if the user is authenticated.
    if 'user_id' not in session:
        return {
            'title': 'Not logged in',
            'message': 'Please log in to have access to the parcels list.'
        }, 401

    # TODO: Query database.

    return {
        'parcels': []
    }


if __name__ == '__main__':
    app.run(debug=True)

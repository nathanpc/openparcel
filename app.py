#!/usr/bin/env python3

import os
import re
import yaml
import json
import sqlite3
import hashlib
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


def is_authenticated() -> bool:
    """Checks if the user is currently authenticated."""
    return 'user_id' in session


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
            'message': 'Carrier ID does not match any of the available '
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
        force = request.args.get('force', default=force, type=bool)
        if abs(row[-1]) <= app.config['CACHE_REFRESH_TIMEOUT'] and not force:
            carrier.from_cache(parcel_id, json.loads(row[7]),
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

    # Hash the password.
    salt = os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                        salt, 100_000)

    # Insert the new user into the database.
    cur = conn.cursor()
    cur.execute('INSERT INTO users (username, password, salt) VALUES (?, ?, ?)',
                (username, password_hash.hex(), salt.hex()))
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
    if is_authenticated():
        message = 'The user is already logged into the system.'
        if username != session['username']:
            message = 'Another user is currently logged in. Please log out ' \
                      'first.'
        return {
            'title': 'User already logged in',
            'message': message
        }, 422

    # Get the salt used to generate the password hash.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT salt FROM users WHERE username = ?', (username,))
    row = cur.fetchone()
    if row is None:
        return {
            'title': 'Invalid username',
            'message': 'Username is not in our database. Maybe you have '
                       'misspelt it?'
        }, 401
    salt = bytes.fromhex(row[0])
    cur.close()

    # Check the credentials against the database.
    cur = conn.cursor()
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                        salt, 100_000)
    cur.execute('SELECT id FROM users WHERE (username = ?) AND '
                '(password = ?)', (username, password_hash.hex()))
    row = cur.fetchone()
    if row is None:
        return {
            'title': 'Wrong password',
            'message': 'Credentials did not match any users in our database. '
                       'Check if you have typed the right password.'
        }, 401

    # Sets the session authentication keys.
    user_id = row[0]
    session['username'] = username
    session['user_id'] = user_id
    cur.close()

    return {
        'title': 'Logged in',
        'message': f'User {username} successfully logged in.'
    }


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Logs out the user."""
    # Check if there's even a logged user.
    if is_authenticated():
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


@app.route('/favorite/<carrier_id>/<code>', methods=['POST', 'DELETE'])
def favorite_parcel(carrier_id: str, code: str, name: str = None,
                    delivered: bool = False):
    """Stores a parcel into the user's favorites list."""
    if name is None:
        name = request.form.get('name') or None

    # Check if the user is currently logged in.
    if not is_authenticated():
        return {
            'title': 'Sign-in required',
            'message': 'You must be signed in to use this function.'
        }, 401

    # Get the parcel ID.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT parcels.id, user_parcels.name FROM parcels '
                'LEFT JOIN user_parcels '
                'ON (parcels.id = user_parcels.parcel_id) '
                'AND (user_parcels.user_id = ?) '
                'WHERE (parcels.carrier = ?) AND (parcels.tracking_code = ?)',
                (session['user_id'], carrier_id, code))
    row = cur.fetchone()
    cur.close()

    # Check if the parcel has been tracked in the past.
    if row is None:
        return {
            'title': 'Parcel does not exist',
            'message': 'Parcel does not exist. Try tracking it first.'
        }, 422

    # Delegate the operation.
    parcel_id = row[0]
    name = row[1]
    return favorite_parcel_id(parcel_id, name, delivered, skip_id_check=True)


@app.route('/favorite/<parcel_id>', methods=['POST', 'DELETE'])
def favorite_parcel_id(parcel_id: int, name: str = None,
                       delivered: bool = False, skip_id_check: bool = False):
    """Stores a parcel into the user's favorites list."""
    if name is None:
        name = request.form.get('name') or None

    # Check if the user is currently logged in.
    if not is_authenticated():
        return {
            'title': 'Sign-in required',
            'message': 'You must be signed in to use this function.'
        }, 401

    # Check if the parcel is already in the favorites.
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('SELECT name FROM user_parcels '
                'WHERE (parcel_id = ?) AND (user_id = ?)',
                (parcel_id, session['user_id']))
    row = cur.fetchone()
    if row is not None:
        if request.method == 'POST':
            return {
                'title': 'Already in favorites',
                'message': 'The parcel is already in the favorites list.'
            }, 422
        elif request.method == 'DELETE':
            name = row[0]
    elif row is None and request.method == 'DELETE':
        return {
            'title': 'Favorite does not exist',
            'message': 'The requested parcel is not in the favorites list.'
        }, 422
    cur.close()

    # Handle the operation of removing a parcel from the favorites.
    if request.method == 'DELETE':
        # Remove it from the favorites.
        cur = conn.cursor()
        cur.execute('DELETE FROM user_parcels '
                    'WHERE (parcel_id = ?) AND (user_id = ?)',
                    (parcel_id, session['user_id']))
        conn.commit()
        cur.close()

        return {
            'title': 'Removed from favorites',
            'message': f'Parcel "{name}" was removed from the favorites list.'
        }

    # Perform some cursory checks.
    if name is None:
        return {
            'title': 'Missing parcel name',
            'message': 'Please supply a parcel name to be stored.'
        }, 400

    # Check if the parcel ID actually exists in the system.
    if not skip_id_check:
        cur = conn.cursor()
        cur.execute('SELECT id FROM parcels WHERE id = ?', (parcel_id,))
        row = cur.fetchone()
        if row is None:
            return {
                'title': 'Parcel does not exist',
                'message': 'Parcel does not exist. Try tracking it first.'
            }, 422
        cur.close()

    # Store the favorite information in the database.
    name = name.strip()
    cur = conn.cursor()
    cur.execute('INSERT INTO user_parcels (name, delivered, user_id, parcel_id) '
                'VALUES (?, ?, ?, ?)',
                (name, delivered, session['user_id'], parcel_id))
    conn.commit()
    cur.close()

    return {
        'title': 'Added to favorites',
        'message': 'The parcel has been successfully added to your favorites.'
    }


@app.route('/parcels')
def list_parcels():
    """Lists the parcels for a registered user."""
    resp = {
        'parcels': []
    }

    # Check if the user is authenticated.
    if 'user_id' not in session:
        return {
            'title': 'Not logged in',
            'message': 'Please log in to have access to the parcels list.'
        }, 401

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
                'GROUP BY sq.parcel_id;', (session['user_id'],))
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

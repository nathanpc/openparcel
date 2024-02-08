#!/usr/bin/env python3

from flask import Flask

import openparcel.carriers as carriers

# Define the global flask application object.
app = Flask(__name__)


@app.route('/')
def hello_world():
    return 'OpenParcel'


@app.route('/track/<carrier_id>/<code>')
def track(carrier_id: str, code: str):
    """Tracks the history of a parcel given a carrier ID and a tracking code."""
    # Get the requested carrier.
    carrier = carriers.from_id(carrier_id)
    if carrier is None:
        return {
            'title': 'Invalid carrier ID',
            'message': 'Carrier ID doesn\'t match any of the available carriers.'
        }, 422

    # Fetch tracking history.
    carrier = carrier(code)
    data = carrier.fetch()

    # Send tracking history to client.
    return data


if __name__ == '__main__':
    app.run(debug=True)

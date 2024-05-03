#!/usr/bin/env python3

import base64
import hashlib
import sys

from Crypto.Cipher import AES
from Crypto.Util import Counter

import config
from scripts import Command, Action, Manager


class InputLineStream:
    """Iterator that allows us to always read an entire line from a stream."""

    def __init__(self, in_stream = sys.stdin):
        self.in_stream = in_stream

    def __iter__(self):
        return self

    def __next__(self):
        line = ''

        # Read an entire line from the input stream.
        while True:
            c = sys.stdin.read(1)

            # Check for operation ending characters.
            if c == '':
                # Check if we've hit EOF.
                raise StopIteration
            elif c == '\n':
                # Have we reached the end of a line?
                return line
            elif c == '\r':
                # Ignored characters.
                continue

            # Append the character to our buffer.
            line += c


class RequestBundle:
    """Abstraction over carrier request bundles."""

    def __init__(self, key: str):
        # Hash the plain text key using SHA-258 as per the specification.
        self.key: bytes = hashlib.sha256(key.encode()).digest()

    def decrypt(self, bundle: str) -> str:
        """Decrypts a carrier request bundle."""
        # Base64 decode the bundle data to get back the original bytes.
        raw = base64.b64decode(bundle)

        # Get the IV from the first 16 bytes of the bundle.
        iv = int.from_bytes(raw[:AES.block_size])

        # Set up the cipher.
        ctr = Counter.new(AES.block_size * 8, initial_value=iv)
        cipher = AES.new(self.key, AES.MODE_CTR, counter=ctr)

        # Decrypt the
        return cipher.decrypt(raw[AES.block_size:]).decode('utf-8')

    def read_bundle(self, line_stream: InputLineStream = InputLineStream()):
        """Reads a bundle from a line buffer."""
        reading_bundle = False
        enc_bundle = ''

        for line in line_stream:
            # Check if the next line will contain the actual bundle data.
            if line == '-----BEGIN OPENPARCEL BUNDLE-----':
                reading_bundle = True
                continue

            # Are we actually reading the bundle data?
            if reading_bundle:
                # Have we finished reading a bundle?
                if line == '------END OPENPARCEL BUNDLE------':
                    break

                # Store the snippet of data we just got.
                enc_bundle += line

        # Decode the bundle data.
        bundle = self.decrypt(enc_bundle)

        return bundle


class DecodeAction(Action):
    name = 'decode'
    description = 'Decodes a carrier request bundle'
    default = True

    def __init__(self):
        super().__init__()

    def perform(self, enc_bundle: str = None):
        bc = RequestBundle(self.parent.key)

        # Read the bundle from stdin if it wasn't passed to us.
        if enc_bundle is not None:
            data = bc.decrypt(enc_bundle)
        else:
            data = bc.read_bundle()

        # Print the decoded bundle.
        print(f'\n\n{data}')


class RequestBundleCommand(Command):
    """The carrier request bundle decoder command."""
    name = 'reqbundle'
    description = 'Deals with carrier request bundles'

    def __init__(self, parent: Manager = None):
        super().__init__(parent)

        # Load key from configuration.
        self.key = config.app('request_bundle_key')

        # Add default actions.
        self.add_action(DecodeAction())


if __name__ == '__main__':
    command = RequestBundleCommand()
    command.run()

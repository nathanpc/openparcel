#!/usr/bin/env python3

import base64
import hashlib

from Crypto.Cipher import AES
from Crypto.Util import Counter


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


if __name__ == '__main__':
    b64_str = 'put base64 text here'
    key = 'please change me'  # TODO: Read from config.

    bc = RequestBundle(key)
    print(bc.decrypt(b64_str))

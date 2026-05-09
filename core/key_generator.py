"""Bitcoin private key generation and WIF encoding using secp256k1."""

from __future__ import annotations

import hashlib
import os
from typing import Tuple

import base58
import coincurve

# secp256k1 group order — private key must be in [1, N-1]
_SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def _sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


class KeyGenerator:
    """Generates and encodes Bitcoin private keys."""

    @staticmethod
    def generate_private_key() -> bytes:
        """Return 32 cryptographically random bytes in the valid secp256k1 range."""
        while True:
            key = os.urandom(32)
            n = int.from_bytes(key, "big")
            if 1 <= n < _SECP256K1_ORDER:
                return key

    @staticmethod
    def get_public_key(private_key: bytes, compressed: bool = True) -> bytes:
        """Derive compressed or uncompressed public key from private key bytes."""
        priv = coincurve.PrivateKey(private_key)
        return priv.public_key.format(compressed=compressed)

    @staticmethod
    def get_wif(private_key: bytes, compressed: bool = True) -> str:
        """
        Encode private key as WIF (Wallet Import Format).
        Mainnet prefix 0x80; compressed keys get an extra 0x01 suffix.
        """
        payload = b"\x80" + private_key + (b"\x01" if compressed else b"")
        checksum = _sha256d(payload)[:4]
        return base58.b58encode(payload + checksum).decode("ascii")

    @staticmethod
    def wif_to_private_key(wif: str) -> Tuple[bytes, bool]:
        """Decode WIF string back to (private_key_bytes, is_compressed)."""
        raw = base58.b58decode(wif)
        payload = raw[1:-4]  # strip 0x80 prefix and 4-byte checksum
        is_compressed = len(payload) == 33 and payload[-1] == 0x01
        return (payload[:-1] if is_compressed else payload), is_compressed

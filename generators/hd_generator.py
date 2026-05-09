"""
HD Wallet key generator — BIP32 / BIP44 / BIP49 / BIP84 / BIP86.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import struct
from typing import Callable, Optional, Sequence

from mnemonic import Mnemonic

from core.address_generator import AddressGenerator
from core.wallet import WalletKeys

_SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_HARDENED = 0x80000000

DEFAULT_PATHS = [
    "m/44'/0'/0'/0/{i}",
    "m/49'/0'/0'/0/{i}",
    "m/84'/0'/0'/0/{i}",
    "m/86'/0'/0'/0/{i}",
]

DEFAULT_CHILD_COUNT = 20


def _hmac_sha512(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha512).digest()


class _BIP32Node:
    __slots__ = ("key", "chain_code")

    def __init__(self, key: bytes, chain_code: bytes) -> None:
        self.key = key
        self.chain_code = chain_code

    @classmethod
    def from_seed(cls, seed: bytes) -> "_BIP32Node":
        I = _hmac_sha512(b"Bitcoin seed", seed)
        return cls(I[:32], I[32:])

    def child(self, index: int) -> "_BIP32Node":
        import coincurve
        if index >= _HARDENED:
            data = b"\x00" + self.key + struct.pack(">I", index)
        else:
            pub = coincurve.PrivateKey(self.key).public_key.format(compressed=True)
            data = pub + struct.pack(">I", index)
        I = _hmac_sha512(self.chain_code, data)
        il, ir = I[:32], I[32:]
        il_int = int.from_bytes(il, "big")
        key_int = (il_int + int.from_bytes(self.key, "big")) % _SECP256K1_ORDER
        if il_int >= _SECP256K1_ORDER or key_int == 0:
            return self.child(index + 1)
        return _BIP32Node(key_int.to_bytes(32, "big"), ir)


def _parse_path(path: str, child_index: int) -> list[int]:
    path = path.format(i=child_index).strip()
    parts = path.split("/")
    if parts[0] == "m":
        parts = parts[1:]
    indices = []
    for p in parts:
        hardened = p.endswith("'")
        n = int(p.rstrip("'"))
        indices.append(n + _HARDENED if hardened else n)
    return indices


def _derive(master: _BIP32Node, indices: list[int]) -> _BIP32Node:
    node = master
    for idx in indices:
        node = node.child(idx)
    return node


class HDWalletGenerator:
    def __init__(
        self,
        queue: asyncio.Queue[WalletKeys],
        derivation_paths: Sequence[str] = DEFAULT_PATHS,
        child_count: int = DEFAULT_CHILD_COUNT,
        stats=None,
        on_key_generated: Optional[Callable[[WalletKeys], None]] = None,
    ) -> None:
        self._queue = queue
        self._paths = list(derivation_paths)
        self._child_count = child_count
        self._stats = stats
        self._on_key_generated = on_key_generated
        self._running = False
        self._mnemo = Mnemonic("english")

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()

        while self._running:
            wallets = await loop.run_in_executor(None, self._generate_batch)
            for wallet in wallets:
                if self._stats is not None:
                    self._stats.increment(keys_generated=1)
                if self._on_key_generated is not None:
                    self._on_key_generated(wallet)
                await self._queue.put(wallet)

    def _generate_batch(self) -> list[WalletKeys]:
        entropy = self._mnemo.generate(strength=256)
        seed = Mnemonic.to_seed(entropy)
        master = _BIP32Node.from_seed(seed)
        results: list[WalletKeys] = []
        for path_template in self._paths:
            for i in range(self._child_count):
                indices = _parse_path(path_template, i)
                node = _derive(master, indices)
                results.append(AddressGenerator.from_private_key(node.key))
        return results

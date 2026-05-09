"""
Balance checker — consulta o banco UTXO local para cada endereço gerado.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from loguru import logger

from checkers.local_utxo_checker import LocalUTXOChecker
from core.wallet import WalletBalance, WalletKeys, FoundWallet
from config.settings import Settings
from utils.utxo_db import UTXODatabase


class ScanStats:
    """
    Contadores compartilhados entre todas as tarefas do scan.

    asyncio é single-threaded — não precisa de lock para atualizar atributos.
    """

    __slots__ = (
        "keys_generated",
        "addresses_checked",
        "wallets_found",
        "total_found_satoshis",
        "started_at",
    )

    def __init__(self) -> None:
        self.keys_generated: int = 0
        self.addresses_checked: int = 0
        self.wallets_found: int = 0
        self.total_found_satoshis: int = 0
        self.started_at: float = time.monotonic()

    def increment(self, **kwargs: int) -> None:
        for k, v in kwargs.items():
            setattr(self, k, getattr(self, k) + v)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def keys_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        return self.keys_generated / elapsed if elapsed > 0 else 0.0

    @property
    def checks_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        return self.addresses_checked / elapsed if elapsed > 0 else 0.0


class BalanceChecker:
    """
    Orquestra a verificação de saldo para toda a sessão de scan.

    N workers assíncronos puxam da key_queue, verificam todos os tipos de
    endereço no banco UTXO local e colocam wallets com saldo na found_queue.
    """

    def __init__(
        self,
        settings: Settings,
        key_queue: asyncio.Queue[WalletKeys],
        found_queue: asyncio.Queue[FoundWallet],
        stats: ScanStats,
        utxo_db: UTXODatabase,
        on_wallet_found: Optional[Callable[[FoundWallet], None]] = None,
    ) -> None:
        self._settings = settings
        self._key_queue = key_queue
        self._found_queue = found_queue
        self._stats = stats
        self._on_found: Optional[Callable[[FoundWallet], None]] = on_wallet_found
        self._local = LocalUTXOChecker(utxo_db)
        self._address_types: list[str] = settings.scanner.address_types
        self._min_balance = settings.scanner.min_balance_satoshis
        self._running = False

    def stop(self) -> None:
        self._running = False

    async def run(self, worker_count: int) -> None:
        self._running = True
        workers = [
            asyncio.create_task(self._worker(i), name=f"worker-{i}")
            for i in range(worker_count)
        ]
        await asyncio.gather(*workers, return_exceptions=True)
        self._running = False

    async def _worker(self, worker_id: int) -> None:
        while self._running:
            try:
                wallet = await asyncio.wait_for(self._key_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            try:
                await self._process_wallet(wallet)
            except Exception as exc:
                logger.debug(f"Worker {worker_id} erro: {exc}")
            finally:
                self._key_queue.task_done()

    async def _process_wallet(self, wallet: WalletKeys) -> None:
        addresses = [
            (addr, atype)
            for atype, addr in wallet.all_addresses.items()
            if atype in self._address_types and addr
        ]

        positive_balances: list[WalletBalance] = []

        for address, address_type in addresses:
            balance = self._local.check_address(address, address_type)
            self._stats.increment(addresses_checked=1)

            if balance and balance.total_satoshis > self._min_balance:
                positive_balances.append(balance)

        if positive_balances:
            found = FoundWallet(keys=wallet, balances=positive_balances)
            await self._found_queue.put(found)
            self._stats.increment(
                wallets_found=1,
                total_found_satoshis=found.total_confirmed_satoshis,
            )
            if self._on_found:
                self._on_found(found)
            logger.success(
                f"WALLET ENCONTRADA | {found.primary_address} | "
                f"{found.total_confirmed_satoshis} sat"
            )

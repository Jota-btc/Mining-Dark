"""
Checker local usando o banco SQLite do UTXO set.

Consulta instantânea sem chamadas de rede.
Retorna WalletBalance com saldo 0 se não encontrado — não é necessário
chamar APIs externas quando o banco local está disponível.
"""

from __future__ import annotations

from typing import Optional

from core.wallet import WalletBalance
from utils.utxo_db import UTXODatabase


class LocalUTXOChecker:
    """Verifica saldo consultando o banco SQLite local do UTXO set."""

    def __init__(self, db: UTXODatabase) -> None:
        self._db = db

    @property
    def is_available(self) -> bool:
        return self._db.is_ready

    def check_address(self, address: str, address_type: str) -> Optional[WalletBalance]:
        """
        Consulta saldo no banco local.
        Retorna WalletBalance sempre (saldo 0 se não encontrado).
        Retorna None apenas se o banco não estiver disponível.
        """
        if not self._db.is_ready:
            return None

        satoshis = self._db.get_balance(address)
        return WalletBalance(
            address=address,
            address_type=address_type,
            confirmed_satoshis=satoshis,
            unconfirmed_satoshis=0,
            tx_count=1 if satoshis > 0 else 0,
            source="local_utxo",
        )

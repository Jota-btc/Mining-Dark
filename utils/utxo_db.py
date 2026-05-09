"""
Gerenciamento do banco SQLite local com o UTXO set do Bitcoin.

Schema:
  addresses(address TEXT PK, satoshis INTEGER)  — todos os endereços com saldo
  meta(key TEXT PK, value TEXT)                  — metadados (data, bloco, fonte)
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_DB_PATH = Path("utxo_data/utxo.db")
_UPDATE_INTERVAL_DAYS = 30


class UTXODatabase:
    """Interface para o banco SQLite do UTXO set local."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ─── Ciclo de vida ───────────────────────────────────────────────────────

    def open(self) -> bool:
        """Abre o banco. Retorna False se o arquivo não existir ainda."""
        if not self.db_path.exists():
            return False
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA cache_size=-65536")   # 64 MB cache
        self._conn.execute("PRAGMA temp_store=MEMORY")
        return True

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "UTXODatabase":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ─── Consultas ───────────────────────────────────────────────────────────

    def get_balance(self, address: str) -> int:
        """Retorna saldo em satoshis. 0 se não encontrado."""
        if self._conn is None:
            return 0
        row = self._conn.execute(
            "SELECT satoshis FROM addresses WHERE address = ?", (address,)
        ).fetchone()
        return row[0] if row else 0

    # ─── Metadados ───────────────────────────────────────────────────────────

    def get_meta(self, key: str, default: str = "") -> str:
        if self._conn is None:
            return default
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value: str) -> None:
        if self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                (key, value),
            )
            self._conn.commit()

    @property
    def last_updated(self) -> Optional[datetime]:
        ts = self.get_meta("last_updated")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    @property
    def block_height(self) -> int:
        return int(self.get_meta("block_height", "0"))

    @property
    def address_count(self) -> int:
        return int(self.get_meta("address_count", "0"))

    @property
    def source(self) -> str:
        return self.get_meta("source", "—")

    @property
    def db_size_mb(self) -> float:
        if not self.db_path.exists():
            return 0.0
        return self.db_path.stat().st_size / (1024 * 1024)

    # ─── Status ──────────────────────────────────────────────────────────────

    @property
    def exists(self) -> bool:
        return self.db_path.exists()

    @property
    def is_ready(self) -> bool:
        return self._conn is not None and self.address_count > 0

    @property
    def needs_update(self) -> bool:
        lu = self.last_updated
        if lu is None:
            return True
        age_days = (datetime.now(timezone.utc) - lu).days
        return age_days >= _UPDATE_INTERVAL_DAYS

    @property
    def age_days(self) -> int:
        lu = self.last_updated
        if lu is None:
            return 9999
        return (datetime.now(timezone.utc) - lu).days

    @property
    def status(self) -> str:
        """'missing' | 'updating' | 'outdated' | 'ok'"""
        if not self.exists:
            return "missing"
        if not self.is_ready:
            return "missing"
        if self.needs_update:
            return "outdated"
        return "ok"

    # ─── Criação do schema (usado pelo update_utxo.py) ───────────────────────

    @classmethod
    def create(cls, db_path: Path = _DB_PATH) -> "UTXODatabase":
        """Cria um novo banco do zero (apaga o anterior se existir)."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = db_path.with_suffix(".tmp.db")
        if tmp_path.exists():
            tmp_path.unlink()

        conn = sqlite3.connect(str(tmp_path))
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA cache_size=-131072")  # 128 MB durante import
        conn.execute("""
            CREATE TABLE IF NOT EXISTS addresses (
                address TEXT PRIMARY KEY,
                satoshis INTEGER NOT NULL
            ) WITHOUT ROWID
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()

        db = cls(tmp_path)
        db._conn = conn
        return db

    def finalize(self) -> None:
        """Fecha, cria índice e move para o caminho final."""
        if self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.commit()
            self._conn.close()
            self._conn = None

        # Substitui o banco antigo atomicamente
        target = _DB_PATH
        if self.db_path != target:
            if target.exists():
                target.unlink()
            self.db_path.rename(target)
            self.db_path = target

    def batch_insert(self, rows: list[tuple[str, int]]) -> None:
        """Insere/acumula lote de (address, satoshis). Usa UPSERT para somar."""
        if self._conn is None:
            return
        self._conn.executemany(
            """
            INSERT INTO addresses(address, satoshis) VALUES(?, ?)
            ON CONFLICT(address) DO UPDATE SET satoshis = satoshis + excluded.satoshis
            """,
            rows,
        )

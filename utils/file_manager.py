"""Persists found wallets to disk as .txt and .json files."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles
from loguru import logger

from core.wallet import FoundWallet


_TXT_TEMPLATE = """\
═══════════════════════════════════════════════════════════════
  BITCOIN WALLET FOUND — Bitcoin Balance Scanner Pro
═══════════════════════════════════════════════════════════════
  Found at   : {found_at}
  Source     : {source}

━━━━━━━━━━━━━━━━━━━━━  PRIVATE KEY  ━━━━━━━━━━━━━━━━━━━━━━━━
  HEX (raw)         : {private_key_hex}
  WIF (compressed)  : {private_key_wif}
  WIF (uncompressed): {private_key_wif_uncompressed}

━━━━━━━━━━━━━━━━━━━━━  PUBLIC KEY  ━━━━━━━━━━━━━━━━━━━━━━━━━
  Compressed   : {public_key_compressed}
  Uncompressed : {public_key_uncompressed}

━━━━━━━━━━━━━━━━━━━━━  ADDRESSES  ━━━━━━━━━━━━━━━━━━━━━━━━━━
  P2PKH        (Legacy compr): {p2pkh}
  P2PKH        (Uncompressed): {p2pkh_uncompressed}
  P2SH-P2WPKH  (Nested SW)  : {p2sh_p2wpkh}
  P2WPKH       (Native SW)  : {p2wpkh}
  P2WSH        (Witness SH) : {p2wsh}
  P2TR         (Taproot)    : {p2tr}

━━━━━━━━━━━━━━━━━━━━━  BALANCES  ━━━━━━━━━━━━━━━━━━━━━━━━━━━
{balance_lines}
═══════════════════════════════════════════════════════════════
"""

_BALANCE_LINE = (
    "  [{address_type}] {address}\n"
    "    Confirmed   : {confirmed_btc:.8f} BTC  ({confirmed_sat} sat)\n"
    "    Unconfirmed : {unconfirmed_btc:.8f} BTC  ({unconfirmed_sat} sat)\n"
    "    Transactions: {tx_count}\n"
    "    Source      : {source}\n"
)


class FileManager:
    """Handles async writing of found wallets to disk."""

    def __init__(
        self,
        output_dir: str = "found_wallets",
        save_csv: bool = True,
        json_indent: int = 2,
    ) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._save_csv = save_csv
        self._json_indent = json_indent
        self._csv_path = self._dir / "summary.csv"
        self._csv_initialized = False

    async def save(self, found: FoundWallet) -> Optional[Path]:
        """Write .txt and .json files; append to summary CSV.  Returns txt path."""
        ts = found.discovered_at.strftime("%Y%m%d_%H%M%S")
        safe_addr = found.primary_address[:20]
        stem = f"wallet_{ts}_{safe_addr}"

        txt_path = self._dir / f"{stem}.txt"
        json_path = self._dir / f"{stem}.json"

        try:
            await self._write_txt(found, txt_path)
            await self._write_json(found, json_path)
            if self._save_csv:
                await self._append_csv(found)
            logger.info(f"Saved found wallet → {txt_path}")
            return txt_path
        except Exception as exc:
            logger.error(f"Failed to save wallet: {exc}")
            return None

    async def _write_txt(self, found: FoundWallet, path: Path) -> None:
        balance_lines = ""
        sources = set()
        for b in found.balances:
            balance_lines += _BALANCE_LINE.format(
                address_type=b.address_type.upper(),
                address=b.address,
                confirmed_btc=b.confirmed_btc,
                confirmed_sat=b.confirmed_satoshis,
                unconfirmed_btc=b.unconfirmed_btc,
                unconfirmed_sat=b.unconfirmed_satoshis,
                tx_count=b.tx_count,
                source=b.source,
            )
            sources.add(b.source)

        content = _TXT_TEMPLATE.format(
            found_at=found.discovered_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            source=", ".join(sorted(sources)),
            private_key_hex=found.keys.private_key_hex,
            private_key_wif=found.keys.private_key_wif,
            private_key_wif_uncompressed=found.keys.private_key_wif_uncompressed,
            public_key_compressed=found.keys.public_key_compressed,
            public_key_uncompressed=found.keys.public_key_uncompressed,
            p2pkh=found.keys.p2pkh,
            p2pkh_uncompressed=found.keys.p2pkh_uncompressed,
            p2sh_p2wpkh=found.keys.p2sh_p2wpkh,
            p2wpkh=found.keys.p2wpkh,
            p2wsh=found.keys.p2wsh,
            p2tr=found.keys.p2tr,
            balance_lines=balance_lines.rstrip(),
        )
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)

    async def _write_json(self, found: FoundWallet, path: Path) -> None:
        data = {
            "discovered_at": found.discovered_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "private_key": {
                "hex": found.keys.private_key_hex,
                "wif_compressed": found.keys.private_key_wif,
                "wif_uncompressed": found.keys.private_key_wif_uncompressed,
            },
            "public_key": {
                "compressed": found.keys.public_key_compressed,
                "uncompressed": found.keys.public_key_uncompressed,
            },
            "addresses": found.keys.all_addresses,
            "balances": [
                {
                    "address": b.address,
                    "address_type": b.address_type,
                    "confirmed_satoshis": b.confirmed_satoshis,
                    "unconfirmed_satoshis": b.unconfirmed_satoshis,
                    "tx_count": b.tx_count,
                    "source": b.source,
                }
                for b in found.balances
            ],
            "total_confirmed_satoshis": found.total_confirmed_satoshis,
            "total_unconfirmed_satoshis": found.total_unconfirmed_satoshis,
        }
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=self._json_indent, ensure_ascii=False))

    async def _append_csv(self, found: FoundWallet) -> None:
        write_header = not self._csv_path.exists() or not self._csv_initialized
        self._csv_initialized = True

        row = {
            "discovered_at": found.discovered_at.isoformat(),
            "primary_address": found.primary_address,
            "address_type": found.primary_address_type,
            "confirmed_sat": found.total_confirmed_satoshis,
            "unconfirmed_sat": found.total_unconfirmed_satoshis,
            "private_key_wif": found.keys.private_key_wif,
            "p2pkh": found.keys.p2pkh,
            "p2sh_p2wpkh": found.keys.p2sh_p2wpkh,
            "p2wpkh": found.keys.p2wpkh,
            "p2tr": found.keys.p2tr,
        }

        async with aiofiles.open(self._csv_path, "a", encoding="utf-8", newline="") as f:
            # aiofiles doesn't support csv.DictWriter directly — build line manually
            if write_header:
                await f.write(",".join(row.keys()) + "\n")
            await f.write(",".join(str(v) for v in row.values()) + "\n")

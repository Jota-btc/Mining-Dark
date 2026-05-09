#!/usr/bin/env python3
"""
Bitcoin Balance Scanner Pro — Entry point.

Usage examples:
  python3 main.py scan
  python3 main.py scan --workers 20
  python3 main.py scan --mode hd
  python3 main.py check 1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf
  python3 main.py found
  python3 main.py keygen
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich import box

from config.settings import load_settings, Settings
from utils.logger import setup_logger

app = typer.Typer(
    name="bitcoin-scanner",
    help="Bitcoin Balance Scanner Pro — educational key-space research tool.",
    add_completion=False,
)
console = Console()


def _load(config: str) -> Settings:
    settings = load_settings(config)
    setup_logger(
        level=settings.logging.level,
        logs_dir=settings.logging.logs_dir,
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
    )
    return settings


@app.command()
def scan(
    config: str = typer.Option("config.yaml", "--config", "-c", help="Path to config.yaml"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="random | hd"),
    workers: Optional[int] = typer.Option(None, "--workers", "-w", help="Parallel worker count"),
) -> None:
    """Start the balance scanner (Ctrl+C to stop gracefully)."""
    from ui.setup_menu import run_setup

    settings = _load(config)

    if not any([mode, workers]):
        settings = run_setup(settings)
    else:
        if mode:
            settings.scanner.mode = mode
        if workers:
            settings.scanner.workers = workers

    try:
        asyncio.run(_run_scan(settings))
    except KeyboardInterrupt:
        console.print("\n[yellow]Scan interrompido.[/yellow]")


@app.command()
def check(
    address: str = typer.Argument(..., help="Bitcoin address to check"),
    config: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """Check balance of a single Bitcoin address in the local UTXO database."""
    _load(config)
    from utils.utxo_db import UTXODatabase

    db = UTXODatabase()
    db.open()

    if not db.is_ready:
        console.print(
            "[red]Banco UTXO local não encontrado.[/red]\n"
            "Execute: [cyan]python3 tools/update_utxo.py[/cyan]"
        )
        raise typer.Exit(1)

    addr_type = _guess_address_type(address)
    satoshis = db.get_balance(address)
    db.close()

    if satoshis > 0:
        console.print(
            f"[bold green]Saldo encontrado![/bold green] "
            f"[cyan]{address}[/cyan] ({addr_type})\n"
            f"  Confirmed: [bold green]{satoshis / 1e8:.8f} BTC[/bold green]  ({satoshis:,} sat)"
        )
    else:
        console.print(
            f"[dim]Sem saldo.[/dim] [cyan]{address}[/cyan] ({addr_type})\n"
            f"  Confirmed: 0.00000000 BTC"
        )


@app.command()
def found(
    output_dir: str = typer.Option("found_wallets", "--dir", "-d", help="found_wallets directory"),
) -> None:
    """List all previously found wallets."""
    _list_found_wallets(output_dir)


@app.command()
def keygen(
    count: int = typer.Option(1, "--count", "-n", help="Number of wallets to generate"),
) -> None:
    """Generate and display sample Bitcoin wallets (no balance check)."""
    from core.key_generator import KeyGenerator
    from core.address_generator import AddressGenerator

    table = Table(title="Generated Wallets", box=box.ROUNDED, show_lines=True)
    table.add_column("P2PKH", style="cyan")
    table.add_column("P2WPKH", style="green")
    table.add_column("P2TR", style="magenta")
    table.add_column("WIF", style="dim", no_wrap=False, max_width=55)

    for _ in range(count):
        pk = KeyGenerator.generate_private_key()
        wallet = AddressGenerator.from_private_key(pk)
        table.add_row(wallet.p2pkh, wallet.p2wpkh, wallet.p2tr, wallet.private_key_wif)

    console.print(table)
    if count > 1:
        console.print(f"\nGenerated {count} wallets.")


async def _run_scan(settings: Settings) -> None:
    from checkers.balance_checker import BalanceChecker, ScanStats
    from core.wallet import WalletKeys, FoundWallet
    from generators.random_generator import RandomKeyGenerator
    from generators.hd_generator import HDWalletGenerator
    from ui.dashboard import Dashboard
    from utils.file_manager import FileManager
    from utils.utxo_db import UTXODatabase

    key_queue: asyncio.Queue[WalletKeys] = asyncio.Queue(maxsize=settings.scanner.queue_size)
    found_queue: asyncio.Queue[FoundWallet] = asyncio.Queue()
    stats = ScanStats()
    file_manager = FileManager(
        output_dir=settings.output.found_wallets_dir,
        save_csv=settings.output.save_csv,
        json_indent=settings.output.json_indent,
    )

    utxo_db = UTXODatabase()
    utxo_db.open()

    if not utxo_db.is_ready:
        console.print(
            "[red]Banco UTXO local não encontrado.[/red]\n"
            "Execute [cyan]python3 tools/update_utxo.py[/cyan] para baixar o banco antes de escanear."
        )
        raise typer.Exit(1)

    if utxo_db.needs_update:
        console.print(
            f"[yellow]Banco com mais de 30 dias — considere atualizar:[/yellow] "
            f"[cyan]python3 tools/update_utxo.py[/cyan]"
        )

    console.print(
        f"[green]UTXO local carregado[/green] — "
        f"{utxo_db.address_count:,} endereços indexados "
        f"(atualizado há {utxo_db.age_days}d)"
    )

    dashboard = Dashboard(
        stats=stats,
        utxo_db=utxo_db,
        recent_rows=settings.ui.recent_table_rows,
        refresh_fps=settings.ui.refresh_fps,
    )

    checker = BalanceChecker(
        settings=settings,
        key_queue=key_queue,
        found_queue=found_queue,
        stats=stats,
        utxo_db=utxo_db,
        on_wallet_found=dashboard.record_found,
    )

    def on_key_generated(wallet: WalletKeys) -> None:
        dashboard.record_key(wallet)

    if settings.scanner.mode == "hd":
        generator: RandomKeyGenerator | HDWalletGenerator = HDWalletGenerator(
            queue=key_queue,
            derivation_paths=settings.hd_wallet.derivation_paths,
            child_count=settings.hd_wallet.child_count,
            stats=stats,
            on_key_generated=on_key_generated,
        )
    else:
        generator = RandomKeyGenerator(
            queue=key_queue,
            stats=stats,
            on_key_generated=on_key_generated,
        )

    async def persist_found() -> None:
        while True:
            fw = await found_queue.get()
            await file_manager.save(fw)
            found_queue.task_done()

    stop_event = asyncio.Event()

    def _handle_sigint(*_: object) -> None:
        stop_event.set()
        generator.stop()
        checker.stop()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, _handle_sigint)
    loop.add_signal_handler(signal.SIGTERM, _handle_sigint)

    tasks = [
        asyncio.create_task(generator.run(), name="generator"),
        asyncio.create_task(checker.run(settings.scanner.workers), name="checker"),
        asyncio.create_task(persist_found(), name="persist"),
        asyncio.create_task(dashboard.run(), name="dashboard"),
    ]

    await stop_event.wait()

    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    utxo_db.close()

    console.print(
        f"\n[bold green]Scan encerrado.[/bold green] "
        f"Keys geradas: [cyan]{stats.keys_generated:,}[/cyan] | "
        f"Endereços verificados: [cyan]{stats.addresses_checked:,}[/cyan] | "
        f"Wallets found: [bold green]{stats.wallets_found}[/bold green]"
    )


def _guess_address_type(address: str) -> str:
    if address.startswith("1"):
        return "p2pkh"
    if address.startswith("3"):
        return "p2sh_p2wpkh"
    if address.startswith("bc1p"):
        return "p2tr"
    if address.startswith("bc1q") and len(address) == 42:
        return "p2wpkh"
    if address.startswith("bc1q") and len(address) == 62:
        return "p2wsh"
    return "unknown"


def _list_found_wallets(output_dir: str) -> None:
    import json

    path = Path(output_dir)
    json_files = sorted(path.glob("wallet_*.json")) if path.exists() else []

    if not json_files:
        console.print(f"[dim]No wallets found in {output_dir}/[/dim]")
        return

    table = Table(title=f"Found Wallets ({output_dir})", box=box.ROUNDED)
    table.add_column("File", style="dim", no_wrap=True)
    table.add_column("Discovered At")
    table.add_column("Address")
    table.add_column("Confirmed BTC", justify="right", style="bold green")

    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            table.add_row(
                jf.name,
                data.get("discovered_at", "?"),
                next(iter(data.get("addresses", {}).values()), "?"),
                f"{data.get('total_confirmed_satoshis', 0) / 1e8:.8f}",
            )
        except Exception:
            table.add_row(jf.name, "?", "?", "?")

    console.print(table)
    console.print(f"\nTotal files: [cyan]{len(json_files)}[/cyan]")


if __name__ == "__main__":
    app()

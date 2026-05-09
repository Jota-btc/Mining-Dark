#!/usr/bin/env python3
"""
Importa o UTXO set do Bitcoin para o banco SQLite local.

Fonte: Bitcoin Core local + bitcoin-utxo-dump
  Setup:  bash tools/setup_bitcoin_core.sh
  Requer: Bitcoin Core sincronizado + bitcoin-utxo-dump instalado

Uso:
  python3 tools/update_utxo.py --from-node          # exporta do nó local
  python3 tools/update_utxo.py --from-node --force  # força mesmo se em dia
  python3 tools/update_utxo.py --file dump.csv      # importa arquivo CSV local
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.panel import Panel
from rich import box

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.utxo_db import UTXODatabase, _DB_PATH

app = typer.Typer(add_completion=False)
console = Console()

_BATCH_SIZE  = 50_000
_TMP_CSV     = _DB_PATH.parent / "utxo_dump_tmp.csv"
_BITCOIN_DIR = Path.home() / ".bitcoin"


# ─── Import ──────────────────────────────────────────────────────────────────

def _parse_csv(src: Path, db: UTXODatabase, progress: Progress, task_id) -> int:
    """Importa CSV do bitcoin-utxo-dump — colunas: address,amount (satoshis por UTXO)."""
    total = 0
    batch: list[tuple[str, int]] = []

    with open(src, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            address = row.get("address", "").strip()
            if not address:
                continue
            try:
                satoshis = int(row.get("amount", 0))
            except ValueError:
                continue
            if satoshis <= 0:
                continue

            batch.append((address, satoshis))
            total += 1

            if len(batch) >= _BATCH_SIZE:
                db.batch_insert(batch)
                db._conn.commit()
                batch.clear()
                progress.update(task_id, description=f"[cyan]Importando... {total:,} UTXOs")

    if batch:
        db.batch_insert(batch)
        db._conn.commit()

    return total


def _do_import(src: Path, source_label: str, block_height: int = 0) -> None:
    if not src.exists() or src.stat().st_size == 0:
        raise RuntimeError(f"Arquivo CSV inválido ou vazio: {src}")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(), TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console, expand=True,
    )

    with progress:
        task = progress.add_task("[cyan]Importando para SQLite...", total=None)
        db = UTXODatabase.create(_DB_PATH)
        _parse_csv(src, db, progress, task)
        progress.update(task, description="[cyan]Contando endereços únicos...")
        unique_count = db._conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0]
        progress.update(task, description="[green]Import concluído")

    now = datetime.now(timezone.utc)
    db.set_meta("last_updated", now.isoformat())
    db.set_meta("source_date", now.strftime("%Y-%m-%d"))
    db.set_meta("source", source_label)
    db.set_meta("address_count", str(unique_count))
    if block_height:
        db.set_meta("block_height", str(block_height))
    db.finalize()

    console.print(Panel(
        f"[bold green]UTXO set importado com sucesso![/bold green]\n\n"
        f"  Endereços indexados : [cyan]{unique_count:,}[/cyan]\n"
        f"  Fonte               : [cyan]{source_label}[/cyan]\n"
        f"  Banco salvo em      : [cyan]{_DB_PATH}[/cyan]\n"
        f"  Tamanho             : [cyan]{_DB_PATH.stat().st_size / 1e9:.2f} GB[/cyan]",
        box=box.ROUNDED,
    ))


# ─── Bitcoin Core ─────────────────────────────────────────────────────────────

def _check_bitcoin_core() -> dict:
    if not shutil.which("bitcoin-cli"):
        return {"error": "bitcoin-cli não encontrado. Execute: bash tools/setup_bitcoin_core.sh"}
    if not shutil.which("bitcoin-utxo-dump"):
        return {"error": "bitcoin-utxo-dump não encontrado. Execute: bash tools/setup_bitcoin_core.sh"}

    try:
        result = subprocess.run(
            ["bitcoin-cli", "getblockchaininfo"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"error": f"Bitcoin Core não está rodando.\nInicie com: bitcoind"}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "Bitcoin Core não respondeu (timeout)."}
    except Exception as e:
        return {"error": str(e)}


def _run_utxo_dump(output_path: Path) -> None:
    cmd = ["bitcoin-utxo-dump", "-nowarnings", "-f", "address,amount", "-o", str(output_path)]

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    )
    with progress:
        task = progress.add_task("[cyan]Exportando UTXO set do Bitcoin Core...", total=None)
        result = subprocess.run(cmd, capture_output=True, text=True)
        progress.update(task, description="[green]Export concluído")

    if result.returncode != 0:
        raise RuntimeError(f"bitcoin-utxo-dump falhou:\n{result.stderr}")

    console.print(f"  [dim]CSV gerado: {output_path.name} ({output_path.stat().st_size / 1e6:.0f} MB)[/dim]")


# ─── Comando ──────────────────────────────────────────────────────────────────

@app.command()
def update(
    from_node: bool = typer.Option(False, "--from-node", "-n", help="Exporta UTXO set do Bitcoin Core local"),
    force: bool     = typer.Option(False, "--force", "-f",     help="Força re-import mesmo se já estiver em dia"),
    file: Optional[Path] = typer.Option(None, "--file",        help="Importa de arquivo CSV local"),
) -> None:
    """
    Importa o UTXO set do Bitcoin para o banco local.

    Requer Bitcoin Core sincronizado + bitcoin-utxo-dump.
    Setup: bash tools/setup_bitcoin_core.sh
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Verifica se já está em dia
    db_check = UTXODatabase()
    db_check.open()
    if not force and not db_check.needs_update and db_check.is_ready:
        console.print(
            f"[green]UTXO já está atualizado[/green] "
            f"(há {db_check.age_days} dias). Use --force para forçar."
        )
        db_check.close()
        return
    db_check.close()

    # Arquivo CSV local
    if file:
        _do_import(file, source_label="local_file")
        return


    # Bitcoin Core
    if not from_node:
        console.print(Panel(
            "Especifique a fonte do UTXO set:\n\n"
            "  [cyan]--from-node[/cyan]   exporta do Bitcoin Core local\n"
            "  [cyan]--file CSV[/cyan]    importa de arquivo CSV\n\n"
            "Para configurar o Bitcoin Core:\n"
            "  [cyan]bash tools/setup_bitcoin_core.sh[/cyan]",
            box=box.ROUNDED,
            title="[yellow]Fonte não especificada[/yellow]",
        ))
        raise typer.Exit(1)

    console.print("[bold cyan]Verificando Bitcoin Core...[/bold cyan]")
    info = _check_bitcoin_core()

    if "error" in info:
        console.print(Panel(
            f"[bold red]{info['error']}[/bold red]",
            box=box.ROUNDED, title="[red]Erro[/red]",
        ))
        raise typer.Exit(1)

    progress_sync = info.get("verificationprogress", 0)
    blocks        = info.get("blocks", 0)
    headers       = info.get("headers", 0)
    chain         = info.get("chain", "?")

    console.print(
        f"  Rede        : [cyan]{chain}[/cyan]\n"
        f"  Blocos      : [cyan]{blocks:,}[/cyan] / {headers:,}\n"
        f"  Sincronizado: [cyan]{progress_sync * 100:.2f}%[/cyan]"
    )

    if progress_sync < 0.9999:
        console.print(Panel(
            f"[bold yellow]Bitcoin Core ainda está sincronizando.[/bold yellow]\n\n"
            f"  Progresso : [cyan]{progress_sync * 100:.2f}%[/cyan]\n"
            f"  Blocos    : [cyan]{blocks:,} / {headers:,}[/cyan]\n\n"
            "Aguarde a sincronização completa e execute novamente.\n"
            "[dim]watch -n 60 'bitcoin-cli getblockchaininfo | grep verificationprogress'[/dim]",
            box=box.ROUNDED, title="[yellow]Sincronização incompleta[/yellow]",
        ))
        raise typer.Exit(1)

    console.print("  [green]Sincronizado! Iniciando export...[/green]\n")

    try:
        _run_utxo_dump(_TMP_CSV)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    try:
        _do_import(_TMP_CSV, source_label="bitcoin_core", block_height=blocks)
    finally:
        _TMP_CSV.unlink(missing_ok=True)


if __name__ == "__main__":
    app()

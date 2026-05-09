"""Interactive setup menu displayed before scan starts."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box

from config.settings import Settings
from utils.utxo_db import UTXODatabase

console = Console()

_BANNER = """
[bold cyan]███╗   ███╗██╗███╗   ██╗██╗███╗   ██╗ ██████╗ [/bold cyan]
[bold cyan]████╗ ████║██║████╗  ██║██║████╗  ██║██╔════╝ [/bold cyan]
[bold cyan]██╔████╔██║██║██╔██╗ ██║██║██╔██╗ ██║██║  ███╗[/bold cyan]
[bold cyan]██║╚██╔╝██║██║██║╚██╗██║██║██║╚██╗██║██║   ██║[/bold cyan]
[bold cyan]██║ ╚═╝ ██║██║██║ ╚████║██║██║ ╚████║╚██████╔╝[/bold cyan]
[bold cyan]╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝ ╚═════╝ [/bold cyan]
[bold cyan]██████╗  █████╗ ██████╗ ██╗  ██╗[/bold cyan]
[bold cyan]██╔══██╗██╔══██╗██╔══██╗██║ ██╔╝[/bold cyan]
[bold cyan]██║  ██║███████║██████╔╝█████╔╝ [/bold cyan]
[bold cyan]██║  ██║██╔══██║██╔══██╗██╔═██╗ [/bold cyan]
[bold cyan]██████╔╝██║  ██║██║  ██║██║  ██╗[/bold cyan]
[bold cyan]╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝[/bold cyan]
[bold orange1]₿itcoin[/bold orange1]         [bold white]Balance Scanner Pro[/bold white]  [dim]by: J.[/dim]
"""

_ALL_ADDRESS_TYPES = ["p2pkh", "p2pkh_uncompressed", "p2sh_p2wpkh", "p2wpkh", "p2wsh", "p2tr"]

# ── Translations ──────────────────────────────────────────────────────────────

_STRINGS: dict[str, dict[str, str]] = {
    "pt": {
        # Language selection
        "lang_prompt":          "  Idioma / Language",
        "lang_pt":              "[bold]  [1][/bold] [cyan]Português[/cyan]",
        "lang_en":              "[bold]  [2][/bold] [cyan]English[/cyan]",

        # Section rules
        "rule_utxo":            "  Banco UTXO  ",
        "rule_config":          "  Configuração  ",
        "rule_hd":              "  HD Wallet  ",

        # UTXO panel
        "utxo_panel_title":     "  Banco UTXO Local  ",
        "utxo_status":          "Status",
        "utxo_addresses":       "Endereços indexados",
        "utxo_updated":         "Última atualização",
        "utxo_size":            "Tamanho",
        "utxo_source":          "Fonte",
        "utxo_block":           "Bloco",
        "utxo_ready":           "[bold green]PRONTO[/bold green]",
        "utxo_outdated":        "[bold yellow]DESATUALIZADO[/bold yellow]",
        "utxo_missing":         "[bold red]NÃO ENCONTRADO[/bold red]",
        "utxo_run_cmd":         "[dim]Execute:[/dim] [cyan]python3 tools/update_utxo.py --from-node[/cyan]",
        "utxo_days_ago":        "d atrás",
        "utxo_missing_msg": (
            "  [red]O banco UTXO é obrigatório para iniciar o scan.[/red]\n"
            "  Aguarde a sincronização do nó e execute:\n"
            "  [cyan]python3 tools/update_utxo.py --from-node[/cyan]\n"
        ),
        "utxo_outdated_msg": (
            "  [yellow]O banco está desatualizado (mais de 30 dias).[/yellow]\n"
            "  Recomendado atualizar antes de continuar:\n"
            "  [cyan]python3 tools/update_utxo.py --from-node[/cyan]\n"
        ),

        # Prompts
        "confirm_continue":     "  Continuar para configuração?",
        "confirm_start":        "  [bold green]Iniciar scan?[/bold green]",
        "cancelled":            "\n  Cancelado.\n",

        # Mode selection
        "mode_random":          "[bold]  [1][/bold] Modo [cyan]Random[/cyan]   — gera chaves privadas aleatórias",
        "mode_hd":              "[bold]  [2][/bold] Modo [cyan]HD Wallet[/cyan] — deriva chaves via BIP32/44/84/86 (mnemônico)",
        "mode_prompt":          "  Escolha o modo",

        # Workers
        "workers_hint": (
            "  Workers = tarefas assíncronas paralelas verificando saldo.\n"
            "  [dim]Recomendado: 5–20. Mais workers = mais consultas ao banco por segundo.[/dim]"
        ),
        "workers_prompt":       "  Número de workers",

        # Child count
        "child_hint": (
            "  Child count = endereços derivados por mnemônica.\n"
            "  [dim]Carteiras reais usam gap limit de 20 — cobre índices 0 a 19.[/dim]\n"
            "  [dim]Mais filhas = maior cobertura, porém mais lento.[/dim]"
        ),
        "child_prompt":         "  Child count",

        # Summary
        "summary_config":       "Configuração",
        "summary_addresses":    "Tipos de endereço verificados",
        "summary_mode":         "Modo",
        "summary_workers":      "Workers",
        "summary_child":        "Child count",
        "summary_keys_per_seed":"chaves/mnemônica",

        # Address type descriptions
        "addr_p2pkh":           "Legacy comprimida",
        "addr_p2pkh_u":         "Legacy não comprimida",
        "addr_p2pkh_u_note":    "(era Satoshi)",
        "addr_p2sh":            "Nested SegWit",
        "addr_p2wpkh":          "Native SegWit",
        "addr_p2wsh":           "Witness Script Hash",
        "addr_p2tr":            "Taproot",
    },

    "en": {
        # Language selection
        "lang_prompt":          "  Idioma / Language",
        "lang_pt":              "[bold]  [1][/bold] [cyan]Português[/cyan]",
        "lang_en":              "[bold]  [2][/bold] [cyan]English[/cyan]",

        # Section rules
        "rule_utxo":            "  UTXO Database  ",
        "rule_config":          "  Configuration  ",
        "rule_hd":              "  HD Wallet  ",

        # UTXO panel
        "utxo_panel_title":     "  Local UTXO Database  ",
        "utxo_status":          "Status",
        "utxo_addresses":       "Indexed addresses",
        "utxo_updated":         "Last updated",
        "utxo_size":            "Size",
        "utxo_source":          "Source",
        "utxo_block":           "Block",
        "utxo_ready":           "[bold green]READY[/bold green]",
        "utxo_outdated":        "[bold yellow]OUTDATED[/bold yellow]",
        "utxo_missing":         "[bold red]NOT FOUND[/bold red]",
        "utxo_run_cmd":         "[dim]Run:[/dim] [cyan]python3 tools/update_utxo.py --from-node[/cyan]",
        "utxo_days_ago":        "d ago",
        "utxo_missing_msg": (
            "  [red]The UTXO database is required to start scanning.[/red]\n"
            "  Wait for node sync and run:\n"
            "  [cyan]python3 tools/update_utxo.py --from-node[/cyan]\n"
        ),
        "utxo_outdated_msg": (
            "  [yellow]Database is outdated (more than 30 days old).[/yellow]\n"
            "  Recommended to update before continuing:\n"
            "  [cyan]python3 tools/update_utxo.py --from-node[/cyan]\n"
        ),

        # Prompts
        "confirm_continue":     "  Continue to configuration?",
        "confirm_start":        "  [bold green]Start scan?[/bold green]",
        "cancelled":            "\n  Cancelled.\n",

        # Mode selection
        "mode_random":          "[bold]  [1][/bold] [cyan]Random[/cyan] mode   — generates random private keys",
        "mode_hd":              "[bold]  [2][/bold] [cyan]HD Wallet[/cyan] mode — derives keys via BIP32/44/84/86 (mnemonic)",
        "mode_prompt":          "  Choose mode",

        # Workers
        "workers_hint": (
            "  Workers = async tasks checking balances in parallel.\n"
            "  [dim]Recommended: 5–20. More workers = more database queries per second.[/dim]"
        ),
        "workers_prompt":       "  Number of workers",

        # Child count
        "child_hint": (
            "  Child count = addresses derived per mnemonic.\n"
            "  [dim]Real wallets use a gap limit of 20 — covers indices 0 to 19.[/dim]\n"
            "  [dim]More children = wider coverage, but slower.[/dim]"
        ),
        "child_prompt":         "  Child count",

        # Summary
        "summary_config":       "Configuration",
        "summary_addresses":    "Address types checked",
        "summary_mode":         "Mode",
        "summary_workers":      "Workers",
        "summary_child":        "Child count",
        "summary_keys_per_seed":"keys/mnemonic",

        # Address type descriptions
        "addr_p2pkh":           "Legacy compressed",
        "addr_p2pkh_u":         "Legacy uncompressed",
        "addr_p2pkh_u_note":    "(Satoshi era)",
        "addr_p2sh":            "Nested SegWit",
        "addr_p2wpkh":          "Native SegWit",
        "addr_p2wsh":           "Witness Script Hash",
        "addr_p2tr":            "Taproot",
    },
}

# Active translation table — set once by _choose_language()
_T: dict[str, str] = _STRINGS["pt"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    console.print(_BANNER, justify="center")
    console.rule(style="cyan dim")
    console.print()


def _choose_language() -> None:
    global _T
    console.print(_STRINGS["pt"]["lang_pt"])
    console.print(_STRINGS["en"]["lang_en"])
    console.print()
    choice = Prompt.ask(
        _STRINGS["pt"]["lang_prompt"],
        choices=["1", "2"],
        default="1",
    )
    _T = _STRINGS["pt"] if choice == "1" else _STRINGS["en"]
    console.print()


def _show_utxo_status() -> bool:
    """Display UTXO database status. Returns True if the database is ready."""
    db = UTXODatabase()
    db.open()

    status   = db.status
    is_ready = db.is_ready

    if status == "missing":
        dot        = "[red]●[/red]"
        status_txt = _T["utxo_missing"]
        border     = "red"
    elif status == "outdated":
        dot        = "[yellow]●[/yellow]"
        status_txt = _T["utxo_outdated"]
        border     = "yellow"
    else:
        dot        = "[bold green]●[/bold green]"
        status_txt = _T["utxo_ready"]
        border     = "green"

    grid = Table.grid(padding=(0, 3))
    grid.add_column(style="dim", no_wrap=True)
    grid.add_column(no_wrap=True)

    grid.add_row(_T["utxo_status"], Text.from_markup(f"{dot}  {status_txt}"))

    if is_ready:
        lu  = db.last_updated
        age = db.age_days
        age_txt = (
            f"[green]{age}{_T['utxo_days_ago']}[/green]" if age < 7
            else f"[yellow]{age}{_T['utxo_days_ago']}[/yellow]" if age < 30
            else f"[red]{age}{_T['utxo_days_ago']}[/red]"
        )
        grid.add_row(_T["utxo_addresses"], f"[bold cyan]{db.address_count:,}[/bold cyan]")
        grid.add_row(_T["utxo_updated"], Text.from_markup(
            lu.strftime("%d/%m/%Y %H:%M") + f"  [dim]({age_txt})[/dim]" if lu else "—"
        ))
        grid.add_row(_T["utxo_size"],   f"{db.db_size_mb:,.1f} MB")
        grid.add_row(_T["utxo_source"], db.source if db.source != "—" else "[dim]—[/dim]")
        if db.block_height:
            grid.add_row(_T["utxo_block"], f"{db.block_height:,}")
    else:
        grid.add_row("", Text.from_markup(_T["utxo_run_cmd"]))

    db.close()

    console.print(Panel(
        grid,
        title=f"[bold {border}]{_T['utxo_panel_title']}[/bold {border}]",
        border_style=border,
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    console.print()

    if status == "missing":
        console.print(_T["utxo_missing_msg"])
        return False

    if status == "outdated":
        console.print(_T["utxo_outdated_msg"])

    return is_ready


def _choose_mode() -> str:
    console.print(_T["mode_random"])
    console.print(_T["mode_hd"])
    console.print()
    choice = Prompt.ask(_T["mode_prompt"], choices=["1", "2"], default="1")
    return "random" if choice == "1" else "hd"


def _choose_workers() -> int:
    console.print()
    console.print(_T["workers_hint"])
    console.print()
    return IntPrompt.ask(_T["workers_prompt"], default=10)


def _choose_child_count() -> int:
    console.print()
    console.print(_T["child_hint"])
    console.print()
    return IntPrompt.ask(_T["child_prompt"], default=20)


def _show_summary(mode: str, workers: int, child_count: int | None = None) -> None:
    console.print()

    addr_table = Table(box=None, show_header=False, padding=(0, 2))
    addr_table.add_column(style="cyan", no_wrap=True)
    addr_table.add_column(no_wrap=True)
    addr_table.add_column(style="dim", no_wrap=True)
    addr_table.add_row("P2PKH",        _T["addr_p2pkh"],   "1…")
    addr_table.add_row("P2PKH uncomp", _T["addr_p2pkh_u"], f"1…  {_T['addr_p2pkh_u_note']}")
    addr_table.add_row("P2SH-P2WPKH", _T["addr_p2sh"],    "3…")
    addr_table.add_row("P2WPKH",       _T["addr_p2wpkh"],  "bc1q… (42)")
    addr_table.add_row("P2WSH",        _T["addr_p2wsh"],   "bc1q… (62)")
    addr_table.add_row("P2TR",         _T["addr_p2tr"],    "bc1p…")

    config_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    config_table.add_column(style="dim", no_wrap=True)
    config_table.add_column(style="bold yellow")
    config_table.add_row(_T["summary_mode"],    mode.upper())
    config_table.add_row(_T["summary_workers"], str(workers))
    if child_count is not None:
        keys_per_seed = child_count * 4
        config_table.add_row(
            _T["summary_child"],
            f"{child_count}  [dim]({keys_per_seed} {_T['summary_keys_per_seed']})[/dim]",
        )

    console.print(Columns(
        [
            Panel(
                config_table,
                title=f"[bold]{_T['summary_config']}[/bold]",
                box=box.ROUNDED,
                padding=(1, 2),
            ),
            Panel(
                addr_table,
                title=f"[bold]{_T['summary_addresses']}[/bold]",
                box=box.ROUNDED,
                padding=(1, 2),
            ),
        ],
        expand=True,
    ))
    console.print()


# ── Entry point ───────────────────────────────────────────────────────────────

def run_setup(settings: Settings) -> Settings:
    """Display interactive setup menu and return updated Settings."""
    console.clear()
    _print_banner()

    _choose_language()

    console.rule(f"[bold cyan]{_T['rule_utxo']}[/bold cyan]", style="cyan dim")
    console.print()

    if not _show_utxo_status():
        raise SystemExit(1)

    if not Confirm.ask(_T["confirm_continue"], default=True):
        console.print(_T["cancelled"])
        raise SystemExit(0)

    console.print()
    console.rule(f"[bold cyan]{_T['rule_config']}[/bold cyan]", style="cyan dim")
    console.print()

    mode    = _choose_mode()
    workers = _choose_workers()

    child_count = None
    if mode == "hd":
        console.print()
        console.rule(f"[bold cyan]{_T['rule_hd']}[/bold cyan]", style="cyan dim")
        child_count = _choose_child_count()

    _show_summary(mode, workers, child_count)

    if not Confirm.ask(_T["confirm_start"], default=True):
        console.print(_T["cancelled"])
        raise SystemExit(0)

    settings.scanner.mode         = mode
    settings.scanner.workers      = workers
    settings.scanner.address_types = _ALL_ADDRESS_TYPES
    if child_count is not None:
        settings.hd_wallet.child_count = child_count

    console.print()
    console.rule(style="cyan dim")
    console.print()

    return settings

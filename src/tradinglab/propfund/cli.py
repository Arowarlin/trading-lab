"""``lab propfund``: estado, matriz de firmas, protección y router en dry-run."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from . import protected
from .console import payload
from .registry import load_registry
from .router import Signal, log_decisions, route

app = typer.Typer(
    no_args_is_help=True,
    help="Prop Fund multiempresa (CFD + Futures): firmas, cuentas, protección y router (dry-run).",
)
console = Console()

_PERM_STYLE = {
    "full": "green", "conditional": "cyan", "semi_auto": "yellow",
    "manual_only": "yellow", "unknown": "dim", "prohibited": "red",
}


@app.command("status")
def status() -> None:
    """Resumen: firmas, cuentas, estrategias, asignaciones y protección."""
    data = payload()
    if not data["ok"]:
        console.print(f"[red]Registro inválido:[/red] {data['error']}")
        raise typer.Exit(1)
    s = data["summary"]
    console.print(
        f"[bold]Prop Fund[/bold] · modo {s['mode']} · firmas {s['firms']} "
        f"(CFD {s['firms_cfd']} / Futures {s['firms_futures']}) · cuentas {s['accounts']} "
        f"({s['accounts_real']} reales, {s['accounts_template']} plantillas) · estrategias "
        f"{s['strategies']} ({s['strategies_protected']} protegidas) · asignaciones "
        f"{s['assignments_enabled']}/{s['assignments']} activas"
    )
    prot = data["protection"]
    color = "green" if prot["ok"] else "red"
    console.print(f"Componentes protegidos: [{color}]{prot['status']}[/{color}]")
    for warning in data["warnings"]:
        console.print(f"[yellow]Aviso:[/yellow] {warning}")


@app.command("firms")
def firms(market: str = typer.Option(None, "--market", help="cfd | futures")) -> None:
    """Matriz de empresas y permisos de automatización."""
    data = payload()
    t = Table(title="Matriz de firmas")
    for col in ("Firma", "Mercado", "Automatización", "Verificación", "Órdenes auto", "Cuentas", "Reglas v."):
        t.add_column(col)
    for f in data["firms"]:
        if market and f["market"] != market:
            continue
        perm = f["automation"]["permission"]
        t.add_row(
            f["name"] + (" 🔒" if f["protected"] else ""),
            f["market"].upper(),
            f"[{_PERM_STYLE.get(perm, 'white')}]{perm}[/]",
            f["automation"]["status"],
            "sí" if f["automation"]["auto_orders"] else "no",
            ", ".join(f["accounts"]) or "—",
            f["rules_version"],
        )
    console.print(t)


@app.command("accounts")
def accounts() -> None:
    """Cuentas registradas y su estado de conexión."""
    data = payload()
    t = Table(title="Cuentas Prop Fund")
    for col in ("Id", "Firma", "Mercado", "Fase", "Tamaño", "Estado", "Tipo", "Instrumentos"):
        t.add_column(col)
    for a in data["accounts"]:
        kind = "protegida" if a["protected"] else ("plantilla" if a["template"] else "real")
        t.add_row(a["id"], a["firm"], a["market"].upper(), a["phase"], f"{a['size']:,.0f}",
                  a["state"], kind, ", ".join(a["instruments"]))
    console.print(t)


@app.command("verify")
def verify() -> None:
    """Comprueba los hashes SHA-256 de los componentes protegidos."""
    report = protected.verify()
    for group, info in report["groups"].items():
        mark = "[green]OK[/green]" if info["ok"] else "[red]ALTERADO[/red]"
        console.print(f"{mark} {group} · {info['files']} archivos · {info['description']}")
        for issue in info["issues"]:
            console.print(f"    {issue['kind']}: {issue['path']}")
    if not report["ok"]:
        raise typer.Exit(1)


@app.command("freeze")
def freeze(
    approved_by_operator: bool = typer.Option(
        False, "--approved-by-operator", help="Obligatorio: el operador aprueba re-congelar."
    ),
) -> None:
    """Re-congela el manifiesto de protegidos (solo tras aprobación humana)."""
    if not approved_by_operator:
        console.print("[red]Re-congelar exige --approved-by-operator.[/red]")
        raise typer.Exit(2)
    path = protected.write_manifest()
    console.print(f"Manifiesto escrito en {path}")


@app.command("affected")
def affected(firm: str = typer.Option(..., "--firm"), program: str = typer.Option(None, "--program")) -> None:
    """Cuentas afectadas por un cambio de reglas de una firma/programa."""
    reg = load_registry()
    console.print(", ".join(reg.affected_accounts(firm, program)) or "Ninguna")


@app.command("route")
def route_cmd(
    strategy: str = typer.Option(..., "--strategy"),
    symbol: str = typer.Option(..., "--symbol"),
    side: str = typer.Option(..., "--side", help="long | short"),
    entry: float = typer.Option(..., "--entry"),
    stop: float = typer.Option(..., "--stop"),
    include_disabled: bool = typer.Option(False, "--include-disabled"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Simula una señal por el router (dry-run, sin órdenes) y registra la decisión."""
    reg = load_registry()
    signal = Signal(strategy, symbol, side, entry, stop)
    decisions = route(signal, reg, snapshots={}, include_disabled=include_disabled)
    log_decisions(signal, decisions)
    if as_json:
        console.print_json(json.dumps([d.as_dict() for d in decisions], default=str))
        return
    t = Table(title=f"Router · {strategy} · {symbol} {side}")
    for col in ("Asignación", "Cuenta", "Firma", "Decisión", "Motivo"):
        t.add_column(col)
    for d in decisions:
        last = next((s for s in reversed(d.steps) if not s["ok"]), None)
        t.add_row(d.assignment, d.account, d.firm, d.decision.value,
                  "; ".join(last["reasons"]) if last else "—")
    console.print(t)

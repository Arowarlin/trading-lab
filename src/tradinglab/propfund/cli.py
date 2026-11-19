"""``lab propfund``: estado, matriz de firmas, protección y router en dry-run."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from . import protected
from .console import payload
from .measure import sync_spreads as sync_spreads_report
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


@app.command("exposure")
def exposure_cmd(as_json: bool = typer.Option(False, "--json")) -> None:
    """Exposición por subyacente desde MT5 (solo lectura, sin órdenes)."""
    from .snapshots import collect_exposure

    data = collect_exposure()
    if as_json:
        console.print_json(json.dumps(data, default=str))
        return
    out = Console(width=150)
    color = "green" if data["ok"] else "yellow"
    out.print(
        f"[bold]Exposición Prop Fund[/bold] · [{color}]{data['status']}[/{color}] · "
        f"fuente {data['source']} · solo lectura · {data['generated_at']}"
    )
    for note in data.get("notes", []):
        out.print(f"[yellow]Aviso:[/yellow] {note}")

    accounts = data.get("accounts") or []
    if accounts:
        t = Table(title="Cuentas MT5 leídas")
        for col in ("Cuenta", "Estado", "Login", "Servidor", "Equity", "Inicio día", "Pico", "Pos.", "Riesgo USD"):
            t.add_column(col, no_wrap=True)
        for a in accounts:
            snap = a.get("snapshot") or {}
            ident = a.get("identity") or {}
            t.add_row(
                a["account"], a["status"],
                str(ident.get("login") or "Sin datos"),
                str(ident.get("server") or "Sin datos"),
                _fmt_money(snap.get("equity")), _fmt_money(snap.get("day_start_equity")),
                _fmt_money(snap.get("peak_equity")),
                str(snap.get("open_positions", "Sin datos")),
                _fmt_money(snap.get("open_risk_usd")),
            )
        out.print(t)

    rows = data.get("by_underlying") or {}
    t = Table(title="Exposición por subyacente")
    for col in ("Subyacente", "Instrumentos", "Cuentas", "Neto USD", "Bruto USD", "Mercados", "Sin datos"):
        t.add_column(col, no_wrap=True)
    for underlying, row in sorted(rows.items()):
        t.add_row(
            underlying,
            ", ".join(row.get("instruments") or []) or "—",
            ", ".join(row.get("accounts") or []) or "—",
            _fmt_money(row.get("net_notional_usd")),
            _fmt_money(row.get("gross_notional_usd")),
            ", ".join(row.get("markets") or []) or "—",
            ", ".join(row.get("sin_datos") or []) or "—",
        )
    out.print(t)
    totals = data.get("totals") or {}
    out.print(
        f"Total nocional bruto {_fmt_money(totals.get('gross_notional_usd'))} USD · "
        f"neto {_fmt_money(totals.get('net_notional_usd'))} USD"
    )

    positions = data.get("positions") or []
    t = Table(title="Posiciones en solo lectura")
    for col in ("Cuenta", "Estrategia", "Carril", "Símbolo", "Lado", "Cantidad", "Precio",
                "Nocional USD", "Riesgo USD", "Magic", "Ticket"):
        t.add_column(col, no_wrap=True)
    for p in positions:
        t.add_row(
            p["account"], p["strategy"], p["lane"], p["symbol"], p["side"],
            f"{float(p['quantity']):g}", f"{float(p['price']):g}",
            _fmt_money(p.get("notional_usd")), _fmt_money(p.get("risk_usd")),
            str(p.get("magic", "—")), str(p.get("ticket", "—")),
        )
    if positions:
        out.print(t)
    elif data["ok"]:
        out.print("[dim]Sin posiciones abiertas.[/dim]")


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


def _fmt_bps(value: float | None) -> str:
    return "Sin datos" if value is None else f"{value:.4f}"


def _fmt_money(value: float | None) -> str:
    return "Sin datos" if value is None else f"{float(value):,.2f}"


def _fmt_price(value: float | None) -> str:
    return "Sin datos" if value is None else f"{value:.6f}".rstrip("0").rstrip(".")


@app.command("sync-spreads")
def sync_spreads_cmd(
    account: str = typer.Option(..., "--account", help="Cuenta CFD, p. ej. CFD-001"),
    write: bool = typer.Option(
        False, "--write",
        help="Escribe en config/propfund/costs.yaml. Sin esta opción solo simula.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Mide spreads desde broker_spreads y los convierte a precio (dry-run)."""
    try:
        report = sync_spreads_report(account, write=write)
    except (ValueError, KeyError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if as_json:
        console.print_json(json.dumps(report, default=str))
        return
    out = Console(width=150)
    t = Table(title=f"Spreads medidos · {account} · {'ESCRITURA' if write else 'dry-run'}")
    for col in ("Símbolo", "Bróker", "Horas", "p50 bps", "p75 bps", "Cierre", "Spread", "Spread p75", "Estado"):
        t.add_column(col, no_wrap=True)
    for row in report["symbols"]:
        color = "green" if row["status"] == "ok" else "yellow"
        t.add_row(
            row["symbol"], row["broker_symbol"], str(row["hours"]),
            _fmt_bps(row["p50_bps"]), _fmt_bps(row["p75_bps"]),
            _fmt_price(row["last_close"]),
            _fmt_price(row["spread_price"]), _fmt_price(row["spread_p75_price"]),
            f"[{color}]{row['status']}[/{color}]",
        )
    out.print(t)
    for warning in report["warnings"]:
        out.print(f"[yellow]Aviso:[/yellow] {warning}")
    if write:
        written = ", ".join(report["planned"]) or "ninguno"
        out.print(f"Escrito en {report['costs_path']} · símbolos: {written}")
    else:
        planned = ", ".join(report["planned"]) or "ninguno"
        out.print(
            f"[bold]Dry-run:[/bold] no se escribió nada. Se escribirían: {planned}. "
            "Usa --write para aplicar."
        )

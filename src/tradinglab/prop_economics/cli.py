"""``lab propecon``: motor EV de prop firms de futuros (FUT-A8).

* ``programs``: programas, caducidad e incógnitas.
* ``simulate``: proyecto Monte Carlo con un pool real (JSONL) o SINTÉTICO (hipotético) y μ* opcional.
* ``ledger …``: libro REAL; solo lo usa el operador con evidencia. El simulador nunca lo toca.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Column, Table

from ..config import ROOT
from .ledger import add_account, add_event, open_ledger, summary
from .pools import load_pool, synthetic_pool
from .project import ProjectConfig, simulate_project
from .report import build_report, to_markdown
from .rules import blocking_unknowns, is_expired, load_program
from .scenarios import min_profitable_edge

PROGRAMS_DIR = ROOT / "config" / "prop_economics" / "programs"
LEDGER_PATH = ROOT / "data" / "prop_economics" / "ledger.db"

app = typer.Typer(no_args_is_help=True,
                  help="Motor EV de prop firms de futuros: programas, simulación, μ* y libro real (separado).")
ledger_app = typer.Typer(no_args_is_help=True, help="Libro REAL (solo el operador, con evidencia).")
app.add_typer(ledger_app, name="ledger")
console = Console()


def _today() -> date:
    """Fecha de hoy en Nueva York (referencia de las sesiones CME del laboratorio)."""
    return datetime.now(ZoneInfo("America/New_York")).date()


def _assume(items: list[str]) -> tuple[tuple[str, float], ...]:
    out = []
    for item in items:
        key, _, val = item.partition("=")
        if not key or not val:
            raise typer.BadParameter(f"--assume espera clave=valor: {item}")
        out.append((key.strip(), math.inf if val.strip().lower() in {"inf", "infinito"} else float(val)))
    return tuple(out)


@app.command("programs")
def programs(today: str = typer.Option(None, help="Fecha AAAA-MM-DD (por defecto, hoy)")) -> None:
    """Programas disponibles, caducidad de sus reglas e incógnitas bloqueantes."""
    day = date.fromisoformat(today) if today else _today()
    table = Table(Column("programa", no_wrap=True), "versión", "consultado", "caducado",
                  Column("incógnitas", overflow="fold"))
    for path in sorted(PROGRAMS_DIR.glob("*.yaml")):
        p = load_program(path)
        table.add_row(p.program_id, p.rules_version, p.consulted_at.isoformat(),
                      "sí" if is_expired(p, day) else "no", ", ".join(blocking_unknowns(p)) or "—")
    console.print(table)


@app.command("simulate")
def simulate(
    program: str = typer.Option(..., help="program_id (fichero en config/prop_economics/programs)"),
    pool: Path = typer.Option(None, help="Pool JSONL de días reales (forward/oos/is)"),
    synthetic_mu: float = typer.Option(None, help="HIPOTÉTICO: ventaja bruta en R del pool sintético"),
    rr: float = typer.Option(1.5, help="Sintético: objetivo/stop"),
    risk: float = typer.Option(50.0, help="Sintético: riesgo por contrato en USD (MNQ 25 pt = 50)"),
    cost: float = typer.Option(2.22, help="Sintético: coste ida y vuelta por contrato en USD"),
    days: int = typer.Option(500, help="Sintético: días del pool"),
    contracts_eval: int = typer.Option(10), contracts_funded: int = typer.Option(10),
    budget: float = typer.Option(1500.0), paths: int = typer.Option(20000), seed: int = typer.Option(7),
    mean_block: float = typer.Option(None, help="Bloque medio del bootstrap (por defecto, óptimo de arch)"),
    assume: list[str] = typer.Option([], help="Supuesto explícito clave=valor para un sin_datos (repetible)"),
    assume_processing_days: int = typer.Option(None),
    policy: str = typer.Option("max_asap"), policy_arg: float = typer.Option(None),
    payout_fee: float = typer.Option(0.0), start: str = typer.Option("2027-01-04"),
    horizons: str = typer.Option("30,90,180,365"),
    mustar: bool = typer.Option(False, help="Calcula también la ventaja mínima rentable a 365 días"),
    out: Path = typer.Option(None, help="Fichero .md o .json del informe"),
) -> None:
    """Simula un proyecto (presupuesto, evaluaciones, financiadas y payouts) y escribe el informe."""
    prog = load_program(PROGRAMS_DIR / f"{program}.yaml")
    if pool is not None:
        days_pool = load_pool(pool)
    elif synthetic_mu is not None:
        days_pool = synthetic_pool(mu_gross_r=synthetic_mu, rr=rr, risk_usd=risk, cost_rt=cost, n_days=days, seed=seed)
    else:
        raise typer.BadParameter("hace falta --pool o --synthetic-mu")
    cfg = ProjectConfig(contracts_eval=contracts_eval, contracts_funded=contracts_funded, budget=budget,
                        start_date=date.fromisoformat(start), horizons_days=tuple(int(h) for h in horizons.split(",")),
                        policy=policy, policy_arg=policy_arg, payout_fee=payout_fee,
                        assume_processing_days=assume_processing_days, assume=_assume(assume))
    n = paths
    while True:   # 04 §6.5: si SE(EV) > max(25, 0,05·|EV|) se dobla n hasta 200.000
        res = simulate_project(prog, days_pool, cfg, n_paths=n, seed=seed, mean_block=mean_block)
        last = res["horizons"][max(res["horizons"], key=int)]
        if last["se"] <= max(25.0, 0.05 * abs(last["ev"])) or n >= 200_000:
            break
        n = min(2 * n, 200_000)
    extra = {}
    if mustar:
        extra["mu_star"] = {k: v for k, v in min_profitable_edge(
            prog, days_pool, cfg, horizon_days=365, n_paths=min(n, 4000), seed=seed, mean_block=mean_block).items()
            if k != "grid"}
    rep = build_report(prog, days_pool, cfg, res, n_paths=n, seed=seed, today=_today(), extra=extra)
    text = json.dumps(rep, ensure_ascii=False, indent=1, default=str) if out and out.suffix == ".json" \
        else to_markdown(rep)
    if out:
        out.write_text(text, encoding="utf-8")
        console.print(f"informe: {out}")
    else:
        console.print(text)


@ledger_app.command("add-account")
def ledger_add_account(account_id: str, firm: str = typer.Option(...), program: str = typer.Option(...),
                       rules_version: str = typer.Option(...), origin: str = typer.Option(...),
                       opened_at: str = typer.Option(...), platform: str = typer.Option(None),
                       db: Path = typer.Option(LEDGER_PATH)) -> None:
    """Alta de una cuenta comprada (solo el operador)."""
    con = open_ledger(db)
    add_account(con, account_id, firm_id=firm, program_id=program, rules_version=rules_version, origin=origin,
                opened_at=opened_at, platform=platform)
    console.print(f"cuenta {account_id} registrada")


@ledger_app.command("add")
def ledger_add(account_id: str, event: str,
               amount_usd: float = typer.Option(..., "--amount-usd", help="USD; los costes en negativo"),
               ts: str = typer.Option(...),
               payout_id: str = typer.Option(None), corrects_id: int = typer.Option(None),
               amount_local: float = typer.Option(None), currency_local: str = typer.Option(None),
               fx_rate: float = typer.Option(None), evidence: str = typer.Option(None),
               note: str = typer.Option(None), db: Path = typer.Option(LEDGER_PATH)) -> None:
    """Añade un evento real con su evidencia (solo el operador). Los costes van en negativo."""
    con = open_ledger(db)
    rid = add_event(con, ts=ts, account_id=account_id, event=event, amount_usd=amount_usd, payout_id=payout_id,
                    corrects_id=corrects_id, amount_local=amount_local, currency_local=currency_local,
                    fx_rate=fx_rate, evidence_path=evidence, note=note)
    console.print(f"evento {rid} registrado")


@ledger_app.command("summary")
def ledger_summary(budget: float = typer.Option(None), next_eval_price: float = typer.Option(None),
                   today: str = typer.Option(None), db: Path = typer.Option(LEDGER_PATH)) -> None:
    """Dinero real: costes, cobrado, neto, canal de payouts, tiempos y alertas (solo lectura)."""
    if not Path(db).exists():
        console.print("Sin datos: no hay libro real todavía")
        raise typer.Exit(0)
    con = open_ledger(db, readonly=True)
    s = summary(con, today=date.fromisoformat(today) if today else _today(), budget=budget,
                next_eval_price=next_eval_price)
    console.print_json(json.dumps(s, ensure_ascii=False, default=str))

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from . import data as data_mod
from .agents import RATING_TO_TARGET, AgentError, run_lite_agent, run_tradingagents
from .alerts import AlertConfig, heartbeat, last_alerts
from .alerts import send as send_alert
from .backtest import run as run_backtest
from .botlab import archive_bot, evaluate_all, propose_bot, restore_bot
from .config import DEFAULT_DB, ROOT, get_settings
from .db import connect, init_db, utcnow
from .decisions import compare as decisions_compare
from .decisions import record_decision, update_outcomes
from .decisions import report as decisions_report
from .execution import get_broker, get_mt5_broker, get_projectx_broker
from .f13 import config_check as f13_config_check
from .f13 import execution_metrics as f13_execution
from .f13 import freeze as f13_freeze
from .f13 import load_criteria as f13_criteria
from .f13 import record_snapshot as f13_record
from .f13 import signal_check as f13_signal_check
from .f13 import status as f13_status
from .indicators import atr as atr_indicator
from .instruments import get_instrument, list_instruments
from .intel.calendar import (
    CalendarStatus,
    DbCalendarProvider,
    add_calendar_event,
    calendar_block_for_settings,
    rules_from_settings,
)
from .intel.fred import FredCalendarProvider
from .intel.news import fetch_rss, news_count, recent_news, store_news
from .intel.sec import SecClient
from .killswitch import allows_order
from .killswitch import ensure as ensure_killswitch
from .killswitch import evaluate as evaluate_killswitch
from .killswitch import load_state as load_killswitch
from .killswitch import reset as reset_killswitch
from .llm import LLMClient
from .orchestrator import load_bots, run_all, write_dry_run_log
from .prop import AccountState, PropGuard, PropRules, from_yaml, ftmo, monte_carlo
from .reconciliation import last_reconciliation
from .reconciliation import reconcile as reconcile_broker
from .reporting import build_dashboard
from .risk import check_order, size_position
from .session import flatten_required, session_block
from .strategies import STRATEGIES

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="TradingLab: datos, backtest, paper trading y agentes LLM.",
)
mt5_app = typer.Typer(no_args_is_help=True, help="MetaTrader 5: conexión, precios, sizing y órdenes.")
prop_app = typer.Typer(no_args_is_help=True, help="Cuentas de fondeo: reglas, estado y Monte Carlo.")
futures_app = typer.Typer(no_args_is_help=True, help="Futuros: ProjectX/TopstepX, contratos y órdenes.")
killswitch_app = typer.Typer(
    no_args_is_help=True, help="Kill-switch persistente: estado, pruebas y reset manual."
)
alerts_app = typer.Typer(
    no_args_is_help=True, help="Alertas ntfy/Telegram, latido y chequeo de servicios."
)
f13_app = typer.Typer(no_args_is_help=True, help="F13: pilot operativo de paper y criterios.")
bots_app = typer.Typer(no_args_is_help=True, help="Bots: listar, evaluar, proponer, archivar.")
decisions_app = typer.Typer(no_args_is_help=True, help="Decisiones LLM: resultados y líneas base.")
fund_app = typer.Typer(no_args_is_help=True, help="Fondo: cuentas, límites e historial.")
operator_app = typer.Typer(
    no_args_is_help=True,
    help="Modo operador de la consola: PIN, estado y auditoría.",
)
lessons_app = typer.Typer(no_args_is_help=True, help="Aprendizaje controlado: lecciones y holdout.")
reports_app = typer.Typer(no_args_is_help=True, help="Reportes CSV/HTML con validación y vista previa.")
markets_app = typer.Typer(no_args_is_help=True, help="Agentes por mercado y coordinador determinista.")
intel_app = typer.Typer(no_args_is_help=True, help="Información continua: RSS, saneado y estado.")
sec_app = typer.Typer(no_args_is_help=True, help="SEC EDGAR: CIK, filings y company facts.")
app.add_typer(mt5_app, name="mt5")
app.add_typer(prop_app, name="prop")
app.add_typer(futures_app, name="futures")
app.add_typer(killswitch_app, name="killswitch")
app.add_typer(alerts_app, name="alerts")
app.add_typer(f13_app, name="f13")
app.add_typer(bots_app, name="bots")
app.add_typer(decisions_app, name="decisions")
app.add_typer(fund_app, name="fund")
app.add_typer(operator_app, name="operator")
app.add_typer(lessons_app, name="lessons")
app.add_typer(reports_app, name="reports")
app.add_typer(markets_app, name="markets")
app.add_typer(intel_app, name="intel")
app.add_typer(sec_app, name="sec")
console = Console()

OK = "[green]OK[/green]"
WARN = "[yellow]WARN[/yellow]"
FAIL = "[red]FAIL[/red]"


def _today() -> str:
    return date.today().isoformat()


def _default_start() -> str:
    return (date.today() - timedelta(days=365 * 8)).isoformat()


def _fmt_pct(value: float) -> str:
    return f"{value * 100:,.2f}%"


def _session_reason(settings, delta: int, asset_class: str = "equity") -> str | None:
    if delta <= 0:
        return None
    block = session_block(rules_from_settings(settings), asset_class=asset_class)
    return block.reason if block.blocked else None


# --------------------------------------------------------------------- helpers

def _prop_rules(
    firm: str | None = None,
    phase: str | None = None,
    account_size: float | None = None,
    buffer_pct: float | None = None,
) -> PropRules:
    settings = get_settings()
    firm = firm or settings.prop.firm
    phase = phase or settings.prop.phase
    size = float(account_size or settings.prop.account_size)
    buffer = settings.prop.buffer_pct if buffer_pct is None else buffer_pct
    try:
        return from_yaml(firm, phase, size, buffer_pct=buffer)  # type: ignore[arg-type]
    except KeyError:
        console.print(f"[yellow]'{firm}' no está en config/prop.yaml; uso el preset FTMO.[/yellow]")
        return ftmo(size, phase, buffer_pct=buffer)  # type: ignore[arg-type]


def _mt5(settings, dry_run: bool = True):
    from .execution.mt5 import MT5Error

    broker = get_mt5_broker(settings, dry_run=dry_run)
    try:
        broker.connect()
    except MT5Error as exc:
        console.print(Panel(str(exc), title="MT5 no disponible", style="bold red"))
        raise typer.Exit(1)
    return broker


def _futures(settings, dry_run: bool = True):
    from .execution.projectx import ProjectXError

    broker = get_projectx_broker(settings, dry_run=dry_run)
    try:
        broker.health()
    except ProjectXError as exc:
        console.print(Panel(str(exc), title="ProjectX no disponible", style="bold red"))
        raise typer.Exit(1)
    return broker


def _quote_rate(broker, instrument) -> float:
    """Unidades de la divisa cotizada por 1 USD."""
    quote = instrument.quote_ccy.upper()
    if quote == "USD":
        return 1.0
    try:
        if quote in {"JPY", "CHF", "CAD"}:
            return float(broker.tick(f"USD{quote}")["bid"])
        return 1.0 / float(broker.tick(f"{quote}USD")["bid"])
    except Exception as exc:
        raise typer.BadParameter(
            f"No pude obtener el cambio de {quote} a USD ({exc}). "
            "Pásalo a mano con --quote-rate (unidades de la divisa por 1 USD)."
        ) from exc


def _prop_state_from_mt5(broker, rules: PropRules) -> AccountState:
    acc = broker.health()
    positions = broker.positions()
    curve = broker.equity_series(180)
    if len(curve) >= 2:
        state = PropGuard.state_from_equity(
            rules, curve, initial_balance=rules.account_size
        )
        state.equity = acc["equity"]
        state.balance = acc["balance"]
        state.open_positions = len(positions)
        state.open_lots = sum(p["volume"] for p in positions)
        state.server_time = None
        return state

    return AccountState(
        balance=acc["balance"],
        equity=acc["equity"],
        initial_balance=rules.account_size,
        day_start_balance=acc["balance"],
        day_start_equity=acc["equity"] - acc.get("profit", 0.0),
        peak_balance=acc["balance"],
        peak_equity=acc["equity"],
        open_positions=len(positions),
        open_lots=sum(p["volume"] for p in positions),
    )


@app.command()
def version() -> None:
    """Muestra la versión instalada."""
    console.print(f"TradingLab [bold]{__version__}[/bold] · Python {sys.version.split()[0]}")


@app.command("instruments")
def instruments_cmd(
    asset_class: str = typer.Option(None, "--class", help="equity|forex|futures|cfd"),
    validate: bool = typer.Option(False, "--validate", help="Validar el catálogo completo"),
) -> None:
    """Catálogo único de instrumentos por clase."""
    from .instruments import catalog, validate_catalog

    rows = catalog(asset_class)
    t = Table(title=f"Catálogo de instrumentos ({len(rows)})")
    for col in ("Símbolo", "Clase", "Fuente", "Sesión", "TZ", "Tick", "Contrato", "Tick $", "Lote"):
        t.add_column(col, justify="right" if col in {"Tick", "Contrato", "Tick $", "Lote"} else "left")
    for item in rows:
        t.add_row(
            item["symbol"],
            item["asset_class"],
            item["data_source"],
            item["session"],
            item["session_tz"],
            f"{item['tick_size']:g}",
            f"{item['contract_size']:g}",
            f"{item['tick_value']:,.2f}" if item["tick_value"] is not None else "variable",
            f"{item['min_lot']:g}/{item['lot_step']:g}/{item['max_lot']:g}",
        )
    console.print(t)
    if validate:
        result = validate_catalog()
        if result["ok"]:
            console.print(
                f"[green]Catálogo OK[/green] · {result['count']} instrumentos · "
                f"clases {', '.join(result['classes'])}"
            )
        else:
            for error in result["errors"]:
                console.print(f"[red]{error}[/red]")
            raise typer.Exit(1)


@app.command()
def doctor(network: bool = typer.Option(False, "--network", help="Probar descarga de datos real")) -> None:
    """Comprueba que todo el entorno está listo."""
    table = Table(title="Diagnóstico del entorno", show_lines=False)
    table.add_column("Componente", style="bold")
    table.add_column("Estado")
    table.add_column("Detalle", overflow="fold")

    # Python
    py_ok = sys.version_info >= (3, 12)
    table.add_row("Python", OK if py_ok else FAIL, f"{sys.version.split()[0]} (>=3.12)")

    # Config
    try:
        settings = get_settings()
        table.add_row("Config", OK, f"modo={settings.mode} · broker={settings.execution.broker}")
    except Exception as exc:
        settings = None
        table.add_row("Config", FAIL, str(exc)[:160])

    # Secretos: solo nombres/orígenes, nunca valores
    try:
        from .config import secret_status

        secrets = secret_status()
        n = len(secrets["keyring"])
        detail = f"keyring {n}"
        if secrets["dotenv"]:
            detail += " · .env presente (fallback)"
        if secrets["missing"]:
            detail += f" · faltan {len(secrets['missing'])}"
        table.add_row("Secretos", OK if n else WARN, detail)
    except Exception as exc:
        table.add_row("Secretos", WARN, str(exc)[:160])

    # Integraciones opcionales: solo estado, nunca valores.
    try:
        from .config import sec_user_agent_status

        sec = sec_user_agent_status()
        if sec["format_ok"]:
            table.add_row("SEC EDGAR", OK, "User-Agent con contacto configurado")
        elif sec["configured"]:
            table.add_row("SEC EDGAR", WARN, "User-Agent sin formato/contacto válido")
        else:
            table.add_row("SEC EDGAR", WARN, "falta SEC_USER_AGENT")
    except Exception as exc:
        table.add_row("SEC EDGAR", WARN, str(exc)[:160])

    fred_ok = bool(os.getenv("FRED_API_KEY"))
    table.add_row(
        "FRED",
        OK if fred_ok else WARN,
        "API key presente" if fred_ok else "falta FRED_API_KEY",
    )
    finnhub_ok = bool(os.getenv("FINNHUB_API_KEY"))
    table.add_row(
        "Finnhub",
        OK if finnhub_ok else WARN,
        "API key presente" if finnhub_ok else "falta FINNHUB_API_KEY (calendario)",
    )
    try:
        alerts_cfg = AlertConfig.from_env()
        table.add_row(
            "Alertas",
            OK if alerts_cfg.configured else WARN,
            f"canal={alerts_cfg.channel} · "
            f"{'configurado' if alerts_cfg.configured else 'sin topic/token'}",
        )
    except Exception as exc:
        table.add_row("Alertas", WARN, str(exc)[:160])
    if settings:
        px = settings.projectx
        px_ok = bool(px.username and os.getenv("PROJECTX_API_KEY") and px.account_id)
        table.add_row(
            "ProjectX",
            OK if px_ok else WARN,
            f"credenciales={'sí' if px_ok else 'faltan'} · "
            f"dry_run={px.dry_run} · simulated={px.require_simulated}",
        )

    # Base de datos
    try:
        init_db(DEFAULT_DB)
        with connect(DEFAULT_DB) as con:
            con.execute("SELECT 1").fetchone()
        table.add_row("SQLite", OK, str(DEFAULT_DB))
    except Exception as exc:
        table.add_row("SQLite", FAIL, str(exc)[:160])

    # Directorios
    for name in ("data", "logs", "reports", "config"):
        p = ROOT / name
        table.add_row(f"Carpeta {name}", OK if p.exists() else WARN, str(p))

    # Repos
    for repo in ("TradingAgents", "Trading-R1"):
        p = ROOT / "vendor" / repo
        table.add_row(repo, OK if (p / ".git").exists() else WARN, str(p))

    # Bun (TUI de Trading-R1)
    import shutil

    bun = shutil.which("bun")
    table.add_row("bun", OK if bun else WARN, bun or "no instalado (necesario para la TUI de Trading-R1)")

    # Alpaca
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if key and secret:
        try:
            from .execution import AlpacaBroker

            health = AlpacaBroker(paper=(settings.mode != "live") if settings else True).health()
            table.add_row(
                "Alpaca",
                OK,
                f"paper={health['paper']} · equity={health['equity']:,.2f} · status={health['status']}",
            )
        except Exception as exc:
            table.add_row("Alpaca", FAIL, str(exc)[:160])
    else:
        table.add_row("Alpaca keys", WARN, "faltan en .env (paper trading)")

    # LM Studio
    if settings:
        try:
            health = LLMClient(settings.llm, DEFAULT_DB).health()
            models = health.get("models") or []
            detail = f"{health['base_url']} · modelos: {', '.join(models) if models else 'ninguno'}"
            lm = health.get("lmstudio") or {}
            ctx = lm.get("context")
            if ctx:
                detail += f" · ctx {ctx:,}"
            table.add_row("LM Studio", OK if models else WARN, detail)
            if ctx and ctx < 16_384:
                table.add_row(
                    "Contexto LLM",
                    WARN,
                    f"{ctx:,} tokens: los agentes necesitan ≥16k. Recarga el modelo "
                    "con --context-length 32768.",
                )
            if models and settings.llm.model not in models:
                table.add_row(
                    "Modelo configurado",
                    WARN,
                    f"'{settings.llm.model}' no aparece; usa uno de: {', '.join(models)}",
                )
        except Exception as exc:
            table.add_row("LM Studio", WARN, f"servidor no disponible: {str(exc)[:120]}")

    # MetaTrader 5
    if settings:
        try:
            from .execution.mt5 import MT5Broker

            mt5 = MT5Broker(
                path=settings.mt5.terminal_path,
                login=settings.mt5.login,
                server=settings.mt5.server,
            )
            health = mt5.connect()
            mt5.shutdown()
            offset = health.get("server_utc_offset_hours")
            offset_text = f"GMT{offset:+g}" if offset is not None else "GMT desconocido"
            table.add_row(
                "MetaTrader 5",
                OK if health["connected"] else WARN,
                f"{health['server']} · {health['mode']} · equity={health['equity']:,.2f} "
                f"· algo={'on' if health['trade_allowed'] else 'OFF'} "
                f"· {offset_text}",
            )
        except Exception as exc:
            table.add_row("MetaTrader 5", WARN, str(exc)[:160])

    # Reglas de fondeo
    if settings:
        try:
            rules = _prop_rules()
            table.add_row("Fondeo", OK, rules.describe())
            if rules.verify_against_contract:
                table.add_row(
                    "Reglas fondeo",
                    WARN,
                    "plantilla: verifica cada límite en el contrato de tu firma",
                )
        except Exception as exc:
            table.add_row("Fondeo", FAIL, str(exc)[:160])

    # Datos
    if network:
        try:
            df = data_mod.fetch("SPY", (date.today() - timedelta(days=30)).isoformat(), _today(), ROOT / "data" / "cache")
            table.add_row("Datos (yfinance)", OK, f"SPY {len(df)} barras")
        except Exception as exc:
            table.add_row("Datos (yfinance)", FAIL, str(exc)[:160])

    console.print(table)


@app.command()
def fetch(
    ticker: str = typer.Argument(..., help="Símbolo, p. ej. NVDA"),
    start: str = typer.Option(None, "--start", help="YYYY-MM-DD"),
    end: str = typer.Option(None, "--end", help="YYYY-MM-DD"),
    refresh: bool = typer.Option(False, "--refresh", help="Ignorar cache"),
) -> None:
    """Descarga y cachea datos OHLCV diarios."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    df = data_mod.fetch(ticker.upper(), start or _default_start(), end or _today(), settings.data.cache_dir, refresh)
    console.print(
        f"[bold]{ticker.upper()}[/bold]: {len(df)} barras · "
        f"{df.index[0].date()} → {df.index[-1].date()} · último cierre {df['close'].iloc[-1]:.2f}"
    )


@app.command()
def backtest(
    ticker: str = typer.Argument(..., help="Símbolo, p. ej. NVDA"),
    strategy: str = typer.Option("trend", "--strategy", "-s", help=", ".join(STRATEGIES)),
    start: str = typer.Option(None, "--start", help="YYYY-MM-DD"),
    end: str = typer.Option(None, "--end", help="YYYY-MM-DD"),
    cash: float = typer.Option(100_000.0, "--cash", help="Capital inicial"),
) -> None:
    """Ejecuta un backtest con costes sobre datos diarios."""
    settings = get_settings()
    if strategy not in STRATEGIES:
        console.print(f"[red]Estrategia desconocida:[/red] {strategy}. Opciones: {', '.join(STRATEGIES)}")
        raise typer.Exit(2)

    df = data_mod.fetch(ticker.upper(), start or _default_start(), end or _today(), settings.data.cache_dir)
    result = STRATEGIES[strategy](df)
    bt = run_backtest(
        df,
        result.target,
        starting_cash=cash,
        commission_bps=settings.execution.commission_bps,
        slippage_bps=settings.execution.slippage_bps,
    )
    m = bt.metrics

    table = Table(title=f"Backtest · {ticker.upper()} · {strategy} · {result.params}")
    table.add_column("Métrica", style="bold")
    table.add_column("Valor", justify="right")
    rows = [
        ("Periodo", f"{df.index[0].date()} → {df.index[-1].date()}"),
        ("Barras", f"{m['bars']}"),
        ("Equity final", f"{m['final_equity']:,.2f}"),
        ("Retorno total", _fmt_pct(m["total_return"])),
        ("CAGR", _fmt_pct(m["cagr"])),
        ("Volatilidad", _fmt_pct(m["volatility"])),
        ("Sharpe", f"{m['sharpe']:.2f}"),
        ("Max drawdown", _fmt_pct(m["max_drawdown"])),
        ("Calmar", f"{m['calmar']:.2f}"),
        ("Operaciones cerradas", f"{m['num_trades']}"),
        ("Win rate", _fmt_pct(m["win_rate"])),
        ("Exposición media", _fmt_pct(m["exposure"])),
    ]
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)

    if not bt.trades.empty:
        console.print(f"[dim]{len(bt.trades)} ejecuciones (compras/ventas) registradas[/dim]")


@app.command()
def run(
    ticker: str = typer.Argument(..., help="Símbolo, p. ej. NVDA"),
    strategy: str = typer.Option("trend", "--strategy", "-s", help=", ".join(STRATEGIES)),
    start: str = typer.Option(None, "--start", help="Inicio del histórico para el cálculo"),
    execute: bool = typer.Option(True, "--execute/--dry-run", help="Enviar la orden al broker paper"),
) -> None:
    """Genera la señal de hoy y la aplica a la cuenta paper."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    if strategy not in STRATEGIES:
        console.print(f"[red]Estrategia desconocida:[/red] {strategy}")
        raise typer.Exit(2)

    broker = get_broker(
        settings,
        DEFAULT_DB,
    )

    df = data_mod.fetch(ticker.upper(), start or _default_start(), _today(), settings.data.cache_dir)
    result = STRATEGIES[strategy](df)
    price = float(df["close"].iloc[-1])
    atr_value = float(atr_indicator(df).iloc[-1])
    target = float(result.target.iloc[-1])

    snap = broker.snapshot({ticker.upper(): price})
    held = next((p["qty"] for p in snap["positions"] if p["ticker"] == ticker.upper()), 0.0)

    desired = size_position(snap["equity"], price, atr_value, settings.risk) if target > 0 else 0
    delta = int(desired - held)
    ks, _ = ensure_killswitch(
        DEFAULT_DB,
        broker.equity_series(),
        settings.risk,
        current=snap["equity"],
        tz=settings.timezone,
    )
    if not allows_order(ks, delta):
        console.print(
            Panel(
                f"KILL SWITCH ACTIVO: {ks.reason}\n"
                "Solo se permiten cierres o reducciones de posición.",
                style="bold red",
            )
        )
        raise typer.Exit(1)
    if ks.active:
        console.print("[yellow]Kill switch activo: se permite reducir/cerrar.[/yellow]")

    blackout = calendar_block_for_settings(DEFAULT_DB, settings)
    if delta > 0 and blackout.blocked:
        console.print(
            Panel(
                f"BLACKOUT DE CALENDARIO: {blackout.reason}\n"
                "Solo se permiten cierres o reducciones de posición.",
                style="bold red",
            )
        )
        raise typer.Exit(1)
    session_reason = _session_reason(settings, delta)
    if session_reason:
        console.print(
            Panel(
                f"FILTRO DE SESIÓN: {session_reason}\n"
                "Solo se permiten cierres o reducciones de posición.",
                style="bold red",
            )
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            f"{ticker.upper()} · {strategy}\n"
            f"Señal: {'LONG' if target > 0 else 'FLAT'} (target={target:.0%})\n"
            f"Precio: {price:,.2f} · ATR14: {atr_value:,.2f}\n"
            f"Posición actual: {held:g} · Objetivo: {desired} · Delta: {delta:+d}",
            title="Decisión",
        )
    )

    with connect(DEFAULT_DB) as con:
        cur = con.execute(
            "INSERT INTO runs(ts, kind, bot, params, status) VALUES(?,?,?,?,?)",
            (utcnow(), "signal", f"{ticker.upper()}:{strategy}", json.dumps(result.params), "ok"),
        )
        run_id = int(cur.lastrowid)
        con.execute(
            "INSERT INTO signals(ts, run_id, ticker, bot, side, strength, price, reason) VALUES(?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                run_id,
                ticker.upper(),
                strategy,
                "buy" if delta > 0 else ("sell" if delta < 0 else "hold"),
                target,
                price,
                f"target={target:.2f}",
            ),
        )

    if delta == 0:
        console.print("[dim]Sin cambios: no se envía orden.[/dim]")
        return

    if delta > 0:
        check = check_order(
            equity=snap["equity"],
            cash=snap["cash"],
            price=price,
            qty=delta,
            current_positions=len(snap["positions"]),
            gross_exposure=snap["positions_value"],
            cfg=settings.risk,
        )
        if not check.approved or check.qty <= 0:
            console.print(f"[yellow]Orden bloqueada por riesgo:[/yellow] {check.reason}")
            return
        delta = check.qty

    if not execute:
        console.print(f"[yellow]DRY RUN[/yellow] · se habría enviado {delta:+d} {ticker.upper()} @ {price:,.2f}")
        return

    fill = broker.submit_market(
        ticker.upper(),
        delta,
        price,
        bot=f"{ticker.upper()}:{strategy}",
        reason=f"target={target:.2f}",
        run_id=run_id,
    )
    console.print(f"[green]Ejecutado[/green] {fill}")
    broker.mark_to_market({ticker.upper(): price})
    console.print(f"Equity paper: {broker.snapshot({ticker.upper(): price})['equity']:,.2f}")


def _agent_decision(
    ticker: str, day: str, analysts: str, save: bool, mode: str
) -> dict:
    """Elige entre el agente lite (1 llamada) y TradingAgents (multi-agente)."""
    if mode == "lite":
        return run_lite_agent(ticker, day, get_settings())
    if mode == "deep":
        return run_tradingagents(ticker, day, analysts, save=save)
    raise typer.BadParameter("--mode debe ser 'lite' o 'deep'")


@app.command()
def agent(
    ticker: str = typer.Argument(..., help="Símbolo, p. ej. NVDA"),
    analysis_date: str = typer.Option(None, "--date", help="YYYY-MM-DD (por defecto hoy)"),
    analysts: str = typer.Option("market,news", "--analysts", help="market,news,social,fundamentals"),
    save: bool = typer.Option(True, "--save/--no-save", help="Guardar informe completo"),
    mode: str = typer.Option(
        "lite", "--mode", help="lite = 1 llamada (minutos) · deep = TradingAgents (horas)"
    ),
) -> None:
    """Decisión del agente: lite (rápido) o deep (TradingAgents)."""
    init_db(DEFAULT_DB)
    day = analysis_date or _today()
    detail = (
        "Una llamada con contexto técnico compacto (~2-10 min)."
        if mode == "lite"
        else "Run multi-agente; con un 27B local puede tardar horas."
    )
    console.print(
        Panel(
            f"Ticker: [bold]{ticker.upper()}[/bold] · fecha: {day}\n"
            f"Modo: {mode} · analistas: {analysts} · modelo: {get_settings().llm.model}\n"
            f"[dim]{detail} No cierres la ventana.[/dim]",
            title="TradingAgents" if mode == "deep" else "Agente lite",
        )
    )
    try:
        result = _agent_decision(ticker, day, analysts, save, mode)
    except AgentError as exc:
        console.print(Panel(str(exc)[-3000:], title="Agente falló", style="bold red"))
        raise typer.Exit(1)

    try:
        record_decision(DEFAULT_DB, result, mode=mode)
    except Exception:
        pass

    table = Table(title=f"Decisión · {ticker.upper()} · {day}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Rating", f"[bold]{result.get('rating')}[/bold]")
    if result.get("confidence") is not None:
        table.add_row("Confianza", f"{float(result['confidence']):.0%}")
    if result.get("horizon_days") is not None:
        table.add_row("Horizonte", f"{result['horizon_days']} días")
    table.add_row("Modelo", str(result.get("model")))
    table.add_row("Duración", f"{result.get('elapsed_s')} s")
    if result.get("reports_path"):
        table.add_row("Informe", str(result["reports_path"]))
    console.print(table)

    decision = (result.get("decision") or "").strip()
    if decision:
        console.print(
            Panel(decision[:4000], title="Tesis del analista"),
            overflow="fold",
        )
    risks = (result.get("risks") or "").strip()
    if risks:
        console.print(
            Panel(risks[:2000], title="Riesgos señalados", style="yellow"),
            overflow="fold",
        )


@app.command("agent-run")
def agent_run(
    ticker: str = typer.Argument(..., help="Símbolo, p. ej. NVDA"),
    analysis_date: str = typer.Option(None, "--date", help="YYYY-MM-DD (por defecto hoy)"),
    analysts: str = typer.Option("market,news", "--analysts"),
    execute: bool = typer.Option(True, "--execute/--dry-run"),
    mode: str = typer.Option("lite", "--mode", help="lite (rápido) · deep (TradingAgents)"),
) -> None:
    """El agente decide y la orden se aplica a la cuenta paper."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    day = analysis_date or _today()

    try:
        result = _agent_decision(ticker, day, analysts, True, mode)
    except AgentError as exc:
        console.print(Panel(str(exc)[-3000:], title="Agente falló", style="bold red"))
        raise typer.Exit(1)

    try:
        record_decision(DEFAULT_DB, result, mode=mode)
    except Exception:
        pass

    rating = str(result.get("rating", "REVIEW"))
    target_fraction = RATING_TO_TARGET.get(rating, None)
    console.print(
        f"[bold]{ticker.upper()}[/bold] · modo={mode} · rating=[bold]{rating}[/bold] "
        f"· target={target_fraction}"
    )

    if target_fraction is None:
        console.print("[yellow]Hold / REVIEW: no se modifica la posición.[/yellow]")
        with connect(DEFAULT_DB) as con:
            con.execute(
                "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) VALUES(?,?,?,?,?,?,?)",
                (
                    utcnow(),
                    ticker.upper(),
                    f"agent-{mode}",
                    "hold",
                    None,
                    None,
                    f"rating={rating}",
                ),
            )
        return

    broker = get_broker(
        settings,
        DEFAULT_DB,
    )
    df = data_mod.fetch(ticker.upper(), _default_start(), _today(), settings.data.cache_dir)
    price = float(df["close"].iloc[-1])
    atr_value = float(atr_indicator(df).iloc[-1])
    snap = broker.snapshot({ticker.upper(): price})
    held = next((p["qty"] for p in snap["positions"] if p["ticker"] == ticker.upper()), 0.0)

    if target_fraction > 0:
        max_pct = settings.risk.max_position_pct * float(target_fraction)
        desired = size_position(snap["equity"], price, atr_value, settings.risk, max_pct=max_pct)
    else:
        desired = 0

    delta = int(desired - held)
    ks, _ = ensure_killswitch(
        DEFAULT_DB,
        broker.equity_series(),
        settings.risk,
        current=snap["equity"],
        tz=settings.timezone,
    )
    if not allows_order(ks, delta):
        console.print(
            Panel(
                f"KILL SWITCH ACTIVO: {ks.reason}\n"
                "Solo se permiten cierres o reducciones de posición.",
                style="bold red",
            )
        )
        raise typer.Exit(1)
    if ks.active:
        console.print("[yellow]Kill switch activo: se permite reducir/cerrar.[/yellow]")
    blackout = calendar_block_for_settings(DEFAULT_DB, settings)
    if delta > 0 and blackout.blocked:
        console.print(
            Panel(
                f"BLACKOUT DE CALENDARIO: {blackout.reason}\n"
                "Solo se permiten cierres o reducciones de posición.",
                style="bold red",
            )
        )
        raise typer.Exit(1)
    session_reason = _session_reason(settings, delta)
    if session_reason:
        console.print(
            Panel(
                f"FILTRO DE SESIÓN: {session_reason}\n"
                "Solo se permiten cierres o reducciones de posición.",
                style="bold red",
            )
        )
        raise typer.Exit(1)
    console.print(
        f"Precio {price:,.2f} · ATR14 {atr_value:,.2f} · posición {held:g} → objetivo {desired} · delta {delta:+d}"
    )

    if delta == 0:
        console.print("[dim]Sin cambios.[/dim]")
        return

    if delta > 0:
        check = check_order(
            equity=snap["equity"],
            cash=snap["cash"],
            price=price,
            qty=delta,
            current_positions=len(snap["positions"]),
            gross_exposure=snap["positions_value"],
            cfg=settings.risk,
        )
        if not check.approved or check.qty <= 0:
            console.print(f"[yellow]Orden bloqueada por riesgo:[/yellow] {check.reason}")
            return
        delta = check.qty

    if not execute:
        console.print(f"[yellow]DRY RUN[/yellow] · se habría enviado {delta:+d} {ticker.upper()} @ {price:,.2f}")
        return

    fill = broker.submit_market(
        ticker.upper(), delta, price, bot=f"agent-{mode}", reason=f"rating={rating}"
    )
    with connect(DEFAULT_DB) as con:
        con.execute(
            "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) VALUES(?,?,?,?,?,?,?)",
            (
                utcnow(),
                ticker.upper(),
                f"agent-{mode}",
                fill["side"],
                target_fraction,
                price,
                f"rating={rating}",
            ),
        )
    console.print(f"[green]Ejecutado[/green] {fill}")
    broker.mark_to_market({ticker.upper(): price})
    console.print(f"Equity paper: {broker.snapshot({ticker.upper(): price})['equity']:,.2f}")


@app.command()
def orchestrate(
    only: str = typer.Option(None, "--bot", help="Ejecutar solo este bot (id de bots.yaml)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Calcular sin enviar órdenes"),
    include_disabled: bool = typer.Option(False, "--include-disabled", help="Incluir bots con enabled: false"),
) -> None:
    """Ejecuta todos los bots habilitados del catálogo sobre el broker configurado."""
    settings = get_settings()
    init_db(DEFAULT_DB)

    try:
        broker = get_broker(settings, DEFAULT_DB)
    except Exception as exc:
        console.print(Panel(str(exc), title="Broker no disponible", style="bold red"))
        raise typer.Exit(1)

    try:
        actions = run_all(
            settings, broker, only=only, dry_run=dry_run, include_disabled=include_disabled
        )
    except Exception as exc:
        console.print(Panel(str(exc)[-2000:], title="Orquestador detenido", style="bold red"))
        raise typer.Exit(1)

    if not actions:
        console.print("[yellow]No hay bots habilitados. Revisa config/bots.yaml[/yellow]")
        return

    t = Table(title=f"Orquestador · broker={settings.execution.broker} · dry_run={dry_run}")
    for col in ("Bot", "Ticker", "Target", "Precio", "Pos.", "Objetivo", "Delta", "Estado", "Detalle"):
        t.add_column(col, justify="right" if col not in ("Bot", "Ticker", "Estado", "Detalle") else "left")
    for a in actions:
        color = {"ejecutado": "green", "error": "red", "bloqueado": "yellow"}.get(a.status, "dim")
        t.add_row(
            a.bot,
            a.ticker,
            f"{a.target:.0%}",
            f"{a.price:,.2f}",
            f"{a.held:g}",
            str(a.desired),
            f"{a.delta:+d}",
            f"[{color}]{a.status}[/{color}]",
            a.detail,
        )
    console.print(t)

    if dry_run:
        log_path = write_dry_run_log(
            actions,
            ROOT / "data" / "dryrun",
            broker=settings.execution.broker,
        )
        console.print(f"[dim]Dry-run registrado: {log_path}[/dim]")

    executed = [a for a in actions if a.status == "ejecutado"]
    if executed:
        console.print(f"[green]{len(executed)} órdenes enviadas[/green]")


@app.command()
def status() -> None:
    """Muestra la cuenta paper, posiciones y últimas órdenes."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    broker = get_broker(settings, DEFAULT_DB)
    snap = broker.snapshot()

    console.print(
        Panel(
            f"Cash: {snap['cash']:,.2f} · Posiciones: {snap['positions_value']:,.2f} · "
            f"Equity: [bold]{snap['equity']:,.2f}[/bold]",
            title=f"Cuenta paper · modo {settings.mode}",
        )
    )

    if snap["positions"]:
        t = Table(title="Posiciones")
        for col in ("Ticker", "Qty", "Precio medio", "Valor", "PnL no realizado"):
            t.add_column(col, justify="right" if col != "Ticker" else "left")
        for p in snap["positions"]:
            t.add_row(
                p["ticker"],
                f"{p['qty']:g}",
                f"{p['avg_price']:,.2f}",
                f"{p['value']:,.2f}",
                f"{p['unrealized']:,.2f}",
            )
        console.print(t)

    with connect(DEFAULT_DB) as con:
        orders = con.execute(
            "SELECT ts, ticker, side, qty, status, bot FROM orders ORDER BY id DESC LIMIT 10"
        ).fetchall()

    if orders:
        t = Table(title="Últimas órdenes")
        for col in ("Fecha", "Ticker", "Lado", "Qty", "Estado", "Bot"):
            t.add_column(col)
        for o in orders:
            t.add_row(o["ts"][:19], o["ticker"], o["side"], f"{o['qty']:g}", o["status"], o["bot"] or "")
        console.print(t)


@app.command("llm-test")
def llm_test(
    prompt: str = typer.Option(
        "Devuelve un JSON con las claves ok (true) y modelo (string).",
        "--prompt",
    )
) -> None:
    """Prueba el servidor LLM local y el modo JSON."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    client = LLMClient(settings.llm, DEFAULT_DB)

    try:
        health = client.health()
        console.print(f"[bold]Servidor:[/bold] {health['base_url']}")
        console.print(f"[bold]Modelos:[/bold] {', '.join(health['models']) or '(ninguno)'}")
        lm = health.get("lmstudio") or {}
        if lm.get("context"):
            ctx = lm["context"]
            style = "green" if ctx >= 16_384 else "yellow"
            console.print(f"[bold]Contexto cargado:[/bold] [{style}]{ctx:,} tokens[/{style}]")
            if ctx < 16_384:
                console.print(
                    "[yellow]Aviso:[/yellow] los agentes de TradingAgents necesitan "
                    "≥16k. Recarga con: lms load qwen3.8-27b --context-length 32768"
                )
    except Exception as exc:
        console.print(f"[red]No se pudo conectar:[/red] {exc}")
        raise typer.Exit(1)

    try:
        result = client.chat_json([{"role": "user", "content": prompt}], purpose="llm-test")
        console.print(f"[green]JSON OK:[/green] {result}")
    except Exception as exc:
        console.print(f"[red]Falló la llamada:[/red] {exc}")
        raise typer.Exit(1)


@app.command()
def report() -> None:
    """Resumen de rendimiento de la cuenta paper."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    broker = get_broker(settings, DEFAULT_DB)
    eq = broker.equity_series()

    if len(eq) < 2:
        console.print("[yellow]Aún no hay historial de equity suficiente.[/yellow]")
        return

    total = eq.iloc[-1] / eq.iloc[0] - 1
    dd = (eq / eq.cummax() - 1).min()
    rets = eq.pct_change().dropna()
    sharpe = rets.mean() / rets.std() * (252**0.5) if len(rets) > 1 and rets.std() > 0 else 0.0

    t = Table(title="Rendimiento paper")
    t.add_column("Métrica", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Equity inicial", f"{eq.iloc[0]:,.2f}")
    t.add_row("Equity actual", f"{eq.iloc[-1]:,.2f}")
    t.add_row("Retorno", _fmt_pct(total))
    t.add_row("Max drawdown", _fmt_pct(float(dd)))
    t.add_row("Sharpe", f"{sharpe:.2f}")
    t.add_row("Snapshots", str(len(eq)))
    console.print(t)

    state = load_killswitch(DEFAULT_DB)
    if state.active:
        console.print(Panel(f"KILL SWITCH: {state.reason}", style="bold red"))
    else:
        evaluation = evaluate_killswitch(eq, settings.risk, tz=settings.timezone)
        if evaluation.active:
            console.print(
                Panel(
                    f"KILL SWITCH se activaría ahora: {evaluation.reason}",
                    style="bold red",
                )
            )


@app.command("journal")
def journal_cmd(
    bot: str = typer.Option(None, "--bot", help="Filtrar por id de bot"),
    account: str = typer.Option(None, "--account", help="Filtrar por cuenta"),
    profile: str = typer.Option(None, "--profile", help="Filtrar por perfil"),
    ticker: str = typer.Option(None, "--ticker", help="Filtrar por activo"),
    since: str = typer.Option(None, "--since", help="Desde YYYY-MM-DD"),
    until: str = typer.Option(None, "--until", help="Hasta YYYY-MM-DD"),
    group_by: str = typer.Option(
        "bot",
        "--group-by",
        help="bot | account | profile | ticker | day | hour",
    ),
    limit: int = typer.Option(15, "--limit", help="Últimas operaciones a mostrar"),
) -> None:
    """Diario de operaciones cerradas reconstruido desde lab.db (solo lectura)."""
    from .journal import MIN_SAMPLE, build_journal

    settings = get_settings()
    try:
        payload = build_journal(
            DEFAULT_DB,
            tz=settings.timezone,
            bot=bot,
            account=account,
            profile=profile,
            ticker=ticker,
            since=since,
            until=until,
            group_by=group_by,
            limit=limit,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    diag = payload["diagnostics"]
    summary = payload["summary"]
    if diag.get("error"):
        console.print(f"[yellow]{diag['error']}[/yellow]")
    console.print(
        f"[dim]lab.db: {diag.get('fills_total', 0)} fills · "
        f"{diag.get('closed_trades', 0)} operaciones cerradas · "
        f"{diag.get('open_lots_qty', 0):g} lotes abiertos · "
        f"{diag.get('unmatched_sell_qty', 0):g} ventas sin lote[/dim]"
    )
    if diag.get("bots_sin_cuenta"):
        console.print(
            "[dim]Sin cuenta en config/bots.yaml: "
            + ", ".join(diag["bots_sin_cuenta"])
            + "[/dim]"
        )

    if summary["n"] == 0:
        console.print(Panel("Sin datos: no hay operaciones cerradas con estos filtros.", style="yellow"))
        return

    t = Table(title="Diario · resumen")
    t.add_column("Métrica", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Operaciones", str(summary["n"]))
    t.add_row("Neto", f"{summary['net_pnl']:,.2f}")
    t.add_row("Retorno", _fmt_pct(summary["total_return"]) if summary["total_return"] is not None else "sin datos")
    t.add_row("Win rate", _fmt_pct(summary["win_rate"]) if summary["win_rate"] is not None else "sin datos")
    t.add_row("Profit factor", f"{summary['profit_factor']:.2f}" if summary["profit_factor"] is not None else "sin datos")
    t.add_row("Expectancy", f"{summary['expectancy']:,.2f}" if summary["expectancy"] is not None else "sin datos")
    t.add_row("Sharpe", f"{summary['sharpe']:.2f}" if summary["sharpe"] is not None else "sin datos")
    t.add_row("Sortino", f"{summary['sortino']:.2f}" if summary["sortino"] is not None else "sin datos")
    t.add_row("Calmar", f"{summary['calmar']:.2f}" if summary["calmar"] is not None else "sin datos")
    t.add_row("MaxDD", _fmt_pct(summary["max_drawdown"]) if summary["max_drawdown"] is not None else "sin datos")
    t.add_row("MaxDD USD", f"{summary['max_drawdown_usd']:,.2f}" if summary["max_drawdown_usd"] is not None else "sin datos")
    t.add_row("Capital atribuido", f"{summary['capital']:,.2f}" if summary["capital"] is not None else "sin datos")
    t.add_row("Rango", f"{summary['first_day'] or 'sin datos'} → {summary['last_day'] or 'sin datos'}")
    if summary["sample_warning"]:
        t.add_row("Muestra", f"[yellow]{summary['sample_warning']}[/yellow]")
    console.print(t)

    conc = summary["concentration"]
    c = Table(title="Concentración")
    c.add_column("Métrica", style="bold")
    c.add_column("Valor", justify="right")
    c.add_row("Top 3 / beneficio neto", _fmt_pct(conc["top3_share"]) if conc["top3_share"] is not None else "sin datos")
    c.add_row("Top 3 / beneficio bruto", _fmt_pct(conc["top3_gross_share"]) if conc["top3_gross_share"] is not None else "sin datos")
    c.add_row("Mejor día", f"{conc['best_day'] or 'sin datos'} · {conc['best_day_pnl']:,.2f}" if conc["best_day_pnl"] is not None else "sin datos")
    c.add_row("Mejor día / neto", _fmt_pct(conc["best_day_share"]) if conc["best_day_share"] is not None else "sin datos")
    c.add_row("Regla de consistencia", _fmt_pct(conc["consistency_pct"]) if conc["consistency_pct"] is not None else (summary["consistency_note"] or "sin datos"))
    if conc["consistency_ok"] is not None:
        c.add_row("Cumple", "[green]sí[/green]" if conc["consistency_ok"] else "[red]no[/red]")
    console.print(c)

    dist = summary["distribution"]
    d = Table(title="Distribución de retornos por operación")
    d.add_column("Estadístico", style="bold")
    d.add_column("Valor", justify="right")
    for label, key in (
        ("N", "n"),
        ("Mín", "min"),
        ("P5", "p5"),
        ("P25", "p25"),
        ("Mediana", "median"),
        ("P75", "p75"),
        ("P95", "p95"),
        ("Máx", "max"),
        ("Media", "mean"),
        ("Desv. típica", "stdev"),
    ):
        value = dist[key]
        d.add_row(label, f"{value:.4%}" if key not in ("n",) and value is not None else ("sin datos" if value is None else str(value)))
    console.print(d)

    group_rows = payload["groups"]
    g = Table(title=f"Agrupado por {group_by}")
    for col in ("Grupo", "N", "Neto", "Retorno", "Win", "PF", "Exp.", "Sharpe", "MaxDD", "Muestra"):
        g.add_column(col, justify="left" if col == "Grupo" else "right")
    for row in group_rows:
        g.add_row(
            str(row["key"]),
            str(row["n"]),
            f"{row['net_pnl']:,.2f}",
            _fmt_pct(row["total_return"]) if row["total_return"] is not None else "sin datos",
            _fmt_pct(row["win_rate"]) if row["win_rate"] is not None else "sin datos",
            f"{row['profit_factor']:.2f}" if row["profit_factor"] is not None else "sin datos",
            f"{row['expectancy']:,.2f}" if row["expectancy"] is not None else "sin datos",
            f"{row['sharpe']:.2f}" if row["sharpe"] is not None else "sin datos",
            _fmt_pct(row["max_drawdown"]) if row["max_drawdown"] is not None else "sin datos",
            "ok" if row["sample_ok"] else f"N<{MIN_SAMPLE}",
        )
    console.print(g)

    t2 = Table(title=f"Últimas {len(payload['trades'])} operaciones cerradas")
    for col in ("Salida", "Bot", "Cuenta", "Perfil", "Activo", "Qty", "Entrada", "Salida", "PnL", "Ret.", "Horas"):
        t2.add_column(col, justify="left" if col in ("Salida", "Bot", "Cuenta", "Perfil", "Activo") else "right")
    for trade in payload["trades"]:
        t2.add_row(
            trade["exit_ts"][:19],
            trade["bot"],
            trade["account"] or "sin datos",
            trade["profile"] or "sin datos",
            trade["ticker"],
            f"{trade['qty']:g}",
            f"{trade['entry_price']:,.5f}",
            f"{trade['exit_price']:,.5f}",
            f"{trade['pnl']:,.2f}",
            _fmt_pct(trade["return_pct"]),
            f"{trade['holding_hours']:.1f}" if trade["holding_hours"] is not None else "sin datos",
        )
    console.print(t2)


@app.command("drift")
def drift_cmd(
    min_trades: int = typer.Option(
        20, "--min-trades", help="Operaciones live mínimas antes de opinar"
    ),
) -> None:
    """Deriva live/paper vs backtest por bot (solo informativo)."""
    from .drift import build_drift

    settings = get_settings()
    payload = build_drift(DEFAULT_DB, settings, min_trades=min_trades)
    summary = payload["summary"]
    console.print(
        f"[dim]{payload['bootstrap_paths']} bootstrap · semilla {payload['seed']} · "
        f"mínimo {payload['min_trades']} operaciones · supuesto slippage "
        f"{payload['backtest_slippage_bps']:.1f} bps[/dim]"
    )
    t = Table(title="Deriva live vs backtest")
    for col in ("Bot", "N", "Sharpe live", "IC 95%", "Sharpe BT", "Expect.", "Slippage", "Estado"):
        t.add_column(col, justify="left" if col == "Bot" else "right")
    for row in payload["bots"]:
        live = row["live"]
        bt = row["backtest"]
        slip = row["slippage"]
        ci = live["sharpe_ci95"]
        ci_text = (
            f"{ci[0]:.2f}…{ci[1]:.2f}"
            if ci and ci[0] is not None and ci[1] is not None
            else "sin datos"
        )
        t.add_row(
            row["bot"],
            str(live["n"]),
            f"{live['sharpe']:.2f}" if live["sharpe"] is not None else "sin datos",
            ci_text,
            f"{bt['sharpe']:.2f}" if bt["sharpe"] is not None else "sin datos",
            f"{live['expectancy']:.2f}" if live["expectancy"] is not None else "sin datos",
            f"{slip['p50_bps']:.1f}/{slip['p95_bps']:.1f}"
            if slip["p50_bps"] is not None and slip["p95_bps"] is not None
            else "sin datos",
            row["status"],
        )
    console.print(t)
    console.print(
        f"[dim]ok={summary.get('ok', 0)} · vigilar={summary.get('vigilar', 0)} · "
        f"deriva={summary.get('deriva', 0)} · sin datos={summary.get('sin datos', 0)}[/dim]"
    )
    for row in payload["bots"]:
        if row["status"] in {"vigilar", "deriva"}:
            console.print(f"[yellow]{row['bot']}[/yellow]: " + "; ".join(row["reasons"]))


@killswitch_app.command("status")
def killswitch_status_cmd() -> None:
    """Estado persistido y evaluación actual del kill-switch."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    state = load_killswitch(DEFAULT_DB)

    current = None
    series = None
    try:
        broker = get_broker(settings, DEFAULT_DB)
        snap = broker.snapshot({})
        current = float(snap["equity"])
        series = broker.equity_series()
    except Exception as exc:
        console.print(f"[dim]No se pudo leer el broker para evaluar: {exc}[/dim]")

    evaluation = (
        evaluate_killswitch(series, settings.risk, current=current, tz=settings.timezone)
        if current is not None
        else None
    )

    t = Table(title="Kill-switch")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    t.add_row("Estado", "[red]ACTIVO[/red]" if state.active else "[green]inactivo[/green]")
    t.add_row("Razón", state.reason or "—")
    t.add_row("Disparado", state.triggered_at or "—")
    t.add_row("Reset", state.reset_at or "—")
    if evaluation:
        t.add_row("Equity actual", f"{evaluation.equity:,.2f}")
        t.add_row("Pico", f"{evaluation.peak:,.2f}")
        t.add_row("Inicio del día", f"{evaluation.day_start:,.2f}")
        t.add_row("Pérdida diaria", _fmt_pct(evaluation.daily_return))
        t.add_row("Drawdown", _fmt_pct(evaluation.drawdown))
    console.print(t)

    if not state.active and evaluation and evaluation.active:
        console.print(
            Panel(
                f"El kill-switch se activaría en la próxima orden: {evaluation.reason}",
                style="bold red",
            )
        )
    if state.active:
        console.print(
            "[yellow]Solo se permiten cierres/reducciones. Reset manual:[/yellow] "
            "lab killswitch reset"
        )


@killswitch_app.command("test")
def killswitch_test_cmd() -> None:
    """Prueba sintética de los dos disparadores, sin tocar la DB."""
    cfg = get_settings().risk
    now = pd.Timestamp("2026-11-05 18:00", tz="UTC")
    scenarios = [
        ("normal", pd.Series([100_000.0, 100_100.0, 100_050.0]), None, cfg),
        ("pérdida diaria", pd.Series([100_000.0, 100_000.0, 96_000.0]), None, cfg),
        (
            "drawdown",
            pd.Series([100_000.0, 110_000.0, 120_000.0, 90_000.0]),
            None,
            cfg.model_copy(update={"daily_loss_limit_pct": 0.5}),
        ),
        ("equity actual", pd.Series([100_000.0, 100_000.0, 100_000.0]), 96_000.0, cfg),
    ]

    t = Table(title="Kill-switch · pruebas sintéticas")
    t.add_column("Escenario", style="bold")
    t.add_column("Activo")
    t.add_column("Razón", overflow="fold")
    t.add_column("Diario", justify="right")
    t.add_column("Drawdown", justify="right")
    for name, series, current, rules in scenarios:
        ev = evaluate_killswitch(series, rules, current=current, tz="UTC", now=now)
        t.add_row(
            name,
            "[red]sí[/red]" if ev.active else "[green]no[/green]",
            ev.reason,
            _fmt_pct(ev.daily_return),
            _fmt_pct(ev.drawdown),
        )
    console.print(t)


@killswitch_app.command("reset")
def killswitch_reset_cmd(
    yes: bool = typer.Option(False, "--yes", help="No pedir confirmación interactiva"),
) -> None:
    """Reset manual y confirmado del kill-switch."""
    init_db(DEFAULT_DB)
    state = load_killswitch(DEFAULT_DB)
    if not state.active:
        console.print("[green]El kill-switch ya está inactivo.[/green]")
        return
    if not yes:
        confirmed = typer.confirm(
            f"Kill-switch activo: {state.reason}. ¿Confirmas el reset manual?"
        )
        if not confirmed:
            console.print("[yellow]Reset cancelado.[/yellow]")
            raise typer.Exit(1)
    new_state = reset_killswitch(DEFAULT_DB, confirm=True)
    console.print(f"[green]Kill-switch reseteado[/green] · reset_at={new_state.reset_at}")


@alerts_app.command("status")
def alerts_status_cmd() -> None:
    """Estado de configuración y últimas alertas (sin mostrar secretos)."""
    cfg = AlertConfig.from_env()
    t = Table(title="Alertas")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    t.add_row("Canal", cfg.channel)
    t.add_row("Configurado", "sí" if cfg.configured else "no")
    t.add_row("Habilitado", "sí" if cfg.enabled else "no")
    t.add_row("Cooldown", f"{cfg.cooldown_s} s")
    t.add_row("Heartbeat", "configurado" if cfg.heartbeat_url else "no")
    console.print(t)

    rows = last_alerts(8)
    if rows:
        h = Table(title="Últimas alertas")
        for col in ("Fecha", "Evento", "Severidad", "Canal", "OK", "Error"):
            h.add_column(col)
        for row in rows:
            h.add_row(
                str(row["ts"])[:19],
                str(row["event"]),
                str(row["severity"] or ""),
                str(row["channel"] or ""),
                "sí" if row["ok"] else "no",
                str(row["error"] or ""),
            )
        console.print(h)


@alerts_app.command("test")
def alerts_test_cmd() -> None:
    """Envía una alerta de prueba por el canal configurado."""
    result = send_alert("test", "Prueba de alertas de TradingLab", severity="info")
    console.print(
        f"Canal={result.channel} ok={result.ok} skipped={result.skipped} error={result.error or '—'}"
    )


@alerts_app.command("send")
def alerts_send_cmd(
    event: str = typer.Argument(..., help="Identificador del evento"),
    message: str = typer.Option(..., "--message", "-m", help="Texto de la alerta"),
    severity: str = typer.Option("warning", "--severity", help="info|warning|error|critical"),
) -> None:
    """Envía una alerta manual."""
    result = send_alert(event, message, severity=severity)
    console.print(
        f"Canal={result.channel} ok={result.ok} skipped={result.skipped} error={result.error or '—'}"
    )


@alerts_app.command("heartbeat")
def alerts_heartbeat_cmd() -> None:
    """Ping de latido (healthchecks.io o similar)."""
    result = heartbeat()
    console.print(f"Heartbeat ok={result.ok} skipped={result.skipped} error={result.error or '—'}")
    if not result.ok:
        raise typer.Exit(1)


@alerts_app.command("check")
def alerts_check_cmd() -> None:
    """Comprueba LM Studio, broker y MT5; alerta solo de los fallos."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    checks: list[tuple[str, bool, str]] = []

    try:
        LLMClient(settings.llm).health()
        checks.append(("LM Studio", True, "ok"))
    except Exception as exc:
        checks.append(("LM Studio", False, str(exc)[:160]))
        send_alert("llm_fail", f"LM Studio no responde: {exc}", severity="error")

    try:
        get_broker(settings, DEFAULT_DB).snapshot({})
        checks.append((f"Broker {settings.execution.broker}", True, "ok"))
    except Exception as exc:
        checks.append((f"Broker {settings.execution.broker}", False, str(exc)[:160]))
        send_alert("broker_fail", f"Broker no responde: {exc}", severity="error")

    if settings.mt5.login or settings.mt5.terminal_path:
        broker = None
        try:
            broker = get_mt5_broker(settings, DEFAULT_DB, dry_run=True)
            broker.connect()
            health = broker.health()
            checks.append(("MT5", True, f"{health['login']} · {health['server']}"))
        except Exception as exc:
            checks.append(("MT5", False, str(exc)[:160]))
            send_alert("mt5_fail", f"MT5 no responde: {exc}", severity="error")
        finally:
            if broker is not None:
                try:
                    broker.shutdown()
                except Exception:
                    pass

    dryruns = sorted((ROOT / "data" / "dryrun").glob("dryrun_*.json"), reverse=True)
    if not dryruns:
        checks.append(("Dry-run diario", False, "sin registros"))
        send_alert("dryrun_missed", "No hay ningún dry-run registrado", severity="warning")
    else:
        age_h = round((datetime.now().timestamp() - dryruns[0].stat().st_mtime) / 3600)
        checks.append(("Dry-run diario", age_h <= 72, f"último hace {age_h} h"))
        if age_h > 72:
            send_alert("dryrun_missed", f"Último dry-run hace {age_h} h", severity="warning")

    t = Table(title="Chequeo de servicios")
    t.add_column("Componente", style="bold")
    t.add_column("Estado")
    t.add_column("Detalle", overflow="fold")
    for name, ok, detail in checks:
        t.add_row(name, "[green]OK[/green]" if ok else "[red]FALLO[/red]", detail)
    console.print(t)
    if any(not ok for _, ok, _ in checks):
        raise typer.Exit(1)


@app.command("reconcile")
def reconcile_cmd(
    mt5: bool = typer.Option(False, "--mt5", help="Reconciliar contra la cuenta MT5 en vez del broker"),
) -> None:
    """Compara posiciones/equity del broker con SQLite y alerta diferencias."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    broker = None
    source = "mt5" if mt5 else settings.execution.broker
    try:
        if mt5:
            broker = get_mt5_broker(settings, DEFAULT_DB, dry_run=True)
            broker.connect()
        else:
            broker = get_broker(settings, DEFAULT_DB)
        result = reconcile_broker(broker, DEFAULT_DB, source=source)
    except Exception as exc:
        console.print(Panel(f"Reconciliación falló: {exc}", style="bold red"))
        raise typer.Exit(1)
    finally:
        if mt5 and broker is not None:
            try:
                broker.shutdown()
            except Exception:
                pass

    t = Table(title=f"Reconciliación · {result.source}")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Estado", "[green]ok[/green]" if result.status == "ok" else "[red]mismatch[/red]")
    t.add_row("Equity broker", f"{result.broker_equity:,.2f}" if result.broker_equity is not None else "—")
    t.add_row("Equity DB", f"{result.db_equity:,.2f}" if result.db_equity is not None else "—")
    t.add_row("Diferencia", f"{result.diff_equity:,.2f}" if result.diff_equity is not None else "—")
    t.add_row("Posiciones broker", str(result.broker_positions))
    t.add_row("Posiciones DB", str(result.db_positions))
    t.add_row("Posiciones distintas", str(result.diff_positions))
    t.add_row("Detalle", result.details or "sin diferencias")
    console.print(t)
    if result.status != "ok":
        raise typer.Exit(1)


@f13_app.command("status")
def f13_status_cmd() -> None:
    """Estado del pilot F13 y hash de configuración."""
    init_db(DEFAULT_DB)
    row = f13_status(DEFAULT_DB)
    criteria = f13_criteria()
    t = Table(title="F13 · estado")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", overflow="fold")
    if row:
        t.add_row("Bot", row["bot"])
        t.add_row("Símbolo", row["symbol"])
        t.add_row("Inicio", row["start_date"])
        t.add_row("Congelado", row["frozen_at"])
        t.add_row("Hash", row["config_hash"][:16] + "…")
    else:
        t.add_row("Estado", "no iniciado")
        t.add_row("Ventana", f"{criteria['window_weeks']} semanas")
        t.add_row("Trades esperados", f"{criteria['expected_trades_8w_low']}–{criteria['expected_trades_8w_high']}")
        t.add_row("Extensión de edge", criteria["edge_extension"])
    console.print(t)

    check = f13_config_check(DEFAULT_DB)
    if check["status"] == "changed":
        console.print(
            Panel(
                "La configuración cambió respecto al hash congelado. "
                "F13 queda invalidado hasta revisión humana.",
                style="bold red",
            )
        )


@f13_app.command("freeze")
def f13_freeze_cmd(
    bot: str = typer.Option("qqq-trend-f13", "--bot"),
    start: str = typer.Option(None, "--start", help="YYYY-MM-DD (por defecto hoy)"),
    yes: bool = typer.Option(False, "--yes", help="No pedir confirmación"),
) -> None:
    """Congela criterios y hash. No activa el bot."""
    init_db(DEFAULT_DB)
    specs = {spec.id: spec for spec in load_bots()}
    spec = specs.get(bot)
    if spec is None:
        console.print(f"[red]Bot no encontrado:[/red] {bot}")
        raise typer.Exit(2)
    if spec.enabled:
        console.print("[red]No se congela un bot enabled.[/red] F13 debe empezar con enabled:false.")
        raise typer.Exit(2)
    if not yes:
        if not typer.confirm(f"¿Congelar F13 con {bot} desde {start or _today()}?"):
            raise typer.Exit(1)
    row = f13_freeze(
        DEFAULT_DB,
        bot=bot,
        symbol=spec.universe[0],
        start_date=start or _today(),
    )
    console.print(
        f"[green]F13 congelado[/green] · bot={row['bot']} · hash={row['config_hash'][:16]}…"
    )
    console.print("[yellow]El bot sigue enabled:false; la activación requiere tu aprobación.[/yellow]")


@f13_app.command("report")
def f13_report_cmd() -> None:
    """Registra un snapshot y muestra el estado de F13 frente a SPY."""
    init_db(DEFAULT_DB)
    row = f13_status(DEFAULT_DB)
    if not row:
        console.print("[yellow]F13 no iniciado. Criterios:[/yellow]")
        console.print_json(data=f13_criteria())
        return

    settings = get_settings()
    broker = get_broker(settings, DEFAULT_DB)
    spy_close = None
    spy_total = None
    try:
        spy = data_mod.fetch("SPY", row["start_date"], _today(), settings.data.cache_dir)
        spy_close = float(spy["close"].iloc[-1])
        spy_total = spy_close / float(spy["close"].iloc[0]) - 1.0
    except Exception as exc:
        console.print(f"[dim]No se pudo leer SPY: {exc}[/dim]")

    specs = {spec.id: spec for spec in load_bots()}
    spec = specs.get(row["bot"])
    backtest_metrics = None
    if spec is not None:
        try:
            df = data_mod.fetch(
                spec.universe[0], row["start_date"], _today(), settings.data.cache_dir
            )
            strategy = STRATEGIES[spec.strategy](df, **spec.params)
            bt = run_backtest(
                df,
                strategy.target,
                starting_cash=settings.starting_cash,
                commission_bps=settings.execution.commission_bps,
                slippage_bps=settings.execution.slippage_bps,
                max_gross=spec.exposure,
            )
            backtest_metrics = bt.metrics
        except Exception as exc:
            console.print(f"[dim]No se pudo ejecutar el backtest de comparación: {exc}[/dim]")

    snap = f13_record(DEFAULT_DB, broker, bot=row["bot"], spy_close=spy_close)
    with connect(DEFAULT_DB) as con:
        first = con.execute("SELECT equity, ts FROM f13_metrics ORDER BY id ASC LIMIT 1").fetchone()
        count = con.execute("SELECT COUNT(*) AS n FROM f13_metrics").fetchone()["n"]
        orders = con.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE bot = ?", (row["bot"],)
        ).fetchone()["n"]

    total = snap["equity"] / float(first["equity"]) - 1.0 if first and first["equity"] else 0.0
    t = Table(title=f"F13 · {row['bot']} · desde {row['start_date']}")
    t.add_column("Métrica", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Equity", f"{snap['equity']:,.2f}")
    t.add_row("Retorno F13", _fmt_pct(total))
    t.add_row("Drawdown actual", _fmt_pct(snap["drawdown"]))
    if spy_total is not None:
        t.add_row("Retorno SPY (mismo periodo)", _fmt_pct(spy_total))
    if backtest_metrics:
        t.add_row("Retorno backtest", _fmt_pct(float(backtest_metrics["total_return"])))
        t.add_row("Sharpe backtest", f"{float(backtest_metrics['sharpe']):.2f}")
        t.add_row("MaxDD backtest", _fmt_pct(float(backtest_metrics["max_drawdown"])))
        t.add_row("Trades backtest", str(backtest_metrics["num_trades"]))
    t.add_row("Snapshots", str(count))
    t.add_row("Órdenes del bot", str(orders))
    exec_metrics = f13_execution(DEFAULT_DB, bot=row["bot"], start_date=row["start_date"])
    t.add_row(
        "Slippage p50 / p95",
        f"{_fmt_pct((exec_metrics['slippage_p50_bps'] or 0) / 10_000)} / "
        f"{_fmt_pct((exec_metrics['slippage_p95_bps'] or 0) / 10_000)}",
    )
    t.add_row("Error tamaño máx.", f"{exec_metrics['size_error_max']:g}")
    console.print(t)
    console.print("[dim]F13 no cambia enabled; el pilot solo se activa con aprobación humana.[/dim]")


@f13_app.command("check")
def f13_check_cmd() -> None:
    """Comprueba las paradas duras de F13 y alerta si alguna falla."""
    init_db(DEFAULT_DB)
    row = f13_status(DEFAULT_DB)
    if not row:
        console.print("[yellow]F13 no iniciado; no hay paradas que comprobar.[/yellow]")
        return

    criteria = f13_criteria()
    checks: list[tuple[str, bool, str]] = []
    config = f13_config_check(DEFAULT_DB)
    checks.append(("Hash de config", config["ok"], config["status"]))
    ks = load_killswitch(DEFAULT_DB)
    checks.append(("Kill-switch", not ks.active, ks.reason if ks.active else "inactivo"))
    rec = last_reconciliation(DEFAULT_DB)
    checks.append(
        ("Reconciliación", bool(rec and rec.get("status") == "ok"), (rec or {}).get("status", "sin ejecutar"))
    )
    dryruns = sorted((ROOT / "data" / "dryrun").glob("dryrun_*.json"), reverse=True)
    age_h = round((datetime.now().timestamp() - dryruns[0].stat().st_mtime) / 3600) if dryruns else 999
    checks.append(("Ciclo diario", age_h <= 72, f"último hace {age_h} h"))

    exec_metrics = f13_execution(DEFAULT_DB, bot=row["bot"], start_date=row["start_date"])
    if exec_metrics["fills"]:
        p50 = exec_metrics["slippage_p50_bps"] or 0.0
        p95 = exec_metrics["slippage_p95_bps"] or 0.0
        checks.append(
            ("Slippage", p50 <= criteria["max_slippage_bps_p50"] and p95 <= criteria["max_slippage_bps_p95"],
             f"p50={p50:.1f} bps · p95={p95:.1f} bps")
        )
        checks.append(
            ("Tamaño", exec_metrics["size_error_max"] <= criteria["max_size_error_shares"],
             f"error máx={exec_metrics['size_error_max']:g}")
        )

    t = Table(title="F13 · paradas duras")
    t.add_column("Chequeo", style="bold")
    t.add_column("Estado")
    t.add_column("Detalle", overflow="fold")
    for name, ok, detail in checks:
        t.add_row(name, "[green]OK[/green]" if ok else "[red]FALLO[/red]", detail)
    console.print(t)

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        send_alert("f13_stop", f"Paradas duras F13: {', '.join(failed)}", severity="critical")
        raise typer.Exit(1)


@f13_app.command("signal-check")
def f13_signal_check_cmd(bot: str = typer.Option("qqq-trend-f13", "--bot")) -> None:
    """Recalcula la señal del bot con los mismos datos y la compara con la última."""
    settings = get_settings()
    specs = {spec.id: spec for spec in load_bots()}
    spec = specs.get(bot)
    if spec is None:
        console.print(f"[red]Bot no encontrado:[/red] {bot}")
        raise typer.Exit(2)
    result = f13_signal_check(settings, spec, DEFAULT_DB)
    if not result.get("ok"):
        console.print(f"[red]{result.get('error')}[/red]")
        raise typer.Exit(1)
    console.print(
        f"{result['ticker']} · target={result['target']:.0%} · precio={result['price']:,.2f} "
        f"· ATR={result['atr']:,.2f}"
    )
    if result.get("last_signal"):
        console.print(f"Última señal: {result['last_signal']}")
        console.print(
            f"Coincide: {'sí' if result.get('match') else 'NO' if result.get('match') is False else 'sin datos'}"
        )
    else:
        console.print("[yellow]Sin señales registradas todavía; ejecuta el bot en paper (no dry-run).[/yellow]")


@f13_app.command("config-check")
def f13_config_check_cmd() -> None:
    """Comprueba que config/*.yaml no cambió desde el freeze."""
    check = f13_config_check(DEFAULT_DB)
    console.print(check)
    if not check["ok"]:
        raise typer.Exit(1)


def _sec_client() -> SecClient:
    settings = get_settings()
    return SecClient(cache_dir=settings.data.cache_dir / "sec", db_path=DEFAULT_DB)


@sec_app.command("status")
def sec_status_cmd() -> None:
    """Estado del cliente SEC, caché y últimas consultas."""
    client = _sec_client()
    try:
        state = client.status()
    finally:
        client.close()
    t = Table(title="SEC EDGAR · estado")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", overflow="fold")
    t.add_row("User-Agent", "válido" if state["user_agent_ok"] else "falta o inválido")
    t.add_row("Caché", state["cache_dir"])
    t.add_row("Rate limit", f"{state['min_interval_s']:.2f} s entre peticiones")
    console.print(t)
    if not state["user_agent_ok"]:
        console.print("[yellow]Define SEC_USER_AGENT con contacto antes de consultar.[/yellow]")
        return
    if state["last"]:
        last = Table(title="Últimas consultas SEC")
        for col in ("Fecha", "Endpoint", "CIK", "Estado", "HTTP", "Caché", "Error"):
            last.add_column(col)
        for row in state["last"]:
            last.add_row(
                str(row["ts"])[:19],
                str(row["endpoint"]),
                str(row["cik"] or ""),
                str(row["status"]),
                str(row["http_status"] or ""),
                "sí" if row["cache_hit"] else "no",
                str(row["error"] or ""),
            )
        console.print(last)


@sec_app.command("cik")
def sec_cik_cmd(ticker: str = typer.Argument(..., help="Ticker, ej. NVDA")) -> None:
    """Resuelve el CIK de un ticker usando company_tickers.json."""
    client = _sec_client()
    try:
        result = client.cik_for_ticker(ticker)
    finally:
        client.close()
    if result.status == "ok":
        console.print(f"{result.data['ticker']} · CIK {result.data['cik']} · {result.data.get('title')}")
        return
    console.print(f"[yellow]SEC {result.status}:[/yellow] {result.error or 'sin resultado'}")
    if result.status in {"error", "unconfigured"}:
        raise typer.Exit(1)


@sec_app.command("filings")
def sec_filings_cmd(
    ticker: str = typer.Argument(..., help="Ticker, ej. NVDA"),
    forms: str = typer.Option("10-K,10-Q,8-K", "--forms"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """Lista filings recientes de SEC (10-K, 10-Q, 8-K)."""
    client = _sec_client()
    try:
        result = client.submissions(
            ticker,
            forms=[x.strip().upper() for x in forms.split(",") if x.strip()],
            limit=limit,
        )
    finally:
        client.close()

    if result.status == "empty":
        console.print(f"[yellow]SEC respondió sin filings para {ticker.upper()}.[/yellow]")
        return
    if not result.usable and result.status != "stale":
        console.print(f"[red]SEC {result.status}:[/red] {result.error}")
        raise typer.Exit(1)
    if result.stale:
        console.print("[yellow]Aviso: datos de caché obsoletos; SEC no respondió.[/yellow]")
    data = result.data or {}
    t = Table(title=f"SEC filings · {data.get('ticker')} · CIK {data.get('cik')}")
    for col in ("Form", "Filed", "Report", "Accession", "Documento"):
        t.add_column(col)
    for filing in data.get("filings") or []:
        t.add_row(
            str(filing.get("form") or ""),
            str(filing.get("filingDate") or ""),
            str(filing.get("reportDate") or ""),
            str(filing.get("accessionNumber") or ""),
            str(filing.get("primaryDocument") or ""),
        )
    console.print(t)


@sec_app.command("facts")
def sec_facts_cmd(ticker: str = typer.Argument(..., help="Ticker, ej. NVDA")) -> None:
    """Extrae hechos XBRL clave de companyfacts."""
    client = _sec_client()
    try:
        result = client.company_facts(ticker)
    finally:
        client.close()

    if result.status == "empty":
        console.print(f"[yellow]SEC respondió sin key facts para {ticker.upper()}.[/yellow]")
        return
    if not result.usable and result.status != "stale":
        console.print(f"[red]SEC {result.status}:[/red] {result.error}")
        raise typer.Exit(1)
    if result.stale:
        console.print("[yellow]Aviso: datos de caché obsoletos; SEC no respondió.[/yellow]")
    data = result.data or {}
    t = Table(title=f"SEC company facts · {data.get('ticker')} · CIK {data.get('cik')}")
    for col in ("Tag", "Valor", "Unidad", "Periodo", "FY", "FP", "Form"):
        t.add_column(col, justify="right" if col in {"Valor"} else "left")
    for fact in data.get("key_facts") or []:
        t.add_row(
            str(fact.get("tag")),
            str(fact.get("value")),
            str(fact.get("unit")),
            str(fact.get("end")),
            str(fact.get("fy") or ""),
            str(fact.get("fp") or ""),
            str(fact.get("form") or ""),
        )
    console.print(t)


@intel_app.command("fetch")
def intel_fetch_cmd(
    source: str = typer.Option(None, "--source", help="Feed concreto de config/intel.yaml"),
    limit: int = typer.Option(30, "--limit"),
) -> None:
    """Descarga RSS, lo sanea y lo guarda con deduplicación. No ejecuta nada."""
    path = ROOT / "config" / "intel.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    feeds = (raw or {}).get("feeds", {})
    if source:
        if source not in feeds:
            console.print(f"[red]Feed desconocido:[/red] {source}")
            raise typer.Exit(2)
        feeds = {source: feeds[source]}

    total = 0
    for name, cfg in feeds.items():
        if not cfg.get("enabled", True):
            continue
        try:
            items = fetch_rss(cfg["url"], name, limit=limit)
            inserted = store_news(DEFAULT_DB, items)
            total += inserted
            console.print(f"[green]{name}[/green] · {len(items)} vistos · {inserted} nuevos")
        except Exception as exc:
            console.print(f"[red]{name}[/red] · {exc}")
    console.print(f"Total nuevos: {total} · texto externo saneado y trusted=false")


@intel_app.command("status")
def intel_status_cmd() -> None:
    """Resumen de noticias almacenadas (sin puntuar todavía)."""
    n = news_count(DEFAULT_DB)
    console.print(f"Noticias almacenadas: [bold]{n}[/bold] · trusted=false")
    rows = recent_news(DEFAULT_DB, 8)
    if rows:
        t = Table(title="Últimas noticias saneadas")
        t.add_column("Fuente")
        t.add_column("Publicada", justify="right")
        t.add_column("Titular", overflow="fold")
        for row in rows:
            t.add_row(str(row["source"]), str(row["published_at"] or "")[:19], str(row["title"]))
        console.print(t)
    console.print(
        "[dim]Calendario macro: FRED con `lab intel fred`; FOMC manual con `lab intel event`.[/dim]"
    )


@intel_app.command("fred")
def intel_fred_cmd(
    days: int = typer.Option(90, "--days", help="Ventana de días hacia delante"),
) -> None:
    """Sincroniza CPI/NFP desde FRED a macro_events. Solo lectura externa."""
    settings = get_settings()
    provider = FredCalendarProvider(
        DEFAULT_DB,
        cache_dir=settings.data.cache_dir / "fred",
    )
    now = datetime.now(timezone.utc)
    try:
        result = provider.fetch(now, now + timedelta(days=max(1, days)))
    finally:
        provider.close()

    t = Table(title="FRED · calendario macro")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", overflow="fold")
    t.add_row("Estado", result.status.value)
    t.add_row("Mensaje", result.message or "—")
    t.add_row("Eventos", str(len(result.events)))
    console.print(t)
    if result.events:
        events = Table(title="Eventos FRED")
        events.add_column("Hora UTC")
        events.add_column("Evento")
        events.add_column("Importancia")
        events.add_column("Fuente")
        for item in result.events[:30]:
            events.add_row(
                item.ts_utc.isoformat(),
                item.event,
                item.importance,
                item.source,
            )
        console.print(events)
    if result.status == CalendarStatus.UNCONFIGURED:
        console.print("[red]Falta FRED_API_KEY; no se ha consultado FRED.[/red]")
        raise typer.Exit(1)
    if result.status != CalendarStatus.OK:
        console.print(
            "[yellow]FRED no disponible: se usan los eventos guardados. "
            "El guard bloqueará aperturas si no hay datos fiables.[/yellow]"
        )


@intel_app.command("event")
def intel_event_cmd(
    event: str = typer.Argument(..., help="Ej. FOMC"),
    at: str = typer.Option(..., "--at", help="ISO UTC, ej. 2026-11-07T19:00:00+00:00"),
    importance: str = typer.Option("high", "--importance", help="low|medium|high"),
) -> None:
    """Añade un evento macro manual (fixture operativo). No activa nada."""
    try:
        when = datetime.fromisoformat(at)
    except ValueError:
        console.print("[red]Fecha inválida; usa ISO 8601 con zona.[/red]")
        raise typer.Exit(2)
    add_calendar_event(DEFAULT_DB, event=event, ts_utc=when, importance=importance)
    console.print(f"[green]Evento añadido[/green] {event} · {when.isoformat()} · {importance}")


@intel_app.command("calendar")
def intel_calendar_cmd(
    hours_before: int = typer.Option(24, "--hours-before"),
    hours_after: int = typer.Option(168, "--hours-after"),
) -> None:
    """Muestra el estado del calendario y los eventos próximos."""
    now = datetime.now(timezone.utc)
    provider = DbCalendarProvider(DEFAULT_DB)
    result = provider.fetch(now - timedelta(hours=hours_before), now + timedelta(hours=hours_after))
    t = Table(title="Calendario macro")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", overflow="fold")
    t.add_row("Estado", result.status.value)
    t.add_row("Mensaje", result.message or "—")
    t.add_row("Eventos", str(len(result.events)))
    console.print(t)
    if result.events:
        events = Table(title="Eventos")
        events.add_column("Hora UTC")
        events.add_column("Evento", overflow="fold")
        events.add_column("Importancia")
        events.add_column("Fuente")
        for item in result.events:
            events.add_row(
                item.ts_utc.isoformat(),
                item.event,
                item.importance,
                item.source,
            )
        console.print(events)
    if result.status != CalendarStatus.OK:
        console.print(
            "[yellow]Sin datos fiables: el blackout bloqueará aperturas si está activado.[/yellow]"
        )


@fund_app.command("accounts")
def fund_accounts_cmd() -> None:
    """Lista cuentas y límites efectivos (firma + propios)."""
    from .accounts import effective_limits, load_accounts

    accounts = load_accounts()
    t = Table(title="Cuentas del fondo")
    for col in ("ID", "Tipo", "Firma", "Estado", "Diario", "MaxDD", "Trade", "Abierto", "Trades/día"):
        t.add_column(col, justify="right" if col not in ("ID", "Tipo", "Firma", "Estado") else "left")
    for account in accounts.values():
        limits = effective_limits(DEFAULT_DB, account)
        t.add_row(
            account.id,
            account.type,
            account.firm or "—",
            account.status,
            f"{limits.daily_loss_pct:.2%}",
            f"{limits.max_drawdown_pct:.2%}",
            f"{limits.per_trade_risk_pct:.2%}",
            f"{limits.max_open_risk_pct:.2%}",
            str(limits.max_trades_per_day),
        )
    console.print(t)


@fund_app.command("set")
def fund_set_cmd(
    account: str = typer.Argument(...),
    daily_loss: float = typer.Option(None, "--daily-loss", help="Fracción, ej. 0.03"),
    max_drawdown: float = typer.Option(None, "--max-drawdown", help="Fracción, ej. 0.08"),
    per_trade_risk: float = typer.Option(None, "--per-trade-risk", help="Fracción, ej. 0.005"),
    max_open_risk: float = typer.Option(None, "--max-open-risk", help="Fracción, ej. 0.015"),
    max_trades: int = typer.Option(None, "--max-trades", help="Operaciones máximas/día"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirmar aflojamiento"),
) -> None:
    """Edita límites propios en SQLite; nunca toca prop.yaml."""
    from .accounts import set_limits

    changes = {
        key: value
        for key, value in {
            "daily_loss_pct": daily_loss,
            "max_drawdown_pct": max_drawdown,
            "per_trade_risk_pct": per_trade_risk,
            "max_open_risk_pct": max_open_risk,
            "max_trades_per_day": max_trades,
        }.items()
        if value is not None
    }
    result = set_limits(
        DEFAULT_DB,
        account_id=account,
        changes=changes,
        origin="cli",
        confirm=confirm,
    )
    if not result["ok"]:
        for error in result["errors"]:
            console.print(f"[red]{error}[/red]")
        raise typer.Exit(2)
    if not result["changes"]:
        console.print("[dim]Sin cambios.[/dim]")
        return
    t = Table(title=f"Límites actualizados · {account}")
    for col in ("Campo", "Antes", "Después", "Efectivo desde", "Tipo"):
        t.add_column(col)
    for change in result["changes"]:
        t.add_row(
            change["field"],
            f"{change['old']:.4g}",
            f"{change['new']:.4g}",
            change["effective_from"],
            "aflojar" if change["loosening"] else "apretar",
        )
    console.print(t)
    if result["pending"]:
        console.print("[yellow]Aflojamiento pendiente: aplica desde el siguiente día hábil.[/yellow]")


@fund_app.command("history")
def fund_history_cmd(account: str = typer.Argument(...)) -> None:
    """Historial de cambios de límites propios."""
    from .accounts import history

    rows = history(DEFAULT_DB, account)
    t = Table(title=f"Historial de límites · {account}")
    for col in ("Fecha", "Campo", "Antes", "Después", "Origen", "Efectivo desde"):
        t.add_column(col)
    for row in rows:
        t.add_row(
            str(row["ts"]),
            str(row["field"]),
            f"{row['old_value']}",
            f"{row['new_value']}",
            str(row["origin"]),
            str(row["effective_from"]),
        )
    console.print(t)


@fund_app.command("flow-add")
def fund_flow_add_cmd(
    account: str = typer.Argument(...),
    amount: float = typer.Option(..., "--amount", help="Importe positivo"),
    kind: str = typer.Option("deposit", "--kind", help="deposit | withdrawal"),
    note: str = typer.Option("", "--note"),
) -> None:
    """Registra un depósito/retiro externo (libro de capital)."""
    from .accounts import add_cash_flow

    try:
        flow = add_cash_flow(
            DEFAULT_DB,
            account_id=account,
            kind=kind,
            amount=amount,
            note=note,
            origin="cli",
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]{flow['kind']}[/green] {flow['amount']:,.2f} · "
        f"{flow['account_id']} · {flow['ts']}"
    )


@fund_app.command("flows")
def fund_flows_cmd(
    account: str = typer.Argument(None),
) -> None:
    """Lista depósitos/retiros y el TWR disponible por cuenta."""
    from .accounts import cash_flows
    from .health import time_weighted_return

    rows = cash_flows(DEFAULT_DB, account or None, limit=200)
    t = Table(title="Flujos de capital")
    for col in ("Fecha", "Cuenta", "Tipo", "Importe", "Origen", "Nota"):
        t.add_column(col)
    for row in rows:
        t.add_row(
            str(row["ts"]),
            str(row["account_id"]),
            str(row["kind"]),
            f"{float(row['amount']):,.2f}",
            str(row["origin"]),
            str(row["note"] or ""),
        )
    console.print(t)
    if account:
        from .db import connect

        curve = []
        if account == "paper_main":
            with connect(DEFAULT_DB) as con:
                curve = [
                    {"ts": r["ts"], "equity": float(r["equity"])}
                    for r in con.execute(
                        "SELECT ts, equity FROM equity ORDER BY ts"
                    ).fetchall()
                ]
        result = time_weighted_return(curve, rows)
        console.print(
            f"[dim]TWR {account}: "
            + (
                f"{result['twr']:.4%}"
                if result["twr"] is not None
                else "Sin datos"
            )
            + f" · {result['days']} días · {result['flows']} flujos[/dim]"
        )


@fund_app.command("pause-status")
def fund_pause_status_cmd(account: str = typer.Argument(None)) -> None:
    """Muestra pausa de aperturas y umbrales de racha/pérdida diaria."""
    from .accounts import load_accounts
    from .riskpause import pause_status

    settings = get_settings()
    accounts = load_accounts()
    rows = [account] if account else list(accounts)
    t = Table(title="Pausa de aperturas")
    for col in ("Cuenta", "Pausa", "Racha", "Máx. racha", "Pérdida día", "Límite día", "Motivo"):
        t.add_column(col)
    for account_id in rows:
        if account_id not in accounts:
            console.print(f"[red]cuenta desconocida: {account_id}[/red]")
            continue
        state = pause_status(
            DEFAULT_DB,
            account_id,
            tz=settings.timezone,
            persist=False,
        )
        t.add_row(
            account_id,
            "SÍ" if state["paused"] else "no",
            str(state.get("consecutive_losses") if state.get("consecutive_losses") is not None else "sin datos"),
            str(state.get("max_consecutive_losses")),
            f"{state.get('daily_loss_usd'):,.2f}" if state.get("daily_loss_usd") is not None else "sin datos",
            f"{state.get('daily_limit_usd'):,.2f}" if state.get("daily_limit_usd") is not None else "sin datos",
            state.get("reason") or "",
        )
    console.print(t)


@fund_app.command("pause-set")
def fund_pause_set_cmd(
    account: str = typer.Argument(...),
    max_losses: int = typer.Option(None, "--max-losses", help="Pérdidas seguidas"),
    daily_loss_pct: float = typer.Option(None, "--daily-loss-pct", help="Fracción, ej. 0.02"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirmar aflojar"),
) -> None:
    """Ajusta umbrales de pausa; apretar es inmediato, aflojar exige confirmar."""
    from .riskpause import set_thresholds

    changes = {}
    if max_losses is not None:
        changes["max_consecutive_losses"] = max_losses
    if daily_loss_pct is not None:
        changes["daily_loss_pct"] = daily_loss_pct
    try:
        result = set_thresholds(
            DEFAULT_DB,
            account,
            changes=changes,
            origin="cli",
            confirm=confirm,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if not result["changes"]:
        console.print("[dim]Sin cambios.[/dim]")
        return
    t = Table(title=f"Umbrales de pausa · {account}")
    for col in ("Campo", "Antes", "Después", "Tipo"):
        t.add_column(col)
    for change in result["changes"]:
        t.add_row(
            change["field"],
            str(change["old"]),
            str(change["new"]),
            "aflojar" if change["loosening"] else "apretar",
        )
    console.print(t)


@fund_app.command("pause-resume")
def fund_pause_resume_cmd(
    account: str = typer.Argument(...),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Reanuda aperturas; exige confirmación y F13 no congelado."""
    from .riskpause import resume

    try:
        result = resume(DEFAULT_DB, account, confirm=confirm, actor="cli")
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Pausa reanudada[/green] · {result['account_id']} · {result['reset_at']}"
    )


@lessons_app.command("list")
def lessons_list_cmd(
    status: str = typer.Option(None, "--status", help="proposed|approved|rejected"),
) -> None:
    """Lista lecciones y challengers."""
    from .learning import list_lessons

    try:
        rows = list_lessons(DEFAULT_DB, status=status)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    t = Table(title="Lecciones")
    for col in ("ID", "Tipo", "Autor", "Estado", "Aplicada", "Tests", "Hipótesis"):
        t.add_column(col, overflow="fold")
    for row in rows:
        t.add_row(
            str(row["id"]),
            str(row["kind"]),
            str(row["author"]),
            str(row["status"]),
            "sí" if row.get("applied_at") else "no",
            str(row.get("tests", 0)),
            str(row["hypothesis"]),
        )
    console.print(t)


@lessons_app.command("show")
def lessons_show_cmd(lesson_id: int = typer.Argument(...)) -> None:
    """Muestra una lección completa."""
    from .learning import get_lesson

    try:
        row = get_lesson(DEFAULT_DB, lesson_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    t = Table(title=f"Lección #{lesson_id}")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", overflow="fold")
    for key, value in row.items():
        t.add_row(key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value or ""))
    console.print(t)


@lessons_app.command("add")
def lessons_add_cmd(
    hypothesis: str = typer.Option(..., "--hypothesis"),
    evidence: str = typer.Option("", "--evidence"),
    author: str = typer.Option("humano", "--author", help="qwen|humano"),
    action: str = typer.Option(None, "--action", help="JSON reduce_risk"),
) -> None:
    """Crea una propuesta; Qwen solo redacta."""
    from .learning import create_lesson

    try:
        parsed = json.loads(action) if action else None
        row = create_lesson(
            DEFAULT_DB,
            hypothesis=hypothesis,
            evidence=evidence,
            author=author,
            action=parsed,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Lección #{row['id']}[/green] · {row['status']} · autor {row['author']}")


@lessons_app.command("approve")
def lessons_approve_cmd(
    lesson_id: int = typer.Argument(...),
    by: str = typer.Option("humano", "--by"),
) -> None:
    """Aprueba una lección desde CLI."""
    from .learning import approve

    try:
        row = approve(DEFAULT_DB, lesson_id, by=by)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Lección #{lesson_id} aprobada[/green] · {row['status']}")


@lessons_app.command("reject")
def lessons_reject_cmd(
    lesson_id: int = typer.Argument(...),
    by: str = typer.Option("humano", "--by"),
    reason: str = typer.Option("", "--reason"),
) -> None:
    """Rechaza una lección."""
    from .learning import reject

    try:
        row = reject(DEFAULT_DB, lesson_id, by=by, reason=reason)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[yellow]Lección #{lesson_id} rechazada[/yellow] · {row['status']}")


@lessons_app.command("test")
def lessons_test_cmd(
    lesson_id: int = typer.Argument(...),
    start: str = typer.Option(..., "--start", help="YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="YYYY-MM-DD"),
    metric: str = typer.Option("", "--metric"),
    value: float = typer.Option(None, "--value"),
    passed: bool = typer.Option(None, "--passed/--failed"),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Registra una prueba; rechaza cualquier ventana sobre el holdout."""
    from .learning import record_test

    try:
        result = record_test(
            DEFAULT_DB,
            lesson_id,
            period_start=start,
            period_end=end,
            metric=metric,
            value=value,
            passed=passed,
            notes=notes,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Prueba registrada[/green] · trials globales {result['global_trials']}"
    )


@lessons_app.command("challenger")
def lessons_challenger_cmd(
    champion: str = typer.Option(..., "--champion"),
    challenger: str = typer.Option(..., "--challenger"),
    hypothesis: str = typer.Option(..., "--hypothesis"),
    evidence: str = typer.Option("", "--evidence"),
    author: str = typer.Option("humano", "--author"),
) -> None:
    """Propone un retador paper; nunca lo activa."""
    from .learning import create_lesson

    try:
        row = create_lesson(
            DEFAULT_DB,
            hypothesis=hypothesis,
            evidence=evidence,
            author=author,
            kind="challenger",
            champion=champion,
            challenger=challenger,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Retador #{row['id']}[/green] · {champion} → {challenger} · proposed"
    )


@lessons_app.command("apply")
def lessons_apply_cmd(
    lesson_id: int = typer.Argument(...),
    auto: bool = typer.Option(False, "--auto", help="Solo reduce_risk"),
) -> None:
    """Aplica una lección aprobada o auto-aplica una reducción de riesgo."""
    from .learning import apply_lesson

    try:
        row = apply_lesson(
            DEFAULT_DB,
            lesson_id,
            actor="auto" if auto else "humano",
            auto=auto,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Lección #{lesson_id} aplicada[/green] · {row.get('applied_at')}")


@lessons_app.command("revert")
def lessons_revert_cmd(
    lesson_id: int = typer.Argument(...),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Revierte una lección aplicada; exige confirmación."""
    from .learning import revert_lesson

    try:
        row = revert_lesson(DEFAULT_DB, lesson_id, actor="humano", confirm=confirm)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Lección #{lesson_id} revertida[/green] · {row.get('reverted_at')}")


@lessons_app.command("holdout")
def lessons_holdout_cmd() -> None:
    """Muestra el tramo sellado y el contador global de pruebas."""
    from .learning import count_tests, holdout_info

    info = holdout_info(DEFAULT_DB)
    t = Table(title="Holdout sellado")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    for key in ("start_date", "end_date", "hash", "sealed_at"):
        t.add_row(key, str(info.get(key) or "Sin datos"))
    t.add_row("trials globales", str(count_tests(DEFAULT_DB)))
    console.print(t)


@reports_app.command("journal")
def reports_journal_cmd(
    fmt: str = typer.Option("csv", "--format", help="csv|html"),
    out: str = typer.Option(None, "--out", help="Subcarpeta dentro de reports/"),
    limit: int = typer.Option(500, "--limit"),
) -> None:
    """Exporta el Diario a CSV/HTML con vista previa."""
    from .exports import export_journal

    try:
        result = export_journal(DEFAULT_DB, get_settings(), fmt=fmt, out_dir=out, limit=limit)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    _print_export(result)


@reports_app.command("drift")
def reports_drift_cmd(
    fmt: str = typer.Option("csv", "--format", help="csv|html"),
    out: str = typer.Option(None, "--out"),
    min_trades: int = typer.Option(20, "--min-trades"),
) -> None:
    """Exporta la deriva live vs backtest."""
    from .exports import export_drift

    try:
        result = export_drift(
            DEFAULT_DB,
            get_settings(),
            fmt=fmt,
            out_dir=out,
            min_trades=min_trades,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    _print_export(result)


@reports_app.command("learning")
def reports_learning_cmd(
    fmt: str = typer.Option("csv", "--format", help="csv|html"),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Exporta lecciones y evidencia."""
    from .exports import export_learning

    try:
        result = export_learning(DEFAULT_DB, get_settings(), fmt=fmt, out_dir=out)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    _print_export(result)


@reports_app.command("list")
def reports_list_cmd() -> None:
    """Lista reportes generados."""
    from .exports import list_exports

    rows = list_exports()
    t = Table(title="Reportes generados")
    for col in ("Archivo", "Formato", "Bytes", "Fecha"):
        t.add_column(col)
    for row in rows:
        t.add_row(row["name"], row["format"], str(row["size"]), row["mtime"])
    console.print(t)


@reports_app.command("preview")
def reports_preview_cmd(
    file: str = typer.Argument(...),
    rows: int = typer.Option(10, "--rows"),
) -> None:
    """Vista previa de un CSV/HTML de reports/."""
    from .exports import preview_file

    try:
        result = preview_file(file, rows=rows)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if result["format"] == "html":
        console.print(
            f"[green]{result['path']}[/green] · HTML · "
            f"{'truncado' if result['truncated'] else 'completo'}"
        )
        return
    data = result["rows"]
    if not data:
        console.print("[yellow]Sin datos[/yellow]")
        return
    t = Table(title=f"Vista previa · {result['path']}")
    for col in data[0].keys():
        t.add_column(col, overflow="fold")
    for row in data:
        t.add_row(*[str(row.get(col, ""))[:120] for col in data[0].keys()])
    console.print(t)


def _print_export(result: dict) -> None:
    console.print(
        f"[green]Reporte generado[/green] · {result['path']} · "
        f"{result['rows']} filas · {result['preview_note']}"
    )
    rows = result.get("preview") or []
    if rows:
        t = Table(title="Vista previa")
        for col in rows[0].keys():
            t.add_column(col, overflow="fold")
        for row in rows:
            t.add_row(*[str(row.get(col, ""))[:100] for col in rows[0].keys()])
        console.print(t)


@markets_app.command("list")
def markets_list_cmd() -> None:
    """Muestra agentes/analistas y presupuesto por mercado."""
    from .market_agents import market_payload

    payload = market_payload()
    t = Table(title=f"Agentes por mercado ({payload['count']})")
    for col in ("Mercado", "Etiqueta", "Perfil", "Analistas", "Peso máx.", "Símbolos"):
        t.add_column(col)
    for row in payload["markets"]:
        t.add_row(
            row["market"],
            row["label"],
            row["profile"] if row["profile_found"] else f"{row['profile']} (sin datos)",
            ", ".join(row["analysts"]),
            f"{row['max_weight']:.0%}",
            str(row["count"]),
        )
    console.print(t)
    console.print(
        f"[dim]gross máximo {payload['max_gross']:.0%} · "
        f"por símbolo {payload['max_per_symbol']:.0%}[/dim]"
    )


@markets_app.command("coordinate")
def markets_coordinate_cmd(
    file: str = typer.Argument(..., help="JSON con lista de señales"),
    max_gross: float = typer.Option(0.90, "--max-gross"),
    max_per_symbol: float = typer.Option(0.25, "--max-per-symbol"),
) -> None:
    """Coordina señales (rating/confidence) sin ejecutar ni activar nada."""
    from .market_agents import coordinate

    try:
        signals = json.loads(Path(file).read_text(encoding="utf-8"))
        if not isinstance(signals, list):
            raise ValueError("el JSON debe ser una lista")
        result = coordinate(
            signals,
            max_gross=max_gross,
            max_per_symbol=max_per_symbol,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    t = Table(title="Coordinador determinista")
    for col in ("Mercado", "Símbolo", "Rating", "Confianza", "Peso"):
        t.add_column(col)
    for row in result["allocations"]:
        t.add_row(
            row["market"],
            row["symbol"],
            row["rating"],
            f"{row['confidence']:.0%}",
            f"{row['weight']:.2%}",
        )
    console.print(t)
    console.print(
        f"[dim]gross {result['gross_weight']:.2%} · cash {result['cash_weight']:.2%} · "
        f"omitidas {len(result['skipped'])}[/dim]"
    )


@markets_app.command("pilots")
def markets_pilots_cmd() -> None:
    """Muestra pilotos/mini-F13 por mercado y el activo."""
    from .market_pilots import pilot_status

    payload = pilot_status(DEFAULT_DB, get_settings())
    t = Table(title="Pilotos por mercado")
    for col in ("Mercado", "Bot", "Perfil", "Estado", "Activo", "Motivo"):
        t.add_column(col, overflow="fold")
    for row in payload["pilots"]:
        t.add_row(
            row["market"],
            row["bot"] or "Sin datos",
            row["profile"],
            row["status"],
            "SÍ" if row["active"] else "no",
            row["reason"],
        )
    console.print(t)
    console.print(
        f"[dim]activo: {payload['active_market'] or 'ninguno'} · "
        "seleccionar no activa bots ni F13[/dim]"
    )


@markets_app.command("pilot-select")
def markets_pilot_select_cmd(
    market: str = typer.Argument(...),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Selecciona el mercado del piloto; no activa bots ni F13."""
    from .market_pilots import select_pilot

    try:
        select_pilot(DEFAULT_DB, market, confirm=confirm, actor="cli")
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Piloto activo: {market}[/green] · bots/F13 sin cambios")


@markets_app.command("pilot-clear")
def markets_pilot_clear_cmd(
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Quita el piloto activo; no toca bots ni F13."""
    from .market_pilots import clear_pilots

    try:
        clear_pilots(DEFAULT_DB, confirm=confirm, actor="cli")
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print("[green]Pilotos limpiados[/green] · bots/F13 sin cambios")


@operator_app.command("pin")
def operator_pin_cmd() -> None:
    """Configura el PIN del modo operador en el keyring (nunca en .env)."""
    from .operator import pin_configured, set_pin

    if pin_configured() and not typer.confirm(
        "Ya existe un PIN. ¿Reemplazarlo?", default=False
    ):
        raise typer.Exit(1)
    pin = typer.prompt(
        "PIN (4-12 dígitos)", hide_input=True, confirmation_prompt=True
    )
    try:
        set_pin(pin)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print("[green]PIN guardado en keyring. No se escribió en .env ni logs.[/green]")


@operator_app.command("status")
def operator_status_cmd() -> None:
    """Muestra si hay PIN y el estado runtime de los bots."""
    from .operator import pin_configured
    from .runtime import get_bot_state

    settings = get_settings()
    t = Table(title="Modo operador")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    t.add_row("mode", settings.mode)
    t.add_row("PIN en keyring", "sí" if pin_configured() else "no")
    t.add_row("Armado", "solo en el servidor web (se pierde al reiniciar)")
    t.add_row(
        "Ventana",
        f"{settings.operator.arm_minutes} min · "
        f"token {settings.operator.confirm_seconds}s",
    )
    console.print(t)
    bots = Table(title="Estado runtime de bots")
    for col in ("Bot", "YAML", "Efectivo", "Actualizado"):
        bots.add_column(col)
    for spec in load_bots():
        state = get_bot_state(DEFAULT_DB, spec.id)
        bots.add_row(
            spec.id,
            "on" if spec.yaml_enabled else "off",
            "on" if spec.enabled else "off",
            str(state["updated_at"]) if state else "sin datos",
        )
    console.print(bots)


@decisions_app.command("update")
def decisions_update_cmd() -> None:
    """Rellena retornos a 1/5/20 días hábiles de decisiones antiguas."""
    settings = get_settings()
    updated = update_outcomes(DEFAULT_DB, settings.data.cache_dir)
    console.print(f"[green]{updated} decisiones actualizadas[/green]")


@decisions_app.command("report")
def decisions_report_cmd() -> None:
    """Compara el rating del LLM con comprar siempre / no hacer nada."""
    settings = get_settings()
    rows = decisions_report(DEFAULT_DB)
    if not rows:
        console.print("[yellow]Sin decisiones con retorno a 20 días todavía.[/yellow]")
        return
    t = Table(title="Decisiones LLM · retorno forward")
    for col in ("Rating", "N", "1d", "5d", "20d", "Hit 20d", "t", "p", "Muestra"):
        t.add_column(col, justify="right" if col != "Rating" else "left")
    for row in rows:
        t.add_row(
            row["rating"],
            str(row["n"]),
            _fmt_pct(row["mean_1d"]) if row["mean_1d"] is not None else "—",
            _fmt_pct(row["mean_5d"]) if row["mean_5d"] is not None else "—",
            _fmt_pct(row["mean_20d"]),
            _fmt_pct(row["hit_rate_20d"]) if row["hit_rate_20d"] is not None else "—",
            f"{row['t_stat']:.2f}" if row["t_stat"] is not None else "—",
            f"{row['p_value']:.3f}" if row["p_value"] is not None else "—",
            "insuficiente" if row["insufficient"] else "ok",
        )
    console.print(t)

    baseline = decisions_compare(DEFAULT_DB, settings.data.cache_dir)
    b = Table(title="Comparación sobre las mismas fechas · forward 20d")
    b.add_column("Estrategia", style="bold")
    b.add_column("N", justify="right")
    b.add_column("Retorno medio", justify="right")
    b.add_column("Hit rate", justify="right")
    b.add_column("Muestra", justify="right")
    comparison_rows = [
        (
            "LLM lite (posición por rating)",
            baseline["matched_llm_mean_20d"],
            baseline["matched_llm_hit_rate"],
        ),
        (
            "Buy & hold (siempre largo)",
            baseline["matched_buy_hold_mean_20d"],
            baseline["matched_buy_hold_hit_rate"],
        ),
        (
            "Señal trend",
            baseline["matched_trend_mean_20d"],
            baseline["matched_trend_hit_rate"],
        ),
    ]
    for label, mean_value, hit_rate in comparison_rows:
        b.add_row(
            label,
            str(baseline["matched_n"]),
            _fmt_pct(mean_value) if mean_value is not None else "—",
            _fmt_pct(hit_rate) if hit_rate is not None else "—",
            "insuficiente" if baseline["insufficient"] else "ok",
        )
    console.print(b)

    total = sum(row["n"] for row in rows)
    if total < 30:
        console.print(
            f"[yellow]Muestra total {total} < 30: no saques conclusiones de edge todavía.[/yellow]"
        )
    if baseline["insufficient"]:
        console.print(f"[yellow]{baseline['sample_warning']}.[/yellow]")
    console.print(
        f"[dim]Cobertura trend: {baseline['trend_coverage']:.0%} "
        f"({baseline['matched_n']}/{baseline['n']} decisiones comparables). "
        "Hold/REVIEW = posición 0 en esta comparación; buy&hold siempre largo.</dim>"
    )


@bots_app.command("list")
def list_bots() -> None:
    """Lista el catálogo de bots definido en config/bots.yaml."""
    path = ROOT / "config" / "bots.yaml"
    if not path.exists():
        console.print("[yellow]No existe config/bots.yaml[/yellow]")
        return

    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    t = Table(title="Catálogo de bots")
    t.add_column("ID", style="bold")
    t.add_column("Tipo")
    t.add_column("Estrategia")
    t.add_column("Perfil")
    t.add_column("Clúster")
    t.add_column("Cuenta")
    t.add_column("Estado")
    t.add_column("Descripción", overflow="fold")
    for bot in data.get("bots", []):
        t.add_row(
            bot.get("id", ""),
            bot.get("type", ""),
            bot.get("strategy", ""),
            bot.get("profile", "—"),
            bot.get("cluster", "—"),
            bot.get("account", "—"),
            bot.get("enabled", False) and "on" or "off",
            bot.get("description", ""),
        )
    console.print(t)


@bots_app.command("evaluate")
def bots_evaluate_cmd(
    start: str = typer.Option("2015-01-01", "--start"),
    apply: bool = typer.Option(
        False, "--apply", help="Archivar los no aptos que estén deshabilitados (nunca enabled)"
    ),
) -> None:
    """Backtest de los bots deterministas y informe de vida o muerte."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    results = evaluate_all(settings, DEFAULT_DB, start=start)
    if not results:
        console.print("[yellow]No hay bots evaluables.[/yellow]")
        return

    specs = {spec.id: spec for spec in load_bots()}
    t = Table(title="Evaluación de bots (sin activar nada)")
    for col in ("Bot", "Estrategia", "Universo", "Trades", "Retorno", "Sharpe", "MaxDD", "Estado"):
        t.add_column(col, justify="right" if col not in ("Bot", "Estrategia", "Universo", "Estado") else "left")
    for row in results:
        t.add_row(
            row["bot"],
            row["strategy"],
            row["universe"],
            str(row.get("num_trades") or 0),
            _fmt_pct(float(row.get("total_return") or 0.0)),
            f"{float(row.get('sharpe') or 0.0):.2f}",
            _fmt_pct(float(row.get("max_drawdown") or 0.0)),
            row["status"],
        )
    console.print(t)

    if apply:
        archived = []
        for row in results:
            spec = specs.get(row["bot"])
            if row["status"] == "archivar" and spec is not None and not spec.enabled:
                archive_bot(row["bot"], reason="evaluación automática: métricas bajo umbral")
                archived.append(row["bot"])
        if archived:
            console.print(f"[yellow]Archivados (sin borrar):[/yellow] {', '.join(archived)}")
        else:
            console.print("[dim]Nada que archivar con los criterios actuales.[/dim]")
    else:
        console.print(
            "[dim]Usa --apply para archivar los 'archivar' deshabilitados. "
            "Los bots enabled nunca se archivan solos.[/dim]"
        )


@bots_app.command("archive")
def bots_archive_cmd(
    bot: str = typer.Argument(..., help="ID del bot"),
    reason: str = typer.Option("manual", "--reason"),
    yes: bool = typer.Option(False, "--yes", help="No pedir confirmación"),
) -> None:
    """Archiva un bot (no lo borra; conserva historial)."""
    if not yes and not typer.confirm(f"¿Archivar {bot}? No se borra, solo se desactiva."):
        raise typer.Exit(1)
    ids = archive_bot(bot, reason=reason)
    console.print(f"[yellow]Archivado[/yellow] {bot} · total={len(ids)}")


@bots_app.command("restore")
def bots_restore_cmd(bot: str = typer.Argument(..., help="ID del bot")) -> None:
    """Restaura un bot archivado (sigue en enabled:false hasta que lo actives)."""
    ids = restore_bot(bot)
    console.print(f"[green]Restaurado[/green] {bot} · quedan {len(ids)} archivados")


@bots_app.command("propose")
def bots_propose_cmd(
    id: str = typer.Argument(..., help="ID nuevo, ej. qqq-breakout"),
    strategy: str = typer.Option("trend", "--strategy"),
    universe: str = typer.Option("SPY", "--universe", help="Lista separada por comas"),
    params: str = typer.Option("{}", "--params", help="JSON de parámetros"),
    exposure: float = typer.Option(1.0, "--exposure"),
    description: str = typer.Option("", "--description"),
) -> None:
    """Crea una propuesta de bot en enabled:false (no se activa)."""
    try:
        parsed = json.loads(params)
        if not isinstance(parsed, dict):
            raise ValueError("params debe ser un objeto JSON")
        spec = propose_bot(
            id=id,
            strategy=strategy,
            universe=[x.strip() for x in universe.split(",") if x.strip()],
            params=parsed,
            exposure=exposure,
            description=description,
        )
    except Exception as exc:
        console.print(f"[red]No se pudo proponer:[/red] {exc}")
        raise typer.Exit(2)
    console.print(
        f"[green]Propuesta creada[/green] {spec.id} · enabled=false · "
        "evalúala con `lab bots evaluate`."
    )


@app.command()
def dashboard() -> None:
    """Genera reports/dashboard.html con equity, posiciones y órdenes."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    broker = get_broker(settings, DEFAULT_DB)
    path = build_dashboard(settings, broker, DEFAULT_DB)
    console.print(f"[green]Dashboard generado:[/green] {path}")
    console.print("[dim]Ábrelo en el navegador o sírvelo con `python -m http.server -d reports`[/dim]")


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", help="Interfaz de escucha (local por defecto)"),
    port: int = typer.Option(8420, "--port", help="Puerto HTTP"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Abrir el navegador al arrancar"),
    no_external: bool = typer.Option(
        False, "--no-external", help="No consultar LM Studio, MT5 ni tareas programadas"
    ),
) -> None:
    """Sirve el panel web local: resumen, bots, agentes, research, riesgo y logs."""
    from .web import serve

    serve(
        get_settings(),
        host=host,
        port=port,
        open_browser=open_browser,
        external=not no_external,
    )


def _print_guard(rules: PropRules, report) -> None:
    color = {"ok": "green", "warn": "yellow", "block": "red", "breach": "bold red"}[report.severity]
    console.print(Panel(report.summary(), title=f"[{color}]{rules.describe()}[/{color}]"))
    if report.warnings:
        for w in report.warnings:
            console.print(f"[yellow]· {w}[/yellow]")


# =============================================================== MetaTrader 5

@mt5_app.command("status")
def mt5_status() -> None:
    """Conecta con el terminal y muestra cuenta, margen y permisos."""
    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        health = broker.health()
    finally:
        broker.shutdown()

    t = Table(title="MetaTrader 5")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    for key in (
        "connected",
        "trade_allowed",
        "mode",
        "login",
        "server",
        "company",
        "currency",
        "leverage",
        "balance",
        "equity",
        "margin",
        "margin_free",
        "margin_level",
        "server_utc_offset_hours",
        "offset_source",
        "offset_known",
        "identity_ok",
        "require_demo",
        "expected_login",
        "expected_server",
        "path",
    ):
        value = health[key]
        t.add_row(key, f"{value:,.2f}" if isinstance(value, float) else str(value))
    console.print(t)

    if health["mode"] == "real":
        if health.get("require_demo"):
            console.print(
                Panel(
                    "CUENTA REAL con require_demo=true: el guard de identidad "
                    "bloqueará cualquier orden.",
                    style="bold red",
                )
            )
        else:
            console.print(Panel("CUENTA REAL: las órdenes exigen ALLOW_LIVE=YES", style="bold red"))
    if not health["trade_allowed"]:
        console.print("[yellow]Algo Trading está desactivado en el terminal.[/yellow]")


@mt5_app.command("symbols")
def mt5_symbols(filter_: str = typer.Option(None, "--filter", "-f", help="Filtro de texto")) -> None:
    """Lista el catálogo local de instrumentos con sus especificaciones."""
    items = list_instruments()
    if filter_:
        f = filter_.upper()
        items = [i for i in items if f in i.symbol]
    t = Table(title=f"Instrumentos ({len(items)})")
    t.add_column("Símbolo", style="bold")
    t.add_column("Clase")
    t.add_column("Tick", justify="right")
    t.add_column("Tick $", justify="right")
    t.add_column("Contrato", justify="right")
    t.add_column("Lote mín/step/máx", justify="right")
    for i in items:
        tv = f"{i.tick_value:,.2f}" if i.tick_value is not None else "variable"
        t.add_row(
            i.symbol,
            i.asset_class,
            f"{i.tick_size:g}",
            tv,
            f"{i.contract_size:g}",
            f"{i.min_lot:g}/{i.lot_step:g}/{i.max_lot:g}",
        )
    console.print(t)


@mt5_app.command("spec")
def mt5_spec(symbol: str = typer.Argument(..., help="Ej. EURUSD")) -> None:
    """Muestra la especificación real que reporta el bróker."""
    broker = _mt5(get_settings(), dry_run=True)
    try:
        spec = broker.symbol_spec(symbol)
        inst = broker.instrument(symbol)
    finally:
        broker.shutdown()
    t = Table(title=f"Especificación del bróker · {symbol}")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    for k, v in spec.items():
        t.add_row(k, f"{v:,.5f}" if isinstance(v, float) else str(v))
    t.add_row("pip_size", f"{inst.pip_size():g}" if inst.is_fx else "n/a")
    console.print(t)


@mt5_app.command("price")
def mt5_price(symbol: str = typer.Argument(..., help="Ej. EURUSD")) -> None:
    """Bid/ask/spread actuales."""
    broker = _mt5(get_settings(), dry_run=True)
    try:
        tick = broker.tick(symbol)
        inst = broker.instrument(symbol)
    finally:
        broker.shutdown()
    spread_pips = tick["spread"] / inst.pip_size() if inst.is_fx else tick["spread"]
    console.print(
        f"[bold]{symbol}[/bold] bid={tick['bid']:.5f} ask={tick['ask']:.5f} "
        f"spread={tick['spread']:.5f} ({spread_pips:.2f} pips) · {tick['time']:%Y-%m-%d %H:%M:%S} UTC"
    )


@mt5_app.command("size")
def mt5_size(
    symbol: str = typer.Argument(..., help="Ej. EURUSD"),
    risk_usd: float = typer.Option(500.0, "--risk-usd", help="Riesgo máximo en USD"),
    stop_pips: float = typer.Option(20.0, "--stop-pips", help="Distancia al stop en pips"),
    quote_rate: float | None = typer.Option(None, "--quote-rate", help="Divisa cotizada por 1 USD"),
) -> None:
    """Calcula lotes a partir del riesgo y del stop (no del notional)."""
    broker = _mt5(get_settings(), dry_run=True)
    try:
        inst = broker.instrument(symbol)
        qr = quote_rate or _quote_rate(broker, inst)
        tick = broker.tick(symbol)
    finally:
        broker.shutdown()

    stop_distance = stop_pips * inst.pip_size()
    risk_per_lot = inst.risk_per_lot(stop_distance, quote_rate=qr)
    lots = inst.lots_for_risk(risk_usd, stop_distance, quote_rate=qr)

    t = Table(title=f"Sizing · {symbol} · stop {stop_pips:g} pips")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Precio", f"{tick['bid']:.5f}")
    t.add_row("Pip", f"{inst.pip_size():g}")
    t.add_row("Valor del pip por lote", f"{risk_per_lot / stop_pips:,.2f} USD")
    t.add_row("Riesgo por lote", f"{risk_per_lot:,.2f} USD")
    t.add_row("Riesgo objetivo", f"{risk_usd:,.2f} USD")
    t.add_row("Lotes", f"[bold]{lots:g}[/bold]")
    t.add_row("Riesgo real", f"{lots * risk_per_lot:,.2f} USD")
    t.add_row("Margen (1:100)", f"{inst.margin_required(lots, tick['bid'], 100):,.2f} USD")
    console.print(t)
    if lots == 0:
        console.print("[yellow]Ni el lote mínimo cabe en ese riesgo: acerca el stop o sube el riesgo.[/yellow]")


@mt5_app.command("order")
def mt5_order(
    symbol: str = typer.Argument(..., help="Ej. EURUSD"),
    lots: float = typer.Option(0.10, "--lots", help="Volumen en lotes"),
    side: str = typer.Option("buy", "--side", help="buy | sell"),
    sl_pips: float = typer.Option(20.0, "--sl-pips", help="Stop loss en pips (0 = sin SL)"),
    tp_pips: float = typer.Option(0.0, "--tp-pips", help="Take profit en pips (0 = sin TP)"),
    execute: bool = typer.Option(False, "--execute", help="Enviar de verdad (por defecto dry-run)"),
) -> None:
    """Envía una orden a mercado con SL/TP calculados en pips."""
    if side not in {"buy", "sell"}:
        raise typer.BadParameter("side debe ser buy o sell")
    if lots <= 0:
        raise typer.BadParameter("lots debe ser > 0")

    broker = _mt5(get_settings(), dry_run=not execute)
    try:
        inst = broker.instrument(symbol)
        qr = _quote_rate(broker, inst)
        tick = broker.tick(symbol)
        entry = tick["ask"] if side == "buy" else tick["bid"]
        pip = inst.pip_size()
        sign = 1 if side == "buy" else -1
        sl = entry - sign * sl_pips * pip if sl_pips else None
        tp = entry + sign * tp_pips * pip if tp_pips else None

        signed = lots if side == "buy" else -lots
        result = broker.submit_market(symbol, signed, sl=sl, tp=tp, reason="cli mt5 order")
    finally:
        broker.shutdown()

    t = Table(title=f"Orden {'ENVIADA' if execute else 'SIMULADA'} · {symbol}")
    for k, v in result.items():
        if k == "request":
            continue
        t.add_row(k, str(v))
    t.add_row("riesgo", f"{lots * inst.risk_per_lot(sl_pips * pip, quote_rate=qr):,.2f} USD")
    console.print(t)
    if not execute:
        console.print("[dim]Dry-run. Añade --execute para enviarla al bróker.[/dim]")


@mt5_app.command("positions")
def mt5_positions() -> None:
    """Posiciones abiertas en la cuenta MT5."""
    broker = _mt5(get_settings(), dry_run=True)
    try:
        positions = broker.positions()
    finally:
        broker.shutdown()
    if not positions:
        console.print("[dim]Sin posiciones abiertas.[/dim]")
        return
    t = Table(title="Posiciones MT5")
    for col in ("Ticket", "Símbolo", "Lado", "Volumen", "Apertura", "Actual", "SL", "TP", "PnL"):
        t.add_column(col, justify="right" if col != "Símbolo" else "left")
    for p in positions:
        t.add_row(
            str(p["ticket"]),
            p["symbol"],
            p["side"],
            f"{p['volume']:g}",
            f"{p['price_open']:.5f}",
            f"{p['price_current']:.5f}",
            f"{p['sl']:.5f}",
            f"{p['tp']:.5f}",
            f"{p['profit']:,.2f}",
        )
    console.print(t)


@mt5_app.command("close")
def mt5_close(
    ticket: int = typer.Argument(..., help="Ticket de la posición"),
    execute: bool = typer.Option(False, "--execute", help="Cerrar de verdad"),
) -> None:
    """Cierra una posición por ticket."""
    broker = _mt5(get_settings(), dry_run=not execute)
    try:
        positions = [p for p in broker.positions() if p["ticket"] == ticket]
        if not positions:
            console.print(f"[red]No existe la posición {ticket}.[/red]")
            raise typer.Exit(1)
        p = positions[0]
        if not execute:
            console.print(
                f"[yellow]DRY RUN[/yellow] cerraría {p['symbol']} {p['volume']:g} lotes "
                f"({p['side']}) · PnL {p['profit']:,.2f}"
            )
            return
        result = broker.close_position(ticket)
    finally:
        broker.shutdown()
    console.print(f"[green]Cerrada[/green] {result}")


@mt5_app.command("fetch")
def mt5_fetch_cmd(
    symbol: str = typer.Argument("EURUSD", help="Par o instrumento"),
    timeframe: str = typer.Option("M15", "--timeframe", help="M15, H1, H4..."),
    bars: int = typer.Option(50_000, "--bars", help="Velas a descargar (lectura)"),
) -> None:
    """Cachea velas MT5 corregidas a UTC en parquet. No envía órdenes."""
    from .intraday import cache_metadata, save_bars

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        df = broker.rates(symbol, timeframe, bars)
    except Exception as exc:
        console.print(f"[red]No se pudo leer MT5:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        broker.shutdown()
    path = save_bars(df, settings.data.cache_dir, symbol, timeframe)
    meta = cache_metadata(df, timeframe)
    console.print(
        Panel(
            f"{symbol} · {timeframe}\n"
            f"Barras: {meta['rows']:,}\n"
            f"Rango: {meta['start']} → {meta['end']} ({meta['years']} años)\n"
            f"Caché: {path}",
            title="MT5 fetch (solo lectura)",
        )
    )


# ==================================================================== Fondeo

@mt5_app.command("run")
def mt5_run(
    symbol: str = typer.Argument("EURUSD", help="Par o instrumento"),
    timeframe: str = typer.Option("H1", "--timeframe", help="M5, M15, M30, H1, H4, D1"),
    bars: int = typer.Option(600, "--bars", help="Velas a descargar"),
    strategy: str = typer.Option("trend-ls", "--strategy", "-s", help=", ".join(STRATEGIES)),
    risk_pct: float = typer.Option(0.005, "--risk-pct", help="Riesgo por operación (0.005 = 0.5%)"),
    stop_atr: float = typer.Option(2.0, "--stop-atr", help="Stop en múltiplos de ATR"),
    tp_rr: float = typer.Option(2.0, "--tp-rr", help="Take profit como múltiplo del riesgo"),
    execute: bool = typer.Option(False, "--execute", help="Enviar órdenes (por defecto dry-run)"),
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase"),
    account_size: float = typer.Option(None, "--account-size"),
) -> None:
    """Bot de forex: señal -> sizing -> guard de fondeo -> orden con SL/TP."""
    if strategy not in STRATEGIES:
        console.print(f"[red]Estrategia desconocida:[/red] {strategy}. Opciones: {', '.join(STRATEGIES)}")
        raise typer.Exit(2)

    settings = get_settings()
    rules = _prop_rules(firm, phase, account_size)
    guard = PropGuard(rules)
    broker = _mt5(settings, dry_run=not execute)

    try:
        inst = broker.instrument(symbol)
        df = broker.rates(inst.symbol, timeframe, bars)
        if len(df) < 210:
            console.print(f"[red]Histórico insuficiente:[/red] {len(df)} velas (necesito >= 210)")
            raise typer.Exit(1)

        df = df.iloc[:-1]  # descarta la vela en formación
        sig = STRATEGIES[strategy](df)
        target = float(sig.target.iloc[-1])
        atr_value = float(atr_indicator(df).iloc[-1])
        if not (atr_value > 0):
            console.print("[red]ATR inválido: histórico demasiado corto o datos rotos.[/red]")
            raise typer.Exit(1)

        tick = broker.tick(inst.symbol)
        qr = _quote_rate(broker, inst)
        positions = broker.positions(inst.symbol)
        signed = sum(p["volume"] if p["side"] == "buy" else -p["volume"] for p in positions)
        state = _prop_state_from_mt5(broker, rules)

        # Protección del capital: si la cuenta ya está fuera del suelo efectivo,
        # lo único seguro es aplanar TODA la cuenta. Cerrar siempre está permitido.
        breach = guard.evaluate(state)
        if breach.breached and state.open_positions > 0:
            everything = broker.positions()
            console.print(
                Panel(
                    f"{breach.reason}\nSe cierran {len(everything)} posiciones "
                    f"({state.open_lots:g} lotes) para no romper el límite real.",
                    title="Breach de fondeo",
                    style="bold red",
                )
            )
            if execute:
                for p in everything:
                    broker.close_position(p["ticket"])
                console.print(f"[green]Cerradas {len(everything)} posiciones[/green]")
            else:
                console.print(
                    f"[yellow]DRY RUN[/yellow] cerraría {len(everything)} posiciones"
                )
            _record_signal(
                inst.symbol, strategy, "close", target, tick["bid"], f"breach: {breach.reason}"
            )
            return

        # Fin de semana: si weekend_holding=false, aplanar SIEMPRE antes del corte.
        if flatten_required(rules, asset_class="forex"):
            everything = broker.positions()
            if everything:
                session = session_block(rules, asset_class="forex")
                console.print(
                    Panel(
                        f"{session.reason}\nSe cierran {len(everything)} posiciones "
                        f"({state.open_lots:g} lotes) para no mantener el fin de semana.",
                        title="Cierre de viernes",
                        style="bold yellow",
                    )
                )
                if execute:
                    for p in everything:
                        broker.close_position(p["ticket"])
                    console.print(f"[green]Cerradas {len(everything)} posiciones[/green]")
                else:
                    console.print(
                        f"[yellow]DRY RUN[/yellow] cerraría {len(everything)} posiciones"
                    )
                _record_signal(
                    inst.symbol,
                    strategy,
                    "close",
                    target,
                    tick["bid"],
                    f"session: {session.reason}",
                )
                return

        desired = 1 if target > 0 else (-1 if target < 0 else 0)
        if desired == 0:
            action = "close" if signed != 0 else "hold"
        elif signed == 0:
            action = "open_long" if desired > 0 else "open_short"
        elif (signed > 0) == (desired > 0):
            action = "hold"
        else:
            action = "reverse"

        console.print(
            Panel(
                f"{inst.symbol} · {timeframe} · {strategy}\n"
                f"Señal: {target:+.0f} · ATR: {atr_value:.5f} · precio: {tick['bid']:.5f}\n"
                f"Posición actual: {signed:+g} lotes · acción: [bold]{action}[/bold]",
                title="Decisión forex",
            )
        )

        # 1) Cerrar si toca
        if action in {"close", "reverse"}:
            if execute:
                for p in positions:
                    broker.close_position(p["ticket"])
                console.print(f"[green]Cerradas {len(positions)} posiciones[/green]")
                state = _prop_state_from_mt5(broker, rules)
            else:
                console.print(
                    f"[yellow]DRY RUN[/yellow] cerraría {len(positions)} posiciones "
                    f"({signed:+g} lotes)"
                )
                state.open_lots = max(0.0, state.open_lots - abs(signed))
                state.open_positions = max(0, state.open_positions - len(positions))

        if action in {"close", "hold"}:
            _record_signal(
                inst.symbol, strategy, "sell" if signed > 0 else "buy", target, tick["bid"], action
            )
            return

        session = session_block(rules, asset_class="forex")
        if session.blocked:
            console.print(f"[red]Filtro de sesión:[/red] {session.reason}")
            _record_signal(
                inst.symbol, strategy, "hold", target, tick["bid"], f"session: {session.reason}"
            )
            return
        blackout = calendar_block_for_settings(DEFAULT_DB, settings)
        if blackout.blocked:
            console.print(f"[red]Blackout de calendario:[/red] {blackout.reason}")
            _record_signal(
                inst.symbol, strategy, "hold", target, tick["bid"], f"calendar: {blackout.reason}"
            )
            return

        # 2) Abrir con sizing por riesgo
        stop_distance = stop_atr * atr_value
        risk_per_lot = inst.risk_per_lot(stop_distance, quote_rate=qr)
        base_report = guard.evaluate(state)
        budget = min(rules.account_size * risk_pct, max(base_report.remaining_usd * 0.5, 0.0))
        lots = inst.lots_for_risk(budget, stop_distance, quote_rate=qr, cap_lots=rules.max_lots)
        report = guard.evaluate(state, proposed_lots=lots, risk_per_lot=risk_per_lot)

        console.print(
            f"Stop: {stop_distance:.5f} · riesgo/lote: {risk_per_lot:,.2f} USD · "
            f"presupuesto: {budget:,.2f} USD · lotes: [bold]{lots:g}[/bold]"
        )
        _print_guard(rules, report)

        if lots <= 0:
            console.print("[yellow]El lote mínimo no cabe en el presupuesto.[/yellow]")
            return
        if not report.allowed:
            console.print("[red]Orden bloqueada por el guard de fondeo.[/red]")
            _record_signal(
                inst.symbol, strategy, "hold", target, tick["bid"], f"blocked: {report.reason}"
            )
            return

        sign = 1 if desired > 0 else -1
        entry = tick["ask"] if sign > 0 else tick["bid"]
        sl = entry - sign * stop_distance
        tp = entry + sign * stop_distance * tp_rr
        side = "buy" if sign > 0 else "sell"

        if not execute:
            console.print(
                f"[yellow]DRY RUN[/yellow] {side} {lots:g} {inst.symbol} @ {entry:.5f} "
                f"SL {sl:.5f} TP {tp:.5f}"
            )
            _record_signal(inst.symbol, strategy, side, target, entry, "dry-run")
            return

        result = broker.submit_market(
            inst.symbol,
            sign * lots,
            sl=sl,
            tp=tp,
            bot=f"forex:{strategy}",
            reason=f"target={target:+.0f}",
        )
        console.print(f"[green]Ejecutado[/green] {result}")
        _record_signal(
            inst.symbol, strategy, side, target, result["price"], f"filled {lots:g} lots"
        )
    finally:
        broker.shutdown()


def _record_signal(
    symbol: str, strategy: str, side: str, strength: float, price: float, reason: str
) -> None:
    try:
        with connect(DEFAULT_DB) as con:
            con.execute(
                "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
                "VALUES(?,?,?,?,?,?,?)",
                (utcnow(), symbol, f"forex:{strategy}", side, strength, price, reason),
            )
    except Exception:
        pass


@prop_app.command("rules")
def prop_rules_cmd(
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase", help="challenge | verification | funded"),
    account_size: float = typer.Option(None, "--account-size"),
) -> None:
    """Muestra las reglas activas y los suelos calculados."""
    rules = _prop_rules(firm, phase, account_size)
    t = Table(title=f"Reglas · {rules.firm} · {rules.phase}")
    t.add_column("Regla", style="bold")
    t.add_column("Valor", justify="right")
    rows = [
        ("Cuenta", f"{rules.account_size:,.2f}"),
        ("Objetivo", f"{rules.profit_target_pct:.2%} ({rules.profit_target_usd:,.2f})"),
        ("Pérdida diaria máxima", f"{rules.max_daily_loss_pct:.2%} ({rules.daily_limit_usd:,.2f})"),
        ("Pérdida máxima", f"{rules.max_loss_pct:.2%} ({rules.max_loss_usd:,.2f})"),
        ("Modo pérdida máxima", rules.max_loss_mode),
        ("Base del límite diario", rules.daily_loss_mode),
        ("Colchón", f"{rules.buffer_pct:.0%}"),
        ("Límite diario efectivo", f"{rules.effective_daily_limit_usd:,.2f}"),
        ("Límite máximo efectivo", f"{rules.effective_max_loss_usd:,.2f}"),
        ("Días mínimos", str(rules.min_trading_days)),
        ("Consistencia", f"{rules.consistency_pct:.0%}" if rules.consistency_pct else "no configurada"),
        ("Máx. lotes", str(rules.max_lots) if rules.max_lots else "sin límite"),
        ("Máx. posiciones", str(rules.max_positions) if rules.max_positions else "sin límite"),
        ("Reset", f"{rules.reset_time} {rules.reset_tz}"),
        (
            "Fin de semana",
            "permitido" if rules.weekend_holding else "aplanar antes del viernes",
        ),
        (
            "Blackout noticias",
            f"{rules.news_blackout_min} min antes/después"
            if rules.news_blackout_min > 0
            else "desactivado",
        ),
        (
            "Corte viernes",
            f"{int(rules.friday_cutoff_hour):02d}:00 {rules.reset_tz}"
            if rules.friday_cutoff_hour is not None
            else f"{rules.friday_close_utc} UTC",
        ),
        (
            "Rollover",
            f"{rules.rollover_utc} UTC ± {rules.rollover_blackout_min} min"
            if rules.rollover_blackout_min > 0
            else "desactivado",
        ),
    ]
    for k, v in rows:
        t.add_row(k, v)
    console.print(t)
    if rules.verify_against_contract:
        console.print(
            "[yellow]Plantilla: confirma cada valor en el contrato de tu firma antes de operar.[/yellow]"
        )


@prop_app.command("status")
def prop_status(
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase"),
    account_size: float = typer.Option(None, "--account-size"),
    equity: float | None = typer.Option(None, "--equity", help="Equity manual si no usas MT5"),
    from_mt5: bool = typer.Option(False, "--from-mt5", help="Leer la cuenta real del terminal"),
) -> None:
    """Dice cuánto colchón queda antes de romper una regla."""
    rules = _prop_rules(firm, phase, account_size)
    guard = PropGuard(rules)

    if from_mt5:
        broker = _mt5(get_settings(), dry_run=True)
        try:
            state = _prop_state_from_mt5(broker, rules)
        finally:
            broker.shutdown()
    else:
        eq = float(equity if equity is not None else rules.account_size)
        state = AccountState(
            balance=eq,
            equity=eq,
            initial_balance=rules.account_size,
            day_start_balance=rules.account_size,
            day_start_equity=rules.account_size,
            peak_balance=max(eq, rules.account_size),
            peak_equity=max(eq, rules.account_size),
        )

    _print_guard(rules, guard.evaluate(state))


@prop_app.command("size")
def prop_size(
    symbol: str = typer.Argument(..., help="Ej. EURUSD"),
    risk_pct: float = typer.Option(0.005, "--risk-pct", help="Riesgo por operación (0.005 = 0.5%)"),
    stop_pips: float = typer.Option(20.0, "--stop-pips"),
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase"),
    account_size: float = typer.Option(None, "--account-size"),
    from_mt5: bool = typer.Option(False, "--from-mt5"),
    quote_rate: float | None = typer.Option(None, "--quote-rate"),
) -> None:
    """Tamaño de la operación aplicando el colchón que exige la firma."""
    rules = _prop_rules(firm, phase, account_size)
    guard = PropGuard(rules)

    if from_mt5:
        broker = _mt5(get_settings(), dry_run=True)
        try:
            inst = broker.instrument(symbol)
            qr = quote_rate or _quote_rate(broker, inst)
            state = _prop_state_from_mt5(broker, rules)
        finally:
            broker.shutdown()
    else:
        inst = get_instrument(symbol)
        qr = quote_rate or 1.0
        eq = rules.account_size
        state = AccountState(
            balance=eq,
            equity=eq,
            initial_balance=rules.account_size,
            day_start_balance=eq,
            day_start_equity=eq,
            peak_balance=eq,
            peak_equity=eq,
        )

    stop_distance = stop_pips * inst.pip_size() if inst.is_fx else stop_pips * inst.tick_size
    risk_per_lot = inst.risk_per_lot(stop_distance, quote_rate=qr)
    report = guard.evaluate(state)
    budget = min(rules.account_size * risk_pct, max(report.remaining_usd * 0.5, 0.0))
    lots = inst.lots_for_risk(budget, stop_distance, quote_rate=qr)

    t = Table(title=f"Sizing con reglas · {symbol} · {rules.firm} {rules.phase}")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Suelo efectivo", f"{report.effective_floor:,.2f}")
    t.add_row("Colchón restante", f"{report.remaining_usd:,.2f}")
    t.add_row("Riesgo por operación", f"{rules.account_size * risk_pct:,.2f}")
    t.add_row("Presupuesto aplicado", f"{budget:,.2f}")
    t.add_row("Riesgo por lote", f"{risk_per_lot:,.2f}")
    t.add_row("Lotes", f"[bold]{lots:g}[/bold]")
    t.add_row("Riesgo real", f"{lots * risk_per_lot:,.2f}")
    console.print(t)
    _print_guard(rules, guard.evaluate(state, proposed_lots=lots, risk_per_lot=risk_per_lot))


@prop_app.command("check")
def prop_check(
    lots: float = typer.Option(0.10, "--lots"),
    stop_pips: float = typer.Option(20.0, "--stop-pips"),
    symbol: str = typer.Option("EURUSD", "--symbol"),
    equity: float | None = typer.Option(None, "--equity"),
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase"),
    account_size: float = typer.Option(None, "--account-size"),
) -> None:
    """Comprueba si una orden concreta sería aceptada o bloqueada."""
    rules = _prop_rules(firm, phase, account_size)
    inst = get_instrument(symbol)
    stop_distance = stop_pips * inst.pip_size() if inst.is_fx else stop_pips * inst.tick_size
    risk_per_lot = inst.risk_per_lot(stop_distance)
    eq = float(equity if equity is not None else rules.account_size)
    state = AccountState(
        balance=eq,
        equity=eq,
        initial_balance=rules.account_size,
        day_start_balance=eq,
        day_start_equity=eq,
        peak_balance=eq,
        peak_equity=eq,
    )
    report = PropGuard(rules).evaluate(state, proposed_lots=lots, risk_per_lot=risk_per_lot)
    _print_guard(rules, report)
    console.print(f"Orden: {lots:g} lotes · riesgo {lots * risk_per_lot:,.2f} USD · stop {stop_pips:g} pips")


@prop_app.command("simulate")
def prop_simulate(
    symbol: str = typer.Argument("SPY", help="Activo para tomar los retornos"),
    strategy: str = typer.Option("trend", "--strategy", "-s", help=", ".join(STRATEGIES)),
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase"),
    account_size: float = typer.Option(None, "--account-size"),
    paths: int = typer.Option(5_000, "--paths"),
    horizon: int = typer.Option(60, "--horizon", help="Días por simulación"),
    block_size: int = typer.Option(1, "--block-size", help="Bootstrap por bloques (captura autocorrelación)"),
    start: str = typer.Option(None, "--start"),
    end: str = typer.Option(None, "--end"),
) -> None:
    """Monte Carlo: probabilidad de pasar el challenge antes de reventar."""
    if strategy not in STRATEGIES:
        console.print(f"[red]Estrategia desconocida:[/red] {strategy}")
        raise typer.Exit(2)

    settings = get_settings()
    rules = _prop_rules(firm, phase, account_size)
    df = data_mod.fetch(
        symbol.upper(), start or _default_start(), end or _today(), settings.data.cache_dir
    )
    sig = STRATEGIES[strategy](df)
    bt = run_backtest(
        df,
        sig.target,
        starting_cash=rules.account_size,
        commission_bps=settings.execution.commission_bps,
        slippage_bps=settings.execution.slippage_bps,
    )
    result = monte_carlo(
        rules, bt.returns, n_paths=paths, horizon=horizon, block_size=block_size
    )

    t = Table(title=f"Monte Carlo · {symbol.upper()} · {strategy} · {rules.firm} {rules.phase}")
    t.add_column("Métrica", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Reglas", rules.describe())
    t.add_row("Días de muestra", str(result["sample_days"]))
    t.add_row("Retorno medio diario", _fmt_pct(result["mean_daily_return"]))
    t.add_row("Volatilidad diaria", _fmt_pct(result["daily_volatility"]))
    t.add_row("Simulaciones", str(result["paths"]))
    t.add_row("Horizonte", f"{result['horizon_days']} días")
    t.add_row("Prob. de pasar", f"[bold]{result['pass_rate']:.1%}[/bold]")
    t.add_row("IC 95%", f"{result['pass_ci95'][0]:.1%} – {result['pass_ci95'][1]:.1%}")
    t.add_row("Prob. de reventar", _fmt_pct(result["breach_rate"]))
    t.add_row("Sin resultado", _fmt_pct(result["timeout_rate"]))
    if result["median_days_to_pass"]:
        t.add_row("Días hasta pasar (mediana)", f"{result['median_days_to_pass']:.0f}")
        t.add_row("Días hasta pasar (p90)", f"{result['p90_days_to_pass']:.0f}")
    t.add_row("Max DD mediana", _fmt_pct(result["median_max_drawdown"]))
    t.add_row("Peor max DD", _fmt_pct(result["worst_max_drawdown"]))
    console.print(t)
    console.print(
        "[dim]Aproximación con datos diarios: el riesgo intradía real es algo mayor.[/dim]"
    )


@app.command("research")
def research_cmd(
    symbols: str = typer.Option(
        None, "--symbols", help="Lista separada por comas (ej. SPY,QQQ,EURUSD=X)"
    ),
    strategies: str = typer.Option(
        None, "--strategies", help="Lista separada por comas: trend, trend-ls, meanrev"
    ),
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase"),
    account_size: float = typer.Option(None, "--account-size"),
    paths: int = typer.Option(2_000, "--paths", help="Simulaciones Monte Carlo por candidato"),
    horizon: int = typer.Option(120, "--horizon", help="Días por simulación (FTMO no tiene límite de tiempo)"),
    block_size: int = typer.Option(5, "--block-size", help="Bootstrap por bloques"),
    start: str = typer.Option("2015-01-01", "--start"),
    end: str = typer.Option(None, "--end"),
    top: int = typer.Option(20, "--top", help="Filas del ranking a mostrar"),
    min_pass: float = typer.Option(0.35, "--min-pass", help="Pasa mínimo para proponer"),
    min_oos_pass: float = typer.Option(0.25, "--min-oos-pass", help="Pasa mínimo out-of-sample"),
    min_dsr: float = typer.Option(0.90, "--min-dsr", help="Deflated Sharpe Ratio mínimo"),
    wf_folds: int = typer.Option(4, "--wf-folds", help="Bloques walk-forward"),
    min_wf_positive: int = typer.Option(2, "--min-wf-positive", help="Bloques positivos mínimos"),
    pbo_slices: int = typer.Option(16, "--pbo-slices", help="Bloques CSCV (par, >= 4)"),
    max_pbo: float = typer.Option(0.30, "--max-pbo", help="PBO máximo (global y por activo)"),
    max_breach: float = typer.Option(0.15, "--max-breach", help="Revienta máximo para proponer"),
    holdout: float = typer.Option(0.30, "--holdout", help="Fracción final reservada a validación"),
    min_trades: int = typer.Option(20, "--min-trades"),
    exposures: str = typer.Option("1.0,0.5", "--exposures", help="Escalas de exposición a probar"),
    out: str = typer.Option(None, "--out", help="Carpeta de salida"),
) -> None:
    """Barrido de activos × estrategias × parámetros, puntuado contra las reglas.

    Genera un ranking y un archivo de propuestas. Nunca activa bots: las
    propuestas quedan con `enabled: false` para revisión humana.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from .research import DEFAULT_SYMBOLS, GRIDS, ResearchConfig, run_research, write_outputs

    settings = get_settings()
    rules = _prop_rules(firm, phase, account_size)
    cfg = ResearchConfig(
        symbols=[s.strip().upper() for s in (symbols or ",".join(DEFAULT_SYMBOLS)).split(",") if s.strip()],
        strategies=[s.strip() for s in (strategies or ",".join(GRIDS)).split(",") if s.strip()],
        start=start,
        end=end or "",
        account_size=rules.account_size,
        paths=paths,
        horizon=horizon,
        block_size=block_size,
        min_trades=min_trades,
        min_pass=min_pass,
        min_oos_pass=min_oos_pass,
        max_breach=max_breach,
        min_dsr=min_dsr,
        wf_folds=wf_folds,
        min_wf_positive=min_wf_positive,
        pbo_slices=pbo_slices,
        max_pbo=max_pbo,
        holdout_fraction=holdout,
        exposures=[float(x) for x in exposures.split(",") if x.strip()],
        commission_bps=settings.execution.commission_bps,
        slippage_bps=settings.execution.slippage_bps,
    )
    unknown = [s for s in cfg.strategies if s not in STRATEGIES]
    if unknown:
        console.print(f"[red]Estrategias desconocidas:[/red] {', '.join(unknown)}")
        raise typer.Exit(2)
    if cfg.pbo_slices < 4 or cfg.pbo_slices % 2:
        console.print("[red]--pbo-slices debe ser par y >= 4[/red]")
        raise typer.Exit(2)

    console.print(
        Panel(
            f"{len(cfg.symbols)} activos × {len(cfg.strategies)} estrategias · "
            f"{cfg.paths} paths · horizonte {cfg.horizon} d · "
            f"OOS {cfg.holdout_fraction:.0%}\n"
            f"Reglas: {rules.describe()}",
            title="Investigación",
        )
    )

    out_dir = Path(out) if out else ROOT / "reports" / "research"
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("Descargando datos, backtest y Monte Carlo...", total=None)
        from .learning import count_tests

        report = run_research(
            cfg,
            rules,
            settings.data.cache_dir,
            artifacts_dir=out_dir / "artifacts",
            extra_trials=count_tests(DEFAULT_DB),
        )

    files = write_outputs(report, out_dir)

    if not report["results"]:
        console.print("[red]Sin candidatos evaluados.[/red] Revisa los errores del reporte.")
        for e in report["errors"][:5]:
            console.print(f"  [yellow]{e}[/yellow]")
        raise typer.Exit(1)

    table = Table(title=f"Ranking · {report['candidates']} candidatos")
    table.add_column("#", justify="right")
    table.add_column("Activo", style="bold")
    table.add_column("Estrategia")
    table.add_column("Parámetros")
    table.add_column("Escala", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("MaxDD", justify="right")
    table.add_column("Pasa", justify="right")
    table.add_column("Revienta", justify="right")
    table.add_column("Score", justify="right")

    for i, r in enumerate(report["results"][:top], 1):
        params = " ".join(f"{k}={v}" for k, v in r["params"].items())
        table.add_row(
            str(i),
            r["symbol"],
            r["strategy"],
            params,
            f"{r['exposure']:g}×",
            f"{r['sharpe']:,.2f}",
            _fmt_pct(r["max_drawdown"]),
            f"[green]{r['pass_rate']:.1%}[/green]",
            f"[red]{r['breach_rate']:.1%}[/red]",
            f"{r['score']:,.3f}",
        )
    console.print(table)

    pbo = report.get("pbo")
    if pbo:
        console.print(
            f"PBO CSCV: [bold]{pbo['pbo']:.1%}[/bold] · {pbo.get('verdict', '—')} · "
            f"{pbo.get('n_variants', 0)} variantes · {pbo.get('n_slices', 0)} bloques · "
            f"{pbo.get('n_combinations', 0):,} combinaciones"
        )
    else:
        console.print("[yellow]PBO CSCV no disponible: muestra insuficiente.[/yellow]")

    n = len(report["proposals"])
    if n:
        console.print(
            f"[bold green]{n} propuesta(s)[/bold green] en {files['proposals_md']} "
            "[dim](enabled: false, requieren aprobación)[/dim]"
        )
    else:
        console.print(
            "[yellow]Ningún candidato cumple los criterios.[/yellow] "
            "No pagues un challenge con estas estrategias todavía."
        )
    console.print(f"Reporte: {files['latest_md']}")
    console.print(f"JSON:    {files['latest_json']}")


@app.command("research-horizons")
def research_horizons_cmd(
    top: int = typer.Option(10, "--top", help="Variantes del ranking a simular"),
    paths: int = typer.Option(2_000, "--paths", help="Paths Monte Carlo por celda"),
    out: str = typer.Option(None, "--out", help="Carpeta de research"),
) -> None:
    """Monte Carlo 22/44/120d para el top de research (informativo)."""
    from .horizons import matrix, write

    report_dir = Path(out) if out else ROOT / "reports" / "research"
    if not (report_dir / "latest.json").exists():
        console.print(f"[red]No existe {report_dir / 'latest.json'}.[/red] Ejecuta lab research.")
        raise typer.Exit(1)
    console.print(
        Panel(
            f"Top {top} · {paths} paths · horizontes 22/44/120d · "
            "exposiciones 0.5×/1×/2×\n"
            "FTMO 100k 2-step + Topstep 50K (plantilla). No cambia criterios.",
            title="Monte Carlo por horizonte",
        )
    )
    payload = matrix(report_dir, top=top, paths=paths)
    files = write(payload, report_dir)
    console.print(
        f"[green]Tabla generada[/green] · {files['md']} · {files['json']}"
    )
    for firm in payload["firms"]:
        console.print(f"[dim]{firm['name']}: {len(firm['variants'])} variantes × "
                      f"{len(payload['exposures'])} exposiciones.[/dim]")


@app.command("research-intraday")
def research_intraday_cmd(
    symbol: str = typer.Option("EURUSD", "--symbol"),
    timeframe: str = typer.Option("M15", "--timeframe"),
    paths: int = typer.Option(500, "--paths"),
    point: float = typer.Option(0.0001, "--point"),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Valida estrategias intradía sobre caché MT5 (DSR/PBO/WF/regímenes)."""
    from .intraday import load_bars, run_intraday, write

    settings = get_settings()
    try:
        df = load_bars(settings.data.cache_dir, symbol, timeframe)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red] Ejecuta: lab mt5 fetch {symbol} --timeframe {timeframe}")
        raise typer.Exit(1)
    report = run_intraday(
        df,
        symbol=symbol,
        timeframe=timeframe,
        paths=paths,
        point=point,
    )
    files = write(report, Path(out) if out else ROOT / "reports" / "research")
    console.print(
        Panel(
            f"{symbol} · {timeframe} · {report['bars']['rows']:,} barras "
            f"({report['bars']['years']} años)\n"
            f"Spread confiable: {'sí' if report['spread_reliable'] else 'NO'}\n"
            f"PBO: {report['pbo']['pbo']:.1%}" if report.get("pbo") else
            f"{symbol} · {timeframe} · PBO sin datos",
            title="Intradía FX/CFD",
        )
    )
    console.print(
        f"Pasan {report['passed']}/{len(report['outcomes'])} · {files['md']}"
    )


@app.command("research-clusters")
def research_clusters_cmd(
    threshold: float = typer.Option(0.70, "--threshold", help="Umbral de |correlación|"),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Agrupa bots correlacionados y aplica presupuesto por clúster."""
    from .portfolio import load_clusters, write

    report_dir = Path(out) if out else ROOT / "reports" / "research"
    report = load_clusters(report_dir, threshold=threshold)
    files = write(report, report_dir)
    t = Table(title=f"Clústeres de correlación · umbral {threshold:.2f}")
    t.add_column("#", justify="right")
    t.add_column("Bots", overflow="fold")
    t.add_column("N", justify="right")
    t.add_column("Riesgo máx.", justify="right")
    for i, cluster in enumerate(report.get("clusters") or [], 1):
        t.add_row(
            str(i),
            "; ".join(cluster["members"]),
            str(cluster["size"]),
            f"{cluster['max_risk_pct']:.1%}",
        )
    console.print(t)
    if report.get("error"):
        console.print(f"[yellow]{report['error']}[/yellow]")
    console.print(f"[green]Tabla generada[/green] · {files['md']} · {files['json']}")


@app.command("portfolio-simulate")
def portfolio_simulate_cmd(
    top: int = typer.Option(10, "--top"),
    paths: int = typer.Option(2_000, "--paths"),
    max_per_cluster: int = typer.Option(2, "--max-per-cluster"),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Simula una cartera equiponderada respetando clústeres."""
    from .portfolio import simulate, write_simulation

    report_dir = Path(out) if out else ROOT / "reports" / "research"
    try:
        payload = simulate(
            report_dir,
            top=top,
            paths=paths,
            max_per_cluster=max_per_cluster,
        )
    except Exception as exc:
        console.print(f"[red]No se pudo simular la cartera:[/red] {exc}")
        raise typer.Exit(1)
    files = write_simulation(payload, report_dir)
    console.print(
        Panel(
            f"{len(payload['members'])} bots · equiponderada · "
            f"retorno {payload['portfolio']['total_return']:.1%} · "
            f"Sharpe {payload['portfolio']['sharpe']:.2f} · "
            f"MaxDD {payload['portfolio']['max_drawdown']:.1%}\n"
            f"Monte Carlo: {len(payload['monte_carlo'])} celdas",
            title="Cartera simulada",
        )
    )
    console.print(f"[green]Tabla generada[/green] · {files['md']} · {files['json']}")


@app.command("research-costs")
def research_costs_cmd(
    top: int = typer.Option(10, "--top"),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Sensibilidad del top de research a comisión y slippage."""
    from .costs import run_costs, write

    settings = get_settings()
    report_dir = Path(out) if out else ROOT / "reports" / "research"
    try:
        payload = run_costs(report_dir, cache_dir=settings.data.cache_dir, top=top)
    except Exception as exc:
        console.print(f"[red]No se pudo calcular la sensibilidad:[/red] {exc}")
        raise typer.Exit(1)
    files = write(payload, report_dir)
    console.print(
        Panel(
            f"{len(payload['results'])} variantes · "
            f"frágiles {payload['fragile_count']} · escenarios {', '.join(payload['scenarios'])}",
            title="Sensibilidad a costes",
        )
    )
    console.print(f"[green]Tabla generada[/green] · {files['md']} · {files['json']}")


# ==================================================================== Futuros

@futures_app.command("status")
def futures_status() -> None:
    """Cuenta de futuros en ProjectX/TopstepX y permiso de trading."""
    settings = get_settings()
    broker = _futures(settings, dry_run=True)
    try:
        health = broker.health()
        accounts = broker.accounts()
    finally:
        broker.close()

    t = Table(title="ProjectX / TopstepX")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    for key in ("account_id", "name", "balance", "simulated", "can_trade", "dry_run", "require_simulated", "base_url"):
        value = health[key]
        t.add_row(key, f"{value:,.2f}" if isinstance(value, float) else str(value))
    console.print(t)

    if len(accounts) > 1:
        tt = Table(title=f"Cuentas activas ({len(accounts)})")
        tt.add_column("ID", justify="right")
        tt.add_column("Nombre")
        tt.add_column("Balance", justify="right")
        tt.add_column("Simulada")
        tt.add_column("CanTrade")
        for a in accounts:
            tt.add_row(
                str(a.get("id")),
                str(a.get("name")),
                f"{float(a.get('balance') or 0):,.2f}",
                str(bool(a.get("simulated"))),
                str(bool(a.get("canTrade"))),
            )
        console.print(tt)

    if not health["can_trade"]:
        console.print("[yellow]La cuenta tiene canTrade=false: las órdenes serán rechazadas.[/yellow]")
    if health["dry_run"]:
        console.print("[dim]dry_run activo: las órdenes se validan pero no se envían.[/dim]")


@futures_app.command("contracts")
def futures_contracts(
    search: str = typer.Argument("NQ", help="Símbolo o texto, ej. NQ, MNQ, ES"),
    live: bool = typer.Option(False, "--live", help="Buscar contratos en vivo (por defecto demo)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Máximo de filas"),
) -> None:
    """Busca contratos disponibles y muestra tick size/value."""
    broker = _futures(get_settings(), dry_run=True)
    try:
        contracts = broker.search_contracts(search, live=live)
    finally:
        broker.close()

    if not contracts:
        console.print(f"[yellow]Sin contratos para '{search}'.[/yellow]")
        return
    t = Table(title=f"Contratos para '{search}' ({len(contracts)})")
    t.add_column("ID", style="bold")
    t.add_column("Nombre")
    t.add_column("Descripción")
    t.add_column("Tick", justify="right")
    t.add_column("Tick $", justify="right")
    t.add_column("Activo")
    for c in contracts[:limit]:
        t.add_row(
            str(c.get("id")),
            str(c.get("name")),
            str(c.get("description")),
            f"{float(c.get('tickSize') or 0):g}",
            f"{float(c.get('tickValue') or 0):,.2f}",
            "sí" if c.get("activeContract") else "no",
        )
    console.print(t)


@futures_app.command("order")
def futures_order(
    symbol: str = typer.Argument(..., help="Ej. NQ, MNQ, ES"),
    side: str = typer.Option(..., "--side", "-s", help="buy | sell"),
    size: int = typer.Option(1, "--size", "-q", help="Número de contratos"),
    order_type: str = typer.Option("market", "--type", "-t", help="market | limit | stop"),
    price: float = typer.Option(None, "--price", help="Precio límite o stop"),
    stop_loss_ticks: int = typer.Option(None, "--stop-loss-ticks", help="Bracket de stop en ticks"),
    take_profit_ticks: int = typer.Option(None, "--take-profit-ticks", help="Bracket de objetivo en ticks"),
    execute: bool = typer.Option(False, "--execute", help="Enviar de verdad (si no, dry-run)"),
) -> None:
    """Valida o envía una orden de futuros con brackets opcionales."""
    settings = get_settings()
    broker = _futures(settings, dry_run=not execute)
    try:
        contract = broker.resolve_contract(symbol)
        result = broker.place_order(
            str(contract["id"]),
            side,
            size,
            order_type=order_type,
            limit_price=price if order_type in {"limit", "stop_limit"} else None,
            stop_price=price if order_type in {"stop", "stop_limit"} else None,
            stop_loss_ticks=stop_loss_ticks,
            take_profit_ticks=take_profit_ticks,
            custom_tag=f"lab:{symbol.upper()}",
            reason="cli futures order",
        )
    finally:
        broker.close()

    t = Table(title="Orden de futuros")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    for key, value in result.items():
        t.add_row(key, f"{value:g}" if isinstance(value, (int, float)) and value is not None else str(value))
    console.print(t)
    console.print(f"Contrato: {contract.get('name')} ({contract.get('id')})")
    if result.get("dry_run"):
        console.print("[yellow]Dry-run: no se envió nada. Añade --execute para operar.[/yellow]")


@futures_app.command("positions")
def futures_positions() -> None:
    """Posiciones abiertas en la cuenta de futuros."""
    broker = _futures(get_settings(), dry_run=True)
    try:
        positions = broker.positions()
    finally:
        broker.close()

    if not positions:
        console.print("[dim]Sin posiciones abiertas.[/dim]")
        return
    t = Table(title="Posiciones de futuros")
    for col in ("Contrato", "Nombre", "Lado", "Tamaño", "Precio medio"):
        t.add_column(col, justify="right" if col in {"Tamaño", "Precio medio"} else "left")
    for p in positions:
        t.add_row(
            str(p["contract_id"]),
            str(p["name"]),
            str(p["side"]),
            str(p["size"]),
            f"{float(p['avg_price'] or 0):,.2f}",
        )
    console.print(t)


@futures_app.command("close")
def futures_close(
    contract_id: str = typer.Argument(..., help="ID del contrato a cerrar"),
    execute: bool = typer.Option(False, "--execute", help="Cerrar de verdad"),
) -> None:
    """Cierra toda la posición de un contrato."""
    broker = _futures(get_settings(), dry_run=not execute)
    try:
        result = broker.close_position(contract_id, reason="cli futures close")
    finally:
        broker.close()
    console.print(
        f"Contrato {result['contract_id']}: {result['status']}"
        + (" [yellow](dry-run)[/yellow]" if result.get("dry_run") else "")
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()

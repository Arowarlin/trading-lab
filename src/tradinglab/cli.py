from __future__ import annotations

import json
import platform
import sys
from datetime import date, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from . import data as data_mod
from .agents import AgentError, RATING_TO_TARGET, run_tradingagents
from .backtest import run as run_backtest
from .config import DEFAULT_DB, ROOT, get_settings
from .db import connect, init_db, utcnow
from .execution import AlpacaError, PaperBroker, get_broker, get_mt5_broker
from .indicators import atr as atr_indicator
from .instruments import InstrumentError, get_instrument, list_instruments
from .llm import LLMClient
from .orchestrator import run_all
from .prop import AccountState, PropError, PropGuard, PropRules, from_yaml, ftmo, monte_carlo
from .reporting import build_dashboard
from .risk import check_order, kill_switch, size_position
from .strategies import STRATEGIES

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="TradingLab: datos, backtest, paper trading y agentes LLM.",
)
mt5_app = typer.Typer(no_args_is_help=True, help="MetaTrader 5: conexión, precios, sizing y órdenes.")
prop_app = typer.Typer(no_args_is_help=True, help="Cuentas de fondeo: reglas, estado y Monte Carlo.")
app.add_typer(mt5_app, name="mt5")
app.add_typer(prop_app, name="prop")
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
    import os

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
            table.add_row(
                "MetaTrader 5",
                OK if health["connected"] else WARN,
                f"{health['server']} · {health['mode']} · equity={health['equity']:,.2f} "
                f"· algo={'on' if health['trade_allowed'] else 'OFF'} "
                f"· server GMT{health['server_utc_offset_hours']:+g}",
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

    killed, reason = kill_switch(broker.equity_series(), settings.risk)
    if killed:
        console.print(Panel(f"KILL SWITCH ACTIVO: {reason}", style="bold red"))
        raise typer.Exit(1)

    desired = size_position(snap["equity"], price, atr_value, settings.risk) if target > 0 else 0
    delta = int(desired - held)

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


@app.command()
def agent(
    ticker: str = typer.Argument(..., help="Símbolo, p. ej. NVDA"),
    analysis_date: str = typer.Option(None, "--date", help="YYYY-MM-DD (por defecto hoy)"),
    analysts: str = typer.Option("market,news", "--analysts", help="market,news,social,fundamentals"),
    save: bool = typer.Option(True, "--save/--no-save", help="Guardar informe completo"),
) -> None:
    """Ejecuta TradingAgents y muestra su rating (lento con modelos locales)."""
    init_db(DEFAULT_DB)
    day = analysis_date or _today()
    console.print(
        Panel(
            f"Ticker: [bold]{ticker.upper()}[/bold] · fecha: {day}\n"
            f"Analistas: {analysts} · modelo: {get_settings().llm.model}\n"
            "[dim]Un run local puede tardar entre 10 y 60 minutos. No cierres la ventana.[/dim]",
            title="TradingAgents",
        )
    )
    try:
        result = run_tradingagents(ticker, day, analysts, save=save)
    except AgentError as exc:
        console.print(Panel(str(exc)[-3000:], title="TradingAgents falló", style="bold red"))
        raise typer.Exit(1)

    table = Table(title=f"Decisión · {ticker.upper()} · {day}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Rating", f"[bold]{result.get('rating')}[/bold]")
    table.add_row("Modelo", str(result.get("model")))
    table.add_row("Duración", f"{result.get('elapsed_s')} s")
    if result.get("reports_path"):
        table.add_row("Informe", str(result["reports_path"]))
    console.print(table)

    decision = (result.get("decision") or "").strip()
    if decision:
        console.print(Panel(decision[:4000], title="Decisión del Portfolio Manager", overflow="fold"))


@app.command("agent-run")
def agent_run(
    ticker: str = typer.Argument(..., help="Símbolo, p. ej. NVDA"),
    analysis_date: str = typer.Option(None, "--date", help="YYYY-MM-DD (por defecto hoy)"),
    analysts: str = typer.Option("market,news", "--analysts"),
    execute: bool = typer.Option(True, "--execute/--dry-run"),
) -> None:
    """TradingAgents decide y la orden se aplica a la cuenta paper."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    day = analysis_date or _today()

    try:
        result = run_tradingagents(ticker, day, analysts, save=True)
    except AgentError as exc:
        console.print(Panel(str(exc)[-3000:], title="TradingAgents falló", style="bold red"))
        raise typer.Exit(1)

    rating = str(result.get("rating", "REVIEW"))
    target_fraction = RATING_TO_TARGET.get(rating, None)
    console.print(f"[bold]{ticker.upper()}[/bold] · rating=[bold]{rating}[/bold] · target={target_fraction}")

    if target_fraction is None:
        console.print("[yellow]Hold / REVIEW: no se modifica la posición.[/yellow]")
        with connect(DEFAULT_DB) as con:
            con.execute(
                "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) VALUES(?,?,?,?,?,?,?)",
                (utcnow(), ticker.upper(), "tradingagents", "hold", None, None, f"rating={rating}"),
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

    killed, reason = kill_switch(broker.equity_series(), settings.risk)
    if killed:
        console.print(Panel(f"KILL SWITCH ACTIVO: {reason}", style="bold red"))
        raise typer.Exit(1)

    if target_fraction > 0:
        max_pct = settings.risk.max_position_pct * float(target_fraction)
        desired = size_position(snap["equity"], price, atr_value, settings.risk, max_pct=max_pct)
    else:
        desired = 0

    delta = int(desired - held)
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
        ticker.upper(), delta, price, bot="tradingagents", reason=f"rating={rating}"
    )
    with connect(DEFAULT_DB) as con:
        con.execute(
            "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) VALUES(?,?,?,?,?,?,?)",
            (utcnow(), ticker.upper(), "tradingagents", fill["side"], target_fraction, price, f"rating={rating}"),
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

    killed, reason = kill_switch(eq, settings.risk)
    if killed:
        console.print(Panel(f"KILL SWITCH: {reason}", style="bold red"))


@app.command("bots")
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
    t.add_column("Estado")
    t.add_column("Descripción", overflow="fold")
    for bot in data.get("bots", []):
        t.add_row(
            bot.get("id", ""),
            bot.get("type", ""),
            bot.get("strategy", ""),
            bot.get("enabled", False) and "on" or "off",
            bot.get("description", ""),
        )
    console.print(t)


@app.command()
def dashboard() -> None:
    """Genera reports/dashboard.html con equity, posiciones y órdenes."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    broker = get_broker(settings, DEFAULT_DB)
    path = build_dashboard(settings, broker, DEFAULT_DB)
    console.print(f"[green]Dashboard generado:[/green] {path}")
    console.print("[dim]Ábrelo en el navegador o sírvelo con `python -m http.server -d reports`[/dim]")


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
            tick = broker.tick(symbol)
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
        tick = {"bid": None}

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
        holdout_fraction=holdout,
        exposures=[float(x) for x in exposures.split(",") if x.strip()],
        commission_bps=settings.execution.commission_bps,
        slippage_bps=settings.execution.slippage_bps,
    )
    unknown = [s for s in cfg.strategies if s not in STRATEGIES]
    if unknown:
        console.print(f"[red]Estrategias desconocidas:[/red] {', '.join(unknown)}")
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

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("Descargando datos, backtest y Monte Carlo...", total=None)
        report = run_research(cfg, rules, settings.data.cache_dir)

    out_dir = Path(out) if out else ROOT / "reports" / "research"
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

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
from .execution import (
    get_broker,
    get_broker_for_account,
    get_mt5_broker,
    get_projectx_broker,
)
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
from .killswitch import allows_order
from .killswitch import ensure as ensure_killswitch
from .killswitch import evaluate as evaluate_killswitch
from .killswitch import load_state as load_killswitch
from .killswitch import reset as reset_killswitch
from .llm import LLMClient
from .orchestrator import load_bots, run_all, write_dry_run_log
from .prop import AccountState, PropGuard, PropRules, from_yaml, ftmo, monte_carlo
from .prop.defense import FlattenClock, TrailingDrawdown
from .reconciliation import reconcile as reconcile_broker
from .reporting import build_dashboard
from .risk import check_order, size_position
from .session import flatten_required, session_block
from .strategies import STRATEGIES
from .time_utils import market_today, utc_now

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
guardian_app = typer.Typer(
    no_args_is_help=True,
    help="Guardián MQL5: exporta límites y magics para el EA de equity.",
)
audit_app = typer.Typer(
    no_args_is_help=True,
    help="Auditoría: cadena de hash de orders y console_actions.",
)
alerts_app = typer.Typer(
    no_args_is_help=True, help="Alertas ntfy/Telegram, latido y chequeo de servicios."
)
heartbeat_app = typer.Typer(
    no_args_is_help=True, help="Latidos Healthchecks.io: setup, ping y estado."
)
bots_app = typer.Typer(no_args_is_help=True, help="Bots: listar, evaluar, proponer, archivar.")
decisions_app = typer.Typer(no_args_is_help=True, help="Decisiones LLM: resultados y líneas base.")
fund_app = typer.Typer(no_args_is_help=True, help="Fondo: cuentas, límites e historial.")
operator_app = typer.Typer(
    no_args_is_help=True,
    help="Modo operador de la consola: PIN, estado y auditoría.",
)
campaign_app = typer.Typer(
    no_args_is_help=True,
    help="Campaña de investigación registrada: universo, N_total y una sola pasada.",
)
data_app = typer.Typer(
    no_args_is_help=True, help="Datos: control cruzado y fuentes públicas."
)
lessons_app = typer.Typer(no_args_is_help=True, help="Aprendizaje controlado: lecciones y holdout.")
reports_app = typer.Typer(no_args_is_help=True, help="Reportes CSV/HTML con validación y vista previa.")
markets_app = typer.Typer(no_args_is_help=True, help="Agentes por mercado y coordinador determinista.")
models_app = typer.Typer(no_args_is_help=True, help="Modelos walk-forward, registry y campeón/retador.")
intel_app = typer.Typer(no_args_is_help=True, help="Información continua: RSS, saneado y estado.")
telegram_app = typer.Typer(
    no_args_is_help=True,
    help="Telegram remoto: setup, estado y puente de control.",
)
lifecycle_app = typer.Typer(
    no_args_is_help=True,
    help="Incubadora: estados, criterios congelados y reporte forward.",
)
ticks_app = typer.Typer(
    no_args_is_help=True,
    help="Ticks Dukascopy: descarga, parquet y métricas de spread.",
)
slippage_app = typer.Typer(
    no_args_is_help=True,
    help="Sonda de slippage real en demo: medición aislada, sin bots.",
)
intraday_app = typer.Typer(
    no_args_is_help=True,
    help="Forward intradía: dos candidatos fijos, dry-run por defecto.",
)
llm_app = typer.Typer(
    no_args_is_help=True,
    help="LLM local: validación de esquema y comparación de modelos lite.",
)
risk_budget_app = typer.Typer(
    no_args_is_help=True,
    help="Riesgo neto por activo, clúster USD y rebanadas por bot.",
)
library_app = typer.Typer(
    no_args_is_help=True,
    help="Biblioteca de conocimiento: fichas de herramientas y metodologías.",
)
stats_app = typer.Typer(
    no_args_is_help=True,
    help="Estadística y DSR: recálculo v2 de solo lectura.",
)
costs_app = typer.Typer(
    no_args_is_help=True,
    help="Costes: sincronización de swap desde MT5 (solo lectura).",
)
app.add_typer(mt5_app, name="mt5")
app.add_typer(prop_app, name="prop")
app.add_typer(futures_app, name="futures")
app.add_typer(killswitch_app, name="killswitch")
app.add_typer(guardian_app, name="guardian")
app.add_typer(audit_app, name="audit")
app.add_typer(alerts_app, name="alerts")
app.add_typer(heartbeat_app, name="heartbeat")
app.add_typer(bots_app, name="bots")
app.add_typer(decisions_app, name="decisions")
app.add_typer(fund_app, name="fund")
app.add_typer(operator_app, name="operator")
app.add_typer(campaign_app, name="campaign")
app.add_typer(data_app, name="data")
app.add_typer(risk_budget_app, name="risk-budget")
app.add_typer(stats_app, name="stats")
app.add_typer(costs_app, name="costs")
app.add_typer(lifecycle_app, name="lifecycle")
ai_trader_app = typer.Typer(
    no_args_is_help=True,
    help="Carril IA discrecional (solo demo): snapshot, propose, skip, execute, status, manage, scoreboard, learn, distill, replay, review.",
)
app.add_typer(ai_trader_app, name="ai-trader")
app.add_typer(llm_app, name="llm")
app.add_typer(ticks_app, name="ticks")
app.add_typer(slippage_app, name="slippage")
app.add_typer(intraday_app, name="intraday")
ea_app = typer.Typer(no_args_is_help=True, help="EAs externos MT5: registro, estado y filtros.")
app.add_typer(ea_app, name="ea")
app.add_typer(lessons_app, name="lessons")
app.add_typer(reports_app, name="reports")
app.add_typer(markets_app, name="markets")
app.add_typer(models_app, name="models")
app.add_typer(intel_app, name="intel")
app.add_typer(telegram_app, name="telegram")
app.add_typer(library_app, name="library")
from .propfund.cli import app as propfund_app  # noqa: E402  (capa Prop Fund aislada)

discovery_app = typer.Typer(
    no_args_is_help=True,
    help="Discovery Lab: datos CFD/M1, calidad y campañas (sin campañas automáticas).",
)
portfolio_app = typer.Typer(
    no_args_is_help=True,
    help="Portfolio Lab: correlación, solape y reto de fondeo sin optimizar pesos.",
)

app.add_typer(propfund_app, name="propfund")
app.add_typer(discovery_app, name="discovery")
app.add_typer(portfolio_app, name="portfolio")


def _harden_stdio() -> None:
    """Evita que un solo glifo (→, ·) tumbe un comando entero.

    En consolas Windows con cp1252/cp850 rich escribe con la codificación del
    stream y lanza UnicodeEncodeError al llegar a un carácter que no existe en
    ella (p. ej. la flecha de "lite → deep"). Se degrada el carácter en vez de
    abortar la salida.
    """
    legacy = {"cp1252", "cp850", "cp437", "cp858"}
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if enc in legacy:
                stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


_harden_stdio()
console = Console()

OK = "[green]OK[/green]"
WARN = "[yellow]WARN[/yellow]"
FAIL = "[red]FAIL[/red]"


def _today() -> str:
    return market_today().isoformat()


def _default_start() -> str:
    return (market_today() - timedelta(days=365 * 8)).isoformat()


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


def _mt5_account_for_rules(rules: PropRules):
    """Cuenta MT5 activa con topes agregados; ftmo_demo tiene prioridad."""
    from .accounts import load_accounts

    candidates = [
        account
        for account in load_accounts().values()
        if account.broker == "mt5" and account.risk_caps.enabled
    ]
    for account in candidates:
        if account.id == "ftmo_demo":
            return account
    for account in candidates:
        if abs(float(account.account_size) - float(rules.account_size)) < 1e-6:
            return account
    return candidates[0] if candidates else None


def _short_risk_source(source: str) -> str:
    """accounts.yaml symbol_risk_caps 2.00% -> accounts.yaml 2.00%."""
    parts = []
    for item in str(source or "").split("/"):
        tokens = item.strip().split()
        if not tokens:
            continue
        file_name = tokens[0]
        pct = tokens[-1] if tokens[-1].endswith("%") else ""
        parts.append(f"{file_name} {pct}".strip())
    return " + ".join(parts)


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

    # Reloj: desviación local frente a NTP y al servidor MT5
    try:
        from .clock import check_clock

        clock_state = check_clock()
        detail = str(clock_state["reason"])
        if clock_state.get("skew_s") is not None:
            detail = f"{detail} · desviación {float(clock_state['skew_s']):.1f} s"
        clock_ok = clock_state["status"] == "ok"
        clock_warn = clock_state["status"] == "aviso"
        table.add_row("Reloj", OK if clock_ok else WARN if clock_warn else FAIL, detail)
    except Exception as exc:
        table.add_row("Reloj", WARN, str(exc)[:160])

    # Frescura del universo activo: bots, forward, carril IA y EA.
    try:
        from .freshness import doctor_status as freshness_status

        fresh = freshness_status()
        table.add_row(
            "Frescura",
            FAIL
            if fresh["status"] == "falla"
            else WARN
            if fresh["status"] == "aviso"
            else OK,
            str(fresh["detail"])[:180],
        )
    except Exception as exc:
        table.add_row("Frescura", WARN, str(exc)[:160])

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
    try:
        from .telegram import doctor_status

        telegram = doctor_status()
        table.add_row(
            "Telegram remoto",
            OK if telegram["configured"] else WARN,
            telegram["detail"],
        )
    except Exception as exc:
        table.add_row("Telegram remoto", WARN, str(exc)[:160])
    if settings:
        px = settings.projectx
        if not px.enabled:
            table.add_row(
                "ProjectX",
                "n/a",
                "desactivada en config/ops.yaml",
            )
        else:
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
                    f"{ctx:,} tokens: los agentes necesitan 16k o más. Recarga "
                    "el modelo con --context-length 32768.",
                )
            # LM Studio lista "proveedor/modelo" pero acepta el nombre corto;
            # el doctor compara por el último segmento para no dar un falso WARN.
            configured = str(settings.llm.model)
            short = configured.split("/")[-1]
            matches = any(
                item == configured or item.split("/")[-1] == short for item in models
            )
            if models and not matches:
                table.add_row(
                    "Modelo configurado",
                    WARN,
                    f"'{settings.llm.model}' no aparece; usa uno de: {', '.join(models)}",
                )
        except Exception as exc:
            table.add_row("LM Studio", WARN, f"servidor no disponible: {str(exc)[:120]}")

    # Proveedor del deep (OpenCode Go u otro): avisa si la clave o el saldo
    # están caídos. Solo se consulta el listado de modelos; no gasta tokens.
    deep_base = os.getenv("LAB_DEEP_LLM_BASE_URL", "").strip()
    deep_key = os.getenv("LAB_DEEP_LLM_API_KEY", "").strip()
    if not deep_base or not deep_key:
        table.add_row(
            "Deep LLM", WARN, "sin configurar: el deep se corre bajo demanda"
        )
    else:
        import urllib.error
        import urllib.request

        request_headers = {"Authorization": f"Bearer {deep_key}"}
        if "opencode.ai" in deep_base:
            request_headers["x-opencode-session"] = "lab-doctor"
            request_headers["User-Agent"] = "trading-lab/1.0"
        request = urllib.request.Request(
            deep_base.rstrip("/") + "/models", headers=request_headers
        )
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                code = int(response.status)
            table.add_row("Deep LLM", OK, f"{deep_base} · HTTP {code}")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                detail = "clave inválida (401): regenera LAB_DEEP_LLM_API_KEY"
            elif exc.code == 402:
                detail = "saldo agotado (402): recarga y luego regenera la clave"
            else:
                detail = f"HTTP {exc.code} en {deep_base}"
            table.add_row("Deep LLM", WARN, detail)
        except Exception as exc:
            table.add_row("Deep LLM", WARN, f"no responde: {str(exc)[:120]}")

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

    # Riesgo abierto por símbolo, grupo y total frente a accounts.yaml.
    if settings:
        try:
            from .accounts import load_accounts
            from .execution import get_mt5_broker
            from .symbol_risk import open_risk_report

            account = load_accounts().get("ftmo_demo")
            if account is not None and (
                account.risk_caps.enabled or account.symbol_risk_caps
            ):
                broker = get_mt5_broker(settings, DEFAULT_DB, dry_run=True)
                broker.connect()
                try:
                    balance = account.account_size
                    try:
                        state = PropGuard.state_from_equity(
                            _prop_rules(),
                            broker.equity_series(),
                            initial_balance=account.account_size,
                            open_positions=len(broker.positions() or []),
                        )
                        balance = float(
                            state.day_start_balance or state.day_start_equity or balance
                        )
                    except Exception:
                        pass
                    prop_pct = _prop_rules().max_open_risk_pct
                    ai_pct = None
                    try:
                        from .ai_trader import load_config as load_ai_config

                        ai_caps = [
                            float(item["max_open_risk"])
                            for item in (
                                (load_ai_config().get("styles") or {}).values()
                            )
                            if item.get("max_open_risk") is not None
                        ]
                        ai_pct = min(ai_caps) if ai_caps else None
                    except Exception:
                        ai_pct = None
                    risk = open_risk_report(
                        DEFAULT_DB,
                        account,
                        broker=broker,
                        balance=balance,
                        prop_pct=prop_pct,
                        ai_pct=ai_pct,
                    )
                finally:
                    try:
                        broker.shutdown()
                    except Exception:
                        pass
                parts = []
                over = False
                for symbol, item in risk["symbols"].items():
                    cap = item.get("cap_usd")
                    if cap is None:
                        parts.append(f"{symbol} {item['open_risk_usd']:,.0f}/sin tope")
                        continue
                    source = _short_risk_source(item.get("source") or "")
                    parts.append(
                        f"{symbol} {item['open_risk_usd']:,.0f}/{cap:,.0f}"
                        + (f" ({source})" if source else "")
                    )
                    if item["open_risk_usd"] > cap + 1e-9:
                        over = True
                for group, item in risk["groups"].items():
                    cap = item.get("cap_usd")
                    if cap is None:
                        continue
                    source = _short_risk_source(item.get("source") or "")
                    parts.append(
                        f"{group} {item['open_risk_usd']:,.0f}/{cap:,.0f}"
                        + (f" ({source})" if source else "")
                    )
                    if item["open_risk_usd"] > cap + 1e-9:
                        over = True
                total = risk["total"]
                if total.get("cap_usd") is not None:
                    source = _short_risk_source(total.get("source") or "")
                    parts.append(
                        f"total {total['open_risk_usd']:,.0f}/{total['cap_usd']:,.0f}"
                        + (f" ({source})" if source else "")
                    )
                    if total["open_risk_usd"] > total["cap_usd"] + 1e-9:
                        over = True
                if risk["ea_over"]:
                    parts.append("EA sobre límite")
                if risk["unknown_magic"]:
                    parts.append(f"desconocido: {len(risk['unknown_magic'])}")
                if risk["missing_sl"]:
                    symbols = ",".join(
                        str(item.get("symbol")) for item in risk["missing_sl"]
                    )
                    parts.insert(0, f"sin SL: {symbols}")
                status = (
                    FAIL
                    if risk["missing_sl"]
                    else WARN
                    if over or risk["ea_over"] or risk["unknown_magic"]
                    else OK
                )
                table.add_row(
                    "Riesgo abierto",
                    status,
                    "; ".join(parts)[:180] if parts else "sin riesgo abierto",
                )
        except Exception as exc:
            table.add_row("Riesgo abierto", WARN, str(exc)[:160])

    # Reglas de fondeo
    if settings:
        try:
            rules = _prop_rules()
            table.add_row("Fondeo", OK, rules.describe())
            if rules.verify_against_contract:
                table.add_row(
                    "Reglas fondeo",
                    WARN,
                    f"plantilla {rules.firm} en config/prop.yaml: límites "
                    "contrastados con el directorio público (verified_source), "
                    "no con tu contrato; aviso aceptable hasta verificarlo: el "
                    "guard usa el lado conservador (equity + colchón)",
                )
        except Exception as exc:
            table.add_row("Fondeo", FAIL, str(exc)[:160])

    # IA discrecional: coherencia de stops por estilo frente al global.
    try:
        from .accounts import load_accounts
        from .ai_trader import daily_stop_check
        from .ai_trader import load_config as load_ai_config

        ai_cfg = load_ai_config()
        account = load_accounts().get(ai_cfg["account"])
        stops = daily_stop_check(
            ai_cfg,
            account.account_daily_stop if account is not None else None,
        )
        table.add_row(
            "IA discrecional",
            WARN if stops["warn"] else OK,
            stops["detail"],
        )
    except Exception as exc:
        table.add_row("IA discrecional", WARN, str(exc)[:160])

    # Latidos externos: sin URL se omite, pero el doctor avisa.
    try:
        from .heartbeat import status as heartbeat_status

        hb = heartbeat_status()
        table.add_row(
            "Latidos",
            WARN if hb["missing"] else OK,
            (
                f"{len(hb['configured'])}/{len(hb['checks'])} checks configurados; "
                f"faltan: {', '.join(hb['missing'])}"
                if hb["missing"] else "todos los checks configurados"
            )[:220],
        )
    except Exception as exc:
        table.add_row("Latidos", WARN, str(exc)[:160])

    # Vector: observabilidad opcional; avisa si está instalado y no corre o
    # si all-*.jsonl se quedó viejo con el mercado abierto.
    try:
        from .vector_health import doctor_status as vector_status

        vector = vector_status()
        table.add_row(
            "Vector",
            WARN if vector["warn"] else OK,
            vector["detail"][:180],
        )
    except Exception as exc:
        table.add_row("Vector", WARN, str(exc)[:160])

    # EAs externos: archivos y setfile, sin ejecutar nada.
    try:
        from .ea_registry import load_eas

        eas = load_eas()
        if not eas:
            table.add_row("EA externos", OK, "sin EAs registrados")
        else:
            pending = [
                ea.id
                for ea in eas
                if not ea.files()["setfile"] or not ea.files()["ex5"]
            ]
            table.add_row(
                "EA externos",
                WARN if pending else OK,
                (
                    f"{len(eas)} registrados; faltan archivos: {', '.join(pending)}"
                    if pending
                    else f"{len(eas)} registrados · {', '.join(ea.id for ea in eas)}"
                )[:180],
            )
    except Exception as exc:
        table.add_row("EA externos", WARN, str(exc)[:160])

    # IA sesiones: una sesión cerrada sin ninguna fila en ai_decisions.
    try:
        from .ai_trader import session_activity

        activity = session_activity()
        decision_warnings = activity.get("decision_warnings") or []
        task_warnings = activity.get("task_warnings") or []
        table.add_row(
            "IA sesiones",
            WARN if decision_warnings else OK,
            (
                "; ".join(decision_warnings)[:160]
                if decision_warnings else activity["detail"][:160]
            ),
        )
        table.add_row(
            "IA tareas",
            WARN if task_warnings else OK,
            (
                "; ".join(task_warnings)[:160]
                if task_warnings else "tareas al día"
            ),
        )
    except Exception as exc:
        table.add_row("IA sesiones", WARN, str(exc)[:160])
        table.add_row("IA tareas", WARN, str(exc)[:160])

    # Tareas programadas: avisa si alguna TradingLab perdió ejecuciones.
    try:
        from .task_health import doctor_status as task_health_status

        task_state = task_health_status()
        table.add_row(
            "Tareas perdidas",
            OK if task_state["status"] == "ok" else WARN,
            str(task_state["detail"])[:180],
        )
    except Exception as exc:
        table.add_row("Tareas perdidas", WARN, str(exc)[:160])

    # Horario NY: compara las tareas con config/schedule.yaml para hoy.
    try:
        from .schedule_tz import doctor_status as schedule_status

        schedule = schedule_status()
        table.add_row(
            "Horario desfasado",
            FAIL if schedule["status"] == "falla" else WARN if schedule["status"] == "aviso" else OK,
            str(schedule["detail"])[:180],
        )
    except Exception as exc:
        table.add_row("Horario desfasado", WARN, str(exc)[:160])

    # Tareas de energía: ningún suspend/reboot/shutdown en la semana de trading.
    try:
        from .schedule_tz import energy_status

        energy = energy_status()
        table.add_row(
            "Tareas de energía",
            FAIL if energy["status"] == "falla" else WARN if energy["status"] == "aviso" else OK,
            str(energy["detail"])[:180],
        )
    except Exception as exc:
        table.add_row("Tareas de energía", WARN, str(exc)[:160])

    # Datos
    if network:
        try:
            df = data_mod.fetch("SPY", (market_today() - timedelta(days=30)).isoformat(), _today(), ROOT / "data" / "cache")
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
    family: str = typer.Option(
        None,
        "--family",
        help="Familia intradía (M15) del motor intradía, p. ej. london_pullback",
    ),
    timeframe: str = typer.Option("M15", "--timeframe", help="Timeframe con --family"),
    params: str = typer.Option(
        None, "--params", help='Parámetros JSON, p. ej. {"fast":50,"slow":200}'
    ),
    exposure: float = typer.Option(
        1.0, "--exposure", help="Exposición objetivo del bot (0-1)"
    ),
    start: str = typer.Option(None, "--start", help="YYYY-MM-DD"),
    end: str = typer.Option(None, "--end", help="YYYY-MM-DD"),
    cash: float = typer.Option(100_000.0, "--cash", help="Capital inicial"),
    session: str = typer.Option(
        None, "--session", help="HH:MM-HH:MM para cerrar fuera de sesión"
    ),
    session_tz: str = typer.Option(
        "UTC", "--session-tz", help="Zona de la sesión (p. ej. America/New_York)"
    ),
    flat_dates: str = typer.Option(
        "", "--flat-dates", help="Fechas planas separadas por comas (rollover)"
    ),
    export_signals: str = typer.Option(
        None, "--export-signals", help="Escribe parquet con la traza de ejecución"
    ),
) -> None:
    """Ejecuta un backtest con costes; sesión/rollover opcionales."""
    settings = get_settings()
    if strategy not in STRATEGIES:
        console.print(f"[red]Estrategia desconocida:[/red] {strategy}. Opciones: {', '.join(STRATEGIES)}")
        raise typer.Exit(2)
    session_bounds = None
    if session:
        parts = session.split("-", 1)
        if len(parts) != 2 or not all(parts):
            console.print("[red]--session debe ser HH:MM-HH:MM.[/red]")
            raise typer.Exit(2)
        session_bounds = (parts[0].strip(), parts[1].strip())
    flat = [item.strip() for item in flat_dates.split(",") if item.strip()]

    kwargs: dict = {}
    if params:
        try:
            loaded = json.loads(params)
        except ValueError as exc:
            console.print(f"[red]--params no es JSON válido:[/red] {exc}")
            raise typer.Exit(2) from exc
        if not isinstance(loaded, dict):
            console.print("[red]--params debe ser un objeto JSON.[/red]")
            raise typer.Exit(2)
        kwargs = loaded

    intraday = bool(family)
    if intraday:
        from .intraday import STRATEGIES as INTRADAY_STRATEGIES
        from .intraday import load_bars

        if family not in INTRADAY_STRATEGIES:
            console.print(
                f"[red]Familia intradía desconocida:[/red] {family}. "
                f"Opciones: {', '.join(sorted(INTRADAY_STRATEGIES))}"
            )
            raise typer.Exit(2)
        try:
            df = load_bars(settings.data.cache_dir, ticker.upper(), timeframe)
        except FileNotFoundError as exc:
            console.print(f"[red]Falta la caché MT5:[/red] {exc}")
            raise typer.Exit(2) from exc
        result = INTRADAY_STRATEGIES[family](df, **kwargs)
        label = f"{family} {timeframe}"
    else:
        df = data_mod.fetch(ticker.upper(), start or _default_start(), end or _today(), settings.data.cache_dir)
        result = STRATEGIES[strategy](df, **kwargs)
        label = f"{strategy} {result.params}"

    target = (result.target.astype(float) * float(exposure)).clip(-1.0, 1.0)
    bt = run_backtest(
        df,
        target,
        starting_cash=cash,
        commission_bps=settings.execution.commission_bps,
        slippage_bps=settings.execution.slippage_bps,
        session=session_bounds,
        session_tz=session_tz,
        flat_dates=flat,
    )
    m = bt.metrics

    if export_signals:
        from .export_signals import export_signals as write_signals

        export = write_signals(
            df,
            target,
            bt,
            export_signals,
            symbol=ticker.upper(),
            strategy=label,
            commission_bps=settings.execution.commission_bps,
            slippage_bps=settings.execution.slippage_bps,
            spread_bps=0.0,
            exposure=exposure,
            session=session_bounds,
            session_tz=session_tz,
            flat_dates=flat,
            meta={
                "bot": ticker.upper(),
                "family": family,
                "params": kwargs,
                "init_cash": float(cash),
                "timeframe": timeframe if intraday else "1d",
            },
        )
        console.print(
            f"[green]Señales exportadas:[/green] {export.path} "
            f"({export.rows} barras, {export.executions} ejecuciones)"
        )

    table = Table(title=f"Backtest · {ticker.upper()} · {label}")
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
    for label_row, value in rows:
        table.add_row(label_row, value)
    console.print(table)

    if intraday:
        console.print(
            "[yellow]Intradía: las métricas anualizadas (CAGR, Sharpe, Calmar) usan "
            "252 días y no son comparables con diario.[/yellow]"
        )

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

    risk_per_share = max(
        atr_value * settings.risk.atr_stop_mult, price * 0.005
    )
    fill = broker.submit_market(
        ticker.upper(),
        delta,
        price,
        bot=f"{ticker.upper()}:{strategy}",
        reason=f"target={target:.2f}",
        run_id=run_id,
        risk_usd=abs(delta) * risk_per_share if delta > 0 else None,
        stop_price=price - risk_per_share if delta > 0 else None,
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


@app.command("briefing")
def briefing_cmd(
    tickers: str = typer.Option(
        "", "--tickers", help="Activos separados por comas (por defecto universo CFD)"
    ),
    session: str = typer.Option(
        "auto",
        "--session",
        help="auto | pre_london | pre_ny (hora de Londres y Nueva York)",
    ),
    hours: int = typer.Option(48, "--hours", help="Ventana de calendario macro"),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Genera solo datos, sin llamar a Qwen"
    ),
    send: bool = typer.Option(False, "--send", help="Enviar el informe por Telegram"),
    out: Path = typer.Option(None, "--out", help="Archivo Markdown de salida"),
) -> None:
    """Briefing pre-Londres y pre-NY del universo CFD; solo lectura."""
    from .briefing import build_report, send_report

    settings = get_settings()
    init_db(DEFAULT_DB)
    try:
        report = build_report(
            DEFAULT_DB,
            settings,
            tickers=[
                item.strip() for item in (tickers or "").split(",") if item.strip()
            ]
            or None,
            include_llm=not no_llm,
            hours=max(1, hours),
            session=session,
        )
    except Exception as exc:
        console.print(f"[red]No se pudo generar el briefing:[/red] {exc}")
        raise typer.Exit(1) from exc
    text = report["text"]
    console.print(text)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        console.print(f"[green]Briefing guardado:[/green] {out}")
    if send:
        try:
            send_report(text)
        except Exception as exc:
            console.print(f"[red]Telegram:[/red] {exc}")
            raise typer.Exit(1) from exc
        console.print("[green]Briefing enviado a Telegram.[/green]")


@app.command("agent-compare")
def agent_compare_cmd(
    ticker: str = typer.Argument(
        None, help="Símbolo a comparar; omítelo para ver solo el reporte"
    ),
    analysis_date: str = typer.Option(
        None, "--date", help="YYYY-MM-DD; fuera de hoy exige --retrospective"
    ),
    analysts: str = typer.Option(
        "market,news,fundamentals,social", "--analysts"
    ),
    retrospective: bool = typer.Option(
        False, "--retrospective", help="Pasada histórica: se excluye del reporte forward"
    ),
    report_only: bool = typer.Option(False, "--report", help="Solo muestra el reporte"),
    min_sample: int = typer.Option(30, "--min-sample", help="Mínimo para conclusiones"),
    deep_timeout: int = typer.Option(
        1800, "--deep-timeout", help="Presupuesto total del deep en segundos (reintentos incluidos)"
    ),
) -> None:
    """Compara lite vs deep sobre el mismo activo y fecha, sin enviar órdenes."""
    from .agent_compare import CompareError, run_comparison
    from .agent_compare import report as compare_report

    init_db(DEFAULT_DB)
    if ticker and not report_only:
        names = [item.strip() for item in analysts.split(",") if item.strip()]
        try:
            row = run_comparison(
                DEFAULT_DB,
                ticker,
                day=analysis_date,
                analysts=names,
                retrospective=retrospective,
                settings=get_settings(),
                deep_timeout=deep_timeout,
            )
        except CompareError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(2) from exc
        table = Table(title=f"Comparación lite/deep · {ticker.upper()}")
        table.add_column("Fuente", style="bold")
        table.add_column("Rating")
        table.add_column("Confianza", justify="right")
        table.add_column("Objetivo", justify="right")
        table.add_column("Analistas", overflow="fold")
        table.add_column("Duración", justify="right")
        table.add_column("Error", overflow="fold")
        table.add_row(
            "lite",
            str(row["lite_rating"] or "sin datos"),
            _fmt_pct(row["lite_confidence"])
            if row["lite_confidence"] is not None
            else "—",
            "—" if row["lite_target"] is None else f"{float(row['lite_target']):.2f}",
            str(row["lite_analysts"] or "—"),
            "—"
            if row["lite_duration_s"] is None
            else f"{float(row['lite_duration_s']):.1f}s",
            str(row["lite_error"] or "—"),
        )
        table.add_row(
            "deep",
            str(row["deep_rating"] or "sin datos"),
            _fmt_pct(row["deep_confidence"])
            if row["deep_confidence"] is not None
            else "—",
            "—" if row["deep_target"] is None else f"{float(row['deep_target']):.2f}",
            str(row["deep_analysts"] or "—"),
            "—"
            if row["deep_duration_s"] is None
            else f"{float(row['deep_duration_s']):.1f}s",
            str(row["deep_error"] or "—"),
        )
        console.print(table)
        if row.get("deep_error") and not row.get("deep_rating"):
            console.print(
                "[yellow]El deep no se completó:[/yellow] "
                + str(row["deep_error"])[:300]
                + f" [dim](presupuesto {deep_timeout} s; el lado lite queda registrado)[/dim]"
            )
        if row["retrospective"]:
            console.print(
                "[yellow]Pasada retrospectiva: no cuenta para el reporte forward.[/yellow]"
            )

    data = compare_report(DEFAULT_DB, min_sample=min_sample)
    if not data["n"]:
        console.print("[yellow]Sin datos: no hay comparaciones forward.[/yellow]")
        return
    target_diff = (
        "sin datos"
        if data["mean_target_diff"] is None
        else f"{float(data['mean_target_diff']):.2f}"
    )
    console.print(
        f"Acuerdo lite/deep: [bold]{data['agreement_rate']:.0%}[/bold] "
        f"({data['n']} comparaciones) · diferencia media de objetivo: "
        f"{target_diff}"
    )
    matrix = Table(title="Matriz de ratings (lite → deep)")
    matrix.add_column("Lite", style="bold")
    columns = sorted(
        {deep for row in data["matrix"].values() for deep in row}
    )
    for column in columns:
        matrix.add_column(column, justify="right")
    for lite in sorted(data["matrix"]):
        matrix.add_row(
            lite,
            *[str(data["matrix"][lite].get(column, 0)) for column in columns],
        )
    console.print(matrix)

    source = Table(title="Decisiones forward por fuente")
    for column in ("Fuente", "N", "1d", "5d", "20d", "Hit 20d", "t", "p", "Muestra"):
        source.add_column(column, overflow="fold")
    for item in data["by_source"]:
        source.add_row(
            str(item["source"]),
            str(item["n"]),
            _fmt_pct(item["mean_1d"]) if item["mean_1d"] is not None else "—",
            _fmt_pct(item["mean_5d"]) if item["mean_5d"] is not None else "—",
            _fmt_pct(item["mean_20d"]) if item["mean_20d"] is not None else "—",
            _fmt_pct(item["hit_rate_20d"])
            if item["hit_rate_20d"] is not None
            else "—",
            f"{item['t_stat']:.2f}" if item["t_stat"] is not None else "—",
            f"{item['p_value']:.3f}" if item["p_value"] is not None else "—",
            "insuficiente" if item["insufficient"] else "ok",
        )
    console.print(source)
    if data["insufficient"]:
        console.print(f"[yellow]{data['sample_warning']}.[/yellow]")


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

    risk_per_share = max(
        atr_value * settings.risk.atr_stop_mult, price * 0.005
    )
    fill = broker.submit_market(
        ticker.upper(),
        delta,
        price,
        bot=f"agent-{mode}",
        reason=f"rating={rating}",
        risk_usd=abs(delta) * risk_per_share if delta > 0 else None,
        stop_price=price - risk_per_share if delta > 0 else None,
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

    def broker_for(account):
        return get_broker_for_account(settings, account, DEFAULT_DB)

    try:
        actions = run_all(
            settings,
            broker_factory=broker_for,
            only=only,
            dry_run=dry_run,
            include_disabled=include_disabled,
        )
    except Exception as exc:
        console.print(Panel(str(exc)[-2000:], title="Orquestador detenido", style="bold red"))
        raise typer.Exit(1)

    if not actions:
        console.print("[yellow]No hay bots habilitados. Revisa config/bots.yaml[/yellow]")
        return

    t = Table(title=f"Orquestador · broker=por cuenta · dry_run={dry_run}")
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

    try:
        from .cushion import STATE_LABELS, STYLE_BY_STATE
        from .cushion import evaluate as cushion_evaluate

        try:
            equity_series = broker.equity_series()
        except Exception:
            equity_series = None
        cushion = cushion_evaluate(
            equity_series,
            settings.risk,
            current=float(snap["equity"]),
            tz=settings.timezone,
        )
    except Exception as exc:
        cushion = None
        console.print(f"[dim]Colchón de riesgo: sin datos ({exc})[/dim]")

    if cushion is not None:
        t = Table(title="Colchón de riesgo (informativo)")
        t.add_column("Límite")
        t.add_column("Estado", justify="center")
        t.add_column("Uso del límite", justify="right")
        t.add_column("Resta (% equity)", justify="right")
        t.add_column("Resta USD", justify="right")
        t.add_column("Límite (% equity)", justify="right")
        for band in (cushion.daily, cushion.drawdown):
            style = STYLE_BY_STATE.get(band.state, "dim")
            label = STATE_LABELS.get(band.state, band.state)
            state_cell = (
                f"[{style}]{label}[/{style}]"
                if style != "dim"
                else f"[dim]{label}[/dim]"
            )
            if band.state == "no_data":
                t.add_row(band.label, state_cell, "sin datos", "sin datos", "sin datos", "sin datos")
                continue
            t.add_row(
                band.label,
                state_cell,
                f"{band.used_fraction:.0%}",
                f"{band.remaining_pct:.2%}",
                f"{band.remaining_usd:,.2f}",
                f"{band.limit_pct:.2%}",
            )
        console.print(t)
        console.print(
            "[dim]Informativo: no bloquea. El kill-switch/guard de riesgo sigue "
            "siendo el único que decide.[/dim]"
        )
        if cushion.warning:
            console.print(f"[yellow]{cushion.warning}[/yellow]")

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


@llm_app.command("status")
def llm_status_cmd() -> None:
    """Llamadas LLM con esquema válido, fallido o sin validar."""
    from .llm import schema_summary

    summary = schema_summary(DEFAULT_DB)
    t = Table(title="Validación de esquema LLM")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Llamadas", str(summary["total_calls"]))
    t.add_row("Validadas", str(summary["checked"]))
    t.add_row("OK", str(summary["ok"]))
    t.add_row("Fallidas", str(summary["failed"]))
    t.add_row("Sin validar", str(summary["unchecked"]))
    console.print(t)
    if summary["by_model"]:
        m = Table(title="Por modelo")
        for col in ("Modelo", "N", "Fallidas"):
            m.add_column(col, overflow="fold")
        for row in summary["by_model"]:
            m.add_row(str(row["model"]), str(row["n"]), str(row["failed"] or 0))
        console.print(m)
    if summary["recent_failures"]:
        f = Table(title="Últimos fallos de esquema")
        for col in ("Fecha", "Modelo", "Propósito", "Error"):
            f.add_column(col, overflow="fold")
        for row in summary["recent_failures"]:
            f.add_row(
                str(row["ts"])[:19],
                str(row["model"] or "—"),
                str(row["purpose"] or "—"),
                str(row["schema_error"] or "")[:120],
            )
        console.print(f)
    elif not summary["failed"]:
        console.print("[green]Sin fallos de esquema registrados.[/green]")


@llm_app.command("compare")
def llm_compare_cmd(
    ticker: str = typer.Argument(..., help="Símbolo, p. ej. SPY"),
    models: str = typer.Option(
        ..., "--models", help="Dos modelos separados por coma: actual,candidato"
    ),
) -> None:
    """Compara dos modelos en modo lite; no cambia el default ni envía órdenes."""
    from .model_compare import ModelCompareError, report, run_comparison

    names = [item.strip() for item in models.split(",") if item.strip()]
    try:
        row = run_comparison(DEFAULT_DB, ticker, names, settings=get_settings())
    except ModelCompareError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    t = Table(title=f"Comparación lite · {ticker.upper()}")
    for col in ("Modelo", "Rating", "Confianza", "Duración", "Error"):
        t.add_column(col, overflow="fold")
    for side in ("a", "b"):
        t.add_row(
            str(row[f"model_{side}"]),
            str(row[f"rating_{side}"] or "sin datos"),
            "—"
            if row[f"confidence_{side}"] is None
            else f"{float(row[f'confidence_{side}']):.0%}",
            "—"
            if row[f"elapsed_{side}"] is None
            else f"{float(row[f'elapsed_{side}']):.1f}s",
            str(row[f"error_{side}"] or "—"),
        )
    console.print(t)
    console.print(
        f"Acuerdo: {'sí' if row['agreement'] else 'no'} · "
        f"hash {str(row['prompt_hash_a'])[:12]}… vs {str(row['prompt_hash_b'])[:12]}…"
    )
    summary = report(DEFAULT_DB)
    if summary["insufficient"]:
        console.print(f"[yellow]{summary['sample_warning']}.[/yellow]")
    else:
        console.print(
            f"Acuerdo acumulado: {summary['agreement_rate']:.0%} "
            f"({summary['n']} comparaciones)."
        )


@llm_app.command("ranking")
def llm_ranking_cmd() -> None:
    """Ranking de modelos por acierto a 20 días."""
    from .agent_compare import model_ranking

    rows = model_ranking(DEFAULT_DB)
    t = Table(title="Ranking de modelos")
    for col in (
        "Modelo",
        "N",
        "Hit 20d",
        "Retorno 20d",
        "Latencia (s)",
        "schema_ok",
        "Acuerdo lite/deep",
        "Muestra",
    ):
        t.add_column(col, overflow="fold")
    for row in rows:
        t.add_row(
            str(row["model"]),
            str(row["n"]),
            _fmt_pct(row["hit_rate_20d"]) if row["hit_rate_20d"] is not None else "-",
            _fmt_pct(row["mean_return_20d"])
            if row["mean_return_20d"] is not None
            else "-",
            f"{row['median_latency_s']:.1f}"
            if row["median_latency_s"] is not None
            else "-",
            _fmt_pct(row["schema_ok_rate"]) if row["schema_ok_rate"] is not None else "-",
            _fmt_pct(row["agreement_rate"]) if row["agreement_rate"] is not None else "-",
            "insuficiente" if row["insufficient"] else "ok",
        )
    console.print(t)
    if not rows:
        console.print(
            "[yellow]Sin datos: no hay decisiones de modelos registradas.[/yellow]"
        )


@llm_app.command("report")
def llm_report_cmd() -> None:
    """Reporte acumulado de comparaciones entre modelos lite."""
    from .model_compare import report

    summary = report(DEFAULT_DB)
    if not summary["n"]:
        console.print("[yellow]Sin datos: no hay comparaciones de modelos.[/yellow]")
        return
    console.print(
        f"Comparaciones: [bold]{summary['n']}[/bold] · acuerdo "
        f"[bold]{summary['agreement_rate']:.0%}[/bold] · diferencia media de "
        f"confianza {summary['mean_confidence_diff'] if summary['mean_confidence_diff'] is not None else 'sin datos'}"
    )
    t = Table(title="Por modelo")
    for col in ("Modelo", "N", "Errores", "Confianza media"):
        t.add_column(col, overflow="fold")
    for row in summary["by_model"]:
        t.add_row(
            str(row["model"]),
            str(row["n"]),
            str(row["errors"]),
            "—"
            if row["mean_confidence"] is None
            else f"{float(row['mean_confidence']):.0%}",
        )
    console.print(t)
    if summary["insufficient"]:
        console.print(f"[yellow]{summary['sample_warning']}.[/yellow]")


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
                    "16k o más. Recarga con: lms load qwen3.8-27b --context-length 32768"
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
    t.add_row("Manuales (fuera de drift/incubación)", str(payload.get("manual_trades", 0)))
    t.add_row("Neto", f"{summary['net_pnl']:,.2f}")
    t.add_row("Retorno", _fmt_pct(summary["total_return"]) if summary["total_return"] is not None else "sin datos")
    t.add_row("Win rate", _fmt_pct(summary["win_rate"]) if summary["win_rate"] is not None else "sin datos")
    t.add_row("Profit factor", f"{summary['profit_factor']:.2f}" if summary["profit_factor"] is not None else "sin datos")
    t.add_row("Expectancy", f"{summary['expectancy']:,.2f}" if summary["expectancy"] is not None else "sin datos")
    t.add_row(
        "R total",
        f"{summary['r_total']:+.2f} R"
        if summary["r_total"] is not None
        else "sin datos",
    )
    t.add_row(
        "R expectancy",
        f"{summary['r_expectancy']:+.2f} R"
        if summary["r_expectancy"] is not None
        else "sin datos",
    )
    t.add_row(
        "R cobertura",
        _fmt_pct(summary["r_coverage"])
        if summary["r_coverage"] is not None
        else "sin datos",
    )
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

    r_dist = summary["r_distribution"]
    r = Table(title="Distribución de R-múltiplos")
    r.add_column("Estadístico", style="bold")
    r.add_column("Valor", justify="right")
    for label, key in (
        ("N con R", "n"),
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
        value = r_dist[key]
        r.add_row(
            label,
            f"{value:+.2f} R"
            if key != "n" and value is not None
            else ("sin datos" if value is None else str(value)),
        )
    console.print(r)

    habits = payload.get("habits") or {}
    revenge = habits.get("revenge") or {}
    overtrading = habits.get("overtrading") or {}
    h = Table(title="Detectores de conducta (informativo)")
    h.add_column("Detector", style="bold")
    h.add_column("Eventos", justify="right")
    h.add_column("Detalle", overflow="fold")
    revenge_events = revenge.get("events") or []
    if revenge_events:
        revenge_detail = "; ".join(
            f"{str(event.get('entry'))[:19]} +{event['minutes']:.0f} min "
            f"riesgo {event['risk_usd']:.2f} > {event['previous_risk_usd']:.2f}"
            for event in revenge_events[:3]
        )
    else:
        revenge_detail = "sin señales"
    h.add_row(
        "Revenge trading",
        str(revenge.get("count", 0)),
        f"{revenge_detail} · ventana {float(revenge.get('window_minutes', 0)):.0f} min",
    )
    overtrading_days = overtrading.get("days") or []
    if overtrading_days:
        overtrading_detail = "; ".join(
            f"{row['day']}: {row['trades']} > {row['threshold']}"
            for row in overtrading_days[:3]
        )
    else:
        overtrading_detail = "sin señales"
    median = overtrading.get("median")
    median_text = "sin datos" if median is None else f"{float(median):.2f}"
    h.add_row(
        "Overtrading",
        str(overtrading.get("count", 0)),
        f"{overtrading_detail} · mediana {median_text} · "
        f"umbral {overtrading.get('threshold', 'sin datos')}",
    )
    console.print(h)
    console.print("[dim]Informativo: no bloquea operaciones.[/dim]")

    group_rows = payload["groups"]
    g = Table(title=f"Agrupado por {group_by}")
    for col in ("Grupo", "N", "Neto", "Retorno", "Win", "PF", "Exp.", "R total", "Sharpe", "MaxDD", "Muestra"):
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
            f"{row['r_total']:+.2f}" if row["r_total"] is not None else "sin datos",
            f"{row['sharpe']:.2f}" if row["sharpe"] is not None else "sin datos",
            _fmt_pct(row["max_drawdown"]) if row["max_drawdown"] is not None else "sin datos",
            "ok" if row["sample_ok"] else f"N<{MIN_SAMPLE}",
        )
    console.print(g)

    t2 = Table(title=f"Últimas {len(payload['trades'])} operaciones cerradas")
    for col in (
        "Salida",
        "Bot",
        "Cuenta",
        "Perfil",
        "Activo",
        "Qty",
        "Entrada",
        "Salida",
        "PnL",
        "Ret.",
        "Riesgo",
        "R",
        "Horas",
    ):
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
            f"{trade['risk_usd']:,.2f}" if trade["risk_usd"] is not None else "sin datos",
            f"{trade['r_multiple']:+.2f} R" if trade["r_multiple"] is not None else "sin datos",
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
        f"deriva={summary.get('deriva', 0)} · sin datos={summary.get('sin datos', 0)} · "
        f"manuales excluidas={payload.get('manual_excluded', 0)}[/dim]"
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


@audit_app.command("verify")
def audit_verify_cmd(
    table: str = typer.Option(None, "--table", help="orders | console_actions"),
    alert: bool = typer.Option(
        True, "--alert/--no-alert", help="Enviar alerta si la cadena está rota"
    ),
) -> None:
    """Verifica la cadena de hash y avisa si está rota."""
    from .audit import CHAINED_TABLES, verify_chain

    tables = [table] if table else list(CHAINED_TABLES)
    unknown = [name for name in tables if name not in CHAINED_TABLES]
    if unknown:
        console.print(f"[red]Tabla desconocida:[/red] {', '.join(unknown)}")
        raise typer.Exit(2)

    t = Table(title="Auditoría · cadena de hash")
    t.add_column("Tabla", style="bold")
    t.add_column("Estado", justify="right")
    t.add_column("Filas", justify="right")
    t.add_column("Encadenadas", justify="right")
    t.add_column("Antes de cadena", justify="right")
    t.add_column("Primera rotura", justify="right")

    broken: list[tuple[str, dict]] = []
    for name in tables:
        result = verify_chain(name)
        t.add_row(
            name,
            "[green]OK[/green]" if result["ok"] else "[red]ROTA[/red]",
            str(result["n"]),
            str(result["hashed"]),
            str(result["legacy"]),
            str(result["first_break_id"]) if result["first_break_id"] is not None else "-",
        )
        if not result["ok"]:
            broken.append((name, result))
    console.print(t)

    for name, result in broken:
        message = (
            f"Cadena de auditoría rota en {name} "
            f"(primera rotura id={result['first_break_id']})"
        )
        if alert:
            try:
                send_alert("audit_chain_broken", message, severity="error")
            except Exception as exc:  # pragma: no cover - depends on the channel
                console.print(f"[dim]No se pudo enviar la alerta: {exc}[/dim]")
        console.print(f"[red]{message}[/red]")
    if broken:
        raise typer.Exit(1)


@guardian_app.command("export")
def guardian_export_cmd(
    account: str = typer.Option(
        "ftmo_demo", "--account", help="Cuenta de accounts.yaml"
    ),
) -> None:
    """Escribe el JSON que lee el EA en MQL5/Files."""
    from .guardian import GuardianError, export_config

    try:
        result = export_config(account)
    except GuardianError as exc:
        console.print(
            Panel(str(exc), title="Guardián no exportado", style="bold red")
        )
        raise typer.Exit(1) from exc

    cfg = result["config"]
    if result["warning"]:
        console.print(f"[yellow]{result['warning']}[/yellow]")

    t = Table(title="Guardián · configuración exportada")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Cuenta", str(cfg["account"]))
    t.add_row("Tamaño", f"{float(cfg['account_size']):,.2f}")
    t.add_row("Pérdida diaria", f"{float(cfg['daily_loss_pct']):.2%}")
    t.add_row("Drawdown máximo", f"{float(cfg['max_drawdown_pct']):.2%}")
    t.add_row("Reset", f"{cfg['reset_time']} {cfg['reset_tz']}")
    t.add_row("Offset UTC", f"{int(cfg['reset_utc_offset_minutes'])} min")
    t.add_row("Magics", ", ".join(str(item) for item in cfg["magics"]))
    t.add_row("Bots", ", ".join(str(item) for item in cfg["bots"]))
    t.add_row("Fuente", str(cfg["limits_source"]))
    console.print(t)
    console.print(f"[green]JSON:[/green] {result['path']}")
    if result["fallback"]:
        console.print(
            "[yellow]Destino de respaldo: copia el JSON a MQL5/Files del terminal "
            "o configura mt5.data_path en config/lab.yaml.[/yellow]"
        )


@guardian_app.command("status")
def guardian_status_cmd(
    account: str = typer.Option(None, "--account", help="Filtra por cuenta"),
    as_json: bool = typer.Option(False, "--json", help="Salida en JSON"),
    required_sessions: int = typer.Option(
        5, "--required-sessions", help="Sesiones en ALERT para la puerta de CLOSE"
    ),
) -> None:
    """Último JSON exportado, su destino y las sesiones en ALERT."""
    from .guardian import GuardianError, guardian_sessions, read_exported

    try:
        state = read_exported()
        sessions = guardian_sessions(required=required_sessions)
    except GuardianError as exc:
        console.print(
            Panel(str(exc), title="Guardián no disponible", style="bold red")
        )
        raise typer.Exit(1) from exc

    if as_json:
        console.print_json(data={"export": state, "sessions": sessions})
        return

    if not state["exists"]:
        console.print(
            "[yellow]Sin datos: ejecuta `lab guardian export`.[/yellow]"
        )
        return

    cfg = state["config"] or {}
    if account and str(cfg.get("account")) != account:
        console.print(
            f"[yellow]El JSON es de {cfg.get('account')}, no de {account}.[/yellow]"
        )

    t = Table(title="Guardián · estado")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Ruta", str(state["path"]))
    t.add_row("Destino", "respaldo data/" if state["fallback"] else "MQL5/Files")
    t.add_row("Cuenta", str(cfg.get("account") or "-"))
    t.add_row("Generado", str(cfg.get("generated_at") or "-"))
    age = state.get("age_s")
    t.add_row("Antigüedad", f"{float(age) / 3600:.1f} h" if age is not None else "Sin datos")
    daily = cfg.get("daily_loss_pct")
    max_dd = cfg.get("max_drawdown_pct")
    t.add_row("Pérdida diaria", f"{float(daily):.2%}" if daily is not None else "Sin datos")
    t.add_row("Drawdown máximo", f"{float(max_dd):.2%}" if max_dd is not None else "Sin datos")
    t.add_row("Reset", f"{cfg.get('reset_time', '-')} {cfg.get('reset_tz', '-')}")
    magics = cfg.get("magics") or []
    t.add_row("Magics", ", ".join(str(item) for item in magics) or "Sin datos")
    t.add_row(
        "Sesiones ALERT",
        f"{sessions.get('sessions', 0)} de {sessions.get('required', required_sessions)}"
        + (f" · días {', '.join(sessions.get('session_days') or [])}" if sessions.get("session_days") else ""),
    )
    t.add_row(
        "Disparos (TRIGGER)",
        str(sessions.get("triggers", 0)) if sessions.get("ok") else "Sin datos",
    )
    t.add_row(
        "Puerta CLOSE",
        "[green]cumple[/green]"
        if sessions.get("gate_ok")
        else f"[yellow]pendiente[/yellow] ({sessions.get('reason', 'sin datos')})",
    )
    console.print(t)
    if state["warning"]:
        console.print(f"[yellow]{state['warning']}[/yellow]")


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


@heartbeat_app.command("setup")
def heartbeat_setup_cmd(
    check: str = typer.Argument(..., help="Nombre del check"),
    url: str = typer.Option(
        None, "--url", help="URL de Healthchecks.io; si falta, se pide oculta"
    ),
) -> None:
    """Guarda la URL del check en keyring; nunca la imprime."""
    from .heartbeat import HeartbeatError, setup

    value = url or typer.prompt("URL del check", hide_input=True)
    try:
        result = setup(check, value)
    except HeartbeatError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Check configurado[/green] {result['check']}")


@heartbeat_app.command("ping")
def heartbeat_ping_cmd(
    check: str = typer.Argument(..., help="Nombre del check"),
    status: str = typer.Option("ok", "--status", help="ok, start o fail"),
    message: str = typer.Option("", "--message", help="Motivo que se envía con el latido"),
) -> None:
    """Envía un latido; si falta la URL se omite sin fallar la tarea."""
    from .heartbeat import HeartbeatError, ping

    try:
        result = ping(check, status, message=message)
    except HeartbeatError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


@heartbeat_app.command("status")
def heartbeat_status_cmd() -> None:
    """Muestra qué checks tienen URL configurada (sin revelarlas)."""
    from .heartbeat import status

    payload = status()
    typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


@heartbeat_app.command("setup-api")
def heartbeat_setup_api_cmd(
    key: str = typer.Option(
        None, "--key", help="API key de Healthchecks; si falta, se pide oculta"
    ),
) -> None:
    """Guarda la API key de gestión en keyring; nunca la imprime."""
    from .heartbeat import HeartbeatError, setup_api

    value = key or typer.prompt("API key de Healthchecks", hide_input=True)
    try:
        setup_api(value)
    except HeartbeatError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print("[green]API key guardada en keyring[/green]")


@heartbeat_app.command("schedule")
def heartbeat_schedule_cmd() -> None:
    """Muestra la tabla objetivo de cron/zona/gracia (sin tocar la API)."""
    from .heartbeat import schedule_summary

    typer.echo(json.dumps(schedule_summary(), ensure_ascii=False, separators=(",", ":")))


@heartbeat_app.command("apply-schedule")
def heartbeat_apply_schedule_cmd(
    apply: bool = typer.Option(
        False, "--apply", help="Escribir en Healthchecks; sin esto es dry-run"
    ),
) -> None:
    """Aplica la tabla de cron por la Management API. Requiere API key."""
    from .heartbeat import CHECK_SCHEDULES, apply_schedules

    payload = apply_schedules(apply=apply)
    typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    if not payload.get("ok"):
        raise typer.Exit(2)
    if apply and (
        payload.get("matched") != len(CHECK_SCHEDULES)
        or payload.get("applied") != len(CHECK_SCHEDULES)
    ):
        raise typer.Exit(2)


@ea_app.command("list")
def ea_list_cmd() -> None:
    """Lista los EAs externos registrados y sus archivos."""
    from .ea_registry import load_eas

    eas = load_eas()
    if not eas:
        console.print("[yellow]No hay EAs en config/mt5_eas.yaml.[/yellow]")
        return
    table = Table(title="EAs externos MT5")
    for column in ("ID", "Símbolo", "Magic", "Estrategia", "Setfile", "MQ5", "EX5", "Enabled"):
        table.add_column(column)
    for ea in eas:
        files = ea.files()
        table.add_row(
            ea.id,
            ea.symbol,
            str(ea.magic),
            ea.strategy,
            "OK" if files["setfile"] else "FALTA",
            "OK" if files["mq5"] else "FALTA",
            "OK" if files["ex5"] else "FALTA",
            "sí" if ea.enabled else "no",
        )
    console.print(table)


@ea_app.command("status")
def ea_status_cmd(
    ea_id: str = typer.Argument("us100-ftmo1", help="ID del EA"),
) -> None:
    """Estado del EA, sus archivos y posiciones de su magic."""
    from .ea_registry import EAError, get_ea, status

    try:
        ea = get_ea(ea_id)
    except EAError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if ea is None:
        console.print(f"[red]EA no registrado:[/red] {ea_id}")
        raise typer.Exit(2)
    broker = None
    try:
        from .execution import get_mt5_broker

        settings = get_settings()
        broker = get_mt5_broker(settings, DEFAULT_DB, dry_run=True)
        broker.connect()
    except Exception:
        broker = None
    try:
        payload = status(ea, broker=broker)
    finally:
        if broker is not None:
            try:
                broker.shutdown()
            except Exception:
                pass
    table = Table(title=f"EA externo · {payload['id']}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", overflow="fold")
    table.add_row("Nombre", payload["name"])
    table.add_row("Símbolo", payload["symbol"])
    table.add_row("Magic", str(payload["magic"]))
    table.add_row("Estrategia", payload["strategy"])
    table.add_row("Timeframe", payload["timeframe"])
    table.add_row("Setfile", payload["setfile"])
    table.add_row("Archivos", json.dumps(payload["files"], ensure_ascii=False))
    table.add_row("Posiciones abiertas", str(payload["open_positions"]))
    table.add_row("Últimos fills", str(len(payload["last_fills"])))
    table.add_row("Notas", payload["notes"] or "—")
    console.print(table)
    if payload["last_fills"]:
        fills = Table(title="Últimos fills del EA")
        for column in ("Fecha", "Símbolo", "Lado", "Qty", "Precio", "Deal"):
            fills.add_column(column)
        for item in payload["last_fills"]:
            fills.add_row(
                str(item.get("ts") or "")[:19],
                str(item.get("symbol") or ""),
                str(item.get("side") or ""),
                f"{float(item.get('qty') or 0):g}",
                f"{float(item.get('price') or 0):.2f}",
                str(item.get("deal_id") or ""),
            )
        console.print(fills)


@ea_app.command("forward")
def ea_forward_cmd(
    ea_id: str = typer.Argument("us100-ftmo1", help="ID del EA"),
) -> None:
    """Pre-registra el forward y muestra sus métricas y criterios congelados."""
    from .ea_forward import criteria_preview, forward_report

    bot = f"ea:{ea_id}"
    payload = forward_report(DEFAULT_DB, bot=bot)
    criteria = criteria_preview(bot)
    table = Table(title=f"Forward EA · {ea_id}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Estado", str(payload.get("state") or "—"))
    table.add_row("Inicio", str(payload.get("start_date") or "pendiente del primer fill"))
    table.add_row("Fin ventana", str(payload.get("end_date") or "—"))
    table.add_row("Hash criterios", str(criteria["hash"]))
    metrics = payload.get("metrics") or {}
    for key in (
        "n_trades",
        "pf",
        "expectancy",
        "max_dd_pct",
        "slippage_mean_points",
        "entry_match_pct",
    ):
        table.add_row(key, str(metrics.get(key)))
    table.add_row("Propuesta", str(payload.get("proposal") or "en curso"))
    failures = payload.get("failures") or []
    if failures:
        table.add_row("Filtros", "; ".join(str(item) for item in failures)[:300])
    console.print(table)


@ea_app.command("horizon")
def ea_horizon_cmd(
    ea_id: str = typer.Argument("us100-ftmo1", help="ID del EA"),
    paths: int = typer.Option(5_000, "--paths", help="Paths de Monte Carlo"),
) -> None:
    """Simula 21/60/120/750 días con riesgo fijo y dinámico."""
    from .ea_horizon import run as run_horizon
    from .ea_horizon import write_report

    with console.status("Simulando horizontes…"):
        payload = run_horizon(ea_id=ea_id, paths=paths)
    files = write_report(payload)
    table = Table(title=f"Horizonte · {ea_id}")
    table.add_column("Riesgo")
    table.add_column("Horizonte")
    table.add_column("P(pasar)", justify="right")
    table.add_column("P(breach)", justify="right")
    table.add_column("Mediana días", justify="right")
    table.add_column("EV EUR", justify="right")
    for mode, label in (("fixed_0.35", "0,35 % fijo"), ("dynamic_v3", "dinámico v3")):
        for key, row in payload["modes"][mode].items():
            table.add_row(
                label,
                "sin límite" if key == "sin_limite" else f"{key} d",
                f"{row['pass_rate']:.2%}",
                f"{row['breach_rate']:.2%}",
                str(row["median_days_to_pass"] or "—"),
                f"{row['ev_eur']:+.0f}" if row["ev_eur"] is not None else "Sin datos",
            )
    console.print(table)
    console.print(f"[dim]JSON: {files['json']} · MD: {files['markdown']}[/dim]")


@ea_app.command("validate")
def ea_validate_cmd(
    ea_id: str = typer.Argument("us100-ftmo1", help="ID del EA"),
    refresh: bool = typer.Option(False, "--refresh", help="Volver a descargar las velas M5"),
    record: bool = typer.Option(False, "--record", help="Registrar el barrido en strategy_trials"),
) -> None:
    """Pasa el setfile por DSR, PBO, WF, regímenes, Monte Carlo y costes."""
    from .ea_registry import EAError, get_ea
    from .ea_us100 import load_bars, load_setfile, validate, write_report

    try:
        ea = get_ea(ea_id)
    except EAError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if ea is None:
        console.print(f"[red]EA no registrado:[/red] {ea_id}")
        raise typer.Exit(2)
    if not ea.setfile.exists():
        console.print(f"[red]Falta el setfile:[/red] {ea.setfile}")
        raise typer.Exit(2)
    console.print(f"[dim]Cargando velas M5 de {ea.symbol}…[/dim]")
    df = load_bars(refresh=refresh)
    values = load_setfile(ea.setfile)
    with console.status("Ejecutando barrido y filtros…"):
        payload = validate(df, values, ea=ea, record=record)
    files = write_report(payload)
    table = Table(title=f"Filtros · {ea.id}")
    table.add_column("Filtro", style="bold")
    table.add_column("Valor")
    table.add_column("Estado")
    for name, item in payload["filters"].items():
        status = str(item.get("status") or ("ok" if item["ok"] else "falla"))
        label = {
            "ok": "[green]OK[/green]",
            "pendiente": "[yellow]PENDIENTE[/yellow]",
            "informativo": "[cyan]INFO[/cyan]",
            "Sin datos": "[yellow]SIN DATOS[/yellow]",
        }.get(status, "[red]FALLO[/red]")
        table.add_row(name, str(item["value"]), label)
    console.print(table)
    console.print(
        f"[bold]{'PASA' if payload['passed'] else 'NO PASA'}[/bold] · "
        f"PBO={payload['pbo']} · DSR local={payload.get('dsr_local')} · "
        f"DSR global={payload.get('dsr_global')} · "
        f"gate={payload.get('dsr_gate')} · "
        f"WF={payload['walk_forward'].get('verdict')}"
    )
    console.print(f"[dim]JSON: {files['json']} · MD: {files['markdown']}[/dim]")


@ea_app.command("optimize")
def ea_optimize_cmd(
    ea_id: str = typer.Argument("us100-ftmo1", help="ID del EA"),
    refresh: bool = typer.Option(False, "--refresh", help="Volver a descargar las velas M5"),
) -> None:
    """Barrido acotado alrededor del setfile v3 y registro de los intentos."""
    from .ea_registry import EAError, get_ea
    from .ea_us100 import load_bars, load_setfile, validate, write_report

    try:
        ea = get_ea(ea_id)
    except EAError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if ea is None:
        console.print(f"[red]EA no registrado:[/red] {ea_id}")
        raise typer.Exit(2)
    df = load_bars(refresh=refresh)
    values = load_setfile(ea.setfile)
    with console.status("Optimizando la vecindad del setfile v3…"):
        payload = validate(df, values, ea=ea, record=True)
    files = write_report(payload)
    best = max(payload["rows"], key=lambda row: float(row.get("totR") or 0))
    console.print(
        f"[bold]Mejor variante:[/bold] score={best['min_score']} rr={best['rr']} "
        f"gap={best['gap_min']} consec={best['max_consec']} · "
        f"exp={best['expR']:+.3f}R · PF={best['pf']:.2f} · total={best['totR']:+.1f}R"
    )
    console.print(
        f"Veredicto: {'PASA' if payload['passed'] else 'NO PASA'} · "
        f"PBO={payload['pbo']} · DSR={payload['dsr']}"
    )
    console.print(f"[dim]JSON: {files['json']} · MD: {files['markdown']}[/dim]")


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
        age_h = round((utc_now().timestamp() - dryruns[0].stat().st_mtime) / 3600)
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


@alerts_app.command("relay")
def alerts_relay_cmd(
    path: str = typer.Option(None, "--path", help="Ruta de alerts.jsonl"),
    window: int = typer.Option(30, "--window", help="Minutos de deduplicación"),
) -> None:
    """Releva las líneas nuevas de alerts.jsonl; si no existe, no hace nada."""
    from .vector_relay import relay

    payload = relay(DEFAULT_DB, path=path, window_minutes=window)
    typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


@app.command("reconcile")
def reconcile_cmd(
    mt5: bool = typer.Option(False, "--mt5", help="Reconciliar contra la cuenta MT5 en vez del broker"),
    account: str = typer.Option(
        None,
        "--account",
        help="Cuenta del laboratorio (p. ej. ftmo_demo)",
    ),
) -> None:
    """Compara posiciones/equity del broker con SQLite y alerta diferencias."""
    settings = get_settings()
    init_db(DEFAULT_DB)
    broker = None
    source = "mt5" if mt5 else (account or settings.execution.broker)
    try:
        if mt5:
            broker = get_mt5_broker(settings, DEFAULT_DB, dry_run=True)
            broker.connect()
            result = reconcile_broker(broker, DEFAULT_DB, source=source)
        elif account:
            from .accounts import load_accounts

            definition = load_accounts().get(str(account))
            if definition is None:
                raise ValueError(f"cuenta desconocida: {account}")
            broker = get_broker_for_account(settings, definition, DEFAULT_DB)
            result = reconcile_broker(broker, DEFAULT_DB, source=source)
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


@intel_app.command("fetch")
def intel_fetch_cmd(
    source: str = typer.Option(None, "--source", help="Feed concreto de config/intel.yaml"),
    limit: int = typer.Option(30, "--limit"),
    retries: int = typer.Option(2, "--retries", help="Reintentos por fallo transitorio"),
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
    attempted = 0
    failures: list[str] = []
    for name, cfg in feeds.items():
        if not cfg.get("enabled", True):
            continue
        attempted += 1
        try:
            items = fetch_rss(
                cfg["url"], name, limit=limit, retries=max(0, retries)
            )
            inserted = store_news(DEFAULT_DB, items)
            total += inserted
            console.print(
                f"[green]{name}[/green] · {len(items)} vistos · {inserted} nuevos"
            )
        except Exception as exc:
            failures.append(name)
            console.print(f"[red]{name}[/red] · {exc}")
    console.print(f"Total nuevos: {total} · texto externo saneado y trusted=false")
    if failures:
        console.print(f"[yellow]Fuentes con fallo:[/yellow] {', '.join(failures)}")
    if attempted and len(failures) == attempted:
        raise typer.Exit(1)


@intel_app.command("status")
def intel_status_cmd(
    model: str = typer.Option(None, "--model", help="Modelo de scoring a consultar"),
) -> None:
    """Resumen de noticias almacenadas, scoring pendiente y proveedores."""
    from .intel.news_scoring import news_score_summary, scoring_config

    settings = get_settings()
    active_model = model or scoring_config(settings)["model"]
    n = news_count(DEFAULT_DB)
    summary = news_score_summary(DEFAULT_DB, model=active_model)
    console.print(
        f"Noticias almacenadas: [bold]{n}[/bold] · trusted=false · "
        f"scoring [bold]{summary['scored']}[/bold] / pendientes "
        f"[bold]{summary['pending']}[/bold] · modelo {active_model}"
    )
    rows = recent_news(DEFAULT_DB, 8)
    if rows:
        t = Table(title="Últimas noticias saneadas")
        t.add_column("Fuente")
        t.add_column("Publicada", justify="right")
        t.add_column("Titular", overflow="fold")
        for row in rows:
            t.add_row(str(row["source"]), str(row["published_at"] or "")[:19], str(row["title"]))
        console.print(t)
    if summary["rows"]:
        s = Table(title="Últimas puntuaciones")
        s.add_column("Fuente")
        s.add_column("Sentimiento", justify="right")
        s.add_column("Relevancia", justify="right")
        s.add_column("Titular", overflow="fold")
        for row in summary["rows"][:8]:
            s.add_row(
                str(row["source"]),
                f"{float(row['sentiment']):+.2f}",
                f"{float(row['relevance']):.2f}",
                str(row["title"]),
            )
        console.print(s)
    console.print(
        "[dim]Calendario macro: FRED con `lab intel fred`; FOMC manual con "
        "`lab intel event`; proveedores con `lab intel providers`.[/dim]"
    )


@intel_app.command("score")
def intel_score_cmd(
    limit: int = typer.Option(20, "--limit", help="Máximo de noticias pendientes"),
    batch_size: int = typer.Option(8, "--batch-size", help="Noticias por llamada"),
    ticker: str = typer.Option(None, "--ticker", help="Activo objetivo; vacío = mercado"),
    model: str = typer.Option(None, "--model", help="Modelo alternativo sin cambiar el default"),
) -> None:
    """Puntúa noticias pendientes con el LLM local. No ejecuta nada."""
    from .intel.news_scoring import NewsScoringError, score_pending, scoring_config

    settings = get_settings()
    try:
        result = score_pending(
            DEFAULT_DB,
            settings,
            ticker=ticker,
            limit=limit,
            batch_size=batch_size,
            model=model or scoring_config(settings)["model"],
        )
    except NewsScoringError as exc:
        console.print(f"[red]Scoring falló:[/red] {exc}")
        raise typer.Exit(1) from exc
    if result["pending"] == 0:
        console.print("[yellow]Sin datos: no hay noticias pendientes de scoring.[/yellow]")
        return
    console.print(
        f"[green]Puntuadas {result['scored']}[/green] de {result['pending']} "
        f"· lotes {result['batches']} · inválidas {result['invalid']} "
        f"· ausentes {result['missing']} · modelo {result['model']}"
    )
    if result["missing"] or result["invalid"]:
        console.print(
            "[yellow]Respuesta parcial:[/yellow] no se inventaron puntuaciones "
            "para las noticias ausentes."
        )


@intel_app.command("providers")
def intel_providers_cmd(
    check: bool = typer.Option(
        False, "--check", help="Verifica Finnhub con una lectura de SPY"
    ),
) -> None:
    """Estado de RSS, FRED, Finnhub y OpenBB; nunca imprime claves."""
    from .intel.providers import provider_status

    status = provider_status(check_finnhub=check)
    t = Table(title="Proveedores de información")
    for col in ("Proveedor", "Estado", "Detalle"):
        t.add_column(col, overflow="fold")
    rss = status["rss"]
    t.add_row(
        "RSS",
        "ok" if rss["enabled"] else "sin feeds",
        f"{rss['enabled']} activos de {rss['configured']} configurados",
    )
    fred = status["fred"]
    t.add_row(
        "FRED",
        fred["status"],
        "configurado; `lab intel fred`" if fred["configured"] else "falta FRED_API_KEY",
    )
    finnhub = status["finnhub"]
    detail = finnhub["message"] or (
        "configurado; usa --check" if finnhub["configured"] else "falta FINNHUB_API_KEY"
    )
    t.add_row("Finnhub", finnhub["status"], detail)
    openbb = status["openbb"]
    t.add_row(
        "OpenBB",
        openbb["status"],
        "paquete instalado" if openbb["installed"] else "no instalado; no se usa",
    )
    console.print(t)
    if check and finnhub["configured"] and not finnhub["verified"]:
        raise typer.Exit(1)


@intel_app.command("finnhub")
def intel_finnhub_cmd(
    limit: int = typer.Option(30, "--limit"),
    category: str = typer.Option("general", "--category"),
    retries: int = typer.Option(2, "--retries"),
) -> None:
    """Descarga noticias generales de Finnhub y las guarda saneadas."""
    from .config import load_secrets
    from .intel.finnhub import FinnhubError, fetch_news

    load_secrets()
    try:
        items = fetch_news(
            os.getenv("FINNHUB_API_KEY"),
            category=category,
            limit=limit,
            retries=max(0, retries),
        )
    except FinnhubError as exc:
        console.print(f"[red]Finnhub:[/red] {exc}")
        raise typer.Exit(1) from exc
    inserted = store_news(DEFAULT_DB, items)
    console.print(
        f"[green]Finnhub[/green] · {len(items)} vistas · {inserted} nuevas · "
        "texto externo saneado y trusted=false"
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
    """Muestra el tramo sellado y cu?ntas veces se ha le?do."""
    from .learning import count_tests, holdout_info, holdout_usage

    info = holdout_info(DEFAULT_DB)
    usage = holdout_usage(DEFAULT_DB)
    t = Table(title="Holdout sellado")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    for key in ("start_date", "end_date", "hash", "sealed_at"):
        t.add_row(key, str(info.get(key) or "Sin datos"))
    t.add_row("trials globales", str(count_tests(DEFAULT_DB)))
    t.add_row("lecturas", str(usage["reads"]))
    t.add_row("configuraciones", str(usage["configs"]))
    last = usage.get("last") or {}
    t.add_row("?ltima lectura", str(last.get("ts") or "Sin datos"))
    t.add_row(
        "?ltima cach?",
        "s?" if last.get("cached") else "no" if last else "Sin datos",
    )
    console.print(t)
    if usage.get("top"):
        top = Table(title="Configuraciones m?s le?das")
        top.add_column("Hash", style="bold")
        top.add_column("S?mbolo")
        top.add_column("Estrategia")
        top.add_column("Lecturas", justify="right")
        top.add_column("?ltima")
        for row in usage["top"]:
            top.add_row(
                str(row.get("config_hash", ""))[:12],
                str(row.get("symbol") or ""),
                str(row.get("strategy") or ""),
                str(row.get("reads", 0)),
                str(row.get("last_read_at") or ""),
            )
        console.print(top)


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


@models_app.command("train")
def models_train_cmd(
    symbol: str = typer.Argument(...),
    start: str = typer.Option("2015-01-01", "--start"),
    end: str = typer.Option(None, "--end"),
    train_days: int = typer.Option(504, "--train-days"),
    test_days: int = typer.Option(126, "--test-days"),
    step: int = typer.Option(126, "--step"),
    alpha: float = typer.Option(1.0, "--alpha"),
) -> None:
    """Entrena walk-forward y registra un challenger (no activa bots)."""
    from .models import train_walk_forward

    settings = get_settings()
    end = end or _today()
    try:
        frame = data_mod.fetch(symbol.upper(), start, end, settings.data.cache_dir)
        result = train_walk_forward(
            frame,
            symbol=symbol,
            db_path=DEFAULT_DB,
            train_days=train_days,
            test_days=test_days,
            step=step,
            alpha=alpha,
            created_by="cli",
        )
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    m = result["metrics"]
    t = Table(title=f"Modelo walk-forward · {result['symbol']}")
    for col in ("Fold", "Train", "Test", "Retorno", "Sharpe", "MaxDD", "Trades"):
        t.add_column(col, justify="left" if col in {"Train", "Test"} else "right")
    for index, fold in enumerate(result["folds"], 1):
        fm = fold["metrics"]
        t.add_row(
            str(index),
            f"{fold['train_start']} → {fold['train_end']}",
            f"{fold['test_start']} → {fold['test_end']}",
            f"{fm['total_return']:.2%}" if fm["total_return"] is not None else "sin datos",
            f"{fm['sharpe']:.2f}" if fm["sharpe"] is not None else "sin datos",
            f"{fm['max_drawdown']:.2%}" if fm["max_drawdown"] is not None else "sin datos",
            str(fm["trades"]),
        )
    console.print(t)
    console.print(
        f"[green]Challenger #{result['registry_id']}[/green] · hash {result['model']['hash']} · "
        f"fold {m['folds'] if 'folds' in m else result['folds']} · "
        f"retorno {m['total_return']:.2%} · Sharpe {m['sharpe']:.2f}"
    )


@models_app.command("list")
def models_list_cmd(symbol: str = typer.Option(None, "--symbol")) -> None:
    """Lista modelos registrados."""
    from .models import list_models

    rows = list_models(DEFAULT_DB, symbol)
    t = Table(title="Model registry")
    for col in ("ID", "Símbolo", "Versión", "Estado", "Sharpe", "Retorno", "MaxDD", "Hash"):
        t.add_column(col, justify="left" if col in {"Símbolo", "Estado", "Hash"} else "right")
    for row in rows:
        m = row.get("metrics") or {}
        t.add_row(
            str(row["id"]),
            row["symbol"],
            str(row["version"]),
            row["status"],
            f"{m['sharpe']:.2f}" if m.get("sharpe") is not None else "sin datos",
            f"{m['total_return']:.2%}" if m.get("total_return") is not None else "sin datos",
            f"{m['max_drawdown']:.2%}" if m.get("max_drawdown") is not None else "sin datos",
            row["hash"],
        )
    console.print(t)


@models_app.command("show")
def models_show_cmd(model_id: int = typer.Argument(...)) -> None:
    """Muestra un modelo."""
    from .models import get_model

    try:
        row = get_model(DEFAULT_DB, model_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    t = Table(title=f"Modelo #{model_id}")
    for key, value in row.items():
        if key in {"metrics", "coefficients", "features"}:
            value = json.dumps(value, ensure_ascii=False)
        t.add_row(str(key), str(value or ""))
    console.print(t)


@models_app.command("promote")
def models_promote_cmd(
    model_id: int = typer.Argument(...),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Promueve un challenger; no activa bots."""
    from .models import promote_model

    try:
        result = promote_model(DEFAULT_DB, model_id, confirm=confirm, by="humano")
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Modelo #{model_id} campeón[/green] · anterior "
        f"{result['previous_id'] or 'ninguno'} · bots sin cambios"
    )


@models_app.command("rollback")
def models_rollback_cmd(
    symbol: str = typer.Argument(...),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Restaura el campeón anterior; no activa bots."""
    from .models import rollback_model

    try:
        result = rollback_model(DEFAULT_DB, symbol, confirm=confirm, by="humano")
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Rollback {symbol.upper()}[/green] · restaurado #{result['restored_id']} · "
        "bots sin cambios"
    )


@models_app.command("compare")
def models_compare_cmd(symbol: str = typer.Argument(...)) -> None:
    """Compara campeón y último challenger."""
    from .models import compare_models

    result = compare_models(DEFAULT_DB, symbol)
    t = Table(title=f"Campeón/retador · {symbol.upper()}")
    t.add_column("Rol")
    t.add_column("ID")
    t.add_column("Versión")
    t.add_column("Sharpe")
    t.add_column("Retorno")
    for role in ("champion", "challenger"):
        row = result[role]
        if row is None:
            t.add_row(role, "Sin datos", "", "", "")
            continue
        m = row.get("metrics") or {}
        t.add_row(
            role,
            str(row["id"]),
            str(row["version"]),
            f"{m['sharpe']:.2f}" if m.get("sharpe") is not None else "sin datos",
            f"{m['total_return']:.2%}" if m.get("total_return") is not None else "sin datos",
        )
    console.print(t)
    console.print(f"[dim]{result['note']}[/dim]")


@models_app.command("qlib")
def models_qlib_cmd() -> None:
    """Comprueba si existe el venv separado de Qlib."""
    from .models import qlib_status

    status = qlib_status()
    console.print(
        f"Qlib disponible: {'sí' if status['available'] else 'no'} · "
        f"{status['path']}"
    )
    console.print(f"[dim]{status['note']}[/dim]")


@fund_app.command("snapshot")
def fund_snapshot_cmd(
    account: str = typer.Argument(...),
    reason: str = typer.Option("", "--reason"),
) -> None:
    """Congela una versión numerada de los límites de una cuenta."""
    from .limit_versions import snapshot_limits

    try:
        result = snapshot_limits(
            DEFAULT_DB, account, created_by="cli", reason=reason
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Versión {result['version']}[/green] · {account} · hash {result['hash']}"
    )


@fund_app.command("versions")
def fund_versions_cmd(account: str = typer.Argument(...)) -> None:
    """Lista versiones congeladas de límites."""
    from .limit_versions import list_versions

    rows = list_versions(DEFAULT_DB, account)
    t = Table(title=f"Versiones de límites · {account}")
    for col in ("Versión", "Fecha", "Hash", "Creador", "Motivo", "Diario", "MaxDD"):
        t.add_column(col)
    for row in rows:
        limits = row.get("limits") or {}
        t.add_row(
            str(row["version"]),
            str(row["ts"]),
            str(row["hash"]),
            str(row["created_by"]),
            str(row["reason"] or ""),
            f"{float(limits.get('daily_loss_pct', 0)):.4g}",
            f"{float(limits.get('max_drawdown_pct', 0)):.4g}",
        )
    console.print(t)


@fund_app.command("rollback")
def fund_rollback_cmd(
    account: str = typer.Argument(...),
    version: int = typer.Option(..., "--version"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Restaura una versión; F13 congelado solo permite apretar."""
    from .limit_versions import rollback_version

    try:
        result = rollback_version(
            DEFAULT_DB, account, version, confirm=confirm, by="cli"
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if not result["changes"]:
        console.print("[dim]Sin cambios: la versión ya coincide.[/dim]")
        return
    t = Table(title=f"Rollback · {account} · v{version}")
    for col in ("Campo", "Antes", "Después", "Efectivo desde", "Tipo"):
        t.add_column(col)
    for change in result["changes"]:
        t.add_row(
            change["field"],
            str(change["old"]),
            str(change["new"]),
            change["effective_from"],
            "aflojar" if change["loosening"] else "apretar",
        )
    console.print(t)
    if any(change["loosening"] for change in result["changes"]):
        console.print("[yellow]Aflojamiento: aplica el siguiente día hábil.[/yellow]")


@bots_app.command("capital")
def bots_capital_cmd() -> None:
    """Lista el capital máximo configurado por bot."""
    from .limit_versions import list_bot_capital

    rows = list_bot_capital(DEFAULT_DB)
    t = Table(title="Capital máximo por bot")
    for col in ("Bot", "Máx. USD", "Actualizado", "Por"):
        t.add_column(col)
    for row in rows:
        t.add_row(
            row["bot"],
            f"{float(row['max_capital_usd']):,.2f}",
            str(row["updated_at"]),
            str(row["updated_by"]),
        )
    console.print(t)


@bots_app.command("capital-set")
def bots_capital_set_cmd(
    bot: str = typer.Argument(...),
    max_capital: float = typer.Option(..., "--max-capital"),
    reason: str = typer.Option("", "--reason"),
) -> None:
    """Fija el capital máximo por bot (SQLite con historial)."""
    from .limit_versions import set_bot_capital

    try:
        result = set_bot_capital(
            DEFAULT_DB, bot, max_capital, by="cli", reason=reason
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]{bot}[/green] · antes {result['old']} · ahora "
        f"{result['max_capital_usd']:,.2f}"
    )


@lessons_app.command("weekly")
def lessons_weekly_cmd(
    min_sample: int = typer.Option(30, "--min-sample"),
    limit: int = typer.Option(3, "--limit"),
) -> None:
    """Job semanal: Qwen redacta propuestas desde decision_outcomes."""
    from .learning import weekly_lessons

    result = weekly_lessons(
        DEFAULT_DB,
        get_settings(),
        min_sample=min_sample,
        limit=limit,
    )
    from .learning import holdout_usage

    usage = holdout_usage(DEFAULT_DB)
    console.print(
        f"[dim]Holdout: {usage['reads']} lecturas / "
        f"{usage['configs']} configuraciones[/dim]"
    )
    for lesson in result["created"]:
        console.print(
            f"[green]Lección #{lesson['id']}[/green] · proposed · "
            f"{lesson['hypothesis'][:120]}"
        )
    if result.get("reason"):
        console.print(f"[yellow]{result['reason']}[/yellow]")
    for row in result.get("skipped") or []:
        console.print(f"[dim]{row['rating']}: {row['reason']}[/dim]")


@operator_app.command("pin")
def operator_pin_cmd() -> None:
    """Configura el PIN del modo operador en el keyring (nunca en .env)."""
    from .operator import pin_configured, set_pin

    if pin_configured() and not typer.confirm(
        "Ya existe un PIN. ¿Reemplazarlo?", default=False
    ):
        raise typer.Exit(1)
    pin = typer.prompt(
        "PIN (6-12 dígitos)", hide_input=True, confirmation_prompt=True
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
    from .operator import (
        OperatorSession,
        pin_configured,
        pin_needs_rotation,
        server_session,
        web_port,
    )
    from .runtime import get_bot_state

    settings = get_settings()
    pin_ok = pin_configured()
    pin_short = pin_needs_rotation()
    cfg = settings.operator
    session_state = OperatorSession(
        db_path=DEFAULT_DB,
        max_attempts=cfg.max_pin_attempts,
        lock_seconds=cfg.lock_seconds,
    ).status()
    t = Table(title="Modo operador")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    t.add_row("mode", settings.mode)
    if not pin_ok:
        pin_text = "no configurado"
    elif pin_short:
        pin_text = "corto (<6 dígitos): debe rotarse"
    else:
        pin_text = "ok (>=6 dígitos)"
    t.add_row("PIN en keyring", pin_text)
    t.add_row(
        "Intentos PIN",
        f"{session_state['attempts_left']} restantes"
        + (" · bloqueado" if session_state["locked"] else ""),
    )
    t.add_row(
        "Bloqueo PIN",
        str(session_state.get("locked_until") or "no"),
    )
    live = server_session()
    if live is None:
        armed_text = f"no visible: el panel web no responde en el puerto {web_port()}"
    elif live.get("armed"):
        armed_text = f"sí · {live.get('seconds_left')}s restantes"
    else:
        armed_text = "no (panel web en marcha, desarmado)"
    t.add_row("Armado", armed_text)
    t.add_row(
        "Ventana",
        f"{settings.operator.arm_minutes} min · "
        f"token {settings.operator.confirm_seconds}s",
    )
    console.print(t)
    if pin_short:
        console.print(
            "[yellow]PIN corto: rótalo con `lab operator pin` "
            "(mínimo 6 dígitos). No se borra automáticamente.[/yellow]"
        )
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

    from .decisions import report_by_source

    sources = report_by_source(DEFAULT_DB)
    if sources:
        s = Table(title="Decisiones forward por fuente")
        for col in ("Fuente", "N", "1d", "5d", "20d", "Hit 20d", "t", "p", "Muestra"):
            s.add_column(col, overflow="fold")
        for row in sources:
            s.add_row(
                str(row["source"]),
                str(row["n"]),
                _fmt_pct(row["mean_1d"]) if row["mean_1d"] is not None else "—",
                _fmt_pct(row["mean_5d"]) if row["mean_5d"] is not None else "—",
                _fmt_pct(row["mean_20d"]) if row["mean_20d"] is not None else "—",
                _fmt_pct(row["hit_rate_20d"])
                if row["hit_rate_20d"] is not None
                else "—",
                f"{row['t_stat']:.2f}" if row["t_stat"] is not None else "—",
                f"{row['p_value']:.3f}" if row["p_value"] is not None else "—",
                "insuficiente" if row["insufficient"] else "ok",
            )
        console.print(s)

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
    discovery_db: str = typer.Option(
        None, "--discovery-db", help="discovery.db de solo lectura (por defecto data/)"
    ),
    costs_db: str = typer.Option(
        None, "--costs-db", help="lab.db de costes de solo lectura (por defecto data/lab.db)"
    ),
    data_root: str = typer.Option(
        None, "--data-root", help="Raíz de datos de solo lectura para el Edge Map"
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
        discovery_db=discovery_db,
        costs_db=costs_db,
        data_root=data_root,
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
    t.add_row("sesion_catalogo", f"{inst.session} ({inst.session_tz})")
    t.add_row(
        "spread_catalogo",
        f"{inst.spread:g}" if inst.spread is not None else (inst.spread_note or "sin datos"),
    )
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
        risk_usd = (
            lots * inst.risk_per_lot(sl_pips * pip, quote_rate=qr)
            if sl_pips
            else None
        )
        result = broker.submit_market(
            symbol,
            signed,
            sl=sl,
            tp=tp,
            reason="cli mt5 order",
            risk_usd=risk_usd,
            stop_price=sl,
        )
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
    periods: list[dict] = []
    try:
        df = broker.rates(symbol, timeframe, bars)
        periods = list(getattr(broker, "rate_offset_periods", []))
    except Exception as exc:
        console.print(f"[red]No se pudo leer MT5:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        broker.shutdown()
    path = save_bars(df, settings.data.cache_dir, symbol, timeframe)
    meta = cache_metadata(df, timeframe)
    offsets_path = path.with_suffix(".offsets.json")
    offsets_path.write_text(
        json.dumps(periods, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    period_lines = "\n".join(
        f"  {row['start'][:16]} → {row['end'][:16]} · {row['offset']:+.2f} h"
        for row in periods
    ) or "  sin tramos detectados"
    console.print(
        Panel(
            f"{symbol} · {timeframe}\n"
            f"Barras: {meta['rows']:,}\n"
            f"Rango: {meta['start']} → {meta['end']} ({meta['years']} años)\n"
            f"Offset por periodo ({len(periods)} tramos):\n{period_lines}\n"
            f"Caché: {path}\n"
            f"Offset sidecar: {offsets_path}",
            title="MT5 fetch (solo lectura)",
        )
    )


@ticks_app.command("fetch")
def ticks_fetch_cmd(
    symbol: str = typer.Argument("EURUSD", help="EURUSD, USDJPY, XAUUSD…"),
    day: str = typer.Option(..., "--day", help="YYYY-MM-DD"),
    hours: str = typer.Option("0-23", "--hours", help="0-23 o 8-16,20"),
    point: float = typer.Option(None, "--point", help="Escala de precio si no está en el mapa"),
    out: Path = typer.Option(None, "--out", help="Directorio de parquet"),
    retries: int = typer.Option(2, "--retries"),
    interval: float = typer.Option(
        0.5, "--interval", help="Segundos entre horas para evitar HTTP 429"
    ),
) -> None:
    """Descarga ticks Dukascopy y los guarda en parquet. No envía órdenes."""
    from .data.ticks import (
        TickError,
        fetch_day,
        parse_hours,
        save_ticks,
        summarize_ticks,
    )

    try:
        target_day = date.fromisoformat(day)
    except ValueError as exc:
        console.print(f"[red]Fecha inválida:[/red] {day}")
        raise typer.Exit(2) from exc
    try:
        selected = parse_hours(hours)
        frame = fetch_day(
            symbol,
            target_day,
            hours=selected,
            point=point,
            retries=max(0, retries),
            min_interval_s=max(0.0, interval),
        )
    except TickError as exc:
        console.print(f"[red]Dukascopy:[/red] {exc}")
        raise typer.Exit(1) from exc
    if frame.empty:
        console.print(
            "[yellow]Sin datos: mercado cerrado o archivo vacío en las horas pedidas.[/yellow]"
        )
        return
    try:
        path = save_ticks(frame, symbol, target_day, out_dir=out)
    except TickError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    summary = summarize_ticks(frame)
    table = Table(title=f"Ticks Dukascopy · {symbol.upper()} · {target_day}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", justify="right")
    table.add_row("Ticks", f"{summary['ticks']:,}")
    table.add_row("Inicio UTC", str(summary["start"]))
    table.add_row("Fin UTC", str(summary["end"]))
    table.add_row("Spread mediano", f"{summary['median_spread']:.5f}")
    table.add_row("Spread p95", f"{summary['p95_spread']:.5f}")
    table.add_row("Spread mediano (bps)", f"{summary['median_spread_bps']:.2f}")
    table.add_row("Parquet", str(path))
    console.print(table)
    console.print("[dim]Solo datos; no se ha enviado ninguna orden.[/dim]")


@ticks_app.command("summary")
def ticks_summary_cmd(
    symbol: str = typer.Argument("EURUSD"),
    day: str = typer.Option(..., "--day", help="YYYY-MM-DD"),
    out: Path = typer.Option(None, "--out", help="Directorio de parquet"),
) -> None:
    """Resume un parquet de ticks ya descargado."""
    from .data.ticks import summarize_ticks

    try:
        target_day = date.fromisoformat(day)
    except ValueError as exc:
        console.print(f"[red]Fecha inválida:[/red] {day}")
        raise typer.Exit(2) from exc
    base = Path(out) if out else ROOT / "data" / "cache" / "ticks"
    path = base / f"{symbol.upper()}_{target_day:%Y%m%d}.parquet"
    if not path.exists():
        console.print(f"[yellow]Sin datos: no existe {path}[/yellow]")
        return
    summary = summarize_ticks(pd.read_parquet(path))
    for key, value in summary.items():
        console.print(f"{key}: {value}")
    console.print(f"[dim]{path}[/dim]")


@ticks_app.command("spread")
def ticks_spread_cmd(
    symbol: str = typer.Argument("EURUSD"),
    day: str = typer.Option(..., "--day", help="YYYY-MM-DD"),
    out: Path = typer.Option(None, "--out", help="Directorio de parquet"),
) -> None:
    """Muestra la mediana de spread por hora de un parquet de ticks."""
    from .data.ticks import TickError, hourly_spread_bps

    try:
        target_day = date.fromisoformat(day)
    except ValueError as exc:
        console.print(f"[red]Fecha inválida:[/red] {day}")
        raise typer.Exit(2) from exc
    base = Path(out) if out else ROOT / "data" / "cache" / "ticks"
    path = base / f"{symbol.upper()}_{target_day:%Y%m%d}.parquet"
    if not path.exists():
        console.print(f"[yellow]Sin datos: no existe {path}[/yellow]")
        return
    try:
        hourly = hourly_spread_bps(path)
    except TickError as exc:
        console.print(f"[red]Ticks:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"Spread por hora · {symbol.upper()} · {target_day}")
    table.add_column("Hora UTC", justify="right")
    table.add_column("Spread bps", justify="right")
    for hour, value in hourly.items():
        table.add_row(f"{int(hour):02d}", f"{float(value):.3f}")
    console.print(table)


@ticks_app.command("broker-spread")
def ticks_broker_spread_cmd(
    symbol: str = typer.Argument("EURUSD", help="EURUSD, USDJPY, XAUUSD, US100.cash…"),
    days: int = typer.Option(7, "--days", help="Días hacia atrás de ticks MT5"),
    out: Path = typer.Option(None, "--out", help="Directorio de reports/research"),
) -> None:
    """Mide el spread efectivo del bróker con ticks MT5. Solo lectura."""
    from .broker_costs import collect_broker, merge_broker_report

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        result = collect_broker(
            symbol,
            days,
            broker.copy_ticks,
            db_path=DEFAULT_DB,
        )
    except Exception as exc:
        console.print(f"[red]No se pudo medir el spread del bróker:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        broker.shutdown()
    report = merge_broker_report(result, out_dir=Path(out) if out else ROOT / "reports" / "research")
    summary = result.get("summary") or {}
    table = Table(title=f"Spread bróker · {result['symbol']} · {days} días")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", justify="right")
    table.add_row("Estado", str(summary.get("status") or "sin datos"))
    table.add_row("Ticks", f"{int(summary.get('n_ticks') or 0):,}")
    table.add_row(
        "Mediana bps",
        "sin datos" if summary.get("median_bps") is None else f"{float(summary['median_bps']):.3f}",
    )
    table.add_row(
        "P75 bps",
        "sin datos" if summary.get("p75_bps") is None else f"{float(summary['p75_bps']):.3f}",
    )
    table.add_row("Horas con datos", str(int(summary.get("hours_with_data") or 0)))
    console.print(table)
    console.print(f"[green]Informe[/green] · {Path(out) if out else ROOT / 'reports' / 'research'}")
    console.print("[dim]Solo datos; no se ha enviado ninguna orden.[/dim]")
    if report.get("symbols", {}).get(result["symbol"], {}).get("status") == "sin datos":
        console.print("[yellow]Sin datos: no hay ticks del bróker; no se rellena con Dukascopy.[/yellow]")


@slippage_app.command("probe")
def slippage_probe_cmd(
    symbol: str = typer.Argument(..., help="Símbolo, p. ej. EURUSD"),
    orders: int = typer.Option(2, "--orders", min=1, help="Round-trips a enviar"),
    volume: float = typer.Option(None, "--volume", help="Debe ser el volumen mínimo"),
    spacing: float = typer.Option(2.0, "--spacing", help="Segundos entre round-trips"),
    max_orders: int = typer.Option(3, "--max-orders", min=1, help="Tope por ejecución"),
    max_orders_day: int = typer.Option(6, "--max-orders-day", min=1, help="Tope diario"),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Enviar órdenes reales en demo; sin esta bandera solo hace dry-run",
    ),
) -> None:
    """Mide slippage real enviando round-trips de volumen mínimo en demo."""
    from .slippage_probe import confirmation_matches, preview_probe, run_probe

    settings = get_settings()
    broker = _mt5(settings, dry_run=not execute)
    try:
        preview = preview_probe(
            broker,
            symbol,
            orders=orders,
            volume=volume,
            spacing_s=spacing,
            max_orders=max_orders,
            max_orders_day=max_orders_day,
        )
        table = Table(
            title=(
                f"Slippage probe · {preview['symbol']} · "
                f"{'EXECUTE' if execute else 'DRY-RUN'}"
            )
        )
        table.add_column("Campo", style="bold")
        table.add_column("Valor", justify="right")
        table.add_row("Modo cuenta", str(preview.get("mode")))
        table.add_row("identity_ok", str(preview.get("identity_ok")))
        table.add_row("Round-trips", str(preview["orders"]))
        table.add_row("Órdenes previstas", str(preview["would_send_orders"]))
        table.add_row("Volumen", f"{preview['volume']:g}")
        table.add_row("Spacing", f"{preview['spacing_s']:g} s")
        table.add_row("Tope ejecución", str(preview["max_orders"]))
        table.add_row("Tope diario", str(preview["max_orders_day"]))
        table.add_row("Entradas hoy", str(preview["entries_today"]))
        console.print(table)
        if not execute:
            console.print(
                "[yellow]Sin --execute: dry-run; no se envía ninguna orden.[/yellow]"
            )
            return
        typed = typer.prompt(
            f"Escribe {preview['symbol']} para confirmar el envío real en demo"
        )
        if not confirmation_matches(preview["symbol"], typed):
            console.print("[red]Confirmación incorrecta; no se envía nada.[/red]")
            raise typer.Exit(2)
        result = run_probe(
            broker,
            symbol,
            orders=orders,
            volume=volume,
            spacing_s=spacing,
            max_orders=max_orders,
            max_orders_day=max_orders_day,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(Panel(str(exc), title="Sonda de slippage abortada", style="bold red"))
        raise typer.Exit(1) from exc
    finally:
        broker.shutdown()

    table = Table(title=f"Slippage probe · {result['symbol']}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", justify="right")
    table.add_row("Round-trips pedidos", str(result["requested_round_trips"]))
    table.add_row("Órdenes enviadas", str(result["sent_orders"]))
    table.add_row("Round-trips completados", str(result["filled_round_trips"]))
    table.add_row("Requotes", str(result["requotes"]))
    table.add_row("Errores", str(result["errors"]))
    table.add_row("Volumen", f"{result['volume']:g}")
    console.print(table)
    console.print(f"[dim]Registrado en {result['db_path']} · solo demo, posiciones cerradas.[/dim]")


@intraday_app.command("status")
def intraday_forward_status() -> None:
    """Muestra los dos candidatos congelados y su estado de armado."""
    from .forward_intraday import load_forward_bots

    try:
        bots = load_forward_bots()
    except Exception as exc:
        console.print(Panel(str(exc), title="Forward no disponible", style="bold red"))
        raise typer.Exit(1) from exc

    console.print("[bold]Forward intradía · configuración congelada[/bold]")
    for bot in bots:
        console.print(
            f"\n[bold]{bot.id}[/bold] · {bot.canonical_symbol} · {bot.strategy}"
        )
        console.print(f"  Parámetros: {json.dumps(bot.params, sort_keys=True)}")
        exit_text = (
            f"{bot.force_exit:%H:%M}" if bot.force_exit is not None else "sin corte (swing)"
        )
        console.print(
            f"  Entrada UTC: {bot.entry_start:%H:%M}-{bot.entry_end:%H:%M} · "
            f"Corte UTC: {exit_text} · Stop: {bot.stop_atr:g} ATR"
        )
        console.print(
            f"  Trades/día: {bot.max_trades_per_day} · Magic: {bot.magic} · "
            f"Armado: {'sí' if bot.enabled else 'no (solo dry-run)'}"
        )
        if bot.notes:
            console.print(f"  [dim]{bot.notes}[/dim]")
    console.print(
        "\n[dim]La ejecución exige enabled:true y `lab intraday forward "
        "--execute --confirm FORWARD-DEMO`.[/dim]"
    )


@intraday_app.command("forward")
def intraday_forward_cmd(
    bot: str = typer.Option(
        None, "--bot", help="ID del forward; por defecto los dos candidatos"
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Enviar órdenes demo; sin esta bandera solo hace dry-run",
    ),
    confirm: str = typer.Option(
        None,
        "--confirm",
        help="Token FORWARD-DEMO obligatorio con --execute",
    ),
    bars: int = typer.Option(
        5_000, "--bars", min=210, help="Velas M15 a cargar por símbolo"
    ),
) -> None:
    """Evalúa los dos forwards fijos y solo con --execute envía en demo."""
    from .forward_intraday import load_forward_bots, run_forward_all

    settings = get_settings()
    try:
        bots = load_forward_bots()
    except Exception as exc:
        console.print(Panel(str(exc), title="Forward no disponible", style="bold red"))
        raise typer.Exit(1) from exc

    if bot:
        wanted = {item.strip() for item in bot.split(",") if item.strip()}
        bots = [item for item in bots if item.id in wanted]
        missing = sorted(wanted - {item.id for item in bots})
        if missing:
            console.print(f"[red]Forward desconocido:[/red] {', '.join(missing)}")
            raise typer.Exit(2)

    if execute:
        if confirm != "FORWARD-DEMO":
            console.print(
                Panel(
                    "La ejecución real exige repetir con "
                    "`--confirm FORWARD-DEMO`.",
                    title="Confirmación requerida",
                    style="bold red",
                )
            )
            raise typer.Exit(2)
        disabled = [item.id for item in bots if not item.enabled]
        if disabled:
            console.print(
                Panel(
                    "Estos forwards están enabled:false y no se envían:\n"
                    + "\n".join(f"- {item}" for item in disabled),
                    title="Forward no armado",
                    style="bold red",
                )
            )
            raise typer.Exit(2)

    broker = _mt5(settings, dry_run=not execute)
    try:
        decisions = run_forward_all(
            bots,
            broker,
            settings,
            dry_run=not execute,
            bars=bars,
        )
        try:
            from .mt5_fills import lab_magic_map, sync_mt5_fills

            fills_report = sync_mt5_fills(
                broker,
                DEFAULT_DB,
                magics=lab_magic_map(),
                account=bots[0].account if bots else "ftmo_demo",
            )
            if fills_report["inserted"]:
                console.print(
                    f"[dim]Fills MT5: {fills_report['inserted']} nuevos "
                    f"({fills_report['manual']} manuales)[/dim]"
                )
        except Exception as exc:
            console.print(
                f"[yellow]Fills MT5: no se pudo sincronizar:[/yellow] {exc}"
            )
    except Exception as exc:
        console.print(
            Panel(str(exc)[-2000:], title="Forward detenido", style="bold red")
        )
        raise typer.Exit(1) from exc
    finally:
        broker.shutdown()

    table = Table(
        title=f"Forward intradía · {'EXECUTE demo' if execute else 'DRY-RUN'}"
    )
    for column in (
        "Bot",
        "Símbolo",
        "Señal",
        "Acción",
        "Precio",
        "ATR",
        "Stop",
        "Vol",
        "Ticket",
        "Defensa",
        "Motivo",
    ):
        table.add_column(column, overflow="fold")
    for item in decisions:
        table.add_row(
            item.bot,
            item.symbol,
            f"{item.signal:+.0f}",
            item.action,
            f"{item.price:.5f}" if item.price is not None else "-",
            f"{item.atr:.5f}" if item.atr is not None else "-",
            f"{item.stop:.5f}" if item.stop is not None else "-",
            f"{item.volume:g}" if item.volume is not None else "-",
            str(item.position_ticket or "-"),
            str(item.guards.get("defense") or "-"),
            item.reason,
        )
    console.print(table)
    if execute:
        console.print(
            "[green]Ejecución demo completada.[/green] Revisa posiciones y "
            "`lab mt5 positions`."
        )
    else:
        console.print(
            "[yellow]Sin --execute: dry-run; no se envía ninguna orden.[/yellow]"
        )


@slippage_app.command("report")
def slippage_report_cmd(
    symbol: str = typer.Option(None, "--symbol", help="Filtrar por símbolo"),
    order_type: str = typer.Option(None, "--order-type", help="market|limit"),
) -> None:
    """Mediana y p75 de slippage por símbolo, lado y hora UTC."""
    from .slippage_probe import report

    if order_type is not None and order_type.lower() not in {"market", "limit"}:
        raise typer.BadParameter("--order-type debe ser market o limit")
    payload = report(symbol=symbol, order_type=order_type)
    if payload["rows"] == 0:
        console.print(Panel("Sin datos de slippage.", style="yellow"))
        return
    console.print(
        f"[dim]{payload['rows']} órdenes registradas · "
        f"{payload['filled_rows']} con fill · {payload['requotes']} requotes[/dim]"
    )
    for title, rows, columns in (
        (
            "Por símbolo",
            payload["by_symbol"],
            ("Símbolo", "N", "Mediana bps", "P75 bps", "Requotes"),
        ),
        (
            "Por lado",
            payload["by_side"],
            ("Símbolo", "Lado", "N", "Mediana bps", "P75 bps", "Requotes"),
        ),
        (
            "Por hora UTC",
            payload["by_hour"],
            ("Símbolo", "Hora UTC", "N", "Mediana bps", "P75 bps", "Requotes"),
        ),
        (
            "Por tipo de orden",
            payload["by_order_type"],
            ("Símbolo", "Tipo", "N", "Mediana bps", "P75 bps", "Requotes"),
        ),
    ):
        table = Table(title=title)
        for column in columns:
            table.add_column(column, justify="left" if column == "Símbolo" else "right")
        for row in rows:
            values = []
            for column in columns:
                if column == "Símbolo":
                    values.append(str(row.get("symbol") or ""))
                elif column == "Lado":
                    values.append(str(row.get("side") or ""))
                elif column == "Hora UTC":
                    values.append(f"{int(row.get('hour_utc') or 0):02d}")
                elif column == "Tipo":
                    values.append(str(row.get("order_type") or ""))
                elif column == "N":
                    values.append(str(row.get("n") or 0))
                elif column == "Mediana bps":
                    values.append(
                        "sin datos"
                        if row.get("median_bps") is None
                        else f"{float(row['median_bps']):.3f}"
                    )
                elif column == "P75 bps":
                    values.append(
                        "sin datos"
                        if row.get("p75_bps") is None
                        else f"{float(row['p75_bps']):.3f}"
                    )
                else:
                    values.append(str(row.get("requotes") or 0))
            table.add_row(*values)
        console.print(table)


@mt5_app.command("aliases")
def mt5_aliases_cmd() -> None:
    """Descubre los símbolos del broker para el universo intradía y los guarda."""
    from .asset_aliases import aliases, canonical_symbols, discover

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        discovered = discover(DEFAULT_DB, broker)
    except Exception as exc:
        console.print(f"[red]No se pudo descubrir el universo MT5:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        broker.shutdown()
    t = Table(title="Alias de activos (descubiertos en MT5)")
    for col in ("Canónico", "Símbolo broker", "Clase", "Perfil", "Descubierto"):
        t.add_column(col, overflow="fold")
    for row in aliases(DEFAULT_DB):
        t.add_row(
            str(row["canonical"]),
            str(row["broker_symbol"]),
            str(row["asset_class"]),
            str(row["profile"]),
            str(row["discovered_at"])[:19],
        )
    console.print(t)
    missing = [c for c in canonical_symbols() if c not in discovered]
    if missing:
        console.print(
            f"[yellow]Sin alias descubierto para: {', '.join(missing)}[/yellow]"
        )


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
        from .symbol_risk import (
            alert_risk_events,
            group_cap_usd,
            risk_group,
            risk_snapshot,
            symbol_cap_usd,
            total_cap_usd,
        )

        account = _mt5_account_for_rules(rules)
        account_id = account.id if account is not None else "ftmo_demo"
        balance = float(state.day_start_balance or state.day_start_equity or state.equity)
        risk = risk_snapshot(
            broker.positions(),
            broker,
            account_id=account_id,
            account=account,
            balance=balance,
        )
        alert_risk_events(account_id, risk, db_path=DEFAULT_DB)

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
        if risk["ea_over"]:
            first = risk["ea_over"][0]
            reason = (
                f"skip: riesgo agregado ({first['kind']}) EA {first['name']} "
                f"{first['risk_usd']:,.2f} > {first['cap_usd']:,.2f}"
            )
            console.print(f"[red]{reason}[/red]")
            _record_signal(inst.symbol, strategy, "hold", target, tick["bid"], reason)
            return
        group = risk_group(account, inst.symbol)
        report = guard.evaluate(
            state,
            proposed_lots=lots,
            risk_per_lot=risk_per_lot,
            open_risk_usd=risk["total_usd"],
            symbol_open_risk_usd=risk["by_symbol"].get(inst.symbol.upper(), 0.0),
            symbol_risk_cap_usd=symbol_cap_usd(account, inst.symbol, balance),
            symbol=inst.symbol,
            group_open_risk_usd=risk["by_group"].get(group, 0.0),
            group_risk_cap_usd=group_cap_usd(account, group, balance),
            group=group,
            total_open_risk_usd=risk["total_usd"],
            total_risk_cap_usd=total_cap_usd(account, balance),
            missing_sl=bool(risk["missing_sl"]),
        )

        console.print(
            f"Stop: {stop_distance:.5f} · riesgo/lote: {risk_per_lot:,.2f} USD · "
            f"presupuesto: {budget:,.2f} USD · lotes: [bold]{lots:g}[/bold]"
        )
        _print_guard(rules, report)

        if lots <= 0:
            console.print("[yellow]El lote mínimo no cabe en el presupuesto.[/yellow]")
            return
        if not report.allowed:
            reason = str(report.reason)
            if reason.startswith("riesgo agregado"):
                reason = f"skip: {reason}"
            console.print(f"[red]Orden bloqueada: {reason}[/red]")
            _record_signal(inst.symbol, strategy, "hold", target, tick["bid"], reason)
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
            risk_usd=float(lots) * float(risk_per_lot),
            stop_price=sl,
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


@prop_app.command("defense")
def prop_defense(
    equity: float | None = typer.Option(None, "--equity", help="Equity actual"),
    hwm: float | None = typer.Option(None, "--hwm", help="Máximo histórico de equity"),
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase"),
    account_size: float = typer.Option(None, "--account-size"),
    flat_by: str = typer.Option("15:55", "--flat-by", help="Hora local de cierre"),
    tz: str = typer.Option("America/New_York", "--tz", help="Zona del cierre"),
) -> None:
    """Zonas de drawdown trailing, factor de tamaño y hora de cierre."""
    rules = _prop_rules(firm, phase, account_size)
    eq = float(equity if equity is not None else rules.account_size)
    peak = float(hwm if hwm is not None else max(eq, rules.account_size))
    limit_pct = rules.effective_max_loss_usd / rules.account_size

    dd = TrailingDrawdown(limit_pct, start_equity=peak)
    report = dd.observe(eq)
    now = datetime.now(timezone.utc)
    clock = FlattenClock(flat_by, tz=tz)
    floor = dd.floor() or 0.0

    t = Table(title=f"Defensa de equity · {rules.firm} · {rules.phase}")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Equity", f"{eq:,.2f}")
    t.add_row("HWM", f"{report.hwm:,.2f}")
    t.add_row("Suelo", f"{floor:,.2f}")
    t.add_row("Drawdown", f"{report.drawdown_pct:.2%}")
    t.add_row("Límite", f"{limit_pct:.2%} ({rules.effective_max_loss_usd:,.2f})")
    t.add_row("Uso del límite", f"{report.utilization:.0%}")
    t.add_row("Zona", report.level)
    t.add_row("Factor de tamaño", f"{report.size_factor:g}x")
    t.add_row("Nuevas entradas", "permitidas" if report.allowed else "bloqueadas")
    t.add_row("Cierre", f"{flat_by} {tz}")
    t.add_row("Reloj", "toca aplanar" if clock.due(now) else "dentro de hora")
    console.print(t)
    for warning in report.warnings:
        console.print(f"[yellow]{warning}[/yellow]")
    console.print(f"Motivo: {report.reason}")


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


@prop_app.command("exposure-sweep")
def prop_exposure_sweep(
    bot: str = typer.Option(..., "--bot", help="Bot con artefacto en swing_cfd/artifacts"),
    artifact: Path = typer.Option(
        None, "--artifact", help="Parquet de retornos diarios (por defecto artifacts/<bot>.parquet)"
    ),
    paths: int = typer.Option(2_000, "--paths"),
    seed: int = typer.Option(42, "--seed"),
    block_size: int = typer.Option(5, "--block-size"),
    fee_eur: float = typer.Option(None, "--fee-eur", help="Cuota del challenge (EUR)"),
    split: float = typer.Option(None, "--split", help="Split del beneficio (0-1)"),
    no_refund: bool = typer.Option(
        False, "--no-refund", help="No devolver la cuota al pasar (EV antiguo)"
    ),
    bootstrap: int = typer.Option(
        200, "--bootstrap", help="Remuestreos del IC 90 % de P(pasar); 0 = sin IC"
    ),
    name: str = typer.Option(
        None, "--name", help="Nombre del informe (sin extensión)"
    ),
    compare: str = typer.Option(
        None, "--compare", help="Bots separados por comas para comparar lado a lado"
    ),
    adopted_k: float = typer.Option(
        None, "--adopted-k", help="k decidida por el operador (para la conclusión)"
    ),
    no_oracle: bool = typer.Option(False, "--no-oracle"),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Escala los retornos por k y mide P(pasar)/EV del challenge FTMO 100k.

    No recalcula el backtest: lee el artefacto del research. No activa nada.
    """
    from .exposure_sweep import SweepError, run_sweep

    try:
        payload = run_sweep(
            bot,
            out_dir=Path(out) if out else None,
            artifact=artifact,
            paths=paths,
            seed=seed,
            block=block_size,
            fee_eur=fee_eur,
            split=split,
            fee_refund_on_pass=not no_refund,
            oracle=not no_oracle,
            bootstrap=max(0, int(bootstrap)),
            name=name,
            compare_with=tuple(
                item.strip() for item in (compare or "").split(",") if item.strip()
            ),
            adopted_k=adopted_k,
        )
    except SweepError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    rate = payload.get("eurusd") or {}
    variant = payload.get("variant") or {}
    variant_text = (
        f"{variant.get('fast')}/{variant.get('slow')} ATR {variant.get('stop_atr')}"
        if variant
        else "Sin datos"
    )
    console.print(
        Panel(
            f"Bot: {bot} · variante {variant_text}\n"
            f"Run: {payload.get('run_id')} · {payload['sample_days']} días "
            f"({payload['start']} → {payload['end']}) · "
            f"{payload.get('num_trades')} operaciones\n"
            f"Reglas: {payload['rules']}\n"
            f"Cuota {payload['economics']['fee_eur']:.0f} EUR · split "
            f"{payload['economics']['profit_split']:.0%} · reembolso "
            f"{'sí' if payload['economics']['fee_refund_on_pass'] else 'no'} · "
            f"EURUSD {rate.get('rate') if rate.get('rate') is not None else 'Sin datos'} "
            f"({rate.get('as_of') or 'Sin datos'})",
            title="Barrido de exposición",
        )
    )
    table = Table(title="Challenge FTMO 100k por exposición")
    for column in (
        "k",
        "Horizonte",
        "P(pasar)",
        "IC 90 %",
        "P(breach)",
        "Sin resolver",
        "Días (mediana)",
        "MaxDD mediano",
        "Peor 5 %",
    ):
        table.add_column(column, overflow="fold")
    for row in payload["rows"]:
        ci = row.get("ci90") or {}
        ci_text = (
            f"{ci['low']:.0%}–{ci['high']:.0%}"
            if ci.get("low") is not None and ci.get("high") is not None
            else "—"
        )
        for label, key in (("120 d", "horizon_120"), ("sin límite", "sin_limite")):
            block = row[key]
            table.add_row(
                f"{row['k']:g}",
                label,
                f"{block['pass_rate']:.1%}",
                ci_text if key == "sin_limite" else "—",
                f"{block['breach_rate']:.1%}",
                f"{block['timeout_rate']:.1%}",
                f"{block['median_days_to_pass']:.0f}"
                if block["median_days_to_pass"] is not None
                else "—",
                f"{block['median_max_drawdown'] * 100:.1f}%",
                f"{block['p5_max_drawdown'] * 100:.1f}%",
            )
    console.print(table)
    ev_table = Table(title="Valor esperado por intento")
    for column in (
        "k",
        "P(pasar)",
        "Pago mes 1 (EUR)",
        "EV neto (EUR)",
        "EV sin reembolso (EUR)",
        "EV oráculo (EUR)",
    ):
        ev_table.add_column(column, overflow="fold")
    for row in payload["rows"]:
        ev_table.add_row(
            f"{row['k']:g}",
            f"{row['sin_limite']['pass_rate']:.1%}",
            f"{row['payout_eur']:,.0f}" if row["payout_eur"] is not None else "Sin datos",
            f"{row['ev_eur']:+,.0f}" if row["ev_eur"] is not None else "Sin datos",
            f"{row['ev_no_refund_eur']:+,.0f}"
            if row.get("ev_no_refund_eur") is not None
            else "Sin datos",
            f"{row['oracle_ev_eur']:+,.0f}"
            if row["oracle_ev_eur"] is not None
            else "Sin datos",
        )
    console.print(ev_table)
    oracle = payload.get("oracle")
    if oracle:
        console.print(
            f"[dim]Oráculo prop-ev {oracle.get('version')}: "
            + ", ".join(
                f"k={k}: {value:.1%}" for k, value in (oracle.get("pass") or {}).items()
            )
            + "[/dim]"
        )
    else:
        console.print("[dim]Sin oráculo.[/dim]")
    rec = payload["recommendation"]
    console.print(
        Panel(
            f"{rec['text']}"
            + (
                f" · EV {rec['ev_eur']:+,.0f} EUR por intento"
                if rec.get("ev_eur") is not None
                else ""
            ),
            title="Recomendación",
        )
    )
    console.print(f"[dim]{payload['files']['markdown']}[/dim]")


@app.command("regimes")
def regimes_cmd(
    symbol: str = typer.Argument("SPY", help="Activo con caché local, p. ej. QQQ"),
    timeframe: str = typer.Option("1d", "--timeframe"),
    bot: str = typer.Option(None, "--bot", help="Bot para rendimiento por régimen"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Clasificador causal de régimen; informativo. No activa ni desactiva bots."""
    from .regimes import bot_performance_by_regime, classify, load_cached, report

    settings = get_settings()
    df, path = load_cached(symbol, settings.data.cache_dir)
    if df is None:
        console.print(f"[yellow]Sin datos: no hay caché para {symbol}.[/yellow]")
        raise typer.Exit(1)
    payload = report(symbol, df, source=str(path) if path else None)

    def fmt_pct(value):
        return "Sin datos" if value is None else _fmt_pct(float(value))
    if bot:
        specs = {spec.id: spec for spec in load_bots()}
        spec = specs.get(bot)
        if spec is None:
            console.print(f"[red]Bot no encontrado:[/red] {bot}")
            raise typer.Exit(2)
        if symbol.upper() not in {item.upper() for item in spec.universe}:
            console.print(f"[red]{bot} no opera {symbol}.[/red]")
            raise typer.Exit(2)
        strategy = STRATEGIES.get(spec.strategy)
        if strategy is None:
            console.print(f"[red]Estrategia desconocida:[/red] {spec.strategy}")
            raise typer.Exit(2)
        signal = strategy(df, **spec.params)
        bt = run_backtest(
            df,
            signal.target,
            starting_cash=settings.starting_cash,
            commission_bps=1.0,
            slippage_bps=5.0,
        )
        labels = classify(df)["label"]
        payload["bot"] = {
            "id": spec.id,
            "regime_stats": bot_performance_by_regime(bt.returns, labels),
        }
    if as_json:
        console.print_json(data=payload)
        return

    if payload["status"] != "ok":
        console.print(f"[yellow]{payload.get('reason', 'Sin datos')}[/yellow]")
        return
    current = payload["current"]
    metrics = payload["metrics"]
    table = Table(title=f"Régimen · {payload['symbol']} · {payload['as_of']}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Régimen", str(current["label"]))
    table.add_row("Volatilidad", str(current["vol_state"]))
    table.add_row("Vol anual", fmt_pct(current["vol"]))
    table.add_row("Mediana vol", fmt_pct(current["vol_median"]))
    table.add_row("Fuerza tendencia", fmt_pct(current["trend_strength"]))
    table.add_row("Estabilidad", fmt_pct(metrics["stability_pct"]))
    table.add_row("Duración media", f"{metrics['avg_duration_days']} días")
    table.add_row("Cambios", str(metrics["changes"]))
    table.add_row("Falsos cambios", fmt_pct(metrics["false_changes_pct"]))
    table.add_row(
        "Retraso detección",
        f"{metrics['detection_delay']['mean_days']} días",
    )
    console.print(table)

    stats = metrics["regime_stats"]
    t = Table(title="Rendimiento por régimen")
    for col in ("Régimen", "N", "Retorno", "Sharpe", "Vol", "MaxDD", "Acierto"):
        t.add_column(col, justify="right" if col != "Régimen" else "left")
    for row in stats:
        t.add_row(
            row["regime"],
            str(row.get("n", 0)),
            fmt_pct(row.get("total_return")),
            f"{row['sharpe']:.2f}" if row.get("sharpe") is not None else "Sin datos",
            fmt_pct(row.get("volatility")),
            fmt_pct(row.get("max_drawdown")),
            fmt_pct(row.get("hit_rate")),
        )
    console.print(t)

    if payload.get("bot"):
        t = Table(title=f"Bot {payload['bot']['id']} por régimen")
        for col in ("Régimen", "N", "Retorno", "Sharpe", "Vol", "MaxDD", "Acierto"):
            t.add_column(col, justify="right" if col != "Régimen" else "left")
        for row in payload["bot"]["regime_stats"]:
            t.add_row(
                row["regime"],
                str(row.get("n", 0)),
                fmt_pct(row.get("total_return")),
                f"{row['sharpe']:.2f}" if row.get("sharpe") is not None else "Sin datos",
                fmt_pct(row.get("volatility")),
                fmt_pct(row.get("max_drawdown")),
                fmt_pct(row.get("hit_rate")),
            )
        console.print(t)

    selector = payload.get("proposed_selector") or {}
    console.print(
        f"[yellow]Selector propuesto:[/yellow] {selector.get('bot', 'flat')} · "
        "status=proposed · enabled:false · no se aplica."
    )


@data_app.command("vix")
def data_vix_cmd() -> None:
    """Actualiza la estructura VIX/VIX3M desde FRED (o caché)."""
    from .data.vix import fetch_vix_structure

    result = fetch_vix_structure()
    typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


@data_app.command("cot")
def data_cot_cmd(
    limit: int = typer.Option(8, "--limit", min=1),
) -> None:
    """Descarga el COT público de la CFTC y lo guarda en caché."""
    from .data.cot import fetch_cot, save_cot

    frame = fetch_cot(limit=limit)
    path = save_cot(frame)
    typer.echo(json.dumps(
        {"rows": len(frame), "path": str(path)},
        ensure_ascii=False, separators=(",", ":"),
    ))


@data_app.command("crosscheck")
def data_crosscheck_cmd(
    symbol: str = typer.Option(
        None, "--symbol", help="XAUUSD, EURUSD, GBPUSD o USDJPY"
    ),
    threshold: float = typer.Option(3.0, "--threshold", min=1.0),
) -> None:
    """Compara H1 de MT5 con ticks Dukascopy agregados; escribe informe."""
    from .data.crosscheck import crosscheck_symbol

    symbols = (
        [part.strip().upper() for part in symbol.split(",") if part.strip()]
        if symbol else ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]
    )
    allowed = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}
    if any(item not in allowed for item in symbols):
        console.print("[red]Símbolo no soportado para crosscheck[/red]")
        raise typer.Exit(2)
    table = Table(title="Crosscheck MT5 vs Dukascopy")
    for column in ("Símbolo", "Estado", "Horas", "Corr 1h", "Corr 1d", "Divergencias", "Informe"):
        table.add_column(column)
    for item in symbols:
        result = crosscheck_symbol(item, threshold=threshold)
        table.add_row(
            item,
            str(result.get("status")),
            str(result.get("n_hours", "Sin datos")),
            str(result.get("corr_1h", "Sin datos")),
            str(result.get("corr_1d", "Sin datos")),
            str(result.get("n_divergences", "Sin datos")),
            str(result.get("reason") or f"reports/data/crosscheck/{item}.md"),
        )
    console.print(table)


@app.command("datacheck")
def datacheck_cmd(
    symbol: str = typer.Argument(..., help="Símbolo, p. ej. SPY o EURUSD=X"),
    timeframe: str = typer.Option("1d", "--timeframe", help="1d, M15, H1..."),
    cache_dir: str = typer.Option(None, "--cache-dir"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    """Valida la caché parquet: huecos, duplicados, OHLC, TZ, ajuste y spread."""
    from .datacheck import check_symbol

    settings = get_settings()
    result = check_symbol(
        symbol,
        cache_dir=Path(cache_dir) if cache_dir else settings.data.cache_dir,
        timeframe=timeframe,
    )
    if as_json:
        console.print_json(data=result)
        raise typer.Exit(0 if result["status"] != "falla" else 1)

    table = Table(title=f"Datacheck · {result['symbol']} · {result['timeframe']}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", overflow="fold")
    table.add_row("Estado", result["status"])
    table.add_row("Barras", str(result["rows"]))
    table.add_row(
        "Rango",
        f"{result['start'] or 'Sin datos'} → {result['end'] or 'Sin datos'}",
    )
    table.add_row("Caché", result.get("cache_path") or "Sin datos")
    if result.get("reasons"):
        table.add_row("Motivos", "\n".join(result["reasons"]))
    console.print(table)
    for name, check in result.get("checks", {}).items():
        color = {"ok": "green", "aviso": "yellow", "falla": "red"}.get(
            check["status"], "dim"
        )
        console.print(f"[{color}]{check['status']}[/{color}] {name}: {check['reason']}")
    if result["status"] == "falla":
        raise typer.Exit(1)


@app.command("optimize")
def optimize_cmd(
    symbol: str = typer.Option("SPY", "--symbol"),
    strategy: str = typer.Option("trend", "--strategy", help="trend, trend-ls o meanrev"),
    trials: int = typer.Option(20, "--trials", help="Número de trials Optuna"),
    start: str = typer.Option("2015-01-01", "--start"),
    end: str = typer.Option(None, "--end"),
    train_days: int = typer.Option(504, "--train-days"),
    test_days: int = typer.Option(126, "--test-days"),
    step: int = typer.Option(126, "--step"),
    out: str = typer.Option(None, "--out"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Optuna + walk-forward; suma cada trial al DSR y respeta el holdout."""
    from .optimize import OptunaError, run_optuna, write_report

    settings = get_settings()
    out_dir = Path(out) if out else ROOT / "reports" / "research" / "optuna"
    try:
        report = run_optuna(
            symbol,
            strategy,
            start=start,
            end=end,
            trials=trials,
            train_days=train_days,
            test_days=test_days,
            step=step,
            cache_dir=settings.data.cache_dir,
            settings=settings,
        )
    except OptunaError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(2) from exc
    files = write_report(report, out_dir)

    def fmt_metric(value):
        return "Sin datos" if value is None else _fmt_pct(float(value))
    if as_json:
        console.print_json(data=report)
        return
    gates = report.get("gates") or {}
    t = Table(title=f"Optuna · {report['symbol']} · {report['strategy']}")
    t.add_column("Campo", style="bold")
    t.add_column("Valor")
    t.add_row("Trials", str(report["trials"]))
    t.add_row("Mejor trial", str(report["best_trial"]))
    t.add_row("Mejor Sharpe", f"{report['best_sharpe']:.2f}")
    t.add_row("Parámetros", str(report["best_params"]))
    t.add_row("DSR", fmt_metric(gates.get("dsr")))
    t.add_row("PBO", fmt_metric(gates.get("pbo")))
    t.add_row("Walk-forward", str(gates.get("walk_forward_verdict")))
    t.add_row("n_trials DSR", str(report["n_trials_dsr"]))
    t.add_row("Holdout", str((report.get("holdout") or {}).get("status")))
    t.add_row("Propuestas", str(len(report.get("proposals") or [])))
    console.print(t)
    if report.get("reason"):
        console.print(f"[yellow]{report['reason']}[/yellow]")
    else:
        console.print("[green]Propuesta Optuna generada con gates DSR/PBO/WF.[/green]")
    console.print(f"[dim]JSON: {files['latest']}[/dim]")


@app.command("research")
def research_cmd(
    conditioned: str = typer.Option(
        "off",
        "--conditioned",
        help="on|off: escribe la comparación con condicionadores",
    ),
    vol_target: str = typer.Option(
        "off",
        "--vol-target",
        help="on|off: escribe la comparación con objetivo de volatilidad",
    ),
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

    from .learning import holdout_usage

    report["holdout_usage"] = holdout_usage(DEFAULT_DB)

    try:
        from .quantstats_report import write_reports

        report["quantstats"] = write_reports(
            report,
            out_dir,
            settings.data.cache_dir,
        )
    except Exception as exc:
        report["quantstats"] = {
            "status": "Sin datos",
            "reason": type(exc).__name__,
            "reports": [],
        }

    files = write_outputs(report, out_dir)

    usage = report.get("holdout_usage") or {}
    console.print(
        f"[dim]Holdout: {usage.get('reads', 0)} lecturas / "
        f"{usage.get('configs', 0)} configuraciones[/dim]"
    )

    qs_payload = report.get("quantstats") or {}
    if qs_payload.get("status") == "ok":
        console.print(
            f"[dim]QuantStats: {len(qs_payload.get('reports') or [])} informes HTML[/dim]"
        )
    else:
        console.print(
            f"[dim]QuantStats: {qs_payload.get('reason', 'Sin datos')}[/dim]"
        )

    datachecks = report.get("datachecks") or {}
    if datachecks:
        console.print(
            "[dim]Datacheck: "
            + ", ".join(
                f"{symbol}={dc['status']}"
                for symbol, dc in sorted(datachecks.items())
            )
            + "[/dim]"
        )

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

    if str(conditioned).lower() == "on":
        from .conditioner_report import compare as conditioner_compare

        for path in conditioner_compare():
            console.print(f"[green]Informe de condicionadores:[/green] {path}")

    if str(vol_target).lower() == "on":
        from .vol_report import compare as vol_compare

        path = vol_compare()
        console.print(
            f"[green]Comparación con objetivo de volatilidad:[/green] {path}"
        )


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
    commission_bps: float | None = typer.Option(
        None, "--commission-bps", help="Override diagnóstico; por defecto, tabla por activo"
    ),
    slippage_bps: float | None = typer.Option(
        None, "--slippage-bps", help="Slippage conservador por lado"
    ),
    slippage_optimistic_bps: float | None = typer.Option(
        None, "--slippage-optimistic-bps", help="Slippage optimista por lado"
    ),
    zero_spread: bool = typer.Option(
        False, "--zero-spread", help="Diagnóstico: coste de spread 0"
    ),
    tick_spread: Path = typer.Option(
        None, "--tick-spread", help="Parquet de ticks Dukascopy para spread horario"
    ),
    force: bool = typer.Option(
        False, "--force", help="Permite exceder el presupuesto semanal del activo"
    ),
    lesson_id: int = typer.Option(
        None, "--lesson-id", help="Hipótesis tomada de una lección (Qwen o humano)"
    ),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Valida estrategias intradía sobre caché MT5 (DSR/PBO/WF/regímenes)."""
    from .intraday import families_for_symbol, load_bars, run_intraday, write
    from .trials import budget_status, discarded_warning

    settings = get_settings()
    try:
        df = load_bars(settings.data.cache_dir, symbol, timeframe)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red] Ejecuta: lab mt5 fetch {symbol} --timeframe {timeframe}")
        raise typer.Exit(1)

    window_start = str(df.index[0].date()) if len(df.index) else None
    window_end = str(df.index[-1].date()) if len(df.index) else None
    budget = budget_status(DEFAULT_DB, symbol)
    if budget["exceeded"] and not force:
        console.print(
            f"[red]Presupuesto semanal agotado para {budget['symbol']}: "
            f"{budget['used']}/{budget['limit']} intentos ({budget['week']}). "
            "Usa --force para continuar o espera a la semana siguiente.[/red]"
        )
        raise typer.Exit(1)
    for family in families_for_symbol(symbol):
        warning = discarded_warning(
            DEFAULT_DB,
            family=family,
            symbol=symbol,
            window_start=window_start,
            window_end=window_end,
        )
        if warning:
            console.print(f"[yellow]{warning}[/yellow]")
    tick_spread_bps = None
    if tick_spread is not None:
        from .data.ticks import TickError, hourly_spread_bps

        try:
            tick_spread_bps = hourly_spread_bps(tick_spread)
        except (OSError, TickError) as exc:
            console.print(f"[red]Ticks:[/red] {exc}")
            raise typer.Exit(1) from exc
        console.print(
            f"[dim]Spread de ticks: {len(tick_spread_bps)} horas desde "
            f"{tick_spread}[/dim]"
        )
    try:
        report = run_intraday(
            df,
            symbol=symbol,
            timeframe=timeframe,
            paths=paths,
            point=point,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            slippage_optimistic_bps=slippage_optimistic_bps,
            spread_override_bps=0.0 if zero_spread else None,
            tick_spread_bps=tick_spread_bps,
            db_path=DEFAULT_DB,
            lesson_id=lesson_id,
        )
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    files = write(report, Path(out) if out else ROOT / "reports" / "research")
    budget_after = budget_status(DEFAULT_DB, symbol)
    best = max(
        report["outcomes"],
        key=lambda row: row["metrics"]["sharpe"],
        default=None,
    )
    best_text = (
        f"Mejor Sharpe: {best['metrics']['sharpe']:.2f}"
        if best is not None
        else "Mejor Sharpe: sin datos"
    )
    costs = report.get("costs") or {}
    model = report.get("cost_model") or {}
    slippage = model.get("slippage") or {}
    commission_median = costs.get("commission_bps_median") or 0.0
    source = costs.get("commission_source") or "sin verificar"
    verified = "sí" if costs.get("commission_verified") else "NO"
    calibrated = model.get("calibrated_cost_bps_median")
    break_even_row = max(
        (
            row
            for row in report["outcomes"]
            if row.get("breakeven_cost_bps") is not None
        ),
        key=lambda row: row["breakeven_cost_bps"],
        default=None,
    )
    break_even = (
        break_even_row.get("breakeven_cost_bps") if break_even_row else None
    )
    break_even_label = (
        f"{break_even:.2f} bps ({break_even_row['strategy']})"
        if break_even is not None
        else "sin cruce"
    )
    cost_text = (
        f"Comisión: {commission_median:.3f} bps/lado · {source} · verificada={verified}\n"
        f"Slippage: opt {slippage.get('optimistic_bps', 0):g} / "
        f"cons {slippage.get('conservative_bps', 0):g} bps · "
        f"spread {'0' if costs.get('spread_override_bps') == 0 else 'observado'} bps\n"
        f"Mejor equilibrio: {break_even_label} · "
        f"calibrado mediano: {'—' if calibrated is None else f'{calibrated:.2f}'} bps"
    )
    pbo_text = (
        f"PBO: {report['pbo']['pbo']:.1%}"
        if report.get("pbo")
        else "PBO: sin datos"
    )
    console.print(
        Panel(
            f"{symbol} · {timeframe} · {report['bars']['rows']:,} barras "
            f"({report['bars']['years']} años)\n"
            f"Spread confiable: {'sí' if report['spread_reliable'] else 'NO'}\n"
            f"{cost_text}\n"
            f"{best_text}\n"
            f"{pbo_text}\n"
            f"Trials registradas: {report.get('trials_recorded', 0)} "
            f"· run {report.get('run_id', '—')}\n"
            f"Presupuesto {budget_after['symbol']}: "
            f"{budget_after['used']}/{budget_after['limit']} intentos "
            f"({budget_after['week']})",
            title="Intradía FX/CFD",
        )
    )
    console.print(
        f"Pasan {report['passed']}/{len(report['outcomes'])} · {files['md']}"
    )


@app.command("research-swing")
def research_swing_cmd(
    symbols: str = typer.Option(
        None, "--symbols", help="Lista separada por comas (US100.CASH,XAUUSD)"
    ),
    paths: int = typer.Option(2_000, "--paths", help="Simulaciones Monte Carlo"),
    horizon: int = typer.Option(120, "--horizon", help="Días por simulación"),
    block_size: int = typer.Option(5, "--block-size", help="Bootstrap por bloques"),
    firm: str = typer.Option(None, "--firm"),
    phase: str = typer.Option(None, "--phase"),
    account_size: float = typer.Option(None, "--account-size"),
    out: str = typer.Option(None, "--out"),
    top: int = typer.Option(10, "--top"),
) -> None:
    """Tendencia diaria en CFDs de tick grande sobre caché H4 de MT5.

    DSR, PBO, walk-forward, holdout y Monte Carlo FTMO 100k. Registra cada
    variante en `strategy_trials` y escribe `reports/research/swing_cfd/`.
    No activa nada: como mucho registra un candidato en el ciclo de vida.
    """
    from .swing import SYMBOLS, run_swing

    settings = get_settings()
    rules = _prop_rules(firm, phase, account_size)
    selected = tuple(
        item.strip().upper()
        for item in (symbols or ",".join(SYMBOLS)).split(",")
        if item.strip()
    )
    out_dir = Path(out) if out else ROOT / "reports" / "research" / "swing_cfd"
    report = run_swing(
        DEFAULT_DB,
        rules,
        settings.data.cache_dir,
        symbols=selected,
        out_dir=out_dir,
        paths=paths,
        horizon=horizon,
        block_size=block_size,
    )
    table = Table(title="Tendencia diaria · CFDs de tick grande")
    for column in (
        "Activo",
        "Rápida",
        "Lenta",
        "Stop",
        "Sharpe",
        "MaxDD",
        "Trades",
        "DSR",
        "P(pasar)",
        "P(breach)",
        "Pasa",
    ):
        table.add_column(column, overflow="fold")
    for row in report["results"][: max(1, int(top))]:
        table.add_row(
            row["symbol"],
            str(row["params"]["fast"]),
            str(row["params"]["slow"]),
            f"{row['params']['stop_atr']:g}",
            f"{row['sharpe']:.2f}",
            f"{row['max_drawdown'] * 100:.1f}%",
            str(row["num_trades"]),
            f"{(row['dsr'] or 0):.0%}",
            f"{row['pass_rate']:.1%}",
            f"{row['breach_rate']:.1%}",
            "sí" if row["passed"] else "no",
        )
    if not report["results"]:
        table.add_row("Sin datos", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-")
    console.print(table)
    data_lines = []
    for symbol, status in report["data"].items():
        h4 = status.get("h4") or {}
        d1 = status.get("d1") or {}
        data_lines.append(
            f"{symbol}: H4 {h4.get('rows', 0):,} barras"
            if h4.get("exists")
            else f"{symbol}: H4 Sin datos"
        )
        data_lines.append(
            f"  D1: {d1.get('status') or ('ok' if d1.get('exists') else 'Sin datos')}"
        )
    console.print(
        Panel(
            "\n".join(data_lines)
            + "\nPBO global: "
            + (f"{report['pbo']['pbo']:.1%}" if report.get("pbo") else "Sin datos")
            + "\nWalk-forward: "
            + (
                str((report.get("walk_forward") or {}).get("verdict") or "Sin datos")
            )
            + f"\nTrials: {report['dsr_n_trials']} · run {report['run_id']}"
            + f"\nPasan {report['passed']}/{len(report['results'])}",
            title="Research swing",
        )
    )
    for item in report.get("errors") or []:
        console.print(f"  [yellow]{item}[/yellow]")
    console.print(f"[dim]{report['files']['markdown']}[/dim]")


@app.command("research-trials")
def research_trials_cmd(
    symbol: str = typer.Option(None, "--symbol"),
    family: str = typer.Option(None, "--family"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """Registro de estrategias probadas (cementerio) y presupuesto semanal."""
    from .learning import count_tests
    from .trials import budget_config, budget_status, list_trials

    rows = list_trials(DEFAULT_DB, symbol=symbol, family=family, limit=limit)
    t = Table(title="Estrategias probadas (cementerio)")
    for col in ("Fecha", "Familia", "Activo", "Resultado", "Motivo", "Fuente"):
        t.add_column(col, overflow="fold")
    for row in rows:
        t.add_row(
            str(row["ts"])[:19],
            str(row["family"]),
            str(row["symbol"]),
            str(row["outcome"]),
            str(row["reason"] or "—"),
            str(row["source"]),
        )
    console.print(t)

    config = budget_config()
    symbols = sorted({str(row["symbol"]) for row in rows}) or sorted(config["assets"])
    budget = Table(title="Presupuesto semanal por activo")
    for col in ("Activo", "Semana", "Intentos", "Límite", "Restante", "Fuente"):
        budget.add_column(col, overflow="fold")
    for item in symbols:
        status = budget_status(DEFAULT_DB, item)
        budget.add_row(
            status["symbol"],
            status["week"],
            str(status["used"]),
            str(status["limit"]),
            str(status["remaining"]),
            status["source"],
        )
    console.print(budget)
    console.print(
        f"[dim]Pruebas DSR (contador único): {count_tests(DEFAULT_DB)}[/dim]"
    )


@risk_budget_app.command("status")
def risk_budget_status_cmd() -> None:
    """Muestra presupuestos por activo, rebanadas y clúster USD."""
    from .risk_budget import (
        load_budget,
        slice_history,
        slice_overrides,
        usd_cluster_state,
    )

    budget = load_budget()
    t = Table(title="Presupuesto de riesgo por activo")
    for col in ("Activo", "Símbolo", "Riesgo abierto", "Rebanada inicial", "Rebanada máx."):
        t.add_column(col, overflow="fold")
    for canonical, item in sorted(budget["assets"].items()):
        t.add_row(
            canonical,
            str(item.get("symbol") or ""),
            f"{float(item['open_risk_pct']):.2%}",
            f"{float(item['initial_slice_pct']):.2%}",
            f"{float(item['max_bot_slice_pct']):.2%}",
        )
    console.print(t)

    overrides = slice_overrides(DEFAULT_DB)
    if overrides:
        o = Table(title="Rebanadas modificadas")
        for col in ("Bot", "Activo", "Rebanada", "Actualizado", "Motivo"):
            o.add_column(col, overflow="fold")
        for row in overrides:
            o.add_row(
                str(row["bot"]),
                str(row["asset"]),
                f"{float(row['slice_pct']):.2%}",
                str(row["updated_at"])[:19],
                str(row["reason"] or ""),
            )
        console.print(o)
    cluster = usd_cluster_state([], budget)
    console.print(
        f"[dim]Clúster {cluster['name']}: miembros "
        f"{', '.join(budget['usd_cluster']['members'])} · tope "
        f"{cluster['cap_pct']:.2%} · riesgo neto actual sin datos de posiciones[/dim]"
    )
    history = slice_history(DEFAULT_DB, limit=5)
    if history:
        h = Table(title="Últimos cambios de rebanada")
        for col in ("ID", "Fecha", "Bot", "Acción", "Antes", "Después"):
            h.add_column(col, overflow="fold")
        for row in history:
            h.add_row(
                str(row["id"]),
                str(row["ts"])[:19],
                str(row["bot"]),
                str(row["action"]),
                "—" if row["old_slice_pct"] is None else f"{float(row['old_slice_pct']):.2%}",
                f"{float(row['new_slice_pct']):.2%}",
            )
        console.print(h)


@risk_budget_app.command("set")
def risk_budget_set_cmd(
    asset: str = typer.Option(..., "--asset"),
    bot: str = typer.Option(..., "--bot"),
    slice_pct: float = typer.Option(..., "--slice-pct", help="Fracción, p. ej. 0.0025"),
    reason: str = typer.Option("", "--reason"),
    confirm: bool = typer.Option(False, "--confirm"),
    armed: bool = typer.Option(
        False, "--armed", help="Operador armado (la consola pasa la sesión real)"
    ),
) -> None:
    """Baja una rebanada al instante; subirla exige --armed --confirm."""
    from .risk_budget import RiskBudgetError, set_bot_slice

    try:
        row = set_bot_slice(
            DEFAULT_DB,
            asset=asset,
            bot=bot,
            slice_pct=slice_pct,
            reason=reason,
            armed=armed,
            confirm=confirm,
        )
    except RiskBudgetError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Rebanada {row['action']}[/green] · {row['bot']} · "
        f"{row['old_slice_pct']:.2%} → {row['new_slice_pct']:.2%}"
    )


@risk_budget_app.command("revert")
def risk_budget_revert_cmd(
    history_id: int = typer.Argument(...),
) -> None:
    """Revierte un cambio de rebanada por su id de historial."""
    from .risk_budget import RiskBudgetError, revert_slice

    try:
        result = revert_slice(DEFAULT_DB, history_id)
    except RiskBudgetError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Revertido[/green] · historial #{result['history_id']}")


@risk_budget_app.command("news")
def risk_budget_news_cmd(
    symbol: str = typer.Option("EURUSD", "--symbol"),
    at: str = typer.Option(None, "--at", help="ISO 8601; por defecto ahora"),
) -> None:
    """Comprueba el apagón de noticias de un activo con macro_events."""
    from .risk_budget import news_blackout

    moment = None
    if at:
        try:
            moment = datetime.fromisoformat(at)
        except ValueError as exc:
            console.print(f"[red]fecha inválida:[/red] {at}")
            raise typer.Exit(2) from exc
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    result = news_blackout(DEFAULT_DB, symbol, now=moment)
    status = "BLOQUEADO" if result["blocked"] else "OK"
    console.print(f"{symbol}: {status} · {result['reason']}")
    if not result["data_ok"]:
        console.print("[yellow]Sin datos de macro_events.[/yellow]")


@lifecycle_app.command("status")
def lifecycle_status_cmd() -> None:
    """Estado de la incubadora, ventana y propuesta."""
    from .lifecycle import status

    rows = status(DEFAULT_DB, settings=get_settings())
    if not rows:
        console.print("[yellow]Sin datos: no hay bots en la incubadora.[/yellow]")
        return
    t = Table(title="Incubadora")
    for col in ("Bot", "Activo", "Estado", "Progreso", "Trades", "Sharpe", "Deriva", "Propuesta"):
        t.add_column(col, overflow="fold")
    for row in rows:
        metrics = row.get("metrics") or {}
        t.add_row(
            str(row.get("bot")),
            str(row.get("asset")),
            str(row.get("state")),
            f"{row.get('progress_pct', 0):.0f}%",
            str(metrics.get("n_trades", 0)),
            "—" if metrics.get("sharpe") is None else f"{float(metrics['sharpe']):.2f}",
            str((row.get("drift") or {}).get("status") or "sin datos"),
            str(row.get("proposal") or "—"),
        )
    console.print(t)
    failures = [
        (row.get("bot"), row.get("failures") or [])
        for row in rows
        if row.get("state") in {"incubando", "evaluado"} and row.get("failures")
    ]
    for bot, reasons in failures:
        console.print(f"[yellow]{bot}:[/yellow] {'; '.join(reasons)}")


@lifecycle_app.command("incubate")
def lifecycle_incubate_cmd(
    bot: str = typer.Argument(..., help="ID del forward (p. ej. us100-trend-d1)"),
    window_days: int = typer.Option(60, "--window-days", min=1),
    min_trades: int = typer.Option(8, "--min-trades", min=1),
    min_sharpe: float = typer.Option(0.0, "--min-sharpe"),
    max_slippage_bps: float = typer.Option(3.0, "--max-slippage-bps", min=0),
    force: bool = typer.Option(
        False,
        "--force",
        help="Incuba aunque la puerta de evidencia no sea elegible (no toca enabled)",
    ),
) -> None:
    """Pasa un forward a `incubando` con criterios congelados. No cambia enabled."""
    from .forward_intraday import load_forward_bots
    from .lifecycle import LifecycleError, register_candidate, start_incubation

    forward = next((item for item in load_forward_bots() if item.id == bot), None)
    if forward is None:
        console.print(f"[red]Forward desconocido:[/red] {bot}")
        raise typer.Exit(2)

    register_candidate(
        DEFAULT_DB,
        bot=bot,
        asset=forward.canonical_symbol,
        note="forward demo; evidencia en reports/research/swing_cfd",
    )
    criteria = {
        "window_days": int(window_days),
        "min_trades": int(min_trades),
        "min_forward_sharpe": float(min_sharpe),
        "max_slippage_bps": float(max_slippage_bps),
        "max_guard_breaches": 0,
        "max_drift_status": "ok",
    }
    try:
        row = start_incubation(
            DEFAULT_DB,
            bot=bot,
            reason="incubacion forward demo",
            criteria_override=criteria,
            require_gate=not force,
        )
    except LifecycleError as exc:
        console.print(f"[red]{exc}[/red]")
        if not force:
            console.print(
                "[dim]La puerta de evidencia no es elegible. Si el operador "
                "asume la incubacion, repite con --force; el bot sigue "
                "enabled:false.[/dim]"
            )
        raise typer.Exit(2) from exc

    table = Table(title=f"Incubadora · {bot}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", overflow="fold")
    table.add_row("Activo", forward.canonical_symbol)
    table.add_row("Estado", str(row.get("state")))
    table.add_row("Ventana", f"{row.get('start_date')} → {row.get('end_date')}")
    table.add_row("Criterios", str(row.get("criteria")))
    table.add_row("Hash", str(row.get("criteria_hash")))
    table.add_row("enabled", "sin cambios (false)")
    console.print(table)


@lifecycle_app.command("report")
def lifecycle_report_cmd(
    bot: str = typer.Option(None, "--bot"),
) -> None:
    """Reporte forward: ventana, trades, Sharpe, slippage, deriva y brechas."""
    from .lifecycle import report_bot, status

    rows = (
        [report_bot(DEFAULT_DB, bot, settings=get_settings())]
        if bot
        else status(DEFAULT_DB, settings=get_settings())
    )
    if not rows:
        console.print("[yellow]Sin datos.[/yellow]")
        return
    for row in rows:
        criteria = row.get("criteria") or {}
        metrics = row.get("metrics") or {}
        panel = Table(title=f"Incubadora · {row.get('bot')} · {row.get('state')}")
        panel.add_column("Campo", style="bold")
        panel.add_column("Valor", overflow="fold")
        panel.add_row("Activo", str(row.get("asset")))
        panel.add_row("Ventana", f"{row.get('start_date')} → {row.get('end_date')}")
        panel.add_row("Progreso", f"{row.get('progress_pct', 0):.1f}% · faltan {row.get('days_left', '—')} días")
        panel.add_row("Criterios", json.dumps(criteria, ensure_ascii=False, sort_keys=True))
        panel.add_row("Hash", str(row.get("criteria_hash") or "—"))
        panel.add_row("Trades", str(metrics.get("n_trades", 0)))
        panel.add_row("Sharpe forward", "—" if metrics.get("sharpe") is None else f"{float(metrics['sharpe']):.2f}")
        panel.add_row("Expectancy", "—" if metrics.get("expectancy") is None else f"{float(metrics['expectancy']):.2f}")
        panel.add_row("Slippage p95", "—" if row.get("slippage_p95_bps") is None else f"{float(row['slippage_p95_bps']):.2f} bps")
        panel.add_row("Deriva", str((row.get("drift") or {}).get("status") or "sin datos"))
        panel.add_row("Brechas guard", str(row.get("guard_breaches", 0)))
        panel.add_row("Propuesta", str(row.get("proposal") or "—"))
        panel.add_row("Motivos", "; ".join(row.get("failures") or []) or "—")
        console.print(panel)


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


@portfolio_app.command("analyze")
def portfolio_analyze_cmd(
    strategies: str = typer.Option(..., "--strategies", help="CSV: A,B,... (syn-0, ftmo-eurusd, id)"),
    account: str = typer.Option(..., "--account", help="Cuenta CFD declarada, p. ej. CFD-001"),
    paths: int = typer.Option(2_000, "--paths", min=2),
    seed: int = typer.Option(42, "--seed"),
    block_size: int = typer.Option(5, "--block-size", min=1),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON compacta"),
) -> None:
    """Analiza cartera vs cada estrategia sola ante las reglas de la firma."""
    from .portfolio_lab import analyze

    try:
        payload = analyze(
            strategies,
            account,
            paths=paths,
            seed=seed,
            block_size=block_size,
        )
    except Exception as exc:
        console.print(f"[red]No se pudo analizar la cartera:[/red] {exc}")
        raise typer.Exit(1) from exc
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str))
        return
    table = Table(title=f"Portfolio Lab · {account} · {payload['firm']}")
    table.add_column("Candidato")
    table.add_column("P(pasar)", justify="right")
    table.add_column("P(romper día)", justify="right")
    table.add_column("P(romper máx.)", justify="right")
    table.add_column("Días al objetivo", justify="right")
    results = payload["challenge"]["results"]

    def _pct(value: object) -> str:
        return "Sin datos" if value is None else f"{float(value):.1%}"

    for label, row in results.items():
        table.add_row(
            str(label),
            _pct(row["p_pasar_fase1"]),
            _pct(row["p_romper_diario"]),
            _pct(row["p_romper_maximo"]),
            str(row["dias_medianos_objetivo"]),
        )
    console.print(table)
    console.print(
        Panel(
            f"{len(payload['members'])} series · {payload['alignment']['days']} días · "
            f"riesgo por 1R {payload['risk_usd_per_r']} USD\n"
            + "\n".join(f"- {method}: {text}" for method, text in payload["verdict"].items()),
            title="Veredicto",
        )
    )
    correlation = payload["correlation"]
    console.print(
        f"Correlaciones: {correlation['labels']} · "
        f"matriz {correlation['matrix']} · tope por idea {payload['cap_note']}"
    )


@app.command("research-costs")
def research_costs_cmd(
    top: int = typer.Option(10, "--top"),
    out: str = typer.Option(None, "--out"),
    source: str = typer.Option(
        "broker", "--source", help="Spread: broker o dukascopy"
    ),
) -> None:
    """Sensibilidad del top de research a comisión, slippage y spread."""
    from .costs import run_costs, write

    selected = str(source or "").strip().lower()
    if selected not in {"broker", "dukascopy"}:
        console.print("[red]--source debe ser broker o dukascopy[/red]")
        raise typer.Exit(2)
    settings = get_settings()
    report_dir = Path(out) if out else ROOT / "reports" / "research"
    try:
        payload = run_costs(
            report_dir,
            cache_dir=settings.data.cache_dir,
            top=top,
            source=selected,
        )
    except Exception as exc:
        console.print(f"[red]No se pudo calcular la sensibilidad:[/red] {exc}")
        raise typer.Exit(1)
    files = write(payload, report_dir)
    console.print(
        Panel(
            f"{len(payload['results'])} variantes · "
            f"frágiles {payload['fragile_count']} · "
            f"sin datos {payload.get('sin_datos_count', 0)} · "
            f"spread {selected}",
            title="Sensibilidad a costes",
        )
    )
    console.print(f"[green]Tabla generada[/green] · {files['md']} · {files['json']}")


@app.command("research-intraday-broker")
def research_intraday_broker_cmd(
    paths: int = typer.Option(500, "--paths"),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Recalcula la etapa 3 con spread bróker p75; no crea trials."""
    from .broker_costs import recalculate_stage3

    reports_dir = Path(out) if out else ROOT / "reports" / "research"
    try:
        result = recalculate_stage3(reports_dir=reports_dir, paths=paths)
    except Exception as exc:
        console.print(f"[red]No se pudo recalcular con coste bróker:[/red] {exc}")
        raise typer.Exit(1)
    comparison = result["comparison"]
    table = Table(title="Coste bróker vs equilibrio")
    for col in ("Activo", "Bróker p75", "Coste cons.", "Equilibrio", "Margen"):
        table.add_column(col, justify="right" if col != "Activo" else "left")
    for row in comparison.get("rows") or []:
        table.add_row(
            str(row["symbol"]),
            "sin datos" if row.get("broker_p75_bps") is None else f"{row['broker_p75_bps']:.3f}",
            "sin datos" if row.get("broker_cost_bps") is None else f"{row['broker_cost_bps']:.2f}",
            "sin cruce" if row.get("breakeven_bps") is None else f"{row['breakeven_bps']:.2f}",
            "sin datos" if row.get("margin") is None else ("sí" if row["margin"] else "no"),
        )
    console.print(table)
    for row in comparison.get("rows") or []:
        console.print(f"- {row['sentence']}")
    if result.get("errors"):
        console.print("[yellow]Avisos:[/yellow] " + "; ".join(result["errors"]))
    console.print(
        f"[green]Informes[/green] · {reports_dir} · "
        "sin trials nuevos; DSR sin cambios."
    )


@app.command("research-caja-ny")
def research_caja_ny_cmd(
    mc_paths: int = typer.Option(500, "--mc-paths"),
    out: str = typer.Option(None, "--out"),
) -> None:
    """Ejecuta caja_ny con eventos y registra sus variantes; sin órdenes."""
    from .event_families import run_caja_ny

    try:
        report = run_caja_ny(
            mc_paths=mc_paths,
            out_dir=Path(out) if out else None,
        )
    except Exception as exc:
        console.print(f"[red]No se pudo ejecutar caja_ny:[/red] {exc}")
        raise typer.Exit(1)
    table = Table(title="Caja NY · eventos")
    for col in (
        "Stop",
        "Trades",
        "Sharpe bruto",
        "Sharpe neto",
        "Coste bps/op",
        "Equilibrio",
        "PBO",
        "WF",
        "DSR",
        "Pasa",
    ):
        table.add_column(col, overflow="fold")
    for row in report["variants"]:
        table.add_row(
            str(row["params"]["stop_rule"]),
            str(row["trades"]),
            f"{row['gross_sharpe']:.2f}",
            f"{row['net_sharpe']:.2f}",
            f"{row['effective_cost_bps']:.2f}",
            "sin cruce"
            if row["breakeven_bps"] is None
            else f"{row['breakeven_bps']:.2f}",
            "sin datos" if row["pbo"] is None else f"{row['pbo']:.2f}",
            str(row["wf_verdict"]),
            f"{row['dsr']:.2f}",
            "sí" if row["passed"] else "no",
        )
    console.print(table)
    counters = report["counters"]
    console.print(
        f"DSR: {counters['before']} → {counters['after']} · "
        f"trials: {counters['trials_before']} → {counters['trials_after']}"
    )
    console.print(
        f"Veredicto: {'PASA' if report['passed'] else 'NO PASA'} · "
        + ("; ".join(report["reasons"]) if report["reasons"] else "sin motivos")
    )
    console.print(f"[green]Informe[/green] · {report['files']['md']}")


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


@futures_app.command("stitch")
def futures_stitch_cmd(
    old: Path = typer.Option(..., "--old", help="Parquet del contrato antiguo"),
    new: Path = typer.Option(..., "--new", help="Parquet del contrato nuevo"),
    roll: str = typer.Option(..., "--roll", help="Fecha de roll YYYY-MM-DD"),
    out: Path = typer.Option(..., "--out", help="Parquet continuo de salida"),
    method: str = typer.Option("ratio", "--method", help="ratio | difference"),
) -> None:
    """Une dos contratos ajustando el salto de rollover (solo lectura)."""
    from .continuous import ContinuousError, stitch_continuous

    try:
        old_frame = pd.read_parquet(old)
        new_frame = pd.read_parquet(new)
        continuous = stitch_continuous(
            [(old.stem, old_frame), (new.stem, new_frame)],
            [roll],
            method=method,
        )
    except (OSError, ValueError, ContinuousError) as exc:
        console.print(f"[red]Contratos continuos:[/red] {exc}")
        raise typer.Exit(1) from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    continuous.to_parquet(out)
    console.print(
        f"[green]Continuo guardado:[/green] {out} · {len(continuous)} barras · "
        f"{continuous.index[0].date()} → {continuous.index[-1].date()} · "
        f"método={method}"
    )


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


@telegram_app.command("setup")
def telegram_setup(
    chat_id: str = typer.Option("", "--chat-id", help="Chat ID autorizado (si ya lo sabes)"),
    user_id: str = typer.Option("", "--user-id", help="User ID autorizado (opcional)"),
    mode: str = typer.Option("commands", "--mode", help="commands | agent"),
    no_test: bool = typer.Option(False, "--no-test", help="No enviar mensaje de prueba"),
) -> None:
    """Valida el bot y guarda token/chat en keyring. No escribe .env."""
    from .telegram import TelegramAPI, TelegramError, discover_chats, save_setup, wait_for_chat

    token = os.getenv("TELEGRAM_BOT_TOKEN") or ""
    if not token:
        if not sys.stdin.isatty():
            console.print(
                "[red]Sin terminal interactiva para pedir el token.[/red] "
                "Exporta TELEGRAM_BOT_TOKEN o ejecuta setup en una terminal normal."
            )
            raise typer.Exit(2)
        token = typer.prompt("Token del bot (se oculta)", hide_input=True).strip()
    if not token:
        console.print("[red]Token vacío.[/red]")
        raise typer.Exit(2)

    api = TelegramAPI(token)
    try:
        me = api.get_me()
    except TelegramError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Bot validado[/green] @{me.get('username') or me.get('id')}")

    candidates, last_update_id = discover_chats(api)
    if not chat_id:
        if not candidates:
            console.print(
                "[yellow]No hay mensajes recientes.[/yellow] Abre el bot en Telegram, "
                "envíale /start y espero hasta 60 segundos…"
            )
            candidates, last_update_id = wait_for_chat(api, 60)
        if len(candidates) == 1:
            candidate = candidates[0]
            chat_id = candidate["chat_id"]
            user_id = user_id or candidate["user_id"]
            console.print(f"Chat detectado: {chat_id} ({candidate['type'] or 'desconocido'})")
        elif candidates:
            table = Table(title="Chats que han escrito al bot")
            table.add_column("Chat ID", style="bold")
            table.add_column("User ID")
            table.add_column("Tipo")
            table.add_column("Usuario")
            for candidate in candidates:
                table.add_row(
                    candidate["chat_id"],
                    candidate["user_id"],
                    candidate["type"],
                    candidate["username"],
                )
            console.print(table)
            chat_id = typer.prompt("Chat ID autorizado").strip()
        else:
            console.print(
                "[yellow]No hay mensajes recientes.[/yellow] Abre el bot en Telegram, "
                "envíale cualquier mensaje y vuelve a ejecutar setup."
            )
            chat_id = typer.prompt("Chat ID autorizado").strip()
    if not chat_id:
        console.print("[red]Falta el chat ID.[/red]")
        raise typer.Exit(2)
    if not user_id:
        user_id = chat_id

    try:
        config = save_setup(
            token,
            chat_id,
            user_id,
            mode=mode,
            last_update_id=last_update_id,
        )
    except TelegramError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    if not no_test:
        try:
            api.send_message(chat_id, "TradingLab: bot conectado. Envía /help.")
            console.print("[green]Mensaje de prueba enviado.[/green]")
        except TelegramError as exc:
            console.print(f"[yellow]No se pudo enviar la prueba: {exc}[/yellow]")

    console.print(
        f"[green]Configuración guardada[/green] · chat={config.allowed_chat_id} · "
        f"modo={config.mode} · token en keyring."
    )
    console.print("[yellow]El puente sigue desactivado.[/yellow] Ejecuta `lab telegram enable`.")


@telegram_app.command("discover")
def telegram_discover() -> None:
    """Muestra chats que han escrito al bot, sin mostrar textos."""
    from .telegram import TelegramAPI, TelegramError, discover_chats, get_token

    try:
        candidates, _ = discover_chats(TelegramAPI(get_token()))
    except TelegramError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if not candidates:
        console.print("[yellow]Sin datos: envía un mensaje al bot y reintenta.[/yellow]")
        return
    table = Table(title="Chats vistos")
    table.add_column("Chat ID", style="bold")
    table.add_column("User ID")
    table.add_column("Tipo")
    table.add_column("Usuario")
    for candidate in candidates:
        table.add_row(
            candidate["chat_id"],
            candidate["user_id"],
            candidate["type"],
            candidate["username"],
        )
    console.print(table)


@telegram_app.command("status")
def telegram_status_cmd() -> None:
    """Estado del puente, sin mostrar el token."""
    from .telegram import STATE_PATH, TelegramConfig, doctor_status

    config = TelegramConfig.load()
    info = doctor_status()
    table = Table(title="Telegram remoto")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", overflow="fold")
    table.add_row("Configurado", "sí" if info["configured"] else "no")
    table.add_row("Puente", "activo" if config.enabled else "pausado")
    table.add_row("Modo", config.mode)
    table.add_row("Chat autorizado", config.allowed_chat_id or "—")
    table.add_row("Usuario autorizado", config.allowed_user_id or "—")
    table.add_row("Agente", config.agent)
    table.add_row("Sesión", config.session_id or "—")
    table.add_row("Estado", str(STATE_PATH))
    console.print(table)


@telegram_app.command("enable")
def telegram_enable() -> None:
    """Activa el puente (sigue sin ejecutar nada hasta recibir mensajes)."""
    from .telegram import TelegramConfig, doctor_status

    if not doctor_status()["configured"]:
        console.print("[red]Sin configurar.[/red] Ejecuta `lab telegram setup`.")
        raise typer.Exit(2)
    config = TelegramConfig.load()
    config.enabled = True
    config.save()
    console.print("[green]Puente activado.[/green] Inicia `lab telegram bridge` o la tarea.")


@telegram_app.command("disable")
def telegram_disable() -> None:
    """Pausa el puente; solo responderá a /status, /help, /ping y /resume."""
    from .telegram import TelegramConfig

    config = TelegramConfig.load()
    config.enabled = False
    config.save()
    console.print("[yellow]Puente pausado.[/yellow]")


@telegram_app.command("mode")
def telegram_mode(
    mode: str = typer.Argument(..., help="commands | agent"),
    yes: bool = typer.Option(False, "--yes", help="No pedir confirmación"),
) -> None:
    """Cambia entre comandos seguros y agente remoto restringido."""
    from .telegram import MODES, TelegramConfig

    mode = mode.strip().lower()
    if mode not in MODES:
        console.print("[red]Modo inválido.[/red] Usa commands o agent.")
        raise typer.Exit(2)
    if mode == "agent" and not yes:
        if not typer.confirm(
            "El modo agent permite ejecutar OpenCode con auto-aprobación restringida. ¿Activar?"
        ):
            raise typer.Exit(1)
    config = TelegramConfig.load()
    config.mode = mode
    config.save()
    console.print(f"[green]Modo {mode} activado.[/green]")


@telegram_app.command("new-session")
def telegram_new_session() -> None:
    """Olvida la sesión remota; el próximo mensaje crea una nueva."""
    from .telegram import TelegramConfig

    config = TelegramConfig.load()
    config.session_id = ""
    config.save()
    console.print("[green]Sesión remota reiniciada.[/green]")


@telegram_app.command("test")
def telegram_test() -> None:
    """Envía un mensaje de prueba al chat autorizado."""
    from .telegram import TelegramAPI, TelegramError, get_chat_id, get_token

    try:
        chat_id = get_chat_id()
        if not chat_id:
            console.print("[red]Falta el chat ID.[/red] Ejecuta `lab telegram setup`.")
            raise typer.Exit(2)
        TelegramAPI(get_token()).send_message(chat_id, "TradingLab: prueba de conexión OK.")
    except TelegramError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print("[green]Mensaje de prueba enviado.[/green]")


@telegram_app.command("send")
def telegram_send(
    text: str = typer.Option("", "--text", "-t", help="Texto a enviar"),
    file: Path = typer.Option(None, "--file", "-f", help="Archivo de texto a enviar"),
    stdin: bool = typer.Option(False, "--stdin", help="Leer el mensaje de stdin"),
) -> None:
    """Envía un resumen o aviso al chat autorizado."""
    from .telegram import TelegramError, send_configured

    if file is not None:
        try:
            content = file.read_text(encoding="utf-8")
        except Exception as exc:
            console.print(f"[red]No se pudo leer el archivo: {type(exc).__name__}[/red]")
            raise typer.Exit(2) from exc
    elif text:
        content = text
    elif stdin:
        content = sys.stdin.read()
    else:
        console.print("[red]Falta texto: usa --text, --file o --stdin.[/red]")
        raise typer.Exit(2)
    if not content.strip():
        console.print("[red]Mensaje vacío.[/red]")
        raise typer.Exit(2)
    try:
        send_configured(content)
    except TelegramError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print("[green]Mensaje enviado a Telegram.[/green]")


@telegram_app.command("bridge")
def telegram_bridge_cmd(
    once: bool = typer.Option(False, "--once", help="Procesa pendientes y sale"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No envía respuestas reales"),
) -> None:
    """Long polling de Telegram; lo normal es lanzarlo con la tarea programada."""
    from .telegram import TelegramAPI, TelegramConfig, TelegramError, get_token, run_bridge

    config = TelegramConfig.load()
    if not config.allowed_chat_id:
        console.print("[red]Sin configurar.[/red] Ejecuta `lab telegram setup`.")
        raise typer.Exit(2)
    try:
        api = TelegramAPI(get_token())
    except TelegramError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Puente Telegram[/green] · modo={config.mode} · "
        f"{'activo' if config.enabled else 'pausado'}"
    )
    try:
        run_bridge(api, once=once, dry_run=dry_run)
    except KeyboardInterrupt:
        console.print("Puente detenido.")


@library_app.command("list")
def library_list_cmd(
    status: str = typer.Option(None, "--status", help="adoptada | evaluada | descartada"),
) -> None:
    """Lista las fichas de la biblioteca."""
    from .library import LibraryError, list_library

    try:
        entries = list_library(status=status)
    except LibraryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if not entries:
        console.print("[yellow]Sin datos en la biblioteca.[/yellow]")
        return
    table = Table(title="Biblioteca de conocimiento")
    for column in ("ID", "Herramienta", "Categoría", "Licencia", "Versión", "Estado"):
        table.add_column(column)
    for entry in entries:
        table.add_row(
            entry["id"],
            entry["name"],
            entry["category"],
            entry["license"],
            entry["version"],
            entry["status"],
        )
    console.print(table)


@library_app.command("show")
def library_show_cmd(
    entry_id: str = typer.Argument(..., help="ID de la ficha, p. ej. dsr"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Muestra una ficha completa."""
    from .library import LibraryError, get_entry

    try:
        entry = get_entry(entry_id)
    except LibraryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    if as_json:
        console.print_json(data=entry)
        return
    table = Table(title=f"Biblioteca · {entry['name']}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", overflow="fold")
    for field, label in (
        ("id", "ID"),
        ("category", "Categoría"),
        ("problem", "Problema"),
        ("official_url", "Enlace oficial"),
        ("license", "Licencia"),
        ("version", "Versión"),
        ("dependencies", "Dependencias"),
        ("data_costs", "Datos/costes"),
        ("advantages", "Ventajas"),
        ("risks", "Riesgos"),
        ("tests", "Pruebas en TradingLab"),
        ("status", "Estado"),
        ("reason", "Motivo"),
    ):
        table.add_row(label, str(entry.get(field) or "Sin datos"))
    console.print(table)


@app.command("tca")
def tca_cmd(
    bot: str = typer.Option(None, "--bot", help="Filtra por bot"),
    min_fills: int = typer.Option(5, "--min-fills", help="Mínimo de fills para concluir"),
) -> None:
    """Estado de TCA: slippage y coste real frente al supuesto."""
    from .tca import build_tca

    state = build_tca(DEFAULT_DB, min_fills=min_fills, alert=False)
    rows = [
        row
        for row in state["rows"]
        if not bot or str(row["bot"]) == bot
    ]
    if not rows:
        console.print("[yellow]Sin datos: no hay fills registrados.[/yellow]")
        return
    t = Table(title="TCA · ejecución real")
    for col in (
        "Bot",
        "Símbolo",
        "Fills",
        "Slippage EWMA",
        "Slippage p50",
        "Coste EWMA",
        "Latencia",
        "Fill rate",
        "Estado",
    ):
        t.add_column(col, overflow="fold")
    for row in rows:
        t.add_row(
            str(row["bot"]),
            str(row["symbol"]),
            str(row["fills"]),
            f"{row['slippage_ewma_bps']:.1f} bps"
            if row["slippage_ewma_bps"] is not None
            else "Sin datos",
            f"{row['slippage_p50_bps']:.1f} bps"
            if row["slippage_p50_bps"] is not None
            else "Sin datos",
            f"{row['cost_ewma_bps']:.1f} bps"
            if row["cost_ewma_bps"] is not None
            else "Sin datos",
            f"{row['median_latency_ms']:.0f} ms"
            if row["median_latency_ms"] is not None
            else "Sin datos",
            f"{row['fill_rate']:.0%}" if row["fill_rate"] is not None else "Sin datos",
            row["status"],
        )
    console.print(t)
    console.print(
        f"[dim]Supuesto medio: "
        f"{rows[0]['expected_cost_bps']:.1f} bps · estado global: {state['status']}[/dim]"
    )


@app.command("drill")
def drill_cmd(
    confirm: bool = typer.Option(False, "--confirm", help="Confirmación explícita del simulacro"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simulación sin tocar nada: informa y deja rastro, no cancela ni cierra",
    ),
    check_backup: bool = typer.Option(
        False,
        "--check-backup",
        help="Restaura el último backup y compara conteos con la base viva",
    ),
) -> None:
    """Simulacro de emergencia (R8). Solo paper/demo y con operador armado."""
    from .drill import DrillError, run_drill, simulate_drill
    from .operator import server_session, web_port

    settings = get_settings()
    if str(settings.mode).lower() == "live":
        console.print("[red]El simulacro no se ejecuta en live.[/red]")
        raise typer.Exit(2)
    if dry_run:
        try:
            resultado = simulate_drill(
                DEFAULT_DB, settings, check_backup=check_backup
            )
        except DrillError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(2) from exc
        console.print(
            f"[cyan]Simulación del simulacro[/cyan] en {resultado['elapsed_s']}s · "
            f"{resultado['pending_orders']} órdenes abiertas · "
            f"{resultado['positions']} posiciones · kill-switch "
            f"{'activo' if resultado['killswitch_active'] else 'inactivo'} · "
            f"ntfy {'sí' if resultado['ntfy_configured'] else 'no'} · "
            f"telegram {'sí' if resultado['telegram_configured'] else 'no'}"
        )
        if check_backup:
            estado = "OK" if resultado["backup_ok"] else "FAIL"
            color = "green" if resultado["backup_ok"] else "red"
            detail = (resultado.get("backup") or {}).get("detail", "")
            console.print(f"[{color}]Backup {estado}[/{color}]: {detail}")
        console.print(
            "[dim]No se canceló nada, no se cerró nada y no se enviaron avisos. "
            "El simulacro real sigue exigiendo operador armado y --confirm.[/dim]"
        )
        if check_backup and not resultado["backup_ok"]:
            raise typer.Exit(1)
        return
    try:
        session = server_session()
        if session is None:
            console.print(
                "[red]El simulacro exige el operador armado y el panel web en "
                f"marcha: no responde en http://127.0.0.1:{web_port()}.[/red]"
            )
            raise typer.Exit(2)
        if not session.get("armed"):
            console.print(
                "[red]El simulacro exige el operador armado. "
                "Ármalo desde la consola con el PIN.[/red]"
            )
            raise typer.Exit(2)
        if not confirm:
            console.print("[red]El simulacro exige --confirm.[/red]")
            raise typer.Exit(2)
        result = run_drill(DEFAULT_DB, settings, confirm=True, armed=True)
    except DrillError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Simulacro completado[/green] en {result['elapsed_s']}s · "
        f"{result['cancelled_orders']} órdenes · {result['closed_positions']} posiciones"
    )


@app.command("budget")
def alerts_budget_cmd() -> None:
    """Presupuesto semanal de alertas."""
    from .alerts_budget import weekly_budget

    state = weekly_budget(DEFAULT_DB)
    t = Table(title="Presupuesto de alertas (7 días)")
    t.add_column("Campo", style="bold")
    t.add_column("Valor", justify="right")
    t.add_row("Presupuesto", str(state["budget"]))
    t.add_row("Usadas", str(state["used"]))
    t.add_row("Restantes", str(state["remaining"]))
    t.add_row("Estado", "excedido" if state["exceeded"] else "ok")
    console.print(t)
    if state["rows"]:
        r = Table(title="Por evento y canal")
        for col in ("Evento", "Canal", "n"):
            r.add_column(col, overflow="fold")
        for row in state["rows"][:20]:
            r.add_row(str(row["event"]), str(row["channel"]), str(row["n"]))
        console.print(r)


# ================================================================== Campaña


def _campaign_universe_path() -> Path:
    from .campaign import REPORT_DIR

    return REPORT_DIR / "universe.json"


def _campaign_load_universe() -> dict:
    from .campaign import CampaignError

    path = _campaign_universe_path()
    if not path.exists():
        raise CampaignError(
            f"falta el universo: {path}. Corre antes `lab campaign universe`."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@campaign_app.command("universe")
def campaign_universe_cmd(
    bars_h1: int = typer.Option(2000, "--bars-h1", help="Velas H1 para el spread horario"),
    bars_h4: int = typer.Option(6000, "--bars-h4", help="Velas H4 para ATR y D1"),
    save: bool = typer.Option(True, "--save/--no-save", help="Cachea las velas medidas"),
) -> None:
    """Mide el universo por coste y escribe universe.md/.json. Solo lectura."""
    from .campaign import CampaignError, build_universe, compute_n_total, write_universe

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        universe = build_universe(
            broker,
            bars={"H1": int(bars_h1), "H4": int(bars_h4)},
            cache_dir=settings.data.cache_dir,
            save=bool(save),
        )
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    finally:
        broker.shutdown()

    paths = write_universe(universe)
    totals = compute_n_total(universe)
    counts = universe["counts"]
    console.print(
        f"[green]Universo medido[/green] · {counts['measured']} activos · "
        f"{counts['verified_commission']} con comisión verificada"
    )
    table = Table(title="Elegibles por timeframe (cost_atr < 0,05)")
    table.add_column("Timeframe", style="bold")
    table.add_column("Activos", justify="right")
    table.add_column("Nombres", overflow="fold")
    for timeframe in ("H1", "H4", "D1"):
        names = universe["eligible_by_timeframe"].get(timeframe) or []
        table.add_row(
            timeframe,
            str(len(names)),
            ", ".join(names) if names else "Sin datos",
        )
    console.print(table)
    console.print(
        f"[bold]N_total[/bold] = {totals['n_total']} "
        f"({totals['per_timeframe']})"
    )
    console.print(f"Escrito: {paths['md']} · {paths['json']}")


@campaign_app.command("n-total")
def campaign_ntotal_cmd() -> None:
    """Calcula N_total con el corte común. No registra nada."""
    from .campaign import CampaignError, compute_n_total

    try:
        universe = _campaign_load_universe()
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    plan = universe.get("plan") or {}
    if not plan:
        console.print(
            "[yellow]Sin plan: N_total teórico. Corre `lab campaign fetch` para "
            "excluir celdas sin historia con el corte común.[/yellow]"
        )
        totals = compute_n_total(universe)
        table = Table(title=f"N_total teórico = {totals['n_total']}")
        table.add_column("Timeframe", style="bold")
        table.add_column("Activos", justify="right")
        table.add_column("Familias", overflow="fold")
        table.add_column("Celdas", justify="right")
        for timeframe in ("H1", "H4", "D1"):
            rows = totals["detail"].get(timeframe) or []
            families = sorted({name for row in rows for name in row["families"]})
            table.add_row(
                timeframe,
                str(len(rows)),
                ", ".join(families) if families else "Sin datos",
                str(totals["per_timeframe"].get(timeframe, 0)),
            )
        console.print(table)
        return
    table = Table(title=f"N_total = {plan['n_total']} · corte {plan['cutoff_utc']}")
    table.add_column("Timeframe", style="bold")
    table.add_column("Activos", justify="right")
    table.add_column("Celdas", justify="right")
    for timeframe in ("H1", "H4", "D1"):
        table.add_row(
            timeframe,
            str(len(universe["eligible_by_timeframe"].get(timeframe) or [])),
            str(plan["per_timeframe"].get(timeframe, 0)),
        )
    console.print(table)
    per_timeframe_total = sum(int(value) for value in plan["per_timeframe"].values())
    if per_timeframe_total != int(plan["n_total"]):
        console.print(
            f"[red]N_total no cuadra: {plan['n_total']} != {per_timeframe_total}[/red]"
        )
        raise typer.Exit(2)
    excluded = plan.get("excluded") or []
    excluded_assets = plan.get("excluded_assets") or []
    holdout_text = (
        "Sin datos"
        if plan.get("holdout_years") is None
        else f"{float(plan['holdout_years']):.2f} años"
    )
    console.print(
        f"Holdout común = {holdout_text} "
        f"(mínimo {float(plan.get('min_holdout_years', 2.0)):g}) · "
        f"activos excluidos por holdout corto = {len(excluded_assets)}"
    )
    for item in excluded_assets:
        console.print(f"  [yellow]· {item['symbol']}[/yellow]: {item['reason']}")
    console.print(
        f"Excluidas por historia: {len(excluded)} · "
        f"holdout_hash = {str(plan.get('holdout_hash') or 'Sin datos')[:16]}…"
    )


def _campaign_config(universe: dict, campaign: str, *,
                     skip_adjacent_if_empty: bool = False,
                     pbo_gate: bool = False) -> dict:
    """Configuración de la campaña a partir del universo y su plan.

    No registra nada: es la misma función la que escribe el yaml y la que
    sellaría, para que las dos no puedan divergir.
    """
    from .campaign import campaign_config

    return campaign_config(
        universe, campaign,
        skip_adjacent_if_empty=skip_adjacent_if_empty,
        pbo_gate=pbo_gate,
    )


@campaign_app.command("fetch")
def campaign_fetch_cmd() -> None:
    """Descarga H1/H4 de todos los candidatos, fija el corte ≥2 años y planifica."""
    from .campaign import (
        CAMPAIGN_BARS,
        CampaignError,
        load_campaign_frames,
        prepare_campaign,
        require_live_data,
        universe_symbols,
        write_universe,
    )

    try:
        universe = _campaign_load_universe()
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    symbols = universe_symbols(universe)
    if not symbols:
        console.print("[red]Sin candidatos en el universo: no hay velas que descargar.[/red]")
        raise typer.Exit(2)

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    names = {
        str(row["symbol"]).upper(): str(row.get("mt5_name") or row["symbol"])
        for row in universe.get("symbols") or []
    }
    try:
        access = require_live_data(broker)
        console.print(
            f"Mercado abierto · tick {access['symbol']} de hace "
            f"{access['age_minutes']:.1f} min · offset "
            f"{access['offset_utc_hours']:+g} h ({access['offset_source']})"
        )
        console.print(
            f"Descargando H1/H4 de {len(symbols)} candidatos "
            f"(máximo {CAMPAIGN_BARS['H1']:,} barras)…"
        )
        frames, _ = load_campaign_frames(
            broker, symbols, names=names, cache_dir=settings.data.cache_dir
        )
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    finally:
        broker.shutdown()
    if not frames:
        console.print("[red]Sin datos: el bróker no devolvió velas.[/red]")
        raise typer.Exit(2)

    try:
        universe = prepare_campaign(
            universe,
            frames,
            cache_dir=settings.data.cache_dir,
        )
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    plan = universe["plan"]
    paths = write_universe(universe)

    table = Table(title=f"Celdas con historia suficiente · corte {plan['cutoff_utc']}")
    table.add_column("Timeframe", style="bold")
    table.add_column("Celdas", justify="right")
    table.add_column("Activos", justify="right")
    for timeframe in ("H1", "H4", "D1"):
        table.add_row(
            timeframe,
            str(plan["per_timeframe"].get(timeframe, 0)),
            str(len(universe["eligible_by_timeframe"].get(timeframe) or [])),
        )
    console.print(table)
    excluded_assets = plan.get("excluded_assets") or []
    console.print(
        f"[bold]N_total[/bold] = {plan['n_total']} · series selladas = "
        f"{len(plan.get('holdout_series') or [])} · celdas excluidas por historia = "
        f"{len(plan['excluded'])}"
    )
    console.print(
        f"Holdout común = {plan['holdout_years']:.2f} años · activos excluidos por "
        f"holdout corto = {len(excluded_assets)}"
    )
    for item in excluded_assets:
        console.print(f"  [yellow]· {item['symbol']}[/yellow]: {item['reason']}")
    console.print(
        f"holdout_hash = {plan['holdout_hash']}",
        markup=False,
    )
    console.print(f"Escrito: {paths['md']} · {paths['json']}")


@campaign_app.command("plan")
def campaign_plan_cmd(
    campaign: str = typer.Option("2026-11-A", "--campaign", help="Identificador"),
    force: bool = typer.Option(False, "--force", help="Reescribe un yaml existente"),
    skip_adjacent_if_empty: bool = typer.Option(
        False, "--skip-adjacent-if-empty",
        help="Exime (c) si el timeframe adyacente no tiene celdas",
    ),
    pbo_gate: bool = typer.Option(
        False, "--pbo-gate",
        help="El PBO de descubrimiento ser? gate (solo campa?as nuevas)",
    ),
) -> None:
    """Escribe config/campaigns/<id>.yaml con el corte y N_total. No registra."""
    from .campaign import CAMPAIGNS_DIR, CampaignError

    try:
        universe = _campaign_load_universe()
        config = _campaign_config(
            universe, campaign,
            skip_adjacent_if_empty=skip_adjacent_if_empty,
            pbo_gate=pbo_gate,
        )
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    path = CAMPAIGNS_DIR / f"{campaign}.yaml"
    if path.exists() and not force:
        console.print(
            f"[yellow]{path} ya existe. Usa --force solo si aún no se ha "
            "registrado.[/yellow]"
        )
        raise typer.Exit(2)
    try:
        import yaml

        path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    except Exception as exc:
        console.print(f"[red]No se pudo escribir {path}: {exc}[/red]")
        raise typer.Exit(1) from exc

    table = Table(title=f"Plan {campaign} (sin registrar)")
    table.add_column("Campo", style="bold")
    table.add_column("Valor", overflow="fold")
    table.add_row("N_total", str(config["n_total"]))
    table.add_row("Por timeframe", str(config["n_total_detail"]))
    table.add_row("N_total teórico", str(config["n_total_theoretical"]))
    table.add_row("Corte común", str(config["cutoff_utc"]))
    table.add_row("Holdout común", f"{config['holdout_years']:.2f} años")
    table.add_row("Activos excluidos", str(len(config["excluded_assets"])))
    table.add_row("Celdas excluidas", str(config["excluded_cells"]))
    table.add_row("config_hash", str(config["config_hash"]))
    table.add_row("holdout_hash", str(config["holdout_hash"]))
    console.print(table)
    console.print(f"Escrito: {path} · [yellow]no registrado[/yellow]")


@campaign_app.command("register")
def campaign_register_cmd(
    campaign: str = typer.Option("2026-11-A", "--campaign", help="Identificador"),
    confirm: bool = typer.Option(False, "--confirm", help="Sella la campaña de verdad"),
    pbo_gate: bool = typer.Option(
        False, "--pbo-gate",
        help="El PBO de descubrimiento será gate (solo si no hay YAML previo)",
    ),
) -> None:
    """Sella la campaña una sola vez con el corte común ya fijado. No corre."""
    from .campaign import (
        CAMPAIGNS_DIR,
        CampaignError,
        campaign_hash,
        load_campaign_yaml,
        register_campaign,
    )

    if not confirm:
        console.print(
            "[yellow]Sin --confirm no se sella nada. Esto consume la única "
            "pasada de la campaña.[/yellow]"
        )
        raise typer.Exit(2)
    path = CAMPAIGNS_DIR / f"{campaign}.yaml"
    stored = None
    skip_adjacent = False
    gate = bool(pbo_gate)
    if path.exists():
        try:
            stored = load_campaign_yaml(path)
            skip_adjacent = bool(
                (stored.get("plateau") or {}).get("skip_adjacent_if_empty")
            )
            gate = bool(stored.get("pbo_gate", False))
        except CampaignError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(2) from exc
    try:
        universe = _campaign_load_universe()
        config = _campaign_config(
            universe, campaign,
            skip_adjacent_if_empty=skip_adjacent,
            pbo_gate=gate,
        )
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    if path.exists():
        if campaign_hash(stored) != config["config_hash"]:
            console.print(
                f"[red]{path.name} no coincide con el universo medido: "
                "rejilla, corte o N_total cambiaron. Regenera el plan antes de "
                "sellar.[/red]"
            )
            raise typer.Exit(2)
    else:
        CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            import yaml

            path.write_text(
                yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        except Exception as exc:
            console.print(f"[red]No se pudo escribir {path}: {exc}[/red]")
            raise typer.Exit(1) from exc

    try:
        record = register_campaign(
            DEFAULT_DB,
            config,
            note=(
                f"corte común {config['cutoff_utc']}; "
                f"{len(config['universe'])} activos; "
                f"{config['excluded_cells']} celdas fuera por historia"
            ),
        )
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Campaña sellada[/green] · {record['campaign_id']} · "
        f"N_total={record['n_total']} · series selladas="
        f"{len(config['holdout_series'])}"
    )
    console.print(f"corte común = {config['cutoff_utc']}")
    console.print(f"config_hash = {record['config_hash'][:16]}…")
    console.print(f"holdout_hash = {str(config['holdout_hash'])[:16]}…")
    console.print(f"YAML: {path}")



@campaign_app.command("status")
def campaign_status_cmd() -> None:
    """Estado del registro: N_total, hashes y si ya se ejecutó."""
    from .campaign import init_campaigns

    init_campaigns(DEFAULT_DB)
    from .db import connect

    with connect(DEFAULT_DB) as con:
        rows = con.execute(
            "SELECT * FROM campaign_registry ORDER BY id DESC"
        ).fetchall()
    if not rows:
        console.print("[yellow]Ninguna campaña registrada.[/yellow]")
        return
    table = Table(title="Campañas registradas")
    for column in (
        "id",
        "N_total",
        "discovery",
        "config_hash",
        "holdout_hash",
        "run_id",
        "started_at",
        "pbo_gate",
        "estado",
    ):
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(
            str(row["campaign_id"]),
            str(row["n_total"]),
            f"{float(row['discovery_pct']):.0%}",
            str(row["config_hash"])[:12] + "…",
            (str(row["holdout_hash"])[:12] + "…") if row["holdout_hash"] else "Sin datos",
            str(row["run_id"] or "Sin datos"),
            str(row["started_at"] or "no ejecutada"),
            "sí" if row["pbo_gate"] else "no",
            (
                "contaminada: " + str(row["contamination_reason"] or "")
                if row["contaminated_at"] else "ok"
            ),
        )
    console.print(table)


@campaign_app.command("run")
def campaign_run_cmd(
    campaign: str = typer.Option("2026-11-A", "--campaign", help="Identificador"),
    confirm: bool = typer.Option(False, "--confirm", help="Consume la única pasada"),
    approved_by_operator: str = typer.Option(
        None, "--approved-by-operator",
        help="Nombre/ID del operador que aprueba esta ejecución en esta sesión",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Reanuda un run cortado por un fallo de código (mismo run_id)",
    ),
    paths: int = typer.Option(5_000, "--paths", help="Caminos del Monte Carlo FTMO"),
) -> None:
    """Corre la campaña una sola vez: descubrimiento, meseta y holdout."""
    from .campaign import (
        CampaignError,
        apply_plateau,
        candidates,
        clip_seal,
        correlation_clusters,
        finish_campaign,
        holdout_hash,
        holdout_rows,
        load_campaign,
        load_campaign_frames,
        load_campaign_yaml,
        run_discovery,
        run_holdout,
        seal_ends,
        write_report,
    )
    from .learning import count_tests

    if not confirm or not str(approved_by_operator or "").strip():
        console.print(
            "[yellow]Sin --confirm y --approved-by-operator no se corre. "
            "La aprobación debe ser explícita en esta misma sesión.[/yellow]"
        )
        raise typer.Exit(2)
    from .campaign import CAMPAIGNS_DIR

    try:
        record = load_campaign(DEFAULT_DB, campaign)
        config = load_campaign_yaml(CAMPAIGNS_DIR / f"{campaign}.yaml")
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    cutoff = config.get("cutoff_utc")
    expected = config.get("holdout_hash")
    if not cutoff or not expected:
        console.print(
            "[red]El yaml no tiene corte común ni holdout_hash: regenera el "
            "plan con `lab campaign fetch` y `lab campaign plan`.[/red]"
        )
        raise typer.Exit(2)

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        frames, points = load_campaign_frames(
            broker,
            list(config.get("universe") or []),
            names=dict(config.get("mt5_names") or {}),
            cache_dir=settings.data.cache_dir,
        )
    finally:
        broker.shutdown()
    if not frames:
        console.print("[red]Sin datos: no hay velas para ningún activo.[/red]")
        raise typer.Exit(2)

    # El holdout se congela en su fin sellado: barras posteriores al sello no
    # entran ni en la confirmación ni en la huella.
    ends = seal_ends(config)
    frames = {key: clip_seal(frame, ends.get(key)) for key, frame in frames.items()}
    sealed_now = holdout_rows(frames, cutoff)
    if holdout_hash(sealed_now, cutoff) != str(expected):
        console.print(
            "[red]El holdout ya no coincide con el sello: los datos cambiaron "
            "antes del fin sellado. No se corre.[/red]"
        )
        raise typer.Exit(2)

    prior = max(0, int(count_tests(DEFAULT_DB)) - int(record["n_total"]))
    try:
        discovery = run_discovery(
            DEFAULT_DB, config, frames, points=points, resume=bool(resume)
        )
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Descubrimiento[/green] · {discovery['n_cells']} celdas · "
        f"run_id={discovery['run_id']}"
        + (" · reanudado" if resume else "")
    )

    clusters = correlation_clusters(frames, cutoff)
    plateau = apply_plateau(
        discovery["cells"], clusters,
        skip_adjacent_if_empty=bool(
            (config.get("plateau") or {}).get("skip_adjacent_if_empty")
        ),
    )
    selected = candidates(plateau)
    console.print(
        f"[green]Meseta[/green] · {len(selected)} candidatas de {len(plateau)} celdas"
    )
    from .stats import period_sharpe

    trial_srs = [
        period_sharpe(series) for series in discovery["returns_by_id"].values()
    ]
    discovery_pbo_payload = discovery.get("pbo") or {}
    pbo_gate = bool(config.get("pbo_gate", False))
    confirmed = run_holdout(
        DEFAULT_DB,
        config,
        frames,
        selected,
        points=points,
        prior_tests=prior,
        paths=int(paths),
        trial_srs_per_period=trial_srs,
        discovery_pbo_payload=discovery_pbo_payload,
        pbo_gate=pbo_gate,
    )
    paths_out = write_report(
        campaign,
        plateau,
        confirmed,
        n_total=int(record["n_total"]),
        discovery_pbo=discovery_pbo_payload,
        pbo_gate=pbo_gate,
    )
    try:
        finish_campaign(DEFAULT_DB, campaign)
    except CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[bold]{len(confirmed)} confirmadas[/bold] · informe: {paths_out['md']}"
    )
    if not confirmed:
        console.print(
            "[yellow]0 confirmadas: no se registra ningún candidato en el "
            "ciclo de vida.[/yellow]"
        )


def _campaign_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ai_trader_error(exc: Exception) -> None:
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(2) from exc


@ai_trader_app.command("snapshot")
def ai_trader_snapshot_cmd(
    symbols: str = typer.Option(
        None, "--symbols", help="Lista separada por comas; por defecto, el universo"
    ),
    style: str = typer.Option(
        None, "--style", help="Snapshot compacto de un estilo (scalping/intraday/swing)"
    ),
) -> None:
    """Snapshot compacto por símbolo para decidir la sesión."""
    from .ai_trader import AiTraderError, snapshot, snapshot_style

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        wanted = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
        payload = snapshot_style(broker, style, wanted) if style else snapshot(broker, wanted)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    finally:
        broker.shutdown()
    typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


@ai_trader_app.command("propose")
def ai_trader_propose_cmd(
    proposal: str = typer.Option(..., "--json", help="JSON de la propuesta"),
) -> None:
    """Valida la propuesta, calcula niveles/volumen y devuelve la orden."""
    from .ai_trader import AiTraderError, propose

    try:
        payload = json.loads(proposal)
    except json.JSONDecodeError as exc:
        console.print(f"[red]JSON inválido:[/red] {exc}")
        raise typer.Exit(2) from exc
    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        result = propose(payload, broker=broker, settings=settings, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    finally:
        broker.shutdown()
    typer.echo(
        json.dumps(
            {"id": result["id"], **result["order"]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


@ai_trader_app.command("skip")
def ai_trader_skip_cmd(
    decision: str = typer.Option(..., "--json", help="JSON de la decisión de no operar"),
) -> None:
    """Registra una decisión de NO operar con su motivo y snapshot."""
    from .ai_trader import AiTraderError, skip

    try:
        payload = json.loads(decision)
    except json.JSONDecodeError as exc:
        console.print(f"[red]JSON inválido:[/red] {exc}")
        raise typer.Exit(2) from exc
    try:
        result = skip(payload, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    console.print(
        f"[green]Decisión registrada[/green] #{result['id']} · skip · "
        f"{result['reason'][:160]}"
    )


@ai_trader_app.command("plan")
def ai_trader_plan_cmd(
    plan: str = typer.Option(None, "--json", help="JSON del plan de scalping"),
    json_file: str = typer.Option(
        None, "--json-file", help="Archivo JSON del plan de scalping"
    ),
) -> None:
    """Valida y guarda el plan del día para un símbolo de scalping."""
    from .ai_trader import AiTraderError, create_plan

    if bool(plan) == bool(json_file):
        console.print("[red]Usa exactamente uno de --json o --json-file[/red]")
        raise typer.Exit(2)
    try:
        raw = (
            Path(json_file).read_text(encoding="utf-8")
            if json_file else str(plan)
        )
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        console.print(f"[red]JSON inválido:[/red] {exc}")
        raise typer.Exit(2) from exc
    try:
        result = create_plan(payload, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


@ai_trader_app.command("plans")
def ai_trader_plans_cmd() -> None:
    """Lista los planes de scalping activos del día."""
    from .ai_trader import _active_plans, _reset_date

    plans = _active_plans(DEFAULT_DB, _reset_date())
    typer.echo(json.dumps(plans, ensure_ascii=False, separators=(",", ":")))


@ai_trader_app.command("scalp")
def ai_trader_scalp_cmd() -> None:
    """Una pasada del scalper sin LLM; pensada para ejecutarse cada minuto."""
    from .ai_trader import AiTraderError, scalp, scalp_window_open

    settings = get_settings()
    try:
        window = scalp_window_open()
    except AiTraderError as exc:
        _ai_trader_error(exc)
    if not window:
        typer.echo(json.dumps({"status": "outside_window"}))
        return
    broker = None
    try:
        broker = _mt5(settings, dry_run=False)
    except typer.Exit:
        result = scalp(broker=None, settings=settings, db_path=DEFAULT_DB)
        typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return
    try:
        result = scalp(broker=broker, settings=settings, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    finally:
        broker.shutdown()
    if result.get("status") == "ok":
        console.print(
            f"[green]scalp[/green] · {result.get('session_date')} · "
            f"{result.get('plans', 0)} planes · "
            f"{len(result.get('executed') or [])} ejecutadas · "
            f"{result.get('skipped', 0)} sin operar"
        )
        for item in result.get("executed") or []:
            console.print(
                f"  {item['symbol']} {item['strategy']} {item['side']} "
                f"{item['timeframe']} · ticket {item.get('ticket')}"
            )
    else:
        console.print(
            f"[yellow]scalp: {result.get('status')}[/yellow] "
            f"{result.get('reason') or ''}".rstrip()
        )


@ai_trader_app.command("execute")
def ai_trader_execute_cmd(
    proposal_id: str = typer.Option(..., "--id", help="ID de la propuesta"),
) -> None:
    """Envía a MT5 demo la propuesta validada, con su magic y SL/TP."""
    from .ai_trader import AiTraderError, execute

    settings = get_settings()
    broker = _mt5(settings, dry_run=False)
    try:
        result = execute(proposal_id, broker=broker, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    finally:
        broker.shutdown()
    console.print(
        f"[green]Ejecutada[/green] {proposal_id[:8]} · "
        f"{result['order'].get('symbol')} {result['order'].get('side')} "
        f"{result['order'].get('volume')} · ticket {result['order'].get('order_id')} "
        f"· estilo {result.get('style')}"
    )
    fills = result.get("fills") or {}
    if fills.get("inserted"):
        console.print(
            f"[dim]Fills MT5: {fills['inserted']} nuevos "
            f"({fills.get('manual', 0)} manuales)[/dim]"
        )
    if result.get("fills_error"):
        console.print(
            f"[yellow]Fills MT5: no se pudo sincronizar:[/yellow] "
            f"{result['fills_error']}"
        )


@ai_trader_app.command("status")
def ai_trader_status_cmd(
    json_output: bool = typer.Option(
        False, "--json", help="Salida JSON para scripts y resúmenes"
    ),
) -> None:
    """Estado por estilo (riesgo, trades, posiciones, PnL y stop) y global."""
    from .ai_trader import AiTraderError
    from .ai_trader import status as lane_status

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        data = lane_status(broker=broker, settings=settings, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    finally:
        broker.shutdown()
    if json_output:
        typer.echo(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        return
    table = Table(title="IA discrecional · estado por estilo")
    for column in ("Estilo", "Magic", "Riesgo", "Trades", "Abiertas",
                   "PnL día", "Stop restante", "Ventana"):
        table.add_column(column)
    for name, item in data["styles"].items():
        trades = str(item["trades_today"])
        if item["max_trades_per_day"] is not None:
            trades += f"/{item['max_trades_per_day']}"
        risk = f"{item['risk_used_pct']:.2%}" if item["risk_used_pct"] is not None else "-"
        window = "abierta" if item["session_open"] else ("cerrada" if item["session_open"] is False else "24h")
        table.add_row(
            name, str(item["magic"]), risk, trades, str(item["open_count"]),
            f"{item['pnl_today']:+.2f}",
            f"{item['stop_remaining_usd']:.2f}"
            + (" (tocado)" if item["stop_hit"] else ""),
            window,
        )
    console.print(table)
    global_data = data["global"]
    console.print(
        f"Global: {global_data['open_count']}/{global_data['max_open_total']} abiertas · "
        f"PnL {global_data['pnl_today']:+.2f} · stop restante "
        f"{global_data['stop_remaining_usd']:.2f} USD"
        + (" · TOCADO" if global_data["stop_hit"] else "")
    )
    if global_data["positions"]:
        pos_table = Table(title="Posiciones del carril")
        for column in ("Ticket", "Símbolo", "Lado", "Volumen", "PnL", "Magic"):
            pos_table.add_column(column)
        for position in global_data["positions"]:
            pos_table.add_row(
                str(position["ticket"]), str(position["symbol"]),
                str(position["side"]), f"{position['volume']:g}",
                f"{position['profit']:+.2f}", str(position["magic"]),
            )
        console.print(pos_table)


@ai_trader_app.command("manage")
def ai_trader_manage_cmd() -> None:
    """Trailing de las posiciones del carril y sincronización de cierres."""
    from .ai_trader import AiTraderError, manage

    settings = get_settings()
    broker = _mt5(settings, dry_run=False)
    try:
        rows = manage(broker=broker, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    finally:
        broker.shutdown()
    if not rows:
        console.print("Sin posiciones del carril.")
        return
    table = Table(title="IA discrecional · manage")
    for column in ("Ticket", "Estilo", "Símbolo", "Lado", "R", "SL", "Nuevo SL", "Cierre"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["ticket"]),
            str(row.get("style") or "-"),
            str(row["symbol"]),
            str(row["side"]),
            f"{row['profit_r']:+.2f}" if row.get("profit_r") is not None else "-",
            f"{row['sl']:.5f}",
            f"{row['new_sl']:.5f}" if row["new_sl"] is not None else "-",
            str(row.get("closed") or row.get("close_error") or "-"),
        )
    console.print(table)


@ai_trader_app.command("scoreboard")
def ai_trader_scoreboard_cmd() -> None:
    """Real vs sombra por estrategia × símbolo × timeframe."""
    from .ai_trader import AiTraderError, scoreboard

    settings = get_settings()
    broker = _mt5(settings, dry_run=True)
    try:
        data = scoreboard(broker=broker, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    finally:
        broker.shutdown()
    cells = data["cells"]
    table = Table(title="IA discrecional · scoreboard")
    for column in ("Estilo", "Estrategia", "Símbolo", "TF", "Versión", "N", "Hit",
                   "R medio", "IC 90%", "Coste/R", "Slippage", "Δ sombra",
                   "Δ sin plan", "Estado", "Celda"):
        table.add_column(column)
    for cell in cells:
        ci = cell.get("ci90_r")
        ci_text = f"[{ci[0]:+.2f}, {ci[1]:+.2f}]" if ci else "-"
        shadow = cell.get("shadow") or {}
        diff = shadow.get("diff")
        dci = shadow.get("ci90")
        diff_text = (
            f"{diff:+.3f} [{dci[0]:+.2f}, {dci[1]:+.2f}]"
            if diff is not None and dci else "-"
        )
        noplan = cell.get("noplan") or {}
        ndiff = noplan.get("diff")
        nci = noplan.get("ci90")
        noplan_text = (
            f"{ndiff:+.3f} [{nci[0]:+.2f}, {nci[1]:+.2f}]"
            if ndiff is not None and nci else "-"
        )
        table.add_row(
            str(cell.get("style") or "-"),
            str(cell["strategy"]),
            str(cell["symbol"]),
            str(cell["timeframe"]),
            str(cell.get("playbook_version") or "-"),
            str(cell["n"]),
            f"{cell['hit']:.0%}" if cell["hit"] is not None else "-",
            f"{cell['avg_r']:+.3f}" if cell["avg_r"] is not None else "-",
            ci_text,
            f"{cell['cost_ratio_avg']:.3f}" if cell["cost_ratio_avg"] is not None else "-",
            f"{cell['slippage_avg']:.1f} bps" if cell["slippage_avg"] is not None else "Sin datos",
            diff_text,
            noplan_text,
            {
                "winner": "ganadora",
                "loser": "perdedora",
                "neutral": "neutral",
                "exploring": "explorando",
            }.get(str(cell["state"]), str(cell["state"])),
            {
                "paused": "pausada",
                "destilada": "destilada",
            }.get(str(cell["cell_status"]), "activa"),
        )
    console.print(table)
    if any(cell["insufficient"] for cell in cells):
        console.print("[yellow]muestra insuficiente: n<30 en alguna celda[/yellow]")


@ai_trader_app.command("learn")
def ai_trader_learn_cmd(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Muestra candidatos sin aplicar ni escribir"
    ),
) -> None:
    """Aprendizaje diario: solo cambios que reducen riesgo, con límite semanal."""
    from .ai_learn import LearnError, learn

    try:
        result = learn(apply=not dry_run, db_path=DEFAULT_DB)
    except LearnError as exc:
        _ai_trader_error(exc)
    typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


@ai_trader_app.command("distill")
def ai_trader_distill_cmd(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Aprende filtros sin validar ni escribir"
    ),
    no_validate: bool = typer.Option(
        False, "--no-validate", help="No corre el embudo de validación"
    ),
) -> None:
    """Destilación semanal: filtro legible, candidato enabled:false e incubación."""
    from .ai_distill import DistillError, distill

    try:
        result = distill(
            apply=not dry_run, validate=not no_validate, db_path=DEFAULT_DB,
        )
    except DistillError as exc:
        _ai_trader_error(exc)
    typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


@ai_trader_app.command("replay")
def ai_trader_replay_cmd(
    style: str = typer.Option(..., "--style", help="intraday o swing"),
    n: int = typer.Option(200, "--n", min=1, help="Decisiones a pedir"),
    strategy: str = typer.Option(None, "--strategy", help="Filtra una estrategia"),
    symbol: str = typer.Option(None, "--symbol", help="Filtra un símbolo"),
    yes: bool = typer.Option(False, "--yes", help="Confirma la ejecución"),
) -> None:
    """Replay ciego de setups históricos anteriores al corte de la campaña."""
    from .ai_replay import ReplayError, prepare_replay, run_replay

    try:
        plan = prepare_replay(style, n=n, strategy=strategy, symbol=symbol)
    except ReplayError as exc:
        _ai_trader_error(exc)
    typer.echo(json.dumps(plan.summary(), ensure_ascii=False, separators=(",", ":")))
    if not yes:
        console.print("[yellow]Replay no ejecutado: falta --yes.[/yellow]")
        return
    try:
        result = run_replay(plan, yes=True, db_path=DEFAULT_DB)
    except ReplayError as exc:
        _ai_trader_error(exc)
    typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


@ai_trader_app.command("resume")
def ai_trader_resume_cmd(
    strategy: str = typer.Option(..., "--strategy"),
    symbol: str = typer.Option(..., "--symbol"),
    timeframe: str = typer.Option(..., "--timeframe"),
) -> None:
    """Reactiva una celda pausada por el scoreboard (decisión del operador)."""
    from .ai_trader import AiTraderError, resume_cell

    try:
        resume_cell(strategy, symbol, timeframe, db_path=DEFAULT_DB)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    console.print(f"[green]Celda reactivada[/green] {strategy} · {symbol} · {timeframe}")


@ai_trader_app.command("review")
def ai_trader_review_cmd(
    days: int = typer.Option(7, "--days", min=1),
) -> None:
    """Informe semanal y lecciones propuestas (no cambia el playbook)."""
    from .ai_trader import AiTraderError, review

    try:
        result = review(db_path=DEFAULT_DB, days=days)
    except AiTraderError as exc:
        _ai_trader_error(exc)
    console.print(f"Informe: {result['path']}")
    console.print(f"Operaciones cerradas: {result['n']}")
    for lesson in result["lessons"]:
        console.print(
            f"[yellow]Lección propuesta[/yellow] #{lesson['id']}: "
            f"{lesson['hypothesis'][:160]}"
        )


@ai_trader_app.command("approve-lesson")
def ai_trader_approve_lesson_cmd(
    lesson_id: int = typer.Argument(..., help="ID de la lección"),
) -> None:
    """Aprueba una lección y sube playbook_version (decisión del operador)."""
    from .ai_trader import AiTraderError, approve_lesson

    try:
        result = approve_lesson(lesson_id, db_path=DEFAULT_DB)
    except Exception as exc:
        _ai_trader_error(AiTraderError(str(exc)))
    console.print(
        f"[green]Lección {lesson_id} aprobada[/green] · "
        f"playbook v{result['playbook_version']}"
    )


@ai_trader_app.command("no-trade")
def ai_trader_no_trade_cmd(
    reason: str = typer.Option(..., "--reason", help="Motivo de no operar"),
    symbols: str = typer.Option(None, "--symbols", help="Símbolos afectados, separados por comas"),
) -> None:
    """Registra una decisión de no operar (también es una decisión)."""
    from .ai_trader import AiTraderError, log_no_trade

    try:
        log_no_trade(
            reason,
            symbols=[s.strip() for s in symbols.split(",") if s.strip()] if symbols else None,
            db_path=DEFAULT_DB,
        )
    except AiTraderError as exc:
        _ai_trader_error(exc)
    console.print(f"[green]Decisión registrada[/green] · no operar: {reason[:120]}")


def main() -> None:
    app()


@costs_app.command("swap-sync")
def costs_swap_sync_cmd(
    write: bool = typer.Option(
        False, "--write", help="Actualiza solo el bloque swap de costs.yaml"
    ),
    symbols: str = typer.Option(
        None, "--symbols", help="Lista separada por comas; por defecto, costs.yaml"
    ),
) -> None:
    """Lee swap_long/swap_short de MT5; dry-run por defecto. No envía órdenes."""
    from .lease import acquire, release
    from .swap_sync import sync_swaps

    requested = (
        [item.strip().upper() for item in symbols.split(",") if item.strip()]
        if symbols
        else None
    )
    lease = acquire(
        DEFAULT_DB, session="costs:swap-sync", ttl_seconds=60
    )
    if not lease["ok"]:
        console.print(f"[red]Lease ocupado:[/red] {lease['reason']}")
        raise typer.Exit(2)
    try:
        try:
            payload = sync_swaps(
                db_path=DEFAULT_DB,
                write=write,
                symbols=requested,
            )
        except Exception as exc:
            console.print(
                f"[yellow]Sin datos:[/yellow] MT5 no respondió ({exc}); "
                "no se escribió costs.yaml."
            )
            raise typer.Exit(2) from exc
    finally:
        release(DEFAULT_DB)

    table = Table(title="Swap · MT5 → costs.yaml")
    for column in (
        "Símbolo", "Long", "Short", "Unidad", "Triple", "Modo", "Estado"
    ):
        table.add_column(column)
    for symbol, item in sorted(payload["symbols"].items()):
        table.add_row(
            symbol,
            f"{item['long']:+.4f}",
            f"{item['short']:+.4f}",
            item["unit"],
            item.get("triple_name", str(item["triple_swap_weekday"])),
            str(item["swap_mode"]),
            item["mode_label"],
        )
    for symbol, item in sorted(payload["skipped"].items()):
        table.add_row(
            symbol, "Sin datos", "Sin datos", "—", "—",
            str(item.get("swap_mode", "—")),
            item.get("reason", item.get("status", "no_soportado")),
        )
    console.print(table)
    console.print(
        f"Leídos: {payload['n_read']} · omitidos: {payload['n_skipped']} · "
        f"{'escrito' if payload['written'] else 'dry-run'}"
    )
    if write and not payload["written"]:
        console.print("[yellow]Nada que escribir: no hay símbolos soportados.[/yellow]")


@stats_app.command("recompute-dsr")
def stats_recompute_dsr_cmd(
    dry_run: bool = typer.Option(
        True, "--dry-run", help="Solo informe; no escribe en SQLite"
    ),
) -> None:
    """Recalcula el DSR v2 del historial sin ejecutar backtests."""
    if not dry_run:
        console.print(
            "[yellow]--write no está implementado en este bloque; "
            "solo se permite --dry-run.[/yellow]"
        )
        raise typer.Exit(2)
    from .dsr_recompute import build_report, write_report

    payload = build_report(DEFAULT_DB)
    files = write_report(payload)
    table = Table(title="DSR v2 · historial")
    table.add_column("Entidad")
    table.add_column("V1", justify="right")
    table.add_column("Local", justify="right")
    table.add_column("Global", justify="right")
    table.add_column("N", justify="right")
    table.add_column("Sharpes", justify="right")
    for row in payload["rows"]:
        def _fmt(value):
            return "Sin datos" if value is None else f"{float(value):.4f}"

        table.add_row(
            row["entity"],
            _fmt(row["dsr_v1"]),
            _fmt(row["dsr_local"]),
            _fmt(row["dsr_global"]),
            str(row["n_trials"]),
            str(row["n_sharpes"]),
        )
    console.print(table)
    console.print(
        f"[dim]JSON: {files['json']} · MD: {files['markdown']} · "
        f"N={payload['n_trials']} · {payload['n_sharpes']} Sharpes[/dim]"
    )


@discovery_app.command("data-check")
def discovery_data_check_cmd(
    symbol: str = typer.Argument(..., help="Símbolo CFD, p. ej. US100.cash"),
    tf: str = typer.Option("M5", "--tf", help="Timeframe"),
    source: str = typer.Option(
        "broker", "--source", help="broker | dukascopy"
    ),
    all_tf: bool = typer.Option(
        False, "--all-tf", help="Matriz de las 7 temporalidades"
    ),
    is_range: str = typer.Option(
        None,
        "--is",
        help="Tramo IS como inicio:fin (por defecto, engine.yaml)",
    ),
    oos1_range: str = typer.Option(
        None,
        "--oos1",
        help="Tramo OOS-1 como inicio:fin (por defecto, engine.yaml)",
    ),
    oos2_range: str = typer.Option(
        None,
        "--oos2",
        help="Tramo OOS-2 como inicio:fin; fin vacío = última vela",
    ),
) -> None:
    """Informe de calidad por fuente y temporalidad. Solo lectura."""
    from .discovery.source_quality import quality_for_source, quality_matrix

    def _range(value: str, name: str):
        start, _, end = str(value or "").partition(":")
        if not start:
            raise typer.BadParameter(f"{name}: falta la fecha de inicio")
        return (start, end or None)

    segments = {}
    for name, value in (("is", is_range), ("oos1", oos1_range), ("oos2", oos2_range)):
        if value:
            segments[name] = _range(value, f"--{name}")

    if all_tf:
        rows = quality_matrix(
            symbol,
            source=source,
            segments=segments or None,
        )
        matrix = Table(
            title=f"Discovery · calidad · {symbol.upper()} · {source.lower()} · 7 TF"
        )
        for column in (
            "TF",
            "Estado",
            "Filas",
            "Inicio útil",
            "Huecos",
            "Pausa",
            "Calendario",
            "Sesiones sin datos",
        ):
            matrix.add_column(column)
        for data in rows:
            pauses = data.get("scheduled_pauses") or []
            matrix.add_row(
                data["timeframe"],
                data["status"].upper(),
                f"{data['rows']:,}",
                (data.get("granularity") or {}).get("useful_start") or "Sin datos",
                str(data.get("non_scheduled_gaps", 0)),
                (
                    f"{pauses[0]['start_hhmm']} ({pauses[0]['count']}×)"
                    if pauses
                    else "ninguna"
                ),
                (data.get("calendar") or {}).get("name") or "sin calendario",
                str(data.get("missing_weekdays", 0)),
            )
        console.print(matrix)
        if all(data["status"] == "fail" for data in rows):
            raise typer.Exit(1)
        return

    data = quality_for_source(
        symbol,
        tf,
        source=source,
        segments=segments or None,
    )

    summary = Table(title=f"Discovery · calidad de datos · {data['symbol']} {data['timeframe']}")
    summary.add_column("Campo", style="bold")
    summary.add_column("Valor")
    summary.add_row("Estado", data["status"].upper())
    summary.add_row("Filas", f"{data['rows']:,}")
    summary.add_row("Inicio", data["start"] or "Sin datos")
    summary.add_row("Fin", data["end"] or "Sin datos")
    summary.add_row(
        "Inicio útil",
        (data.get("granularity") or {}).get("useful_start") or "Sin datos",
    )
    summary.add_row("Hash", data["dataset_hash"][:16] + "…" if data["dataset_hash"] else "Sin datos")
    summary.add_row("Huecos no programados", str(data["non_scheduled_gaps"]))
    thresholds = data.get("gap_thresholds") or {}
    gap_pct = thresholds.get("gap_pct")
    summary.add_row(
        "Huecos no programados (%)",
        f"{float(gap_pct) * 100.0:.3f}%" if gap_pct is not None else "Sin datos",
    )
    pauses = data.get("scheduled_pauses") or []
    summary.add_row(
        "Pausa detectada",
        (
            f"{pauses[0]['start_hhmm']} ({pauses[0]['count']}×)"
            if pauses
            else "ninguna"
        ),
    )
    summary.add_row("Zona de pausa", str(thresholds.get("pause_tz") or "Sin datos"))
    summary.add_row(
        "Calendario",
        (data.get("calendar") or {}).get("name") or "sin calendario",
    )
    summary.add_row(
        "Huecos de calendario",
        str(len(data.get("calendar_gaps") or [])),
    )
    source_info = data.get("source") or {}
    summary.add_row(
        "Fuente",
        f"{data.get('source_name') or source_info.get('source') or 'Sin datos'} · "
        f"{source_info.get('path') or 'Sin datos'}",
    )
    summary.add_row(
        "Zona fuente / ajustes",
        f"{source_info.get('timezone') or 'Sin datos'} · "
        f"{source_info.get('adjusted', 0)} ajustadas · {source_info.get('dropped', 0)} descartadas",
    )
    summary.add_row(
        "Sesiones sin datos",
        str(data.get("missing_weekdays", 0)),
    )
    bad_months = (data.get("granularity") or {}).get("bad_months") or []
    summary.add_row(
        "Meses no homogéneos",
        ", ".join(item["month"] for item in bad_months[:6]) + ("…" if len(bad_months) > 6 else "")
        if bad_months
        else "ninguno",
    )
    console.print(summary)

    segment_table = Table(title="Tramos IS / OOS-1 / OOS-2 (solo cobertura)")
    for column in ("Tramo", "Filas", "Inicio", "Fin", "Cobertura", "Sellado"):
        segment_table.add_column(column)
    for name, item in data["segments"].items():
        segment_table.add_row(
            name,
            f"{item['rows']:,}",
            item["start"] or "Sin datos",
            item["end"] or "Sin datos",
            "Sin datos" if item["coverage_pct"] is None else f"{item['coverage_pct']:.1f}%",
            "sí" if item["sealed"] else "no",
        )
    console.print(segment_table)

    if data["scheduled_pauses"]:
        pauses = Table(title="Pausas programadas (hora local de sesión)")
        pauses.add_column("Hora local")
        pauses.add_column("Veces", justify="right")
        pauses.add_column("Minutos", justify="right")
        for item in data["scheduled_pauses"]:
            pauses.add_row(
                item["start_hhmm"],
                str(item["count"]),
                f"{item['minutes']:.1f}",
            )
        console.print(pauses)

    if data["issues"]:
        console.print("[bold]Motivos[/bold]")
        for issue in data["issues"]:
            console.print(f"- {issue}")
    if data["status"] == "fail":
        raise typer.Exit(1)


@discovery_app.command("fetch-dukascopy")
def discovery_fetch_dukascopy_cmd(
    symbol: str = typer.Argument(
        ...,
        help="US100 | US500 | US30 | XAUUSD | EURUSD | GBPUSD | USDJPY",
    ),
    start: str = typer.Option(
        None,
        "--from",
        help="Inicio UTC (YYYY-MM-DD); por defecto, el inicio real del símbolo",
    ),
    end: str = typer.Option(
        None, "--to", help="Fin UTC (YYYY-MM-DD); por defecto, ayer"
    ),
    workers: int = typer.Option(4, "--workers", help="Descargas en paralelo"),
    rate: float = typer.Option(5.0, "--rate", help="Peticiones por segundo"),
    no_ask: bool = typer.Option(False, "--no-ask", help="No descargar ASK"),
    force: bool = typer.Option(False, "--force", help="Rehacer meses ya cacheados"),
) -> None:
    """Descarga M1 de Dukascopy y escribe SOLO la caché M1 (UTC)."""
    from .discovery import fetch_dukascopy

    if int(workers) < 1:
        raise typer.BadParameter("--workers debe ser >= 1")
    if float(rate) < 0:
        raise typer.BadParameter("--rate debe ser >= 0")

    def _progress(item: dict) -> None:
        console.print(
            f"[dim]{item['month']}: {item['rows']:,} velas · "
            f"{item['empty_days']} días sin datos[/dim]"
        )

    try:
        result = fetch_dukascopy.download(
            symbol,
            start=start,
            end=end,
            workers=int(workers),
            rate_per_s=float(rate),
            include_ask=not no_ask,
            force=force,
            progress=_progress,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Dukascopy no disponible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(
        title=f"Discovery · Dukascopy · {result['symbol']} M1 "
        f"({result['instrument']})"
    )
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Filas", f"{result['rows']:,}")
    table.add_row("Filas con ASK", f"{result['ask_rows']:,}")
    table.add_row("Inicio UTC", result["start"])
    table.add_row("Fin UTC", result["end"])
    table.add_row("Meses descargados", str(result["months_fetched"]))
    table.add_row("Meses saltados", str(result["months_skipped"]))
    table.add_row("Días sin datos", str(result["empty_days"]))
    table.add_row("Ruta", result["path"])
    console.print(table)


@discovery_app.command("derive-sessions")
def discovery_derive_sessions_cmd(
    symbol: str = typer.Argument(..., help="US100 | US500 | US30 | XAUUSD | EURUSD | GBPUSD | USDJPY"),
    source: str = typer.Option("dukascopy", "--source", help="dukascopy | broker"),
    start_year: int = typer.Option(None, "--start-year"),
    end_year: int = typer.Option(2026, "--end-year"),
) -> None:
    """Deriva por año la moda semanal del horario de sesión (solo lectura)."""
    from .discovery import sessions

    try:
        result = sessions.derive_sessions(
            symbol,
            source,
            start_year=start_year,
            end_year=int(end_year),
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]No se pudo derivar:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(
        title=f"Discovery · sesiones · {result['symbol']} · {result['source']}"
    )
    for column in ("Año", "Viernes", "%", "Domingo", "%", "Pausa", "%", "Corta", "%", "Estado"):
        table.add_column(column)
    for year in result["years"]:
        if year.reasons == ["sin datos"]:
            table.add_row(str(year.year), "Sin datos", "", "", "", "", "", "", "", "SIN DATOS")
            continue
        table.add_row(
            str(year.year),
            year.friday_close or "—",
            f"{year.friday_share:.0%}" if year.friday_share is not None else "—",
            year.sunday_open or "—",
            f"{year.sunday_share:.0%}" if year.sunday_share is not None else "—",
            f"{year.pause_start}→{year.pause_end}" if year.pause_start else "—",
            f"{year.pause_share:.0%}" if year.pause_share is not None else "—",
            year.short_close or "—",
            f"{year.short_share:.0%}" if year.short_share is not None else "—",
            "ESTABLE" if year.stable else "INESTABLE: " + "; ".join(year.reasons),
        )
    console.print(table)
    console.print(sessions.yaml_block(result))
    if not result["stable"]:
        console.print("[yellow]Símbolo/fuente inestable: no escribir en engine.yaml.[/yellow]")
        raise typer.Exit(1)


@discovery_app.command("usable-from")
def discovery_usable_from_cmd(
    source: str = typer.Option(None, "--source", help="dukascopy | broker"),
    symbol: str = typer.Option(None, "--symbol", help="Símbolo; vacío = los 7"),
    tf: str = typer.Option(None, "--tf", help="Timeframe; vacío = todos"),
    write: bool = typer.Option(
        False, "--write", help="Escribe data_quality.usable_from en engine.yaml"
    ),
) -> None:
    """Primera fecha usable por fuente:símbolo:TF (historia recortada no FAIL)."""
    from .discovery import usability

    sources = (
        (str(source).strip().lower(),)
        if source
        else usability.SOURCES
    )
    symbols = (
        (str(symbol).strip().upper(),) if symbol else usability.SYMBOLS
    )
    timeframes = (
        (str(tf).strip().upper(),) if tf else usability.TIMEFRAMES
    )
    try:
        results = usability.compute_all(
            sources=sources, symbols=symbols, timeframes=timeframes
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]No se pudo calcular usable_from:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title="Discovery · usable_from")
    for column in ("Clave", "Desde", "Estado", "Huecos", "Año", "Motivo"):
        table.add_column(column)
    for key, item in sorted(results.items()):
        table.add_row(
            key,
            item.get("date") or "—",
            str(item.get("status") or "fail").upper(),
            str(item.get("gaps", 0)),
            str(item.get("year") or "—"),
            item.get("reason") or "",
        )
    console.print(table)
    console.print(usability.yaml_block(results))
    if write:
        path = usability.write_usable_from(results)
        console.print(f"[green]Escrito:[/green] {path}")
    else:
        console.print("[yellow]Sin --write no se escribe engine.yaml.[/yellow]")


@discovery_app.command("compare-dukascopy")
def discovery_compare_dukascopy_cmd(
    symbol: str = typer.Argument(
        None, help="Símbolo; vacío = los 7"
    ),
    start: str = typer.Option("2021-10-01", "--from", help="Inicio UTC"),
    end: str = typer.Option(None, "--to", help="Fin UTC; vacío = última vela"),
    tf: str = typer.Option("M5", "--tf", help="Temporalidad de comparación"),
) -> None:
    """Compara Dukascopy con el bróker; no usa campañas ni OOS."""
    from .discovery import compare

    try:
        rows = compare.compare_all(
            [symbol] if symbol else None,
            start=start,
            end=end,
            timeframe=tf,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Comparación no disponible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"Discovery · Dukascopy vs bróker · {tf.upper()}")
    for column in (
        "Símbolo",
        "Velas",
        "Corr",
        "Δnivel",
        "Δnivel bps",
        "Lag",
        "Coincidencia",
        "Veredicto",
    ):
        table.add_column(column)
    for row in rows:
        table.add_row(
            row["symbol"],
            f"{row['rows']:,}",
            "Sin datos" if row["correlation"] is None else f"{row['correlation']:.4f}",
            "Sin datos" if row["mean_diff"] is None else f"{row['mean_diff']:+.5f}",
            "Sin datos" if row["mean_diff_bps"] is None else f"{row['mean_diff_bps']:+.2f}",
            "Sin datos" if row["lag"] is None else f"{row['lag']:+d}",
            "Sin datos" if row["match_pct"] is None else f"{row['match_pct']:.1f}%",
            row["verdict"],
        )
    console.print(table)
    console.print(
        "[dim]Lag +1 = Dukascopy va una vela por detrás del bróker; "
        "criterio: corr ≥ 0,95 y lag 0.[/dim]"
    )
    for row in rows:
        if row["verdict"] != "apta":
            console.print(f"[yellow]{row['symbol']}:[/yellow] {row['reason']}")


@discovery_app.command("fetch")
def discovery_fetch_cmd(
    symbol: str = typer.Argument(..., help="Símbolo CFD, p. ej. EURUSD"),
    account: str = typer.Option("CFD-001", "--account", help="Cuenta Prop Fund"),
    tf: str = typer.Option("M5", "--tf", help="Timeframe a descargar"),
    start: str = typer.Option("2021-09-01", "--start", help="Inicio UTC"),
    end: str = typer.Option(None, "--end", help="Fin UTC (por defecto, ahora)"),
    block_days: int = typer.Option(90, "--block-days", help="Días por bloque"),
) -> None:
    """Descarga M5 por cuenta desde el terminal MT5 adjunto (solo lectura)."""

    from .discovery import fetch

    try:
        result = fetch.download(
            symbol,
            account=account,
            timeframe=tf,
            start=start,
            end=end,
            block_days=int(block_days),
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Fetch no disponible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"Discovery · fetch {result['symbol']} {result['timeframe']}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Cuenta", result["account"])
    table.add_row("Símbolo bróker", result["broker_symbol"])
    table.add_row("Filas", f"{result['rows']:,}")
    table.add_row("Inicio UTC", result["start"])
    table.add_row("Fin UTC", result["end"])
    table.add_row("Ruta", result["path"])
    console.print(table)


@discovery_app.command("register")
def discovery_register_cmd(
    instrument: str = typer.Option("US100", "--instrument", help="Instrumento canónico"),
    tf: str = typer.Option("M5", "--tf", help="Timeframe"),
    template: str = typer.Option(
        "ny_open_vol_filter", "--template", help="Plantilla de config/discovery/templates"
    ),
    profile: str = typer.Option("small", "--profile", help="small | medium | large"),
    mode: str = typer.Option("ga", "--mode", help="ga | grid"),
    data_source: str = typer.Option(
        "broker", "--source", help="Fuente única de la campaña: broker | dukascopy"
    ),
    is_range: str = typer.Option(None, "--is", help="IS como inicio:fin"),
    oos1_range: str = typer.Option(None, "--oos1", help="OOS-1 como inicio:fin"),
    oos2_range: str = typer.Option(None, "--oos2", help="OOS-2 como inicio:fin (fin vacío = última vela)"),
    seed: int = typer.Option(0, "--seed"),
    campaign_id: str = typer.Option(None, "--campaign-id"),
    spec: str = typer.Option(
        None, "--spec", help="Especificación YAML (incluye grid y segmentos)"
    ),
    cost_account: list[str] = typer.Option(
        None,
        "--cost-account",
        help="Cuenta de coste; repetible. Por defecto, todas las CFD no plantilla",
    ),
    cost_mode: str = typer.Option(
        "best", "--cost-mode", help="best | worst | target"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Previsualiza sin escribir"),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Registra un BORRADOR de campaña; no cuenta hasta aprobarlo."""

    from .discovery import campaigns
    from .discovery.config import load_engine_config

    def _range(value: str, name: str) -> list[str | None]:
        start, _, end = str(value or "").partition(":")
        if not start:
            raise typer.BadParameter(f"{name}: falta la fecha de inicio")
        return [start, end or None]

    defaults = load_engine_config().data_quality.default_segments
    segments: dict[str, list[str | None]] = {
        name: [value[0], value[1]] for name, value in defaults.items()
    }
    for name, value in (("is", is_range), ("oos1", oos1_range), ("oos2", oos2_range)):
        if value:
            segments[name] = _range(value, f"--{name}")

    try:
        if spec:
            campaign = campaigns.register_from_spec(
                spec, dry_run=dry_run, db_path=db
            )
            data_source = str(
                (campaign.get("config") or {}).get("data_source") or data_source
            )
        else:
            campaign = campaigns.register(
                instrument,
                tf,
                template,
                profile,
                segments=segments,
                seed=seed,
                campaign_id=campaign_id,
                mode=mode,
                data_source=data_source,
                cost_accounts=cost_account,
                cost_mode=cost_mode,
                dry_run=dry_run,
                db_path=db,
            )
    except campaigns.CampaignError as exc:
        console.print(f"[red]Rechazada:[/red] {exc}")
        raise typer.Exit(1) from exc

    table = Table(title=f"Discovery · registro · {campaign['campaign_id']}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Estado", "BORRADOR (no cuenta)" if not dry_run else "DRY-RUN (no escribe)")
    table.add_row("Fuente", str((campaign.get("config") or {}).get("data_source") or data_source))
    table.add_row("n_total", f"{campaign['n_total']:,} pruebas")
    table.add_row("dataset_hash", campaign["dataset_hash"][:16] + "…")
    table.add_row("Snapshot", str(campaign.get("snapshot_path") or "Sin datos"))
    table.add_row("config_hash", campaign["config_hash"][:16] + "…")
    cost_config = (campaign.get("config") or {}).get("cost") or {}
    table.add_row(
        "Coste",
        f"{cost_config.get('mode', 'target')} · "
        f"{', '.join(cost_config.get('accounts') or []) or cost_config.get('account') or 'Sin datos'}",
    )
    slippage = cost_config.get("assumed_slippage") or {}
    table.add_row(
        "Slippage asumido",
        f"{slippage.get('value', 'Sin datos')} ({slippage.get('source', 'Sin datos')})",
    )
    table.add_row("OOS-2 fin real", campaign.get("oos2_end") or "Sin datos")
    table.add_row(
        "Calidad",
        f"{(campaign.get('quality') or {}).get('status', 'Sin datos')} · "
        f"inicio útil {(campaign.get('quality') or {}).get('useful_start') or 'Sin datos'}",
    )
    console.print(table)
    console.print(
        "Para que cuente en el DSR: "
        f"lab discovery approve {campaign['campaign_id']} --approved-by-operator"
    )


@discovery_app.command("preflight")
def discovery_preflight_cmd(
    campaign_id: str = typer.Argument(None, help="ID de la campaña"),
    spec: str = typer.Option(
        None, "--spec", help="Especificación YAML; no registra campaña"
    ),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Solo inicialización: sin backtests ni OOS. Falla si faltan válidos."""

    from .discovery import engine

    if bool(campaign_id) == bool(spec):
        console.print("[red]Indica campaign_id o --spec (uno solo).[/red]")
        raise typer.Exit(2)
    try:
        if spec:
            report = engine.preflight_spec(spec)
            label = f"spec {spec}"
        else:
            report = engine.preflight(campaign_id, db_path=db)
            label = str(campaign_id)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Preflight imposible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"Discovery · preflight {label}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Estado", str(report["status"]))
    table.add_row("Instrumento", f"{report['instrument']} {report['timeframe']}")
    table.add_row("Plantilla", str(report["template"]))
    table.add_row("Semilla", str(report["seed"]))
    table.add_row("Población", str(report["population"]))
    table.add_row("Generados", str(report["generated"]))
    table.add_row("Válidos", str(report["valid"]))
    table.add_row("Rechazados", str(report["rejected"]))
    table.add_row("Duplicadas", str(report.get("duplicates", 0)))
    if report.get("last_error"):
        table.add_row("Último error", str(report["last_error"]))
    console.print(table)
    for reason, count in sorted(
        report["reasons"].items(), key=lambda item: (-item[1], item[0])
    ):
        console.print(f"  {count:4d}  {reason}")
    if int(report["valid"]) < int(report["population"]):
        console.print(
            f"[red]Preflight FAIL:[/red] {report['valid']} válidos < "
            f"población {report['population']}."
        )
        raise typer.Exit(1)
    console.print(
        f"[green]Preflight OK:[/green] {report['valid']} válidos "
        f"para población {report['population']}."
    )


@discovery_app.command("feasibility")
def discovery_feasibility_cmd(
    campaign_id: str = typer.Argument(None, help="ID del borrador de campaña"),
    spec: str = typer.Option(
        None, "--spec", help="Especificación YAML; no registra campaña"
    ),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Viabilidad sin PnL: operaciones, pliegues, coste_R y tiempo. No suma al DSR."""

    from .discovery import feasibility

    if bool(campaign_id) == bool(spec):
        console.print("[red]Indica campaign_id o --spec (uno solo).[/red]")
        raise typer.Exit(2)
    try:
        if spec:
            report = feasibility.check_spec(spec)
            label = f"spec {spec}"
        else:
            report = feasibility.check(campaign_id, db_path=db)
            label = str(campaign_id)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Feasibility imposible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"Discovery · feasibility {label}")
    table.add_column("#", justify="right")
    table.add_column("Combinación")
    table.add_column("Ops IS", justify="right")
    table.add_column("Ops/pliegue")
    table.add_column("Cost_R", justify="right")
    table.add_column("Coste por cuenta (sí/no)")
    table.add_column("Más barata")
    table.add_column("Elegida")
    table.add_column("Peor")
    table.add_column("Velas", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("¿Factible?")
    table.add_column("Motivo")
    for row in report["rows"]:
        by_account = row.get("cost_by_account") or {}
        viability = row.get("cost_viable_by_account") or {}
        cost_text = " · ".join(
            f"{name} {'Sin datos' if value is None else f'{float(value):.4f}'} "
            f"({'sí' if viability.get(name) else 'no' if viability.get(name) is False else 'Sin datos'})"
            for name, value in by_account.items()
        ) or "Sin datos"
        best = row.get("best_account") or "Sin datos"
        best_share = row.get("best_share")
        if best_share is not None and row.get("best_account"):
            best = f"{best} ({float(best_share) * 100:.0f} %)"
        selected = row.get("selected_account") or "Sin datos"
        selected_share = row.get("selected_share")
        if selected_share is not None and row.get("selected_account"):
            selected = f"{selected} ({float(selected_share) * 100:.0f} %)"
        worst = row.get("worst_account") or "Sin datos"
        share = row.get("worst_share")
        if share is not None and row.get("worst_account"):
            worst = f"{worst} ({float(share) * 100:.0f} %)"
        table.add_row(
            str(int(row["index"]) + 1),
            str(row["label"]),
            str(int(row["trades_is"])),
            "/".join(str(int(value)) for value in row["fold_trades"]) or "Sin datos",
            "Sin datos"
            if row["cost_r"] is None
            else f"{float(row['cost_r']):.4f}",
            cost_text,
            best,
            selected,
            worst,
            f"{float(row['mean_bars']):.2f}",
            f"{float(row['mean_minutes']):.0f}",
            "sí" if row["feasible"] else "NO",
            "; ".join(row["reasons"]) or "",
        )
    console.print(table)
    console.print(
        f"Factibles {report['n_feasible']}/{report['n_checked']} "
        f"({report['feasible_pct']:.1f} %) · gate ≥{feasibility.MIN_FEASIBLE_PCT:.0f} %: "
        f"{'PASA' if report['passes'] else 'FALLA'}"
    )
    if not report["passes"]:
        raise typer.Exit(1)


@discovery_app.command("feasibility-scan")
def discovery_feasibility_scan_cmd(
    template: str = typer.Argument(
        ..., help="Plantilla de config/discovery/templates"
    ),
    symbol: str = typer.Argument(..., help="Símbolo canónico, p. ej. US100"),
    source: str = typer.Option(
        "dukascopy", "--source", help="Fuente única: broker | dukascopy"
    ),
    account: str = typer.Option(
        "CFD-001", "--account", help="Cuenta para cost_R"
    ),
    is_range: str = typer.Option(
        None, "--is", help="Tramo IS como inicio:fin (por defecto, engine.yaml)"
    ),
) -> None:
    """TF × factibilidad: solo operaciones y cost_R. Sin PnL ni DSR."""

    from .discovery import feasibility

    selected = None
    if is_range:
        start, _, end = str(is_range).partition(":")
        if not start:
            raise typer.BadParameter("--is necesita inicio:fin")
        selected = (start, end or None)
    try:
        report = feasibility.scan(
            template,
            symbol,
            source=source,
            account=account,
            is_range=selected,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Feasibility-scan imposible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(
        title=(
            f"Discovery · feasibility-scan · {template} · {symbol.upper()} · "
            f"{report['source']}"
        )
    )
    table.add_column("TF")
    table.add_column("Estado")
    table.add_column("Estrategias", justify="right")
    table.add_column("Ops IS", justify="right")
    table.add_column("Ops/pliegue")
    table.add_column("Cost_R", justify="right")
    table.add_column("Velas", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("¿Factible?")
    table.add_column("Motivo")
    for row in report["timeframes"]:
        table.add_row(
            str(row["timeframe"]),
            str(row["status"]),
            str(int(row["n_strategies"])),
            "Sin datos"
            if row["trades_is"] is None
            else f"{float(row['trades_is']):.1f}",
            "/".join(f"{value:.1f}" for value in row["fold_trades"]) or "Sin datos",
            "Sin datos"
            if row["cost_r"] is None
            else f"{float(row['cost_r']):.4f}",
            "Sin datos"
            if row["mean_bars"] is None
            else f"{float(row['mean_bars']):.2f}",
            "Sin datos"
            if row["mean_minutes"] is None
            else f"{float(row['mean_minutes']):.0f}",
            "sí" if row["passes"] else "NO",
            "; ".join(row.get("reasons") or []) or "",
        )
    console.print(table)
    if not report["passes"]:
        console.print(
            "[yellow]Ninguna temporalidad pasa el gate de viabilidad.[/yellow]"
        )
        raise typer.Exit(1)


@discovery_app.command("edge-map")
def discovery_edge_map_cmd(
    by: str = typer.Option(
        "hipotesis", "--by", help="hipotesis | cuenta | instrumento"
    ),
    account: str = typer.Option(None, "--account", help="Filtrar una cuenta"),
    discovery_db: str = typer.Option(
        None, "--discovery-db", help="discovery.db (solo lectura)"
    ),
    costs_db: str = typer.Option(
        None, "--costs-db", help="lab.db de costes (solo lectura)"
    ),
    data_root: str = typer.Option(
        None, "--data-root", help="Raíz de datos/snapshots (solo lectura)"
    ),
    no_dukascopy: bool = typer.Option(
        False,
        "--no-dukascopy",
        help="No leer Dukascopy (descarga en curso); H4/D1 Sin datos",
    ),
    mc_paths: int = typer.Option(
        None, "--mc-paths", help="Caminos del Monte Carlo del challenge"
    ),
) -> None:
    """Edge Map: hipótesis × instrumento × TF × fuente y capa de firma."""

    from .discovery import databank, edge_map

    if by not in {"hipotesis", "cuenta", "instrumento"}:
        raise typer.BadParameter("--by debe ser hipotesis, cuenta o instrumento")
    try:
        report = edge_map.build(
            discovery_db or databank.DEFAULT_DISCOVERY_DB,
            costs_db=costs_db or databank.LAB_DB,
            data_root=data_root or ROOT,
            account=account,
            allow_dukascopy=not no_dukascopy,
            n_paths=mc_paths,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Edge Map imposible:[/red] {exc}")
        raise typer.Exit(1) from exc
    if by == "cuenta":
        table = Table(title="Discovery · Edge Map · por cuenta")
        for column in (
            "Cuenta",
            "Firma",
            "Estrategia",
            "Nivel",
            "Veredicto",
            "PBO",
            "WF",
            "Neto R",
            "Cost_R",
            "Ops",
            "P(pasar)",
            "Auto",
            "Candidata",
            "Confirmación",
        ):
            table.add_column(column)
        for row in report["firms"]:
            table.add_row(
                str(row["account"]),
                str(row["firm"]),
                str(row["strategy_id"]),
                str(row["level"]),
                str(row["verdict"] or "Sin datos"),
                "Sin datos" if row["pbo"] is None else f"{float(row['pbo']):.4f}",
                "Sin datos" if row["wf_ok"] is None else ("sí" if row["wf_ok"] else "no"),
                "Sin datos"
                if row["net_expectancy_r"] is None
                else f"{float(row['net_expectancy_r']):.4f}",
                "Sin datos" if row["cost_r"] is None else f"{float(row['cost_r']):.4f}",
                str(row["trades"]),
                "Sin datos"
                if row["pass_rate"] is None
                else f"{float(row['pass_rate']) * 100:.1f}%",
                "sí" if row["automation_allowed"] else "no",
                "sí" if row["candidate"] else "no",
                str(row["confirm_status"]),
            )
    else:
        table = Table(title=f"Discovery · Edge Map · por {by}")
        for column in (
            "Hipótesis",
            "Instrumento",
            "TF",
            "Fuente",
            "Estado",
            "Bruto mediana",
            "Bruto mejor",
            "Neto mediana",
            "Cost_R",
            "Ops+",
            "Candidatas",
            "Confirmadas",
            "Datos",
        ):
            table.add_column(column)
        groups = edge_map.group_by(report, by)
        for group in groups:
            for row in group["rows"]:
                table.add_row(
                    str(row["template"]),
                    str(row["instrument"]),
                    str(row["timeframe"]),
                    str(row["source"]),
                    str(row["state"]),
                    "Sin datos"
                    if row["raw_median_r"] is None
                    else f"{float(row['raw_median_r']):.4f}",
                    "Sin datos"
                    if row["raw_best_r"] is None
                    else f"{float(row['raw_best_r']):.4f}",
                    "Sin datos"
                    if row["net_median_r"] is None
                    else f"{float(row['net_median_r']):.4f}",
                    "Sin datos" if row.get("cost_r") is None else f"{float(row['cost_r']):.4f}",
                    (
                        "Sin datos"
                        if row["raw_median_r"] is None
                        else f"{row['positive_folds_count']}/{row['strategy_total']}"
                    ),
                    str(row["candidate_count"]),
                    str(row["confirmed_count"]),
                    str(row["dataset_source"]),
                )
    console.print(table)
    if report.get("disconnected_accounts"):
        names = ", ".join(
            f"{item['id']} ({item['firm']})"
            for item in report["disconnected_accounts"]
        )
        console.print(f"[yellow]Cuentas sin conectar:[/yellow] {names} · fuera de la capa de firma")
    if report.get("blocked"):
        for item in report["blocked"]:
            console.print(f"[yellow]{item['timeframe']}:[/yellow] {item['reason']}")
    files = edge_map.export(report, by="hipotesis")
    console.print(
        f"[dim]Exportado: {files['markdown']} · {files['json']} · "
        f"combos {report['n_combos']} · firmas {report['n_firms']}[/dim]"
    )


@discovery_app.command("suggest")
def discovery_suggest_cmd(
    account: str = typer.Option(None, "--account", help="Cuenta objetivo"),
    discovery_db: str = typer.Option(
        None, "--discovery-db", help="discovery.db (solo lectura)"
    ),
    costs_db: str = typer.Option(
        None, "--costs-db", help="lab.db de costes (solo lectura)"
    ),
    data_root: str = typer.Option(
        None, "--data-root", help="Raíz de datos (solo lectura)"
    ),
    no_dukascopy: bool = typer.Option(
        False, "--no-dukascopy", help="No leer Dukascopy (descarga en curso)"
    ),
    limit: int = typer.Option(None, "--limit", help="Máximo de combinaciones"),
) -> None:
    """Combinaciones NO probadas y viables; etiqueta siempre 'por probar'."""

    from .discovery import databank, edge_map

    try:
        report = edge_map.suggest(
            account,
            discovery_db=discovery_db or databank.DEFAULT_DISCOVERY_DB,
            costs_db=costs_db or databank.LAB_DB,
            data_root=data_root or ROOT,
            allow_dukascopy=not no_dukascopy,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Suggest imposible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title="Discovery · combinaciones por probar")
    for column in (
        "Plantilla",
        "Instrumento",
        "TF",
        "Fuente",
        "Sesión",
        "Cuentas",
        "Ops IS",
        "Ops/pliegue",
        "Cost_R cribado",
        "Cost_R ops",
        "Etiqueta",
    ):
        table.add_column(column)
    for row in report["rows"]:
        table.add_row(
            str(row["template"]),
            str(row["instrument"]),
            str(row["timeframe"]),
            str(row["source"]),
            str(row["session"]),
            ", ".join(row["accounts"]),
            str(row["trades_is"]),
            "/".join(str(value) for value in row["fold_trades"]),
            "Sin datos"
            if row.get("cost_r_screening") is None
            else f"{float(row['cost_r_screening']):.4f}",
            "Sin datos" if row["cost_r"] is None else f"{float(row['cost_r']):.4f}",
            str(row["label"]),
        )
    console.print(table)
    for item in report.get("blocked") or []:
        console.print(f"[yellow]{item['timeframe']}:[/yellow] {item['reason']}")
    console.print(
        f"[dim]{report['n_rows']} combinaciones por probar; "
        "no son candidatas y no se ha registrado nada.[/dim]"
    )


@discovery_app.command("invalidate")
def discovery_invalidate_cmd(
    campaign_id: str = typer.Argument(..., help="ID de la campaña"),
    reason: str = typer.Option(..., "--reason", help="Motivo de la invalidez"),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Archiva una campaña como inválida; conserva su cuenta en el DSR."""

    from .discovery import campaigns

    try:
        campaign = campaigns.invalidate(campaign_id, str(reason), db_path=db)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]No se pudo invalidar:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(
        f"Campaña {campaign_id}: {campaign['status']} · "
        f"motivo {campaign.get('reject_reason')} · "
        f"approved_at {campaign.get('approved_at') or 'Sin datos'}"
    )


@discovery_app.command("approve")
def discovery_approve_cmd(
    campaign_id: str = typer.Argument(..., help="ID de la campaña"),
    approved_by_operator: bool = typer.Option(
        False, "--approved-by-operator", help="Aprobación explícita del operador"
    ),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Aprueba una campaña; sin el flag no hace nada."""

    if not approved_by_operator:
        console.print(
            "Sin --approved-by-operator no se aprueba: "
            f"{campaign_id} sigue en borrador y no cuenta."
        )
        return
    from .discovery import campaigns

    try:
        campaign = campaigns.approve(campaign_id, db_path=db)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]No se pudo aprobar:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(
        f"Campaña {campaign['campaign_id']}: {campaign['status']} · "
        f"approved_at {campaign.get('approved_at') or 'Sin datos'} · "
        f"cuenta {int(campaign.get('n_total') or 0):,} pruebas"
    )


@discovery_app.command("supersede")
def discovery_supersede_cmd(
    campaign_id: str = typer.Argument(..., help="Campaña antigua (fallida)"),
    approved_by_operator: bool = typer.Option(
        False, "--approved-by-operator", help="Aprobación explícita del operador"
    ),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Reemplaza una campaña fallida; sin el flag no hace nada."""

    if not approved_by_operator:
        console.print(
            "Sin --approved-by-operator no se reemplaza: "
            f"{campaign_id} queda igual."
        )
        return
    from .discovery import campaigns

    try:
        new = campaigns.supersede(campaign_id, db_path=db)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]No se pudo reemplazar:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"Discovery · reemplazo · {campaign_id}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Campaña nueva", str(new["campaign_id"]))
    table.add_row("Estado", str(new["status"]))
    table.add_row("config_hash", str(new["config_hash"])[:16] + "…")
    table.add_row("n_total", f"{int(new.get('n_total') or 0):,}")
    table.add_row("Snapshot", str(new.get("snapshot_path") or "Sin datos"))
    table.add_row("Hash snapshot", str(new.get("snapshot_hash") or "Sin datos")[:16] + "…")
    table.add_row("Cuenta antes", f"{int(new.get('count_before') or 0):,}")
    table.add_row("Cuenta después", f"{int(new.get('count_after') or 0):,}")
    console.print(table)
    console.print(
        "Siguiente: "
        f"lab discovery preflight {new['campaign_id']} y después "
        f"lab discovery run {new['campaign_id']} --approved-by-operator"
    )


@discovery_app.command("reject")
def discovery_reject_cmd(
    campaign_id: str = typer.Argument(..., help="ID de la campaña"),
    reason: str = typer.Option(
        ..., "--reason", help="Motivo del rechazo"
    ),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Rechaza una campaña; si nunca se aprobó, no cuenta en el DSR."""

    from .discovery import databank

    campaign = databank.get_campaign(campaign_id, db_path=db)
    if campaign is None:
        console.print(f"[red]Campaña no registrada:[/red] {campaign_id}")
        raise typer.Exit(1)
    if campaign.get("approved_at"):
        console.print(
            "[yellow]La campaña ya estaba aprobada: el rechazo no borra "
            "su cuenta en el DSR.[/yellow]"
        )
    databank.set_campaign_rejected(campaign_id, str(reason), db_path=db)
    row = databank.get_campaign(campaign_id, db_path=db)
    console.print(
        f"Campaña {campaign_id}: {row['status']} · motivo {row['reject_reason']} · "
        f"approved_at {row.get('approved_at') or 'Sin datos'}"
    )


@discovery_app.command("cancel")
def discovery_cancel_cmd(
    campaign_id: str = typer.Argument(..., help="ID de la campaña"),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Cancela los jobs en cola; lo ya aprobado sigue contando."""

    from .discovery import databank, jobs

    try:
        pending = jobs.cancel_campaign(campaign_id, db_path=db)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]No se pudo cancelar:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"Cancelados {pending} jobs en cola de {campaign_id}.")
    campaign = databank.get_campaign(campaign_id, db_path=db)
    if campaign and campaign.get("approved_at"):
        console.print(
            f"La campaña estaba aprobada: sigue contando "
            f"{int(campaign.get('n_total') or 0):,} pruebas."
        )


@discovery_app.command("run")
def discovery_run_cmd(
    campaign_id: str = typer.Argument(..., help="ID de la campaña"),
    approved_by_operator: bool = typer.Option(
        False, "--approved-by-operator", help="Ejecución real aprobada"
    ),
    synthetic: bool = typer.Option(
        False, "--synthetic", help="Paseo aleatorio en una discovery.db temporal"
    ),
    workers: int = typer.Option(None, "--workers", help="Workers (máximo engine.yaml)"),
    time_limit: float = typer.Option(
        None, "--time-limit", help="Límite de tiempo en minutos"
    ),
    seed: int = typer.Option(42, "--seed", help="Semilla del paseo sintético"),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Ejecuta el GA. Real: registered + --approved-by-operator. Sintético: no cuenta."""

    import tempfile
    from pathlib import Path

    from .discovery import campaigns, databank, engine

    if synthetic:
        with tempfile.TemporaryDirectory() as tmp:
            sdb = Path(tmp) / "discovery.db"
            frame = engine.synthetic_frame(years=1.0, seed=seed)
            segments = {
                "is": ["2023-01-02", "2023-09-30"],
                "oos1": ["2023-10-01", "2023-11-30"],
                "oos2": ["2023-12-01", None],
            }
            identifier = campaign_id or f"synthetic-{seed}"
            campaigns.register_synthetic(
                frame,
                template="ny_open_vol_filter",
                profile="small",
                segments=segments,
                seed=seed,
                campaign_id=identifier,
                db_path=sdb,
            )
            summary = engine.run_campaign(
                identifier,
                workers=workers,
                time_limit=time_limit,
                synthetic=True,
                db_path=sdb,
                bars=frame,
            )
        console.print(
            f"[bold]Sintética {identifier}[/bold] · no cuenta en el DSR · "
            f"n_total {summary['n_total']} · evaluados {summary['n_evaluated']} · "
            f"n_effective {summary['n_effective']} · factibles {summary['feasible']} · "
            f"frontera {summary['frontier']} · finalistas {len(summary['finalists'])}"
        )
        console.print(f"Tiempo {summary['elapsed_s']:.1f} s · semilla {summary['seed']}")
        return

    if not approved_by_operator:
        console.print(
            "Sin --approved-by-operator no se ejecuta una campaña real."
        )
        raise typer.Exit(1)
    campaign = databank.get_campaign(campaign_id, db_path=db)
    if campaign is None:
        console.print(f"[red]Campaña no registrada:[/red] {campaign_id}")
        raise typer.Exit(1)
    campaign = campaigns.reopen_empty_running(campaign_id, db_path=db)
    if campaign["status"] != "registered":
        console.print(
            f"[red]La campaña debe estar registered (está {campaign['status']}).[/red]"
        )
        raise typer.Exit(1)
    try:
        summary = engine.run_campaign(
            campaign_id,
            workers=workers,
            time_limit=time_limit,
            db_path=db,
        )
    except campaigns.CampaignError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(
        f"[bold]{campaign_id}[/bold] · n_total {summary['n_total']} · "
        f"evaluados {summary['n_evaluated']} · n_effective {summary['n_effective']} · "
        f"factibles {summary['feasible']} · frontera {summary['frontier']} · "
        f"finalistas {len(summary['finalists'])} · "
        f"OOS-1 medio {summary['oos1_mean']}"
    )


@discovery_app.command("results")
def discovery_results_cmd(
    campaign_id: str = typer.Argument(..., help="ID de la campaña"),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
    json_output: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    """Resultados IS por estrategia: nivel, estado, veredicto, bruto/neto y motivo."""
    from .discovery import databank, results

    try:
        report = results.campaign_results(
            campaign_id, db_path=db or databank.DEFAULT_DISCOVERY_DB
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Results imposible:[/red] {exc}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(
            data=json.dumps(report, ensure_ascii=False, default=str)
        )
        return
    campaign = report["campaign"]
    table = Table(
        title=f"Discovery · results {campaign_id} · "
        f"{campaign['instrument']} {campaign['timeframe']}"
    )
    for column in (
        "ID",
        "Params",
        "Ops",
        "Bruto R",
        "Neto R",
        "cost_R CF1",
        "cost_R CF6",
        "PF",
        "Pliegues+",
        "Nivel",
        "Estado",
        "Veredicto",
        "Motivo",
    ):
        table.add_column(column)
    for row in report["rows"]:
        params = row.get("params") or {}
        cost = row.get("cost_by_account") or {}
        table.add_row(
            str(row["id"]),
            "thr={threshold} stop={stop} rr={target_rr}".format(**params)
            if params
            else "Sin datos",
            str(row.get("trades") or 0),
            f"{float(row['gross_r']):.4f}"
            if row.get("gross_r") is not None
            else "Sin datos",
            f"{float(row['net_r']):.4f}"
            if row.get("net_r") is not None
            else "Sin datos",
            f"{float(cost['CFD-001']):.4f}"
            if cost.get("CFD-001") is not None
            else "Sin datos",
            f"{float(cost['CFD-006']):.4f}"
            if cost.get("CFD-006") is not None
            else "Sin datos",
            f"{float(row['profit_factor']):.4f}"
            if row.get("profit_factor") is not None
            else "Sin datos",
            f"{row.get('positive_folds', 0)}/{row.get('folds', 0)}",
            str(row.get("level", 1)),
            str(row.get("status") or "Sin datos"),
            str(row.get("verdict") or "Sin datos"),
            str(row.get("reason") or ""),
        )
    console.print(table)
    console.print(
        f"[dim]{campaign['status']} · n_total {campaign['n_total']} · "
        f"evaluados {campaign['n_evaluated']} · finalistas {campaign['n_finalists']} · "
        "solo IS; OOS-2 no se lee.[/dim]"
    )


@discovery_app.command("show")
def discovery_show_cmd(
    strategy_id: int = typer.Argument(..., help="ID de la estrategia"),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Muestra estrategia, nivel, veredicto y validaciones (solo lectura)."""

    from .discovery import databank

    strategy = databank.get_strategy(strategy_id, db_path=db)
    if strategy is None:
        console.print(f"[red]Estrategia no encontrada:[/red] {strategy_id}")
        raise typer.Exit(1)
    table = Table(title=f"Discovery · estrategia {strategy_id}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Hash", strategy["strategy_hash"][:20] + "…")
    table.add_row("Campaña", str(strategy["campaign_id"]))
    table.add_row("Instrumento", f"{strategy['instrument']} {strategy['timeframe']}")
    table.add_row("Nivel", str(strategy["level"]))
    table.add_row("Veredicto", strategy.get("verdict") or "Sin datos")
    table.add_row("Estado", str(strategy["status"]))
    table.add_row("Selección", strategy.get("selection_reason") or "Sin datos")
    console.print(table)
    campaign = databank.get_campaign(strategy["campaign_id"], db_path=db)
    evaluations = databank.list_evaluations(strategy_id, db_path=db)
    if evaluations:
        costs = Table(title="Evaluaciones y coste")
        costs.add_column("Segmento")
        costs.add_column("Ops", justify="right")
        costs.add_column("Cost_R", justify="right")
        costs.add_column("Cuentas")
        costs.add_column("Coste por cuenta (sí/no)")
        costs.add_column("Más barata")
        costs.add_column("Elegida")
        costs.add_column("Peor")
        costs.add_column("Slippage")
        legacy_account = (
            ((campaign or {}).get("config") or {}).get("cost", {}).get("account")
            or "Sin datos"
        )
        for evaluation in evaluations:
            metrics = evaluation.get("metrics") or {}
            by_account = metrics.get("cost_by_account")
            if not by_account and metrics.get("cost_r") is not None:
                by_account = {legacy_account: metrics.get("cost_r")}
            viability = metrics.get("cost_viable_by_account") or {}
            if not viability and by_account:
                from .discovery.config import load_engine_config

                max_cost_r = float(load_engine_config().fitness.cost_r_max)
                viability = {
                    name: (
                        None if value is None else bool(float(value) <= max_cost_r)
                    )
                    for name, value in by_account.items()
                }
            cost_text = " · ".join(
                f"{name} {'Sin datos' if value is None else f'{float(value):.4f}'} "
                f"({'sí' if viability.get(name) else 'no' if viability.get(name) is False else 'Sin datos'})"
                for name, value in (by_account or {}).items()
            ) or "Sin datos"
            best = metrics.get("best_account")
            if not best and by_account:
                valid_costs = {
                    name: value
                    for name, value in by_account.items()
                    if value is not None
                }
                best = (
                    min(valid_costs, key=lambda name: valid_costs[name])
                    if valid_costs
                    else "Sin datos"
                )
            best = best or "Sin datos"
            best_share = metrics.get("best_share")
            if best_share is not None and metrics.get("best_account"):
                best = f"{best} ({float(best_share) * 100:.0f} %)"
            selected = metrics.get("selected_account") or best
            selected_share = metrics.get("selected_share")
            if selected_share is not None and metrics.get("selected_account"):
                selected = f"{selected} ({float(selected_share) * 100:.0f} %)"
            worst = metrics.get("worst_account") or (
                legacy_account if by_account else "Sin datos"
            )
            if metrics.get("worst_share") is not None and metrics.get("worst_account"):
                worst = f"{worst} ({float(metrics['worst_share']) * 100:.0f} %)"
            assumption = metrics.get("slippage_assumption") or {}
            assumption_text = ", ".join(
                f"{name} {item.get('value')} ({item.get('source')})"
                for name, item in assumption.items()
            ) or "Sin datos"
            costs.add_row(
                str(evaluation.get("segment")),
                str(evaluation.get("trades_count") or 0),
                "Sin datos"
                if metrics.get("cost_r") is None
                else f"{float(metrics['cost_r']):.4f}",
                ", ".join(metrics.get("cost_accounts") or []) or legacy_account,
                cost_text,
                best,
                selected,
                worst,
                assumption_text,
            )
        console.print(costs)
    validations = databank.list_validations(strategy_id, db_path=db)
    if validations:
        tests = Table(title="Validaciones")
        tests.add_column("Prueba")
        tests.add_column("Pasó")
        tests.add_column("Estado")
        for row in validations:
            result = row.get("result") or {}
            status = result.get("status") or (
                "Sin datos" if result.get("pbo") is None else "ok"
            )
            tests.add_row(
                row["test"],
                "—" if row["passed"] is None else ("sí" if row["passed"] else "no"),
                str(status),
            )
        console.print(tests)


@discovery_app.command("retest")
def discovery_retest_cmd(
    strategy_id: int = typer.Argument(..., help="ID de la estrategia"),
    transfer: str = typer.Option(
        None, "--transfer", help="Símbolo extra (solo informativo: transfer)"
    ),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Costes ×1,5/×2 y slippage +1/+2 sobre IS+OOS-1 (sin OOS-2)."""

    from dataclasses import replace

    from .discovery import campaigns, databank, dsl, fastbt, jobs, retester
    from .propfund.costs import load_profile

    strategy = databank.get_strategy(strategy_id, db_path=db)
    if strategy is None:
        console.print(f"[red]Estrategia no encontrada:[/red] {strategy_id}")
        raise typer.Exit(1)
    campaign = databank.get_campaign(strategy["campaign_id"], db_path=db)
    if campaign is None:
        console.print("[red]Campaña no registrada.[/red]")
        raise typer.Exit(1)
    model = dsl.Strategy.model_validate(strategy["dsl"])
    setup = jobs.QueueSetup.from_campaign(campaign)
    profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
    cost = fastbt.cost_from_profile(profile, use_p75=bool(setup.use_p75))
    try:
        is_frame = campaigns.load_segment(
            strategy["campaign_id"], "is", db_path=db
        )
        oos1_frame = campaigns.load_segment(
            strategy["campaign_id"], "oos1", db_path=db
        )
        result = retester.retest(model, is_frame, oos1_frame, cost, setup)
        if transfer:
            from .discovery.data_sources import load_source

            source = load_source(transfer, campaign["timeframe"]).frame
            other_setup = replace(setup, instrument=transfer.upper())
            other_cost = fastbt.cost_from_profile(
                load_profile(setup.account, transfer.upper(), firm=setup.firm),
                use_p75=bool(setup.use_p75),
            )
            is_mask = source.index < oos1_frame.index[0]
            other_is = source[is_mask & (source.index >= is_frame.index[0])]
            other_oos1 = source[
                (source.index >= oos1_frame.index[0])
                & (source.index <= oos1_frame.index[-1])
            ]
            result["transfer"] = retester.transfer(
                model,
                {transfer.upper(): (other_is, other_oos1)},
                {transfer.upper(): other_cost},
                {transfer.upper(): other_setup},
            )
        databank.add_validation(
            strategy_id,
            "retest",
            result,
            bool(result.get("stress_cost_x1_5_ok")),
            db_path=db,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Retest no disponible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"Discovery · retest {strategy_id} (IS+OOS-1)")
    table.add_column("Escenario")
    table.add_column("Expectativa R", justify="right")
    table.add_column("PF", justify="right")
    table.add_column("Ops", justify="right")
    for name in ("base", "cost_x1_5", "cost_x2", "slippage_plus_1", "slippage_plus_2"):
        row = result.get(name) or {}
        table.add_row(
            name,
            f"{row.get('expectancy_r'):.4f}"
            if row.get("expectancy_r") is not None
            else "Sin datos",
            f"{row.get('profit_factor'):.2f}"
            if row.get("profit_factor") is not None
            else "Sin datos",
            str(row.get("trades") or 0),
        )
    console.print(table)
    if result.get("transfer"):
        console.print("[dim]Transfer: informativo, no cuenta como validación.[/dim]")


@discovery_app.command("robustness")
def discovery_robustness_cmd(
    strategy_id: int = typer.Argument(..., help="ID de la estrategia"),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Robustness Lab completo sobre IS+OOS-1; actualiza niveles y veredicto."""

    from .discovery import levels, robustness

    try:
        result = robustness.run(strategy_id, db_path=db)
        evaluation = levels.evaluate(strategy_id, db_path=db)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Robustness no disponible:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"Discovery · robustness {strategy_id}")
    table.add_column("Prueba")
    table.add_column("Resultado")
    table.add_column("Estado")
    table.add_row(
        "test_vs_random_insample",
        f"percentil {result['validations']['test_vs_random_insample'].get('percentile')}",
        "informativo",
    )
    random_oos2 = evaluation.get("test_vs_random_oos2_pct")
    table.add_row(
        "test_vs_random_oos2",
        (
            f"percentil {random_oos2}"
            if random_oos2 is not None
            else "no leído (confirm)"
        ),
        (
            "nivel 4"
            if random_oos2 is not None and float(random_oos2) >= 95.0
            else "no decide aquí"
        ),
    )
    table.add_row(
        "coste ×1,5",
        str(result["validations"]["retest"].get("cost_x1_5", {}).get("expectancy_r")),
        "sí" if result["validations"]["retest"].get("stress_cost_x1_5_ok") else "no",
    )
    table.add_row(
        "PBO",
        str(result["validations"]["pbo"].get("pbo")),
        "sí" if result["passed"]["pbo"] else "no",
    )
    table.add_row(
        "WF",
        str(result["validations"]["wf"].get("verdict")),
        "sí" if result["passed"]["wf"] else "no",
    )
    table.add_row(
        "Regímenes",
        str(result["validations"]["regime"].get("passed")),
        "sí" if result["passed"]["regime"] else "no",
    )
    table.add_row(
        "Challenge MC",
        str(result["validations"]["challenge"].get("passed")),
        "sí" if result["passed"]["challenge"] else "no",
    )
    console.print(table)
    console.print(
        f"Nivel {evaluation['level']} · veredicto {evaluation['verdict']} · "
        f"Sin datos: {', '.join(evaluation['sin_datos']) or 'ninguno'}"
    )


@discovery_app.command("perturb")
def discovery_perturb_cmd(
    strategy_id: int = typer.Argument(..., help="ID de la estrategia"),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Perturbation Lab: ruido, retardos y MC de ejecución (IS+OOS-1)."""

    from .discovery import databank, dsl, levels, perturb
    from .discovery.config import load_engine_config

    strategy = databank.get_strategy(strategy_id, db_path=db)
    if strategy is None:
        console.print(f"[red]Estrategia no encontrada:[/red] {strategy_id}")
        raise typer.Exit(1)
    campaign = databank.get_campaign(strategy["campaign_id"], db_path=db)
    if campaign is None:
        console.print("[red]Campaña no registrada.[/red]")
        raise typer.Exit(1)
    if str(campaign["status"]) != "done":
        console.print(
            "[red]Perturb solo sobre una campaña done (IS+OOS-1).[/red] "
            f"Estado actual: {campaign['status']}."
        )
        raise typer.Exit(1)

    config = load_engine_config().perturb
    try:
        frame, campaign, setup, cost = perturb.load_campaign_inputs(
            str(strategy["campaign_id"]), db_path=db
        )
        model = dsl.Strategy.model_validate(strategy["dsl"])
        seed = int(campaign["config"].get("seed", 0))
        noise = perturb.noise_test(
            model,
            frame,
            paths=int(config.noise_paths),
            scale_atr=float(config.noise_scale_atr),
            seed=seed + 10_000,
            cost=cost,
            setup=setup,
            strategy_id=strategy_id,
            db_path=db,
        )
        delay = perturb.delay_test(
            model,
            frame,
            entry_delays=tuple(int(item) for item in config.entry_delays),
            exit_delays=tuple(int(item) for item in config.exit_delays),
            cost=cost,
            setup=setup,
            strategy_id=strategy_id,
            db_path=db,
        )
        spread_source = perturb.load_spread_histogram(setup.instrument)
        execution = perturb.execution_mc(
            model,
            frame,
            skip_frac=float(config.exec_skip_frac),
            spread_source=spread_source,
            slippage_pts=perturb.default_slippage(cost),
            paths=int(config.exec_paths),
            seed=seed + 20_000,
            cost=cost,
            setup=setup,
            strategy_id=strategy_id,
            db_path=db,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Perturb no disponible:[/red] {exc}")
        raise typer.Exit(1) from exc

    limit = float(config.min_median_ratio)
    base = noise.get("base")

    def _passes(value: object) -> bool:
        if value is None or base is None or float(base) <= 0.0:
            return False
        numeric = float(value)
        return numeric > 0.0 and (numeric / float(base)) >= limit

    noise_passed = _passes(noise.get("median"))
    first_delay = str(config.entry_delays[0])
    delay_entry = (delay.get("entry") or {}).get(first_delay) or {}
    delay_passed = _passes(delay_entry.get("expectancy_r"))
    execution_passed = _passes(execution.get("median"))

    databank.add_validation(
        strategy_id,
        "perturb_noise",
        {**noise, "min_median_ratio": limit, "passed": noise_passed},
        noise_passed,
        db_path=db,
    )
    databank.add_validation(
        strategy_id,
        "perturb_delay",
        {
            **delay,
            "min_median_ratio": limit,
            "entry_delay_checked": int(config.entry_delays[0]),
            "passed": delay_passed,
        },
        delay_passed,
        db_path=db,
    )
    databank.add_validation(
        strategy_id,
        "perturb_execution",
        {**execution, "min_median_ratio": limit, "passed": execution_passed},
        execution_passed,
        db_path=db,
    )

    table = Table(title=f"Discovery · perturb {strategy_id} (IS+OOS-1)")
    table.add_column("Prueba")
    table.add_column("Base", justify="right")
    table.add_column("Mediana", justify="right")
    table.add_column("P10", justify="right")
    table.add_column("Ratio", justify="right")
    table.add_column("Pasa")
    table.add_row(
        "noise",
        f"{base:.4f}" if base is not None else "Sin datos",
        f"{noise['median']:.4f}" if noise.get("median") is not None else "Sin datos",
        f"{noise['p10']:.4f}" if noise.get("p10") is not None else "Sin datos",
        f"{noise['ratio']:.3f}" if noise.get("ratio") is not None else "Sin datos",
        "sí" if noise_passed else "no",
    )
    for delay_key, row in sorted((delay.get("entry") or {}).items()):
        table.add_row(
            f"delay entrada +{delay_key}",
            f"{base:.4f}" if base is not None else "Sin datos",
            f"{row['expectancy_r']:.4f}"
            if row.get("expectancy_r") is not None
            else "Sin datos",
            f"{row['expectancy_r']:.4f}"
            if row.get("expectancy_r") is not None
            else "Sin datos",
            f"{row['ratio']:.3f}" if row.get("ratio") is not None else "Sin datos",
            "sí" if _passes(row.get("expectancy_r")) else "no",
        )
    table.add_row(
        "execution_mc",
        f"{base:.4f}" if base is not None else "Sin datos",
        f"{execution['median']:.4f}"
        if execution.get("median") is not None
        else "Sin datos",
        f"{execution['p10']:.4f}"
        if execution.get("p10") is not None
        else "Sin datos",
        f"{execution['ratio']:.3f}"
        if execution.get("ratio") is not None
        else "Sin datos",
        "sí" if execution_passed else "no",
    )
    console.print(table)

    try:
        evaluation = levels.evaluate(strategy_id, db_path=db)
        console.print(
            f"Nivel {evaluation['level']} · veredicto {evaluation['verdict']} · "
            f"Sin datos: {', '.join(evaluation['sin_datos']) or 'ninguno'}"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Nivel no actualizado:[/yellow] {exc}")


@discovery_app.command("confirm")
def discovery_confirm_cmd(
    strategy_id: int = typer.Argument(..., help="ID de la estrategia"),
    approved_by_operator: bool = typer.Option(
        False, "--approved-by-operator", help="Lectura única de OOS-2 aprobada"
    ),
    db: str = typer.Option(None, "--db", help="discovery.db alternativo"),
) -> None:
    """Lectura única de OOS-2 y DSR de confirmación (solo nivel 3)."""

    if not approved_by_operator:
        console.print(
            "Sin --approved-by-operator no se lee OOS-2; no se hace nada."
        )
        return
    from .discovery import levels

    try:
        result = levels.confirm(
            strategy_id, approved_by_operator=True, db_path=db
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Confirmación no disponible:[/red] {exc}")
        raise typer.Exit(1) from exc
    random_oos2 = result.get("test_vs_random_oos2") or {}
    random_pct = random_oos2.get("percentile")
    random_text = (
        f"{random_pct}" if random_pct is not None else "Sin datos"
    )
    console.print(
        f"Estrategia {strategy_id} · OOS-2 expectativa "
        f"{result['oos2_expectancy_r']} · DSR confirmación "
        f"{result['dsr_confirm'].get('dsr')} (K={result['dsr_confirm'].get('k_finalists')}) "
        f"· azar OOS-2 {random_text} "
        f"({random_oos2.get('trades_oos2', 'Sin datos')} ops, "
        f"mín {random_oos2.get('min_trades_oos2', 'Sin datos')}) "
        f"· DSR global {result.get('global_dsr_tests')} · nivel {result['level']} "
        f"· veredicto {result['verdict']}"
    )


if __name__ == "__main__":
    main()

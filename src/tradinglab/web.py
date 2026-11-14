"""Panel web local del laboratorio.

Servidor HTTP basado solo en la biblioteca estándar (sin FastAPI/Flask) para
que el panel funcione aunque el entorno esté sin red o sin dependencias extra.

Expone una API JSON de solo lectura y dos acciones seguras:
  * dry-run del orquestador (nunca envía órdenes)
  * análisis del agente lite (una llamada al LLM, nunca envía órdenes)

El servidor escucha en 127.0.0.1 por defecto: no se publica en la red.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pandas as pd

from . import __version__
from .accounts import (
    cash_flows,
    effective_limits,
    firm_limits,
    load_accounts,
    own_limits,
    set_limits,
)
from .accounts import (
    history as limit_history,
)
from .alerts import AlertConfig, last_alerts, last_heartbeat
from .botlab import (
    archive_bot,
    evaluate_all,
    latest_evaluations,
    load_proposed,
    propose_bot,
    restore_bot,
)
from .config import DEFAULT_DB, ROOT, Settings, get_settings
from .cushion import DEFAULT_THRESHOLDS, load_thresholds
from .drift import build_drift
from .exports import list_exports, preview_file
from .health import score_account, time_weighted_return
from .instruments import catalog, validate_catalog
from .journal import build_journal, load_closed_trades
from .killswitch import load_state as load_killswitch
from .learning import (
    apply_lesson,
    count_tests,
    holdout_info,
    holdout_usage,
    list_lessons,
    revert_lesson,
)
from .learning import (
    approve as approve_lesson,
)
from .learning import (
    reject as reject_lesson,
)
from .market_agents import market_payload
from .market_pilots import pilot_status
from .models import promote_model, registry_payload, rollback_model
from .operator import OperatorError, OperatorService
from .orchestrator import load_bots
from .profiles import load_profiles
from .prop import AccountState, PropGuard, PropRules, from_yaml, ftmo
from .prop.simulator import multiverse_by_trade
from .reconciliation import last_reconciliation
from .riskpause import pause_status
from .riskpause import resume as resume_pause

INDEX_FILE = Path(__file__).with_name("webui") / "index.html"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,11}$")
MAX_LOG_BYTES = 96 * 1024
LOCAL_HOST = "127.0.0.1"
# Única superficie de escritura de la consola. Cualquier ruta nueva debe
# añadirse aquí y al test de auditoría; no hay endpoints de órdenes, de
# activación de bots ni de edición de prop.yaml.
WRITE_ROUTES = (
    "/api/actions/dryrun",
    "/api/actions/agent",
    "/api/bots/evaluate",
    "/api/bots/archive",
    "/api/bots/restore",
    "/api/bots/propose",
    "/api/fund/limits",
    "/api/fund/killswitch",
    "/api/fund/pause/resume",
    "/api/learning/approve",
    "/api/learning/reject",
    "/api/learning/apply",
    "/api/learning/revert",
    "/api/models/promote",
    "/api/models/rollback",
    "/api/operator/arm",
    "/api/operator/disarm",
    "/api/operator/preview",
    "/api/operator/execute",
)
POCKET_LABELS = {
    "swing_equity": "Swing acciones/ETF",
    "intraday_fx": "Forex/CFD",
    "intraday_futures": "Futuros",
}
LIMIT_META = (
    {"field": "daily_loss_pct", "label": "Pérdida diaria", "kind": "pct"},
    {"field": "max_drawdown_pct", "label": "Drawdown máximo", "kind": "pct"},
    {"field": "per_trade_risk_pct", "label": "Riesgo por operación", "kind": "pct"},
    {"field": "max_open_risk_pct", "label": "Riesgo abierto máximo", "kind": "pct"},
    {"field": "max_trades_per_day", "label": "Operaciones máximas/día", "kind": "int"},
)


def compute_build_id(root: Path | None = None) -> str:
    """Huella de código/UI/config para detectar un panel desactualizado."""
    base = Path(root) if root else ROOT
    files: list[Path] = []
    files.extend((base / "src" / "tradinglab").rglob("*.py"))
    files.extend((base / "src" / "tradinglab" / "webui").rglob("*"))
    files.extend((base / "config").glob("*.yaml"))
    files.extend([base / "pyproject.toml"])
    digest = hashlib.sha256()
    for path in sorted({p for p in files if p.is_file()}):
        try:
            rel = path.relative_to(base).as_posix()
        except ValueError:
            rel = path.name
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:20]


BUILD_ID = compute_build_id()

SEVERITY_LABEL = {
    "ok": "OK",
    "warn": "AVISO",
    "block": "BLOQUEO",
    "breach": "BREACH",
}

REPO_AUDIT = [
    {
        "id": "autohedge",
        "name": "AutoHedge",
        "url": "https://github.com/The-Swarm-Corporation/AutoHedge",
        "license": "MIT",
        "license_class": "permisiva",
        "focus": "Pipeline de agentes Director → Quant → Risk → Execution y riesgo primero.",
        "adopted": [
            "Pipeline visual de decisión en el Resumen",
            "Checklist de riesgo antes de cualquier apertura",
            "Salida estructurada y logs auditables",
        ],
        "not_adopted": [
            "Ejecución autónoma en Solana",
            "Dependencias swarms/solders",
            "Claves de wallet o exchanges",
        ],
        "decision": "Tomar el diseño de pipeline y la separación de responsabilidades; no ejecutar.",
    },
    {
        "id": "vibe-trading",
        "name": "Vibe-Trading",
        "url": "https://github.com/HKUDS/Vibe-Trading",
        "license": "MIT",
        "license_class": "permisiva",
        "focus": "Research Lab, Run Detail, Pixel Office, Alpha Zoo y paper/shadow trading.",
        "adopted": [
            "Detalle de research con PBO, walk-forward y regímenes",
            "Mercado local con sparklines y detalle por activo",
            "Paleta de comandos y navegación de terminal",
        ],
        "not_adopted": [
            "Stack React/FastAPI (la consola actual usa stdlib)",
            "Conectores de bróker y ejecución live",
            "Dependencias externas nuevas",
        ],
        "decision": "Replicar la UX de investigación y terminal, no importar el stack.",
    },
    {
        "id": "fincept-terminal",
        "name": "Fincept Terminal",
        "url": "https://github.com/Fincept-Corporation/FinceptTerminal",
        "license": "AGPL-3.0",
        "license_class": "copyleft fuerte",
        "focus": "Terminal financiera nativa, módulos densos, editor de nodos y command center.",
        "adopted": [
            "Densidad visual de terminal profesional",
            "Barra de estado y atajos de teclado",
            "Módulos de mercado, research y sistema",
        ],
        "not_adopted": [
            "Código C++/Qt (licencia AGPL)",
            "Activos, iconos o marca Fincept",
            "Cualquier dependencia o binario externo",
        ],
        "decision": "Tomar solo ideas de UX; no copiar código ni assets por la AGPL-3.0.",
    },
]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalars
        return value.item()
    return value


def _decode_log(data: bytes, encoding: str) -> str:
    if encoding == "utf-8":
        return data.decode("utf-8", errors="replace")
    try:
        return data.decode(encoding, errors="replace").lstrip("\ufeff")
    except (LookupError, ValueError):
        return data.decode("utf-8", errors="replace")


def _tail(path: Path, max_bytes: int = MAX_LOG_BYTES) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            head = handle.read(4)
        if head.startswith(b"\xff\xfe") or (len(head) >= 2 and head[1] == 0 and head[0] != 0):
            encoding = "utf-16-le"  # PowerShell 5.1 escribe *> en UTF-16LE
        elif head.startswith(b"\xfe\xff") or (len(head) >= 2 and head[0] == 0 and head[1] != 0):
            encoding = "utf-16-be"
        elif head.startswith(b"\xef\xbb\xbf"):
            encoding = "utf-8-sig"
        else:
            encoding = "utf-8"

        prefix = ""
        with path.open("rb") as handle:
            if size > max_bytes:
                start = size - max_bytes
                if encoding.startswith("utf-16") and start % 2:
                    start += 1
                handle.seek(start)
                prefix = "[... salida truncada; mostrando el final ...]\n"
            data = handle.read()
        return prefix + _decode_log(data, encoding)
    except OSError as exc:
        return f"[No se pudo leer {path.name}: {exc}]"


def _connect_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    return con


def _iso_from_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="seconds")


class TTLCache:
    """Caché simple por clave con vencimiento, protegida por lock."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: float, factory) -> Any:
        now = time.monotonic()
        with self._lock:
            cached = self._items.get(key)
            if cached and now - cached[0] < ttl:
                return cached[1]
        value = factory()
        with self._lock:
            self._items[key] = (time.monotonic(), value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


# ------------------------------------------------------------------- datos


class LabData:
    """Recolecta el estado del laboratorio desde disco, SQLite y MT5."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        root: Path | str = ROOT,
        db_path: Path | str = DEFAULT_DB,
        external: bool = True,
        operator_service: OperatorService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.root = Path(root)
        self.db_path = Path(db_path)
        self.external = external
        self.cache = TTLCache()
        self._action_lock = threading.Lock()
        self._action: dict[str, Any] | None = None
        self.operator = operator_service or OperatorService(
            self.settings, self.db_path
        )

    # --------------------------------------------------------------- rutas

    @property
    def agent_runs_dir(self) -> Path:
        return self.root / "data" / "agent_runs"

    @property
    def dryrun_dir(self) -> Path:
        return self.root / "data" / "dryrun"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def research_dir(self) -> Path:
        return self.root / "reports" / "research"

    @property
    def bots_file(self) -> Path:
        return self.root / "config" / "bots.yaml"

    # ------------------------------------------------------------- resumen

    def overview(self) -> dict:
        return {
            "generated_at": _now(),
            "version": __version__,
            "meta": {
                "mode": self.settings.mode,
                "broker": self.settings.execution.broker,
                "timezone": self.settings.timezone,
                "llm_model": self.settings.llm.model,
                "llm_base_url": self.settings.llm.base_url,
                "prop_firm": self.settings.prop.firm,
                "prop_phase": self.settings.prop.phase,
                "prop_enabled": self.settings.prop.enabled,
                "data_provider": self.settings.data.provider,
                "starting_cash": self.settings.starting_cash,
                "build": BUILD_ID,
            },
            "account": self.account(),
            "killswitch": self.killswitch_status(),
            "alerts": self.alerts_status(),
            "reconciliation": self.reconciliation_status(),
            "llm": self._llm_status(),
            "scheduler": self._scheduler(),
            "git": self.git_info(),
            "agents": self.agent_runs(limit=30),
            "deep_logs": self.deep_logs(),
            "dryruns": self.dryruns(limit=10),
            "bots": self.bots(),
            "research": self.research(limit=15),
            "regime": self.regime("QQQ"),
            "market": self.market(),
            "calendar": self.calendar(),
            "decisions": self.decisions(),
            "agent_comparisons": self.agent_comparisons(),
            "lifecycle": self.lifecycle(),
            "repos": self.repo_audit(),
            "logs": self.logs(limit=40),
            "action": self.action_status(),
        }

    def account(self) -> dict:
        out = {
            "equity": self.settings.starting_cash,
            "cash": self.settings.starting_cash,
            "positions_value": 0.0,
            "return_pct": 0.0,
            "drawdown_pct": 0.0,
            "positions": [],
            "orders": [],
            "signals": [],
            "equity_curve": [],
            "llm_calls": {"count": 0, "avg_latency_s": 0.0, "ok": 0},
        }
        if not self.db_path.exists():
            return out
        try:
            with contextlib.closing(_connect_ro(self.db_path)) as con:
                row = con.execute(
                    "SELECT ts, cash, positions_value, equity FROM equity ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row:
                    out["cash"] = float(row["cash"])
                    out["positions_value"] = float(row["positions_value"])
                    out["equity"] = float(row["equity"])

                positions = []
                for p in con.execute(
                    "SELECT ticker, qty, avg_price FROM positions ORDER BY ticker"
                ).fetchall():
                    qty = float(p["qty"])
                    avg = float(p["avg_price"])
                    positions.append(
                        {
                            "ticker": p["ticker"],
                            "qty": qty,
                            "avg_price": avg,
                            "value": abs(qty) * avg,
                            "unrealized": 0.0,
                        }
                    )
                out["positions"] = positions

                out["orders"] = [
                    {
                        "ts": o["ts"],
                        "ticker": o["ticker"],
                        "side": o["side"],
                        "qty": float(o["qty"]),
                        "status": o["status"],
                        "bot": o["bot"],
                    }
                    for o in con.execute(
                        "SELECT ts, ticker, side, qty, status, bot FROM orders ORDER BY id DESC LIMIT 25"
                    ).fetchall()
                ]

                out["signals"] = [
                    {
                        "ts": s["ts"],
                        "ticker": s["ticker"],
                        "bot": s["bot"],
                        "side": s["side"],
                        "strength": s["strength"],
                        "price": s["price"],
                        "reason": s["reason"],
                    }
                    for s in con.execute(
                        "SELECT ts, ticker, bot, side, strength, price, reason "
                        "FROM signals ORDER BY id DESC LIMIT 20"
                    ).fetchall()
                ]

                curve_rows = con.execute(
                    "SELECT ts, equity FROM equity ORDER BY id DESC LIMIT 600"
                ).fetchall()
                out["equity_curve"] = [
                    {"ts": r["ts"], "equity": float(r["equity"])} for r in reversed(curve_rows)
                ]

                llm = con.execute(
                    "SELECT COUNT(*) AS n, COALESCE(AVG(latency_ms), 0) AS avg_ms, "
                    "COALESCE(SUM(ok), 0) AS ok FROM llm_calls"
                ).fetchone()
                out["llm_calls"] = {
                    "count": int(llm["n"]),
                    "avg_latency_s": round(float(llm["avg_ms"]) / 1000.0, 1),
                    "ok": int(llm["ok"]),
                }
        except sqlite3.Error as exc:
            out["db_error"] = str(exc)

        start = float(self.settings.starting_cash or 0.0)
        if start:
            out["return_pct"] = out["equity"] / start - 1.0
        curve = out["equity_curve"]
        if curve:
            peak = max(p["equity"] for p in curve)
            if peak:
                out["drawdown_pct"] = out["equity"] / peak - 1.0
        return out

    # ------------------------------------------------------------ LLM / MT5

    def killswitch_status(self) -> dict:
        try:
            state = self.cache.get("killswitch", 5.0, lambda: load_killswitch(self.db_path))
        except Exception as exc:
            return {"active": False, "reason": f"error: {exc}"[:240]}
        return {
            "active": state.active,
            "reason": state.reason,
            "triggered_at": state.triggered_at,
            "reset_at": state.reset_at,
            "equity": state.equity,
            "peak": state.peak,
            "day_start": state.day_start,
        }

    def alerts_status(self) -> dict:
        cfg = AlertConfig.from_env()

        def collect() -> dict:
            return {
                "channel": cfg.channel,
                "configured": cfg.configured,
                "enabled": cfg.enabled,
                "heartbeat": bool(cfg.heartbeat_url),
                "last_heartbeat": last_heartbeat(self.db_path),
                "last": last_alerts(5, self.db_path),
            }

        try:
            return self.cache.get("alerts", 10.0, collect)
        except Exception as exc:
            return {"channel": cfg.channel, "configured": cfg.configured, "error": str(exc)[:200]}

    def reconciliation_status(self) -> dict:
        try:
            return self.cache.get(
                "reconciliation",
                15.0,
                lambda: last_reconciliation(self.db_path) or {},
            )
        except Exception as exc:
            return {"status": "error", "details": str(exc)[:200]}

    def accounts(self) -> list[dict]:
        """Resumen normalizado de todas las cuentas configuradas."""
        return self.cache.get("accounts", 20.0, self._accounts)

    def _accounts(self) -> list[dict]:
        out: list[dict] = []
        paper = self.account()
        out.append(
            {
                "id": "paper",
                "name": "Paper interno",
                "kind": "acciones/ETF",
                "mode": "paper",
                "configured": True,
                "ok": True,
                "source": "SQLite local",
                "currency": "USD",
                "equity": paper["equity"],
                "cash": paper["cash"],
                "positions": [
                    {
                        "symbol": p["ticker"],
                        "qty": p["qty"],
                        "value": p["value"],
                        "pnl": p.get("unrealized", 0.0),
                    }
                    for p in paper["positions"]
                ],
                "status": "ok",
            }
        )

        try:
            from .execution.alpaca import AlpacaBroker

            if os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"):
                broker = AlpacaBroker(paper=True, db_path=self.db_path)
                health = broker.health()
                positions = broker.positions()
                out.append(
                    {
                        "id": "alpaca",
                        "name": "Alpaca Paper",
                        "kind": "acciones/ETF",
                        "mode": "paper",
                        "configured": True,
                        "ok": bool(health.get("ok")),
                        "source": "Alpaca API",
                        "currency": health.get("currency", "USD"),
                        "equity": health.get("equity"),
                        "cash": health.get("cash"),
                        "positions": [
                            {
                                "symbol": p["ticker"],
                                "qty": p["qty"],
                                "value": p["value"],
                                "pnl": p.get("unrealized", 0.0),
                            }
                            for p in positions
                        ],
                        "status": str(health.get("status", "ok")),
                        "buying_power": health.get("buying_power"),
                    }
                )
        except Exception as exc:
            out.append(
                {
                    "id": "alpaca",
                    "name": "Alpaca Paper",
                    "kind": "acciones/ETF",
                    "mode": "paper",
                    "configured": True,
                    "ok": False,
                    "source": "Alpaca API",
                    "equity": None,
                    "cash": None,
                    "positions": [],
                    "status": "error",
                    "error": str(exc)[:240],
                }
            )

        risk = self.risk()
        mt5 = risk.get("mt5", {})
        account = mt5.get("account") or {}
        out.append(
            {
                "id": "mt5",
                "name": "FTMO Demo · MT5",
                "kind": "forex/CFD",
                "mode": account.get("mode", "demo"),
                "configured": bool(mt5.get("configured")),
                "ok": bool(mt5.get("ok")),
                "source": "MetaTrader 5",
                "currency": account.get("currency", "USD"),
                "equity": account.get("equity"),
                "cash": account.get("balance"),
                "positions": [
                    {
                        "symbol": p.get("symbol", "?"),
                        "qty": p.get("volume", 0.0),
                        "value": None,
                        "pnl": p.get("profit", 0.0),
                    }
                    for p in (mt5.get("positions") or [])
                ],
                "status": "ok" if mt5.get("ok") else "error",
                "error": mt5.get("error"),
                "trade_allowed": account.get("trade_allowed"),
            }
        )

        futures = risk.get("futures", {})
        fut_account = futures.get("account") or {}
        out.append(
            {
                "id": "projectx",
                "name": "TopstepX · ProjectX",
                "kind": "futuros",
                "mode": "simulada" if futures.get("require_simulated") else "real",
                "configured": bool(futures.get("configured")),
                "ok": bool(futures.get("ok")),
                "source": "ProjectX API",
                "currency": "USD",
                "equity": fut_account.get("balance"),
                "cash": fut_account.get("balance"),
                "positions": [],
                "status": "ok" if futures.get("ok") else "no configurada",
                "error": futures.get("error") or futures.get("note"),
            }
        )
        return out

    # ------------------------------------------------------------- diario

    def journal(self, **filters) -> dict:
        """Diario de operaciones cerradas; solo lee lab.db."""
        key = "journal:" + json.dumps(filters, sort_keys=True, default=str)
        return self.cache.get(
            key,
            5.0,
            lambda: build_journal(
                self.db_path, tz=self.settings.timezone, **filters
            ),
        )

    def drift(self, *, min_trades: int = 20) -> dict:
        """Deriva live vs backtest por bot; solo informativo."""
        key = f"drift:{int(min_trades)}"
        return self.cache.get(
            key,
            30.0,
            lambda: build_drift(
                self.db_path, self.settings, min_trades=int(min_trades)
            ),
        )

    def learning(self) -> dict:
        """Lecciones, holdout sellado y contador global de pruebas."""
        def collect() -> dict:
            lessons = list_lessons(self.db_path)
            evaluations = latest_evaluations(self.db_path)
            return {
                "generated_at": _now(),
                "lessons": lessons,
                "holdout": holdout_info(self.db_path),
                "trials": count_tests(self.db_path),
                "auto_apply_reduce_risk": self.settings.learning.auto_apply_reduce_risk,
                "evaluations": {
                    bot: {
                        "status": row.get("status"),
                        "sharpe": row.get("sharpe"),
                        "expectancy": row.get("expectancy"),
                        "num_trades": row.get("num_trades"),
                    }
                    for bot, row in evaluations.items()
                },
            }

        return self.cache.get("learning", 5.0, collect)

    # ------------------------------------------------------------- fondo

    def fund(self) -> dict:
        """Vista del fondo: límites por cuenta, uso, bolsillos y clústeres."""
        return self.cache.get("fund", 5.0, self._fund)

    def _fund(self) -> dict:
        definitions = load_accounts()
        now = datetime.now(UTC)
        accounts_info = (
            {item["id"]: item for item in self.accounts()} if self.external else {}
        )
        specs = load_bots()
        bot_accounts = {spec.id: spec.account for spec in specs}
        trades, _ = load_closed_trades(
            self.db_path,
            tz=self.settings.timezone,
            bots={
                spec.id: {"account": spec.account, "profile": spec.profile}
                for spec in specs
            },
        )
        trades_by_account: dict[str, list] = {}
        for trade in trades:
            if trade.account:
                trades_by_account.setdefault(trade.account, []).append(trade)
        drift_by_bot = {
            row["bot"]: row["status"]
            for row in (self.drift().get("bots") or [])
        }
        paper_curve = self.account().get("equity_curve") or []
        rows: list[dict] = []
        for account in definitions.values():
            firm = firm_limits(account)
            own = own_limits(self.db_path, account)
            effective = effective_limits(self.db_path, account)
            source_id = {
                "internal": "paper",
                "paper": "paper",
                "alpaca": "alpaca",
                "mt5": "mt5",
                "projectx": "projectx",
            }.get(account.platform, account.platform)
            usage = self._fund_usage(account, effective, accounts_info.get(source_id))
            history = []
            for row in limit_history(self.db_path, account.id, 20):
                item = _json_safe(row)
                item["pending"] = str(row["effective_from"]) > now.isoformat()
                history.append(item)
            account_trades = trades_by_account.get(account.id, [])
            drift_statuses = [
                status
                for bot, assigned in bot_accounts.items()
                if assigned == account.id
                for status in [drift_by_bot.get(bot)]
                if status
            ]
            health = score_account(
                usage=usage,
                trades=account_trades,
                drift_statuses=drift_statuses,
                cfg=self.settings.fund_health,
            )
            flows = cash_flows(self.db_path, account.id, limit=50)
            twr = time_weighted_return(
                paper_curve if account.id == "paper_main" else [], flows
            )
            try:
                pause = pause_status(
                    self.db_path,
                    account.id,
                    trades=account_trades,
                    tz=self.settings.timezone,
                    persist=False,
                )
            except Exception as exc:
                pause = {
                    "paused": False,
                    "reason": f"Sin datos: {exc}",
                    "trigger_type": None,
                }
            rows.append(
                {
                    "id": account.id,
                    "name": account.name,
                    "type": account.type,
                    "broker": account.broker,
                    "platform": account.platform,
                    "status": account.status,
                    "firm": account.firm,
                    "phase": account.phase,
                    "pocket": account.pocket,
                    "pocket_label": POCKET_LABELS.get(account.pocket, account.pocket),
                    "account_size": account.account_size,
                    "firm_limits": firm,
                    "own_limits": _json_safe(asdict(own)),
                    "effective_limits": _json_safe(asdict(effective)),
                    "usage": usage,
                    "cash_flows": flows,
                    "cash_flow_net": round(
                        sum(
                            float(flow["amount"])
                            * (1 if flow["kind"] == "deposit" else -1)
                            for flow in flows
                        ),
                        2,
                    ),
                    "twr": twr,
                    "health": health,
                    "pause": pause,
                    "history": history,
                    "pending": [item for item in history if item["pending"]],
                }
            )

        total_capital = sum(row["account_size"] for row in rows)
        scored = [row for row in rows if row["health"]["score"] is not None]
        fund_health = None
        if scored:
            scored_capital = sum(row["account_size"] for row in scored)
            fund_health = {
                "score": round(
                    sum(row["health"]["score"] * row["account_size"] for row in scored)
                    / scored_capital,
                    1,
                ),
                "coverage": round(scored_capital / total_capital, 4)
                if total_capital
                else 0.0,
                "accounts": len(scored),
                "partial": len(scored) < len(rows),
            }
        twr_rows = [row for row in rows if row["twr"]["twr"] is not None]
        fund_return = {"twr": None, "coverage": 0.0, "accounts": []}
        if twr_rows:
            twr_capital = sum(row["account_size"] for row in twr_rows)
            fund_return = {
                "twr": round(
                    sum(
                        row["twr"]["twr"] * row["account_size"] for row in twr_rows
                    )
                    / twr_capital,
                    6,
                ),
                "coverage": round(twr_capital / total_capital, 4)
                if total_capital
                else 0.0,
                "accounts": [row["id"] for row in twr_rows],
                "note": "TWR ponderado por capital; solo cuentas con equity histórico",
            }
        else:
            fund_return["note"] = "Sin datos de equity histórico por cuenta"

        pocket_rows = []
        for pocket in list(POCKET_LABELS) + sorted(
            {row["pocket"] for row in rows} - set(POCKET_LABELS)
        ):
            members = [row for row in rows if row["pocket"] == pocket]
            if not members:
                continue
            capital = sum(row["account_size"] for row in members)
            equity_values = [
                row["usage"]["equity"]
                for row in members
                if row["usage"].get("equity") is not None
            ]
            pocket_rows.append(
                {
                    "pocket": pocket,
                    "label": POCKET_LABELS.get(pocket, pocket),
                    "capital": capital,
                    "pct": (capital / total_capital) if total_capital else 0.0,
                    "equity": sum(equity_values) if equity_values else None,
                    "accounts": [row["id"] for row in members],
                }
            )

        try:
            cushion_thresholds = load_thresholds()
        except Exception:
            cushion_thresholds = {
                section: dict(values)
                for section, values in DEFAULT_THRESHOLDS.items()
            }
        return {
            "generated_at": _now(),
            "limit_meta": [dict(item) for item in LIMIT_META],
            "accounts": rows,
            "pockets": pocket_rows,
            "health": fund_health,
            "fund_return": fund_return,
            "clusters": self._fund_clusters(definitions),
            "exposure": self._fund_exposure(accounts_info),
            "killswitch": self.killswitch_status(),
            "cushion_thresholds": cushion_thresholds,
        }

    def _fund_usage(
        self,
        account,
        effective,
        broker_info: dict | None,
    ) -> dict:
        size = float(account.account_size)
        daily_limit = size * float(effective.daily_loss_pct)
        max_limit = size * float(effective.max_drawdown_pct)
        out = {
            "available": False,
            "source": None,
            "equity": None,
            "day_start_equity": None,
            "daily_loss_usd": None,
            "daily_limit_usd": round(daily_limit, 2),
            "daily_used_pct": None,
            "daily_cushion_usd": None,
            "peak_equity": None,
            "drawdown_limit_usd": round(max_limit, 2),
            "drawdown_used_pct": None,
            "drawdown_cushion_usd": None,
            "as_of": None,
            "reason": "sin fuente de equity para esta cuenta",
        }

        if account.id == "paper_main":
            paper = self.account()
            curve = paper.get("equity_curve") or []
            if curve:
                try:
                    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

                    try:
                        tz = ZoneInfo(self.settings.timezone)
                    except ZoneInfoNotFoundError:
                        tz = UTC
                    points: list[tuple[datetime, float]] = []
                    for point in curve:
                        stamp = datetime.fromisoformat(str(point["ts"]))
                        points.append((stamp.astimezone(tz), float(point["equity"])))
                    current = points[-1][1]
                    peak = max(value for _, value in points)
                    today = datetime.now(tz).date()
                    today_points = [value for stamp, value in points if stamp.date() == today]
                    day_start = today_points[0] if today_points else current
                    self._fill_usage(
                        out,
                        equity=current,
                        day_start=day_start,
                        peak=peak,
                        daily_limit=daily_limit,
                        max_limit=max_limit,
                        source="sqlite",
                        as_of=str(curve[-1]["ts"]),
                    )
                    return out
                except (ValueError, TypeError, KeyError):
                    pass
            if paper.get("equity") is not None:
                out["equity"] = float(paper["equity"])
            out["reason"] = "sin historial de equity todavía"
            return out

        if account.id == "ftmo_demo" and self.external:
            risk = self.risk()
            prop = risk.get("prop") or {}
            rules = risk.get("rules") or {}
            mt5 = risk.get("mt5") or {}
            if prop.get("source") == "mt5" and prop.get("daily_used_pct") is not None:
                equity = (mt5.get("account") or {}).get("equity")
                firm_daily = float(rules.get("daily_limit_usd") or 0.0)
                firm_max = float(rules.get("max_loss_usd") or 0.0)
                if equity is not None and firm_daily > 0:
                    used_daily = float(prop["daily_used_pct"])
                    used_max = float(prop.get("max_used_pct") or 0.0)
                    day_start = float(equity) + used_daily * firm_daily
                    peak = (
                        float(equity) + used_max * firm_max
                        if firm_max > 0
                        else None
                    )
                    self._fill_usage(
                        out,
                        equity=float(equity),
                        day_start=day_start,
                        peak=peak,
                        daily_limit=daily_limit,
                        max_limit=max_limit,
                        source="mt5",
                        as_of=str(prop.get("generated_at") or _now()),
                    )
                    return out
            out["reason"] = "MT5 no disponible; no se inventa el uso del día"
            return out

        equity = (broker_info or {}).get("equity")
        if equity is not None:
            out["equity"] = float(equity)
            out["reason"] = "sin base diaria por cuenta; solo equity actual"
        return out

    @staticmethod
    def _fill_usage(
        out: dict,
        *,
        equity: float,
        day_start: float,
        peak: float | None,
        daily_limit: float,
        max_limit: float,
        source: str,
        as_of: str,
    ) -> None:
        daily_loss = max(0.0, float(day_start) - float(equity))
        max_loss_used = (
            max(0.0, float(peak) - float(equity)) if peak is not None else None
        )
        out.update(
            {
                "available": True,
                "source": source,
                "equity": round(float(equity), 2),
                "day_start_equity": round(float(day_start), 2),
                "daily_loss_usd": round(daily_loss, 2),
                "daily_limit_usd": round(daily_limit, 2),
                "daily_used_pct": (
                    round(daily_loss / daily_limit, 6) if daily_limit > 0 else None
                ),
                "daily_cushion_usd": round(max(0.0, daily_limit - daily_loss), 2),
                "peak_equity": round(float(peak), 2) if peak is not None else None,
                "drawdown_limit_usd": round(max_limit, 2),
                "drawdown_used_pct": (
                    round(max_loss_used / max_limit, 6)
                    if max_loss_used is not None and max_limit > 0
                    else None
                ),
                "drawdown_cushion_usd": (
                    round(max(0.0, max_limit - max_loss_used), 2)
                    if max_loss_used is not None
                    else None
                ),
                "as_of": as_of,
                "reason": None,
            }
        )

    def _fund_clusters(self, definitions: dict) -> list[dict]:
        try:
            profiles = load_profiles()
            bots = load_bots()
        except Exception:
            return []
        groups: dict[tuple[str, str], dict] = {}
        for spec in bots:
            if spec.archived or not spec.enabled:
                continue
            account = definitions.get(spec.account)
            profile = profiles.get(spec.profile or "")
            if account is None or profile is None:
                continue
            limits = effective_limits(self.db_path, account)
            risk_pct = min(float(profile.max_risk_pct), float(limits.per_trade_risk_pct))
            key = (account.id, spec.cluster or "sin_cluster")
            group = groups.setdefault(
                key,
                {
                    "account": account.id,
                    "cluster": spec.cluster or "sin_cluster",
                    "bots": [],
                    "reserved_usd": 0.0,
                    "budget_pct": float(profile.max_cluster_risk_pct),
                    "account_size": float(account.account_size),
                },
            )
            group["reserved_usd"] += float(account.account_size) * risk_pct
            group["budget_pct"] = min(
                group["budget_pct"], float(profile.max_cluster_risk_pct)
            )
            group["bots"].append(spec.id)
        rows = []
        for group in groups.values():
            budget = group["account_size"] * group["budget_pct"]
            reserved = group["reserved_usd"]
            rows.append(
                {
                    "account": group["account"],
                    "cluster": group["cluster"],
                    "bots": group["bots"],
                    "reserved_usd": round(reserved, 2),
                    "budget_usd": round(budget, 2),
                    "budget_pct": group["budget_pct"],
                    "used_pct": (reserved / budget) if budget > 0 else None,
                    "over_budget": reserved > budget + 1e-9,
                }
            )
        rows.sort(key=lambda row: (not row["over_budget"], row["account"], row["cluster"]))
        return rows

    def _fund_exposure(self, accounts_info: dict) -> dict:
        known = 0.0
        positions = 0
        reporting: set[str] = set()
        equity_total = 0.0
        equity_seen = False
        for info in accounts_info.values():
            if info.get("equity") is not None:
                equity_total += float(info["equity"])
                equity_seen = True
            for position in info.get("positions") or []:
                value = position.get("value")
                if value is None:
                    continue
                known += abs(float(value))
                positions += 1
                reporting.add(str(info.get("id")))
        if "paper" not in accounts_info:
            paper = self.account()
            if paper.get("equity") is not None:
                equity_total += float(paper["equity"])
                equity_seen = True
            for position in paper.get("positions") or []:
                known += abs(float(position.get("value") or 0.0))
                positions += 1
                reporting.add("paper_main")
        return {
            "known_notional_usd": round(known, 2),
            "open_positions": positions,
            "accounts_reporting": sorted(reporting),
            "equity_known_usd": round(equity_total, 2) if equity_seen else None,
            "note": (
                "Notional absoluto de las posiciones que reportan valor; "
                "MT5 no publica notional por posición y no se estima."
            ),
        }

    def _llm_status(self) -> dict:
        if not self.external:
            return {"ok": None, "model": self.settings.llm.model, "context": None}
        return self.cache.get("llm", 15.0, self._llm_check)

    def _llm_check(self) -> dict:
        cfg = self.settings.llm
        base = cfg.base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {cfg.api_key}"}
        result: dict[str, Any] = {
            "ok": False,
            "model": cfg.model,
            "base_url": base,
            "models": [],
            "context": None,
            "loaded_model": None,
            "error": None,
        }
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{base}/models", headers=headers)
                response.raise_for_status()
                data = response.json()
            result["models"] = [m.get("id") for m in data.get("data", []) if m.get("id")]
            result["ok"] = True
        except Exception as exc:  # conexión rechazada, timeout, HTTP...
            result["error"] = str(exc)[:200]
            return result

        origin = base.removesuffix("/v1")
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{origin}/api/v0/models")
            if response.status_code == 200:
                for model in response.json().get("data", []):
                    if model.get("state") != "loaded":
                        continue
                    model_id = str(model.get("id", ""))
                    if model_id == cfg.model or cfg.model in model_id or model_id.endswith(cfg.model):
                        ctx = model.get("loaded_context_length") or model.get("max_context_length")
                        result["context"] = int(ctx) if ctx else None
                        result["loaded_model"] = model_id
                        break
        except Exception:
            pass
        return result

    def _rules(self) -> PropRules:
        try:
            return from_yaml(
                self.settings.prop.firm,
                self.settings.prop.phase,  # type: ignore[arg-type]
                self.settings.prop.account_size,
                buffer_pct=self.settings.prop.buffer_pct,
            )
        except KeyError:
            return ftmo(
                self.settings.prop.account_size,
                self.settings.prop.phase,  # type: ignore[arg-type]
                buffer_pct=self.settings.prop.buffer_pct,
            )

    @staticmethod
    def _simulated_state(rules: PropRules, equity: float | None = None) -> AccountState:
        eq = float(equity if equity is not None else rules.account_size)
        return AccountState(
            balance=eq,
            equity=eq,
            initial_balance=rules.account_size,
            day_start_balance=eq,
            day_start_equity=eq,
            peak_balance=max(eq, rules.account_size),
            peak_equity=max(eq, rules.account_size),
        )

    def risk(self) -> dict:
        return self.cache.get("risk", 45.0, self._risk_uncached)

    def _risk_uncached(self) -> dict:
        rules = self._rules()
        try:
            from dataclasses import replace as dataclass_replace

            from .accounts import effective_limits, load_accounts

            account = load_accounts().get("ftmo_demo")
            if account is not None:
                limits = effective_limits(self.db_path, account)
                rules = dataclass_replace(
                    rules,
                    max_daily_loss_pct=limits.daily_loss_pct,
                    max_loss_pct=limits.max_drawdown_pct,
                )
        except Exception:
            pass
        payload: dict[str, Any] = {
            "generated_at": _now(),
            "rules": self._rules_payload(rules),
            "prop": {},
            "mt5": {"configured": bool(self.settings.mt5.login or self.settings.mt5.terminal_path)},
            "futures": self._futures_status(),
        }

        if not self.external:
            report = PropGuard(rules).evaluate(self._simulated_state(rules))
            payload["prop"] = self._guard_payload(report, source="simulado")
            payload["mt5"].update({"ok": None, "error": None})
            return payload

        broker = None
        try:
            from .execution.mt5 import MT5Broker

            broker = MT5Broker(
                path=self.settings.mt5.terminal_path,
                login=self.settings.mt5.login,
                server=self.settings.mt5.server,
                magic=self.settings.mt5.magic,
                deviation=self.settings.mt5.deviation,
                dry_run=True,
                db_path=self.db_path,
                timeout_ms=8000,
                server_utc_offset_hours=self.settings.mt5.server_utc_offset_hours,
                require_demo=self.settings.mt5.require_demo,
            )
            broker.connect()
            health = broker.health()
            positions = broker.positions()
            curve = broker.equity_series(180)

            if len(curve) >= 2:
                state = PropGuard.state_from_equity(rules, curve, initial_balance=rules.account_size)
                state.equity = health["equity"]
                state.balance = health["balance"]
                state.open_positions = len(positions)
                state.open_lots = sum(float(p.get("volume") or 0) for p in positions)
                state.server_time = None
            else:
                state = AccountState(
                    balance=health["balance"],
                    equity=health["equity"],
                    initial_balance=rules.account_size,
                    day_start_balance=health["balance"],
                    day_start_equity=health["equity"] - health.get("profit", 0.0),
                    peak_balance=health["balance"],
                    peak_equity=health["equity"],
                    open_positions=len(positions),
                    open_lots=sum(float(p.get("volume") or 0) for p in positions),
                )

            report = PropGuard(rules).evaluate(state)
            payload["mt5"] = {
                "configured": True,
                "ok": True,
                "error": None,
                "account": health,
                "positions": positions,
            }
            payload["prop"] = self._guard_payload(report, source="mt5")
        except Exception as exc:
            payload["mt5"] = {
                "configured": bool(self.settings.mt5.login or self.settings.mt5.terminal_path),
                "ok": False,
                "error": str(exc)[:400],
                "account": None,
                "positions": [],
            }
            report = PropGuard(rules).evaluate(self._simulated_state(rules))
            payload["prop"] = self._guard_payload(report, source="config")
        finally:
            if broker is not None:
                with contextlib.suppress(Exception):
                    broker.shutdown()
        return payload

    @staticmethod
    def _rules_payload(rules: PropRules) -> dict:
        return {
            "description": rules.describe(),
            "firm": rules.firm,
            "program": rules.program,
            "phase": rules.phase,
            "account_size": rules.account_size,
            "profit_target_pct": rules.profit_target_pct,
            "profit_target_usd": rules.profit_target_usd,
            "max_daily_loss_pct": rules.max_daily_loss_pct,
            "daily_limit_usd": rules.daily_limit_usd,
            "max_loss_pct": rules.max_loss_pct,
            "max_loss_usd": rules.max_loss_usd,
            "max_loss_mode": rules.max_loss_mode,
            "daily_loss_mode": rules.daily_loss_mode,
            "buffer_pct": rules.buffer_pct,
            "effective_daily_limit_usd": rules.effective_daily_limit_usd,
            "effective_max_loss_usd": rules.effective_max_loss_usd,
            "min_trading_days": rules.min_trading_days,
            "max_lots": rules.max_lots,
            "max_positions": rules.max_positions,
            "reset": f"{rules.reset_time} {rules.reset_tz}",
            "weekend_holding": rules.weekend_holding,
            "news_blackout_min": rules.news_blackout_min,
            "friday_cutoff_hour": rules.friday_cutoff_hour,
            "rollover_utc": rules.rollover_utc,
            "rollover_blackout_min": rules.rollover_blackout_min,
            "verify_against_contract": rules.verify_against_contract,
            "enabled": rules.enabled,
            "template": rules.template,
            "automation_allowed": rules.automation_allowed,
            "automation_note": rules.automation_note,
        }

    @staticmethod
    def _guard_payload(report, source: str) -> dict:
        data = _json_safe(asdict(report))
        data.update(
            {
                "source": source,
                "label": SEVERITY_LABEL.get(report.severity, report.severity),
                "summary": report.summary(),
            }
        )
        return data

    def _futures_status(self) -> dict:
        base = {
            "provider": "TopstepX / ProjectX",
            "base_url": self.settings.projectx.base_url,
            "configured": bool(self.settings.projectx.username and os.getenv("PROJECTX_API_KEY")),
            "dry_run": self.settings.projectx.dry_run,
            "require_simulated": self.settings.projectx.require_simulated,
        }
        if not base["configured"] or not self.external:
            base["ok"] = None
            base["note"] = (
                "Faltan PROJECTX_USERNAME / PROJECTX_API_KEY en .env. "
                "El adaptador está listo, pero no hay cuenta que consultar."
            )
            return base
        try:
            from .execution import get_projectx_broker

            broker = get_projectx_broker(self.settings, self.db_path, dry_run=True)
            try:
                base.update({"ok": True, "account": broker.health()})
            finally:
                broker.close()
        except Exception as exc:
            base.update({"ok": False, "error": str(exc)[:300]})
        return base

    # --------------------------------------------------------------- agentes

    def agent_runs(self, limit: int = 40) -> list[dict]:
        if not self.agent_runs_dir.exists():
            return []
        files = sorted(
            self.agent_runs_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
        runs = []
        for path in files:
            payload = _read_json(path, {}) or {}
            mode = payload.get("mode") or ("deep" if path.name.startswith("ta_") else "lite")
            ok = bool(payload.get("ok", True))
            rating = payload.get("rating") or ("ERROR" if not ok else "?")
            if payload.get("decision") or payload.get("final_trade_decision"):
                decision = payload.get("decision") or payload.get("final_trade_decision")
            elif not ok:
                decision = f"Run fallido: {payload.get('error', 'error desconocido')}"
            elif mode == "deep":
                decision = "Run deep completado; la tesis está en el informe completo."
            else:
                decision = ""
            runs.append(
                {
                    "file": path.name,
                    "mode": mode,
                    "ticker": payload.get("ticker", path.stem),
                    "date": payload.get("date"),
                    "rating": rating,
                    "confidence": payload.get("confidence"),
                    "horizon_days": payload.get("horizon_days"),
                    "elapsed_s": payload.get("elapsed_s"),
                    "model": payload.get("model"),
                    "generated_at": payload.get("generated_at") or _iso_from_timestamp(path.stat().st_mtime),
                    "decision": str(decision)[:1200],
                    "risks": str(payload.get("risks") or "")[:800],
                    "context": payload.get("context"),
                    "error": payload.get("error"),
                    "reports_path": payload.get("reports_path"),
                    "analysts": payload.get("analysts"),
                    "ok": ok,
                }
            )
        return runs

    def agent_report(self, file_name: str) -> dict:
        """Devuelve el informe markdown de un run deep (solo dentro del lab)."""
        runs_dir = self.agent_runs_dir.resolve()
        run_path = (self.agent_runs_dir / file_name).resolve()
        if not run_path.is_file() or runs_dir not in run_path.parents:
            raise FileNotFoundError(file_name)
        payload = _read_json(run_path, {}) or {}
        rel = payload.get("reports_path")
        if not rel:
            return {
                "exists": False,
                "path": None,
                "content": "",
                "reason": "El run no tiene informe guardado.",
            }
        root = self.root.resolve()
        report_path = (self.root / str(rel)).resolve()
        if not report_path.is_file() or root not in report_path.parents:
            return {
                "exists": False,
                "path": str(rel),
                "content": "",
                "reason": "El informe ya no existe en disco.",
            }
        return {
            "exists": True,
            "path": str(rel),
            "suffix": report_path.suffix.lower(),
            "content": _tail(report_path, 300 * 1024),
        }

    def deep_logs(self, limit: int = 8) -> list[dict]:
        if not self.logs_dir.exists():
            return []
        logs = []
        for path in sorted(self.logs_dir.glob("deep_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[
            :limit
        ]:
            tail = _tail(path, 4000)
            running = "EXIT=" not in tail
            logs.append(
                {
                    "name": path.name,
                    "mtime": _iso_from_timestamp(path.stat().st_mtime),
                    "size": path.stat().st_size,
                    "running": running,
                    "tail": tail[-1500:],
                }
            )
        return logs

    # --------------------------------------------------------------- dry-run

    def dryruns(self, limit: int = 10) -> list[dict]:
        if not self.dryrun_dir.exists():
            return []
        files = sorted(self.dryrun_dir.glob("*.json"), reverse=True)[:limit]
        out = []
        for path in files:
            payload = _read_json(path, {}) or {}
            actions = payload.get("actions") or []
            counts = Counter(str(a.get("status", "?")) for a in actions)
            out.append(
                {
                    "file": path.name,
                    "generated_at": payload.get("generated_at") or _iso_from_timestamp(path.stat().st_mtime),
                    "broker": payload.get("broker"),
                    "actions": actions,
                    "counts": dict(counts),
                }
            )
        return out

    # --------------------------------------------------------------- research

    def regime(self, symbol: str = "QQQ") -> dict:
        """Régimen causal del activo; informativo y cacheado 5 minutos."""
        key = f"regime:{symbol.upper()}"
        return self.cache.get(
            key,
            300.0,
            lambda: self._regime_payload(symbol),
        )

    def _regime_payload(self, symbol: str) -> dict:
        from .regimes import load_cached, report

        df, path = load_cached(symbol, self.settings.data.cache_dir)
        if df is None:
            return {
                "symbol": symbol.upper(),
                "status": "Sin datos",
                "reason": "sin caché local para régimen",
                "current": None,
                "metrics": None,
                "selector": [],
                "proposed_selector": None,
                "source": str(path) if path else None,
            }
        return report(symbol, df, source=str(path) if path else None)

    def research(self, limit: int = 15) -> dict:
        latest = _read_json(self.research_dir / "latest.json", {}) or {}
        proposals = _read_json(self.research_dir / "proposals.json", {}) or {}
        proposal_rows = proposals.get("proposals") if isinstance(proposals, dict) else None
        if proposal_rows is None:
            proposal_rows = latest.get("proposals") or []
        portfolio = _read_json(self.research_dir / "portfolio.json", {}) or {}
        costs = _read_json(self.research_dir / "costs.json", {}) or {}
        intraday = _read_json(self.research_dir / "intraday.json", {}) or {}
        return {
            "generated_at": latest.get("generated_at"),
            "rules": latest.get("rules"),
            "config": latest.get("config") or {},
            "candidates": latest.get("candidates") or len(latest.get("results") or []),
            "results": (latest.get("results") or [])[:limit],
            "proposals": proposal_rows,
            "datachecks": latest.get("datachecks") or proposals.get("datachecks") or {},
            "holdout": holdout_usage(self.db_path),
            "near_misses": latest.get("near_misses") or [],
            "pbo": latest.get("pbo"),
            "pbo_ok": latest.get("pbo_ok"),
            "pbo_by_symbol": latest.get("pbo_by_symbol") or {},
            "walk_forward": latest.get("walk_forward"),
            "walk_forward_ok": latest.get("walk_forward_ok"),
            "dsr_n_trials": latest.get("dsr_n_trials"),
            "dsr_trial_sr_std": latest.get("dsr_trial_sr_std"),
            "horizons": _read_json(self.research_dir / "horizons.json", {}) or {},
            "intraday": intraday,
            "clusters": _read_json(self.research_dir / "clusters.json", {}) or {},
            "portfolio": portfolio,
            "costs": costs,
            "profiles": self._research_profiles(portfolio, costs, intraday),
            "errors": latest.get("errors") or [],
        }

    @staticmethod
    def _research_profiles(
        portfolio: dict, costs: dict, intraday: dict
    ) -> list[dict]:
        """Resumen honesto por perfil: solo datos generados, sin inventar."""
        port = portfolio.get("portfolio") or {}
        mc = portfolio.get("monte_carlo") or []
        ftmo_120 = next(
            (
                row
                for row in mc
                if row.get("firm_id") == "ftmo" and row.get("horizon") == 120
            ),
            None,
        )
        fragile = costs.get("fragile_count")
        costs_note = (
            f"{fragile}/10 variantes frágiles a 2/20 bps"
            if fragile is not None
            else "sin informe de costes"
        )
        swing = {
            "profile": "swing_equity",
            "label": "Swing acciones/ETF",
            "status": "validado" if port else "sin datos",
            "total_return": port.get("total_return"),
            "sharpe": port.get("sharpe"),
            "max_drawdown": port.get("max_drawdown"),
            "pass_rate": ftmo_120.get("pass_rate") if ftmo_120 else None,
            "breach_rate": ftmo_120.get("breach_rate") if ftmo_120 else None,
            "notes": f"Cartera de 3 bots; FTMO 120d; {costs_note}.",
        }

        passed = intraday.get("passed")
        trials = intraday.get("n_trials")
        spread_ok = intraday.get("spread_reliable")
        if intraday.get("outcomes"):
            fx_status = "validado" if spread_ok else "no confiable"
            model = intraday.get("cost_model") or {}
            commission = model.get("commission") or {}
            calibrated = model.get("calibrated_cost_bps_median")
            fx_note = (
                f"{passed}/{trials} variantes pasan; spread "
                f"{'realista' if spread_ok else 'no realista'}; comisión "
                f"{'verificada' if commission.get('verified') else 'SIN VERIFICAR'}; "
                f"coste calibrado "
                f"{'sin datos' if calibrated is None else f'{calibrated:.2f} bps'}."
            )
        else:
            fx_status = "pendiente"
            fx_note = (
                "Sin datos M15/H1: `offset_source=unknown` y mercado cerrado; "
                "no se descargó ni se inventó el offset."
            )
        fx = {
            "profile": "intraday_fx",
            "label": "Intradía forex/CFD",
            "status": fx_status,
            "total_return": None,
            "sharpe": None,
            "max_drawdown": None,
            "pass_rate": None,
            "breach_rate": None,
            "notes": fx_note,
        }
        futures = {
            "profile": "intraday_futures",
            "label": "Intradía futuros",
            "status": "stub",
            "total_return": None,
            "sharpe": None,
            "max_drawdown": None,
            "pass_rate": None,
            "breach_rate": None,
            "notes": (
                "ProjectX sin credenciales/suscripción; proxy diario ES=F/NQ=F "
                "documentado, sin conclusiones intradía."
            ),
        }
        return [swing, fx, futures]

    def research_detail(self, artifact: str) -> dict:
        """Curva de equity/drawdown de una variante frente a buy&hold.

        Solo lee parquet locales generados por `lab research`; si falta el
        artefacto o no es válido, lanza FileNotFoundError/ValueError.
        """
        root = self.research_dir.resolve()
        rel = str(artifact or "").strip().replace("\\", "/")
        if not rel or not rel.endswith(".parquet") or ".." in Path(rel).parts:
            raise ValueError("artefacto inválido")
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError(f"sin datos para {rel}")
        frame = pd.read_parquet(path)
        if "equity" not in frame.columns or "buy_hold" not in frame.columns:
            raise ValueError("artefacto sin equity/buy_hold")
        data = frame[["equity", "buy_hold"]].apply(pd.to_numeric, errors="coerce").dropna()
        if data.empty:
            raise ValueError("artefacto sin datos")
        data = data.sort_index()
        equity = data["equity"].astype(float)
        buy_hold = data["buy_hold"].astype(float)
        eq_dd = equity / equity.cummax() - 1.0
        bh_dd = buy_hold / buy_hold.cummax() - 1.0
        returns = equity.pct_change().dropna()
        std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
        sharpe = (
            float(returns.mean() / std * math.sqrt(252)) if std > 0 else 0.0
        )
        step = max(1, len(data) // 400)
        indexes = list(range(0, len(data), step))
        if indexes[-1] != len(data) - 1:
            indexes.append(len(data) - 1)
        points = []
        for i in indexes:
            ts = data.index[i]
            points.append(
                {
                    "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "equity": float(equity.iloc[i]),
                    "buy_hold": float(buy_hold.iloc[i]),
                    "drawdown": float(eq_dd.iloc[i]),
                    "buy_hold_drawdown": float(bh_dd.iloc[i]),
                }
            )
        return {
            "ok": True,
            "artifact": rel,
            "rows": len(data),
            "points": points,
            "stats": {
                "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1.0),
                "max_drawdown": float(eq_dd.min()),
                "sharpe": sharpe,
                "buy_hold_total_return": float(buy_hold.iloc[-1] / buy_hold.iloc[0] - 1.0),
                "buy_hold_max_drawdown": float(bh_dd.min()),
            },
            **self._artifact_multiverse(path),
        }

    def _artifact_multiverse(self, path: Path) -> dict:
        """Multiverse por operación si el artefacto tiene sidecar de trades."""
        sidecar = path.with_suffix(".trades.parquet")
        if not sidecar.is_file():
            return {
                "multiverse": None,
                "multiverse_reason": (
                    "Sin datos: artefacto sin operaciones "
                    "(no existe .trades.parquet)"
                ),
                "artifact_trades": 0,
            }
        try:
            frame = pd.read_parquet(sidecar)
            if "pnl" not in frame.columns:
                raise ValueError("sidecar sin columna pnl")
            pnls = pd.to_numeric(frame["pnl"], errors="coerce").dropna().tolist()
            days = (
                frame["day"].astype(str).tolist()
                if "day" in frame.columns
                else []
            )
        except Exception as exc:
            return {
                "multiverse": None,
                "multiverse_reason": f"Sin datos: sidecar inválido ({exc})",
                "artifact_trades": 0,
            }
        if len(pnls) < 2:
            return {
                "multiverse": None,
                "multiverse_reason": "Sin datos: menos de 2 operaciones",
                "artifact_trades": len(pnls),
            }
        latest = _read_json(self.research_dir / "latest.json", {}) or {}
        meta = latest.get("rules_meta") or {}
        try:
            if meta:
                allowed = set(PropRules.__dataclass_fields__)
                rules = PropRules(
                    **{key: value for key, value in meta.items() if key in allowed}
                )
            else:
                rules = from_yaml(
                    self.settings.prop.firm,
                    self.settings.prop.phase,
                    self.settings.prop.account_size,
                    buffer_pct=self.settings.prop.buffer_pct,
                )
        except Exception:
            rules = ftmo(self.settings.prop.account_size, self.settings.prop.phase)
        day_sizes: list[int] = []
        if len(days) == len(pnls):
            last = None
            for day in days:
                if day != last:
                    day_sizes.append(0)
                    last = day
                day_sizes[-1] += 1
        try:
            multiverse = multiverse_by_trade(
                rules,
                pnls,
                n_paths=1_000,
                seed=42,
                day_sizes=day_sizes or None,
            )
        except ValueError as exc:
            return {
                "multiverse": None,
                "multiverse_reason": f"Sin datos: {exc}",
                "artifact_trades": len(pnls),
            }
        return {
            "multiverse": multiverse,
            "multiverse_reason": None,
            "artifact_trades": len(pnls),
            "rules": rules.describe(),
        }

    # --------------------------------------------------------------- mercado

    def market(self, limit: int = 30) -> dict:
        """Watchlist desde la caché local de parquet; nunca descarga datos."""

        def collect() -> dict:
            cache_dir = self.root / "data" / "cache"
            out = {
                "as_of": _now(),
                "source": str(cache_dir),
                "rows": [],
                "count": 0,
                "breadth": {"up": 0, "down": 0, "flat": 0, "avg_1d": None},
                "error": None,
            }
            if not cache_dir.exists():
                out["error"] = "sin caché local"
                return out
            newest: dict[str, Path] = {}
            try:
                files = list(cache_dir.glob("*.parquet"))
            except OSError as exc:
                out["error"] = str(exc)[:200]
                return out
            for path in files:
                safe = path.name.split("__", 1)[0]
                current = newest.get(safe)
                if current is None or path.stat().st_mtime > current.stat().st_mtime:
                    newest[safe] = path
            rows = []
            for safe, path in sorted(newest.items()):
                try:
                    frame = pd.read_parquet(path, columns=["close"])
                    close = frame["close"].dropna().astype(float)
                    if len(close) < 25:
                        continue
                    last = float(close.iloc[-1])

                    def ret(days: int) -> float | None:
                        if len(close) <= days:
                            return None
                        return last / float(close.iloc[-1 - days]) - 1.0

                    def sma(days: int) -> float | None:
                        if len(close) < days:
                            return None
                        return float(close.iloc[-days:].mean())

                    sma20, sma50, sma200 = sma(20), sma(50), sma(200)
                    trend = "mixed"
                    if sma20 and sma50 and sma200:
                        if last > sma20 > sma50 > sma200:
                            trend = "up"
                        elif last < sma20 < sma50 < sma200:
                            trend = "down"
                    last_ts = close.index[-1]
                    as_of = (
                        str(last_ts.date())
                        if hasattr(last_ts, "date")
                        else str(last_ts)
                    )
                    stale_days = None
                    if hasattr(last_ts, "date"):
                        stale_days = (datetime.now(UTC).date() - last_ts.date()).days
                    symbol = safe[:-2] + "=X" if safe.endswith("_X") else safe
                    rows.append(
                        {
                            "symbol": symbol,
                            "safe": safe,
                            "close": last,
                            "return_1d": ret(1),
                            "return_5d": ret(5),
                            "return_20d": ret(20),
                            "sma20": sma20,
                            "sma50": sma50,
                            "sma200": sma200,
                            "trend": trend,
                            "as_of": as_of,
                            "stale_days": stale_days,
                            "spark": [round(float(x), 6) for x in close.iloc[-60:].tolist()],
                            "source_file": path.name,
                        }
                    )
                except Exception:
                    continue
            rows = rows[:limit]
            up = sum(1 for r in rows if (r["return_1d"] or 0) > 0)
            down = sum(1 for r in rows if (r["return_1d"] or 0) < 0)
            flat = len(rows) - up - down
            avg = (
                sum(float(r["return_1d"]) for r in rows if r["return_1d"] is not None)
                / max(1, sum(1 for r in rows if r["return_1d"] is not None))
                if rows
                else None
            )
            out.update(
                {
                    "rows": rows,
                    "count": len(rows),
                    "breadth": {
                        "up": up,
                        "down": down,
                        "flat": flat,
                        "avg_1d": avg,
                    },
                }
            )
            return out

        return self.cache.get("market", 60.0, collect)

    # -------------------------------------------------------------- calendario

    def calendar(self, days: int = 60) -> dict:
        """Próximos eventos macro desde SQLite; no consulta Finnhub todavía."""
        out = {
            "status": "missing",
            "events": [],
            "count": 0,
            "fetched_at": None,
            "message": "",
            "error": None,
        }
        if not self.db_path.exists():
            out["error"] = "sin base de datos"
            return out
        try:
            with contextlib.closing(_connect_ro(self.db_path)) as con:
                cutoff = (datetime.now(UTC) + timedelta(days=days)).isoformat()
                rows = con.execute(
                    "SELECT event, ts_utc, importance, source FROM macro_events "
                    "WHERE ts_utc >= ? AND ts_utc <= ? ORDER BY ts_utc LIMIT 30",
                    (_now(), cutoff),
                ).fetchall()
                fetch = con.execute(
                    "SELECT status, fetched_at, message FROM calendar_fetches "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
            out["events"] = [
                {
                    "event": row["event"],
                    "ts_utc": row["ts_utc"],
                    "importance": row["importance"] or "medium",
                    "source": row["source"] or "manual",
                }
                for row in rows
            ]
            out["count"] = len(out["events"])
            if fetch:
                out["status"] = str(fetch["status"])
                out["fetched_at"] = fetch["fetched_at"]
                out["message"] = str(fetch["message"] or "")
            elif out["events"]:
                out["status"] = "manual"
            else:
                out["status"] = "empty"
        except sqlite3.Error as exc:
            out["status"] = "unavailable"
            out["error"] = str(exc)[:240]
        return self.cache.get(f"calendar:{days}", 30.0, lambda: out)

    # --------------------------------------------------------------- decisiones

    def decisions(self) -> dict:
        from .decisions import report, report_by_source

        def collect() -> dict:
            out = {
                "rows": [],
                "by_source": [],
                "total": 0,
                "min_sample": 30,
                "error": None,
            }
            if not self.db_path.exists():
                out["error"] = "sin base de datos"
                return out
            try:
                rows = report(self.db_path)
                by_source = report_by_source(self.db_path)
            except Exception as exc:
                out["error"] = str(exc)[:240]
                return out
            out["rows"] = rows
            out["by_source"] = by_source
            out["total"] = sum(int(row.get("n") or 0) for row in rows)
            return out

        return self.cache.get("decisions", 60.0, collect)

    def agent_comparisons(self) -> dict:
        """Acuerdo lite/deep y procedencia por fuente; solo lectura."""
        from .agent_compare import report

        def collect() -> dict:
            out = {
                "n": 0,
                "agreement_rate": None,
                "matrix": {},
                "mean_target_diff": None,
                "by_source": [],
                "insufficient": True,
                "sample_warning": "sin comparaciones",
                "error": None,
            }
            if not self.db_path.exists():
                out["error"] = "sin base de datos"
                return out
            try:
                out.update(report(self.db_path))
            except Exception as exc:
                out["error"] = str(exc)[:240]
            return out

        return self.cache.get("agent_comparisons", 60.0, collect)

    def lifecycle(self) -> dict:
        """Incubadora: estados, métricas forward y eventos; no activa bots."""
        from .lifecycle import events, load_config, status

        def collect() -> dict:
            out = {
                "bots": [],
                "events": [],
                "count": 0,
                "incubating": 0,
                "evaluated": 0,
                "promotable": 0,
                "max_concurrent": 3,
                "config": {},
                "error": None,
            }
            if not self.db_path.exists():
                out["error"] = "sin base de datos"
                return out
            try:
                config = load_config()
                rows = status(self.db_path, settings=self.settings)
                history = events(self.db_path, limit=20)
            except Exception as exc:
                out["error"] = str(exc)[:240]
                return out
            out.update(
                {
                    "bots": rows,
                    "events": history,
                    "count": len(rows),
                    "incubating": sum(
                        1 for row in rows if row.get("state") == "incubando"
                    ),
                    "evaluated": sum(
                        1 for row in rows if row.get("state") == "evaluado"
                    ),
                    "promotable": sum(
                        1 for row in rows if row.get("state") == "promovible"
                    ),
                    "max_concurrent": config["max_concurrent"],
                    "config": {
                        "gate": config["gate"],
                        "criteria": config["criteria"],
                    },
                }
            )
            return out

        return self.cache.get("lifecycle", 60.0, collect)

    def decisions_compare(self) -> dict:
        """Comparación LLM/buy&hold/trend bajo demanda; cachea 5 minutos."""
        from .decisions import compare

        def collect() -> dict:
            if not self.db_path.exists():
                return {"error": "sin base de datos"}
            try:
                return compare(self.db_path, self.root / "data" / "cache")
            except Exception as exc:
                return {"error": str(exc)[:240]}

        return self.cache.get("decisions_compare", 300.0, collect)

    def model_ranking(self) -> dict:
        """Ranking de modelos por acierto a 20 días; cachea 5 minutos."""
        from .agent_compare import model_ranking

        def collect() -> dict:
            if not self.db_path.exists():
                return {"items": [], "error": "sin base de datos"}
            try:
                return {"items": model_ranking(self.db_path)}
            except Exception as exc:
                return {"items": [], "error": str(exc)[:240]}

        return self.cache.get("model_ranking", 300.0, collect)

    def tca(self) -> dict:
        """Ejecución (TCA): slippage EWMA frente al supuesto, por bot."""
        from .tca import build_tca

        def collect() -> dict:
            if not self.db_path.exists():
                return {"rows": [], "status": "sin datos", "error": "sin base de datos"}
            try:
                return build_tca(self.db_path)
            except Exception as exc:
                return {"rows": [], "status": "sin datos", "error": str(exc)[:240]}

        return self.cache.get("tca", 120.0, collect)

    def conditioners_today(self) -> dict:
        """Flags de condicionadores de la última sesión (solo lectura)."""
        from .conditioners import today_flags

        def collect() -> dict:
            if not self.db_path.exists():
                return {"items": [], "error": "sin base de datos"}
            try:
                symbols = [str(spec.universe[0]).upper() for spec in load_bots() if spec.universe]
                items = [
                    today_flags(symbol, db_path=self.db_path)
                    for symbol in sorted(set(symbols))[:8]
                ]
                return {"items": items, "generated_at": _now()}
            except Exception as exc:
                return {"items": [], "error": str(exc)[:240]}

        return self.cache.get("conditioners_today", 300.0, collect)

    def funnel(self) -> dict:
        """Embudo de etapas del laboratorio (solo lectura)."""
        from .funnel import funnel as funnel_state

        def collect() -> dict:
            if not self.db_path.exists():
                return {"counts": {}, "error": "sin base de datos"}
            try:
                return funnel_state(self.db_path)
            except Exception as exc:
                return {"counts": {}, "error": str(exc)[:240]}

        return self.cache.get("funnel", 120.0, collect)

    def discipline(self) -> dict:
        """Bloqueos por guard en los ?ltimos d?as (solo lectura)."""
        from .funnel import discipline as discipline_state

        def collect() -> dict:
            if not self.db_path.exists():
                return {"blocked_by_guard": {}, "error": "sin base de datos"}
            try:
                return discipline_state(self.db_path)
            except Exception as exc:
                return {"blocked_by_guard": {}, "error": str(exc)[:240]}

        return self.cache.get("discipline", 120.0, collect)

    def slo(self) -> dict:
        """SLO operativo: frescura por símbolo, reloj, drift y último latido."""
        from .alerts import last_heartbeat
        from .clock import STATUS_AVISO as CLOCK_AVISO
        from .clock import STATUS_FALLA as CLOCK_FALLA
        from .clock import check_clock
        from .db import connect
        from .freshness import STATUS_AVISO as FRESH_AVISO
        from .freshness import STATUS_FALLA as FRESH_FALLA
        from .freshness import check as check_freshness

        def collect() -> dict:
            symbols: list[tuple[str, str]] = []
            drift: dict = {"status": "sin_datos", "detail": "sin datos: no hay reconciliación"}
            try:
                with connect(self.db_path) as con:
                    rows = con.execute(
                        "SELECT symbol, timeframe, MAX(id) AS last FROM data_freshness "
                        "GROUP BY symbol, timeframe ORDER BY symbol LIMIT 12"
                    ).fetchall()
                    symbols = [(str(row["symbol"]), str(row["timeframe"])) for row in rows]
                    last = con.execute(
                        "SELECT * FROM reconciliation ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                if last is not None:
                    diff_positions = int(last["diff_positions"] or 0)
                    diff_equity = float(last["diff_equity"] or 0.0)
                    if diff_positions or abs(diff_equity) > 1.0:
                        drift = {
                            "status": "aviso",
                            "detail": (
                                f"{diff_positions} posición(es) de diferencia, "
                                f"equity {diff_equity:+,.2f}"
                            ),
                            "ts": str(last["ts"] or ""),
                        }
                    else:
                        drift = {
                            "status": "ok",
                            "detail": "broker y base coinciden",
                            "ts": str(last["ts"] or ""),
                        }
            except Exception as exc:
                drift = {"status": "sin_datos", "detail": str(exc)[:200]}

            freshness = [check_freshness(symbol, timeframe) for symbol, timeframe in symbols]
            clock_state = check_clock()

            status = "ok"
            if any(item["status"] == FRESH_FALLA for item in freshness) or (
                clock_state["status"] == CLOCK_FALLA
            ):
                status = "falla"
            elif (
                any(item["status"] == FRESH_AVISO for item in freshness)
                or clock_state["status"] == CLOCK_AVISO
                or drift.get("status") == "aviso"
            ):
                status = "aviso"

            return {
                "status": status,
                "generated_at": _now(),
                "freshness": freshness,
                "clock": clock_state,
                "position_drift": drift,
                "heartbeat": last_heartbeat(self.db_path),
                "symbols": len(freshness),
            }

        return self.cache.get("slo", 60.0, collect)

    # ------------------------------------------------------------------- repos

    def repo_audit(self) -> dict:
        return {
            "audited_at": "2026-11-07",
            "policy": (
                "Solo se reutiliza código MIT. De AGPL-3.0 se copian ideas de UX, "
                "no código ni assets. Sin dependencias nuevas."
            ),
            "repos": REPO_AUDIT,
        }

    # ------------------------------------------------------------------ bots

    def bots(self) -> list[dict]:
        try:
            specs = load_bots(self.bots_file)
        except Exception:
            return []
        latest_actions: dict[str, list[dict]] = {}
        recent = self.dryruns(limit=1)
        if recent:
            for action in recent[0]["actions"]:
                latest_actions.setdefault(action.get("bot", ""), []).append(action)
        evaluations = latest_evaluations(self.db_path)
        out = []
        for spec in specs:
            data = asdict(spec)
            data["last_actions"] = latest_actions.get(spec.id, [])
            data["evaluation"] = evaluations.get(spec.id)
            data["proposed"] = False
            out.append(data)
        for spec in load_proposed():
            data = asdict(spec)
            data["last_actions"] = []
            data["evaluation"] = evaluations.get(spec.id)
            data["proposed"] = True
            out.append(data)
        try:
            from .ea_registry import as_bot_row, load_eas

            for ea in load_eas():
                out.append(as_bot_row(ea, db_path=self.db_path))
        except Exception:
            pass
        return out

    # ------------------------------------------------------------------ logs

    def logs(self, limit: int = 40) -> list[dict]:
        if not self.logs_dir.exists():
            return []
        rows = []
        for path in self.logs_dir.rglob("*.log"):
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append(
                {
                    "name": path.relative_to(self.logs_dir).as_posix(),
                    "size": stat.st_size,
                    "mtime": _iso_from_timestamp(stat.st_mtime),
                }
            )
        rows.sort(key=lambda r: r["mtime"], reverse=True)
        return rows[:limit]

    def tail_log(self, name: str, max_bytes: int = MAX_LOG_BYTES) -> dict:
        base = self.logs_dir.resolve()
        path = (self.logs_dir / name).resolve()
        if not path.is_file() or (path != base and base not in path.parents):
            raise FileNotFoundError(name)
        text = _tail(path, max_bytes)
        return {
            "name": name,
            "content": text,
            "size": path.stat().st_size,
            "truncated": path.stat().st_size > max_bytes,
        }

    # ------------------------------------------------------------- scheduler

    def git_info(self) -> dict:
        """Estado del repositorio local para mostrarlo en el panel."""
        if not self.external:
            return {"ok": None}
        return self.cache.get("git", 30.0, self._git_check)

    def _git_check(self) -> dict:
        def run(*args: str) -> str:
            completed = subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return completed.stdout.strip()

        try:
            branch = run("rev-parse", "--abbrev-ref", "HEAD")
            commit = run("rev-parse", "--short", "HEAD")
            dirty = bool(run("status", "--porcelain"))
            remote = run("remote", "get-url", "origin")
            return {
                "ok": bool(commit),
                "branch": branch or "—",
                "commit": commit or "—",
                "dirty": dirty,
                "remote": remote,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    def _scheduler(self) -> dict:
        if not self.external:
            return {"ok": None, "tasks": []}
        return self.cache.get("scheduler", 60.0, self._scheduler_check)

    @staticmethod
    def _scheduler_check() -> dict:
        script = r"""
$names = @('TradingLab-DryRun','TradingLab-Backup','TradingLab-Web','TradingLab-Intel','TradingLab-Agents','TradingLab-LMStudio')
$rows = foreach ($n in $names) {
  $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
  if ($t) {
    $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue
    [pscustomobject]@{
      name = $t.TaskName
      state = [string]$t.State
      last_run = if ($i -and $i.LastRunTime) { $i.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss') } else { $null }
      next_run = if ($i -and $i.NextRunTime) { $i.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss') } else { $null }
      last_result = if ($i) { $i.LastTaskResult } else { $null }
      missed = if ($i) { $i.NumberOfMissedRuns } else { $null }
    }
  }
}
@($rows) | ConvertTo-Json -Compress
"""
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=12,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raw = (completed.stdout or "").strip().lstrip("\ufeff")
            if not raw:
                return {"ok": False, "tasks": [], "error": "schtasks sin respuesta"}
            data = json.loads(raw)
            tasks = data if isinstance(data, list) else [data]
            return {"ok": True, "tasks": tasks}
        except Exception as exc:
            return {"ok": False, "tasks": [], "error": str(exc)[:200]}

    # -------------------------------------------------------------- acciones

    def _lab_command(self) -> list[str]:
        return [sys.executable, "-m", "tradinglab.cli"]

    def start_action(self, kind: str, ticker: str | None = None) -> tuple[dict | None, str | None]:
        with self._action_lock:
            if self._action and self._action.get("status") == "running":
                return None, "Ya hay una acción en curso. Espera a que termine."

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if kind == "dryrun":
                cmd = self._lab_command() + ["orchestrate", "--dry-run"]
                log_rel = f"dryrun/manual_{stamp}.log"
                label = "Dry-run del orquestador"
                ticker = None
            elif kind == "agent":
                ticker = (ticker or "").strip().upper()
                if not TICKER_RE.match(ticker):
                    return None, "Ticker inválido. Usa un símbolo como NVDA o SPY."
                cmd = self._lab_command() + ["agent", ticker, "--mode", "lite"]
                log_rel = f"lite_{ticker}_{stamp}.log"
                label = f"Análisis lite · {ticker}"
            else:
                return None, "Acción desconocida."

            log_path = self.logs_dir / log_rel
            log_path.parent.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"

            try:
                handle = log_path.open("w", encoding="utf-8")
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.root),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                handle.close()
            except Exception as exc:
                return None, f"No se pudo lanzar: {exc}"

            self._action = {
                "id": stamp,
                "kind": kind,
                "label": label,
                "ticker": ticker,
                "status": "running",
                "pid": proc.pid,
                "started_at": _now(),
                "finished_at": None,
                "exit_code": None,
                "log": log_rel,
            }
            threading.Thread(target=self._watch_action, args=(proc,), daemon=True).start()
            return dict(self._action), None

    def _watch_action(self, proc: subprocess.Popen) -> None:
        code = proc.wait()
        with self._action_lock:
            if self._action:
                self._action.update(
                    {
                        "status": "done" if code == 0 else "error",
                        "exit_code": code,
                        "finished_at": _now(),
                    }
                )

    def action_status(self) -> dict:
        with self._action_lock:
            return dict(self._action) if self._action else {"status": "idle"}


# ------------------------------------------------------------------ servidor


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    # En Windows, allow_reuse_address=True permite que dos procesos escuchen el
    # mismo puerto y el navegador acabe hablando con el servidor viejo.
    # El panel es local y de un solo proceso: prohibimos el bind duplicado.
    allow_reuse_address = False
    allow_reuse_port = False

    def handle_error(self, request, client_address) -> None:
        """Silencia cortes normales del navegador; el resto sí se registra."""
        exc = sys.exc_info()[1]
        if isinstance(
            exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)
        ):
            return
        super().handle_error(request, client_address)

    def __init__(self, address: tuple[str, int], data: LabData) -> None:
        super().__init__(address, DashboardHandler)
        self.data = data
        # Token por proceso: sin él, cualquier POST se rechaza con 403.
        self.csrf_token = secrets.token_urlsafe(32)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer
    server_version = f"TradingLab/{__version__}"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------- utilidades

    def log_message(self, fmt: str, *args) -> None:  # silencio en consola
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status=status)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 64 * 1024))
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    # ------------------------------------------------------------- seguridad

    def _host_ok(self) -> bool:
        """Solo se acepta Host=127.0.0.1 (con puerto opcional)."""
        raw = (self.headers.get("Host") or "").strip()
        if not raw:
            return False
        try:
            return (urlparse(f"//{raw}").hostname or "") == LOCAL_HOST
        except ValueError:
            return False

    def _origin_ok(self) -> bool:
        """Si el navegador envía Origin, debe ser local; si no, manda el token."""
        raw = self.headers.get("Origin")
        if not raw:
            return True
        if raw == "null":
            return False
        try:
            parsed = urlparse(raw)
        except ValueError:
            return False
        return parsed.scheme in ("http", "https") and parsed.hostname == LOCAL_HOST

    def _csrf_ok(self) -> bool:
        supplied = self.headers.get("X-CSRF-Token") or ""
        token = getattr(self.server, "csrf_token", "")
        return bool(token) and secrets.compare_digest(supplied, token)

    def _write_gate(self) -> str | None:
        if not self._host_ok():
            return "Host no permitido: usa 127.0.0.1"
        if not self._origin_ok():
            return "Origin no permitido"
        if not self._csrf_ok():
            return "CSRF token inválido"
        return None

    def _audit_learning(self, action: str, lesson_id: int, result: str) -> None:
        try:
            from .runtime import record_console_action

            record_console_action(
                self.server.data.db_path,
                action=action,
                params={"lesson_id": lesson_id},
                result=result,
                ok=True,
                actor="console",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------ rutas

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if not self._host_ok():
            self._error(403, "Host no permitido: usa 127.0.0.1")
            return
        try:
            if path in ("/", "/index.html"):
                if not INDEX_FILE.exists():
                    self._error(500, "Falta webui/index.html")
                    return
                self._send(200, INDEX_FILE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/session":
                self._json({"csrf": self.server.csrf_token})
            elif path == "/api/health":
                self._json({"ok": True, "version": __version__, "build": BUILD_ID, "time": _now()})
            elif path == "/api/overview":
                self._json(self.server.data.overview())
            elif path == "/api/ai-trader":
                from .ai_trader import panel

                try:
                    equity = float(self.server.data.account().get("equity") or 0)
                except Exception:
                    equity = None
                account_risk = None
                try:
                    account_risk = (
                        self.server.data.risk().get("prop") or {}
                    )
                except Exception:
                    account_risk = None
                self._json(panel(
                    self.server.data.db_path,
                    equity=equity,
                    account_risk=account_risk,
                ))
            elif path == "/api/risk":
                self._json(self.server.data.risk())
            elif path == "/api/market":
                self._json(self.server.data.market())
            elif path == "/api/instruments":
                self._json({
                    "items": catalog(),
                    "validation": validate_catalog(),
                })
            elif path == "/api/markets":
                payload = market_payload()
                payload["pilots"] = pilot_status(
                    self.server.data.db_path, self.server.data.settings
                )
                self._json(payload)
            elif path == "/api/calendar":
                self._json(self.server.data.calendar())
            elif path == "/api/research/detail":
                artifact = (parse_qs(urlparse(self.path).query).get("artifact") or [""])[0]
                try:
                    self._json(self.server.data.research_detail(artifact))
                except FileNotFoundError:
                    self._json({"ok": False, "error": "sin datos"}, status=404)
                except ValueError as exc:
                    self._error(400, str(exc))
            elif path == "/api/research/horizons":
                self._json(self.server.data.research().get("horizons") or {})
            elif path == "/api/research/intraday":
                self._json(self.server.data.research().get("intraday") or {})
            elif path == "/api/research/clusters":
                self._json(self.server.data.research().get("clusters") or {})
            elif path == "/api/research/portfolio":
                self._json(self.server.data.research().get("portfolio") or {})
            elif path == "/api/research/costs":
                self._json(self.server.data.research().get("costs") or {})
            elif path == "/api/decisions":
                self._json(self.server.data.decisions())
            elif path == "/api/decisions/compare":
                self._json(self.server.data.decisions_compare())
            elif path == "/api/repos":
                self._json(self.server.data.repo_audit())
            elif path == "/api/accounts":
                self._json({"accounts": self.server.data.accounts()})
            elif path == "/api/fund":
                self._json(self.server.data.fund())
            elif path == "/api/operator":
                self._json(self.server.data.operator.status())
            elif path == "/api/learning":
                self._json(self.server.data.learning())
            elif path == "/api/models":
                self._json(registry_payload(self.server.data.db_path))
            elif path == "/api/models/ranking":
                self._json(self.server.data.model_ranking())
            elif path == "/api/slo":
                self._json(self.server.data.slo())
            elif path == "/api/funnel":
                self._json(self.server.data.funnel())
            elif path == "/api/discipline":
                self._json(self.server.data.discipline())
            elif path == "/api/conditioners/today":
                self._json(self.server.data.conditioners_today())
            elif path == "/api/tca":
                self._json(self.server.data.tca())
            elif path == "/api/reports":
                self._json({"files": list_exports()})
            elif path == "/api/reports/preview":
                file_name = (parse_qs(urlparse(self.path).query).get("file") or [""])[0]
                try:
                    self._json(preview_file(file_name))
                except ValueError as exc:
                    self._error(400, str(exc))
            elif path == "/api/journal":
                params = parse_qs(urlparse(self.path).query)

                def value(name: str) -> str | None:
                    return (params.get(name) or [None])[0] or None

                try:
                    self._json(
                        self.server.data.journal(
                            bot=value("bot"),
                            account=value("account"),
                            profile=value("profile"),
                            ticker=value("ticker"),
                            since=value("since"),
                            until=value("until"),
                            group_by=value("group_by") or "bot",
                            limit=int(value("limit") or 200),
                        )
                    )
                except ValueError as exc:
                    self._error(400, str(exc))
            elif path == "/api/drift":
                params = parse_qs(urlparse(self.path).query)
                raw = (params.get("min_trades") or ["20"])[0]
                try:
                    min_trades = max(1, int(raw))
                except ValueError:
                    self._error(400, "min_trades inválido")
                    return
                self._json(self.server.data.drift(min_trades=min_trades))
            elif path == "/api/bots":
                self._json({"bots": self.server.data.bots()})
            elif path == "/api/action":
                self._json(self.server.data.action_status())
            elif path == "/api/logs":
                self._json({"logs": self.server.data.logs()})
            elif path == "/api/agent-report":
                file_name = (parse_qs(urlparse(self.path).query).get("file") or [""])[0]
                try:
                    self._json(self.server.data.agent_report(file_name))
                except FileNotFoundError:
                    self._error(404, f"Run no encontrado: {file_name}")
            elif path.startswith("/api/logs/"):
                name = unquote(path[len("/api/logs/") :])
                try:
                    self._json(self.server.data.tail_log(name))
                except FileNotFoundError:
                    self._error(404, f"Log no encontrado: {name}")
            else:
                self._error(404, "Ruta no encontrada")
        except Exception as exc:
            self._error(500, str(exc)[:500])

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._body()  # consumir siempre el cuerpo (keep-alive)
        problem = self._write_gate()
        if problem is not None:
            self._error(403, problem)
            return
        if path.startswith("/api/operator/") and self.headers.get("X-Operator-Client") != "console":
            self._error(403, "Solo la consola puede llamar al modo operador")
            return
        try:
            if path not in WRITE_ROUTES:
                self._error(404, "Ruta no encontrada")
            elif path == "/api/actions/dryrun":
                action, error = self.server.data.start_action("dryrun")
                if error:
                    self._error(409, error)
                else:
                    self._json(action, status=202)
            elif path == "/api/actions/agent":
                action, error = self.server.data.start_action("agent", body.get("ticker"))
                if error:
                    self._error(409, error)
                else:
                    self._json(action, status=202)
            elif path == "/api/bots/evaluate":
                results = evaluate_all(self.server.data.settings, self.server.data.db_path)
                self._json({"results": results})
            elif path == "/api/bots/archive":
                bot = str(body.get("id") or "").strip()
                if not bot:
                    self._error(400, "Falta id")
                else:
                    self._json({"archived": archive_bot(bot, str(body.get("reason") or "manual"))})
            elif path == "/api/bots/restore":
                bot = str(body.get("id") or "").strip()
                if not bot:
                    self._error(400, "Falta id")
                else:
                    self._json({"archived": restore_bot(bot)})
            elif path == "/api/bots/propose":
                spec = propose_bot(
                    id=str(body.get("id") or "").strip(),
                    strategy=str(body.get("strategy") or "trend").strip(),
                    universe=[x.strip() for x in str(body.get("universe") or "SPY").split(",") if x.strip()],
                    params=body.get("params") or {},
                    exposure=float(body.get("exposure") or 1.0),
                    description=str(body.get("description") or ""),
                )
                self._json({"bot": asdict(spec)}, status=201)
            elif path == "/api/fund/limits":
                changes = body.get("changes")
                if not isinstance(changes, dict) or not changes:
                    self._error(400, "Falta changes")
                else:
                    result = set_limits(
                        self.server.data.db_path,
                        account_id=str(body.get("account") or "").strip(),
                        changes=changes,
                        origin="console",
                        confirm=bool(body.get("confirm")),
                    )
                    if result["ok"]:
                        self.server.data.cache.clear()
                        self._json(result)
                    else:
                        self._json(result, status=400)
            elif path == "/api/fund/killswitch":
                action = str(body.get("action") or "").strip()
                try:
                    if action == "activate":
                        result = self.server.data.operator.activate_killswitch(
                            reason=str(
                                body.get("reason")
                                or "activación manual desde la consola"
                            ),
                            confirm=bool(body.get("confirm")),
                        )
                    elif action == "reset":
                        result = self.server.data.operator.reset_killswitch(
                            pin=str(body.get("pin") or ""),
                            confirm=bool(body.get("confirm")),
                        )
                    else:
                        self._error(400, "action debe ser activate o reset")
                        return
                except OperatorError as exc:
                    self._error(exc.status, str(exc))
                    return
                self.server.data.cache.clear()
                self._json(result)
            elif path == "/api/fund/pause/resume":
                account = str(body.get("account") or "").strip()
                try:
                    result = resume_pause(
                        self.server.data.db_path,
                        account,
                        confirm=bool(body.get("confirm")),
                        actor="console",
                    )
                except ValueError as exc:
                    self._error(403, str(exc))
                else:
                    try:
                        from .runtime import record_console_action

                        record_console_action(
                            self.server.data.db_path,
                            action="fund_pause_resume",
                            params={"account": account},
                            result="reanudado",
                            ok=True,
                            actor="console",
                        )
                    except Exception:
                        pass
                    self.server.data.cache.clear()
                    self._json(result)
            elif path == "/api/learning/approve":
                lesson_id = int(body.get("id") or 0)
                try:
                    row = approve_lesson(
                        self.server.data.db_path,
                        lesson_id,
                        by=str(body.get("by") or "humano"),
                    )
                except ValueError as exc:
                    self._error(403, str(exc))
                else:
                    self._audit_learning("lesson_approve", lesson_id, "aprobada")
                    self.server.data.cache.clear()
                    self._json({"ok": True, "lesson": row})
            elif path == "/api/learning/reject":
                lesson_id = int(body.get("id") or 0)
                try:
                    row = reject_lesson(
                        self.server.data.db_path,
                        lesson_id,
                        by=str(body.get("by") or "humano"),
                        reason=str(body.get("reason") or ""),
                    )
                except ValueError as exc:
                    self._error(403, str(exc))
                else:
                    self._audit_learning("lesson_reject", lesson_id, "rechazada")
                    self.server.data.cache.clear()
                    self._json({"ok": True, "lesson": row})
            elif path == "/api/learning/apply":
                lesson_id = int(body.get("id") or 0)
                auto = bool(body.get("auto"))
                try:
                    row = apply_lesson(
                        self.server.data.db_path,
                        lesson_id,
                        actor="auto" if auto else "humano",
                        auto=auto,
                    )
                except ValueError as exc:
                    self._error(403, str(exc))
                else:
                    self.server.data.cache.clear()
                    self._json({"ok": True, "lesson": row})
            elif path == "/api/learning/revert":
                lesson_id = int(body.get("id") or 0)
                try:
                    row = revert_lesson(
                        self.server.data.db_path,
                        lesson_id,
                        actor="humano",
                        confirm=bool(body.get("confirm")),
                    )
                except ValueError as exc:
                    self._error(403, str(exc))
                else:
                    self.server.data.cache.clear()
                    self._json({"ok": True, "lesson": row})
            elif path == "/api/models/promote":
                model_id = int(body.get("id") or 0)
                try:
                    result = promote_model(
                        self.server.data.db_path,
                        model_id,
                        confirm=bool(body.get("confirm")),
                        by="humano",
                    )
                except ValueError as exc:
                    self._error(403, str(exc))
                else:
                    self._audit_learning("model_promote", model_id, "campeón")
                    self.server.data.cache.clear()
                    self._json({"ok": True, **result})
            elif path == "/api/models/rollback":
                symbol = str(body.get("symbol") or "").strip().upper()
                try:
                    result = rollback_model(
                        self.server.data.db_path,
                        symbol,
                        confirm=bool(body.get("confirm")),
                        by="humano",
                    )
                except ValueError as exc:
                    self._error(403, str(exc))
                else:
                    self._audit_learning(
                        "model_rollback", int(result.get("restored_id") or 0), "rollback"
                    )
                    self.server.data.cache.clear()
                    self._json({"ok": True, **result})
            elif path == "/api/operator/arm":
                try:
                    state = self.server.data.operator.arm(
                        str(body.get("pin") or "")
                    )
                except OperatorError as exc:
                    self._error(exc.status, str(exc))
                else:
                    self._json({"ok": True, "session": state})
            elif path == "/api/operator/disarm":
                self._json(
                    {"ok": True, "session": self.server.data.operator.disarm()}
                )
            elif path == "/api/operator/preview":
                params = body.get("params")
                try:
                    result = self.server.data.operator.preview(
                        str(body.get("action") or ""),
                        params if isinstance(params, dict) else {},
                    )
                except OperatorError as exc:
                    self._error(exc.status, str(exc))
                else:
                    self._json(result)
            elif path == "/api/operator/execute":
                params = body.get("params")
                try:
                    result = self.server.data.operator.execute(
                        str(body.get("action") or ""),
                        params if isinstance(params, dict) else {},
                        str(body.get("token") or ""),
                    )
                except OperatorError as exc:
                    self._error(exc.status, str(exc))
                else:
                    self.server.data.cache.clear()
                    self._json(result)
            else:
                self._error(404, "Ruta no encontrada")
        except Exception as exc:
            self._error(500, str(exc)[:500])


def serve(
    settings: Settings | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8420,
    open_browser: bool = True,
    external: bool = True,
) -> None:
    """Arranca el panel web hasta Ctrl+C."""
    settings = settings or get_settings()
    data = LabData(settings, external=external)
    server = DashboardServer((host, port), data)

    def _warm() -> None:
        try:
            data.overview()
        except Exception:
            pass

    threading.Thread(target=_warm, daemon=True).start()
    url = f"http://{host}:{port}/"
    print(f"TradingLab Console · {url}")
    print("Pulsa Ctrl+C para detener el servidor.")
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


__all__ = ["DashboardServer", "LabData", "serve"]

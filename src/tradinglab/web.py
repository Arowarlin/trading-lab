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
from .killswitch import load_state as load_killswitch
from .orchestrator import load_bots
from .prop import AccountState, PropGuard, PropRules, from_yaml, ftmo
from .reconciliation import last_reconciliation

INDEX_FILE = Path(__file__).with_name("webui") / "index.html"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,11}$")
MAX_LOG_BYTES = 96 * 1024


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
    ) -> None:
        self.settings = settings or get_settings()
        self.root = Path(root)
        self.db_path = Path(db_path)
        self.external = external
        self.cache = TTLCache()
        self._action_lock = threading.Lock()
        self._action: dict[str, Any] | None = None

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
            "market": self.market(),
            "calendar": self.calendar(),
            "decisions": self.decisions(),
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

    def research(self, limit: int = 15) -> dict:
        latest = _read_json(self.research_dir / "latest.json", {}) or {}
        proposals = _read_json(self.research_dir / "proposals.json", {}) or {}
        proposal_rows = proposals.get("proposals") if isinstance(proposals, dict) else None
        if proposal_rows is None:
            proposal_rows = latest.get("proposals") or []
        return {
            "generated_at": latest.get("generated_at"),
            "rules": latest.get("rules"),
            "config": latest.get("config") or {},
            "candidates": latest.get("candidates") or len(latest.get("results") or []),
            "results": (latest.get("results") or [])[:limit],
            "proposals": proposal_rows,
            "near_misses": latest.get("near_misses") or [],
            "pbo": latest.get("pbo"),
            "pbo_ok": latest.get("pbo_ok"),
            "pbo_by_symbol": latest.get("pbo_by_symbol") or {},
            "walk_forward": latest.get("walk_forward"),
            "walk_forward_ok": latest.get("walk_forward_ok"),
            "dsr_n_trials": latest.get("dsr_n_trials"),
            "dsr_trial_sr_std": latest.get("dsr_trial_sr_std"),
            "horizons": _read_json(self.research_dir / "horizons.json", {}) or {},
            "intraday": _read_json(self.research_dir / "intraday.json", {}) or {},
            "clusters": _read_json(self.research_dir / "clusters.json", {}) or {},
            "portfolio": _read_json(self.research_dir / "portfolio.json", {}) or {},
            "costs": _read_json(self.research_dir / "costs.json", {}) or {},
            "errors": latest.get("errors") or [],
        }

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
        from .decisions import report

        def collect() -> dict:
            out = {"rows": [], "total": 0, "min_sample": 30, "error": None}
            if not self.db_path.exists():
                out["error"] = "sin base de datos"
                return out
            try:
                rows = report(self.db_path)
            except Exception as exc:
                out["error"] = str(exc)[:240]
                return out
            out["rows"] = rows
            out["total"] = sum(int(row.get("n") or 0) for row in rows)
            return out

        return self.cache.get("decisions", 60.0, collect)

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
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], data: LabData) -> None:
        super().__init__(address, DashboardHandler)
        self.data = data


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

    # ------------------------------------------------------------------ rutas

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                if not INDEX_FILE.exists():
                    self._error(500, "Falta webui/index.html")
                    return
                self._send(200, INDEX_FILE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/health":
                self._json({"ok": True, "version": __version__, "build": BUILD_ID, "time": _now()})
            elif path == "/api/overview":
                self._json(self.server.data.overview())
            elif path == "/api/risk":
                self._json(self.server.data.risk())
            elif path == "/api/market":
                self._json(self.server.data.market())
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
        try:
            if path == "/api/actions/dryrun":
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

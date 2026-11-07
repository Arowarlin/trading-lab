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
import json
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
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

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

SEVERITY_LABEL = {
    "ok": "OK",
    "warn": "AVISO",
    "block": "BLOQUEO",
    "breach": "BREACH",
}


# --------------------------------------------------------------------- utiles


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
            "errors": latest.get("errors") or [],
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
                self._json({"ok": True, "version": __version__, "time": _now()})
            elif path == "/api/overview":
                self._json(self.server.data.overview())
            elif path == "/api/risk":
                self._json(self.server.data.risk())
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

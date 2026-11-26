"""Aísla la suite de la `discovery.db` real.

``count_tests`` lee por defecto ``data/discovery.db``. Sin este fixture, una
campaña real aprobada (small = 440 pruebas) contamina cualquier test que use
un ``lab.db`` temporal y afirme valores absolutos del contador.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# ENG-1 F5: la suite nunca escribe en data/lab.db real. Debe fijarse antes de
# importar tradinglab, porque DEFAULT_DB se lee al importar config y muchos
# módulos lo copian como argumento por defecto. Si alguien ya la definió a
# propósito, se respeta.
if not os.environ.get("TRADINGLAB_DB"):
    _SUITE_DATA = Path(tempfile.mkdtemp(prefix="tradinglab-tests-"))
    os.environ["TRADINGLAB_DB"] = str(_SUITE_DATA / "lab.db")


@pytest.fixture(autouse=True)
def _isolate_discovery_db(tmp_path, monkeypatch):
    from tradinglab import learning
    from tradinglab.discovery import databank

    empty = tmp_path / "discovery-empty.db"
    databank.init_databank(empty)
    monkeypatch.setattr(databank, "DEFAULT_DISCOVERY_DB", empty)
    monkeypatch.setattr(learning, "CANONICAL_DISCOVERY_DB", empty)


# Marcadores cuyos tests necesitan, a propósito, las credenciales reales.
_REAL_SECRET_MARKERS = ("network", "credentials", "mt5", "alpaca", "lmstudio")
# Variables de canal que no están en SECRET_KEYS pero deciden adónde va una alerta.
_CHANNEL_VARS = (
    "ALERT_CHANNEL",
    "ALERTS_ENABLED",
    "NTFY_URL",
    "HEALTHCHECKS_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
)


@pytest.fixture(autouse=True)
def _no_real_secrets(request, monkeypatch):
    """Ningún test sin marcador de red/credenciales ve los secretos reales.

    Sin esto, ``alerts.AlertConfig.from_env`` llama a ``load_secrets``, que lee
    ``.env`` y el keyring de Windows. En el equipo del operador, tests como los
    de ``test_freshness`` o ``test_intraday_bots`` podían enviar alertas reales
    por ntfy/Telegram (por ejemplo "posición BTCUSD sin SL"). Ver
    docs/engineering/AUDIT_FINDINGS.md (F0-08).
    """

    if any(request.node.get_closest_marker(name) for name in _REAL_SECRET_MARKERS):
        return
    from tradinglab import config

    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)
    try:
        import keyring
    except Exception:  # noqa: BLE001
        keyring = None
    if keyring is not None:
        monkeypatch.setattr(keyring, "get_password", lambda *args, **kwargs: None)
    for key in (*config.SECRET_KEYS, *_CHANNEL_VARS):
        monkeypatch.delenv(key, raising=False)


# Firmas de las alertas que generan los tests (F0-08). Otras escrituras en la
# lab.db real (tareas programadas cada 15 min, bots, consola) son legítimas, así
# que no se mira la fecha del fichero: se cuentan solo filas con estas firmas.
_TEST_ALERT_SQL = (
    "SELECT COUNT(*) FROM alerts WHERE message LIKE '%gate-test%' OR message LIKE '%intra-x%'"
    " OR message LIKE '%BTCUSD%' OR message LIKE '%presupuesto test%'"
)


def _real_test_alerts():
    import sqlite3

    from tradinglab.config import ROOT

    path = ROOT / "data" / "lab.db"
    if not path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            return int(con.execute(_TEST_ALERT_SQL).fetchone()[0])
        finally:
            con.close()
    except sqlite3.Error:
        return None


def _seed_synthetic_spreads() -> None:
    """Spreads horarios sintéticos en la lab.db temporal de la suite (ENG-1 F2b).

    Los tests de Discovery leían ``broker_spreads`` de la lab.db real del
    operador: en CI fallaban y en local dependían de lo medido ese día. Aquí se
    siembra un perfil plano de 24 horas para cada cuenta CFD e instrumento
    permitido. No son datos de mercado: CFD-006 es más barata en FX y oro y más
    cara en índices (donde además paga más swap), para que el modo ``best``
    reparta entre cuentas como con los spreads reales
    (``test_feasibility_cesta_cubre_todas_las_cuentas``).
    """

    import sqlite3

    from tradinglab.config import DEFAULT_DB, ROOT
    from tradinglab.db import init_db
    from tradinglab.propfund.costs import broker_symbol
    from tradinglab.propfund.models import Market
    from tradinglab.propfund.registry import load_registry

    if DEFAULT_DB == ROOT / "data" / "lab.db":
        return  # nunca sembrar en la lab.db real
    init_db(DEFAULT_DB)
    rows = set()
    for account in load_registry().accounts.values():
        if account.market is not Market.CFD:
            continue
        source = str(account.spread_source or "broker")
        for instrument in account.allowed_instruments or []:
            canonical = str(instrument).upper()
            name = (account.broker_symbols or {}).get(canonical) or broker_symbol(canonical)
            index_like = canonical in {"US100", "US500", "US30", "GER40"}
            cheap = (account.id == "CFD-006") != index_like
            median, p75 = (0.8, 1.3) if cheap else (1.4, 2.3)
            for hour in range(24):
                rows.add((str(name).upper(), hour, median, p75, 1000, None, None, source))
    with sqlite3.connect(DEFAULT_DB) as con:
        con.executemany(
            "INSERT OR IGNORE INTO broker_spreads (symbol, hour_utc, median_bps, p75_bps,"
            " n_ticks, from_ts, to_ts, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            sorted(rows, key=str),
        )


def pytest_sessionstart(session):
    session.config._tl_test_alerts = _real_test_alerts()
    _seed_synthetic_spreads()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    before = getattr(config, "_tl_test_alerts", None)
    after = _real_test_alerts()
    if before is None or after is None or after <= before:
        return
    terminalreporter.write_sep(
        "!",
        f"AVISO: la suite escribió {after - before} alertas de test en data/lab.db real"
        " (docs/engineering/AUDIT_FINDINGS.md, F0-08)",
        yellow=True,
    )


@pytest.fixture(autouse=True)
def _allow_unapproved_performance(monkeypatch):
    """Los tests calculan rendimiento con datos sintéticos por diseño."""

    from tradinglab.discovery import guard

    monkeypatch.setenv("TRADINGLAB_ALLOW_UNAPPROVED", "1")
    monkeypatch.setattr(guard, "ALLOW_UNAPPROVED", True)

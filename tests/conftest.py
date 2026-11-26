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


_WATCHED = ("data/lab.db", "data/telegram_state.json", "data/task_missed_seen.json")


def _stat_watched():
    from tradinglab.config import ROOT

    out = {}
    for rel in _WATCHED:
        path = ROOT / rel
        out[rel] = path.stat().st_mtime_ns if path.exists() else None
    return out


def pytest_sessionstart(session):
    session.config._tl_watched = _stat_watched()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    before = getattr(config, "_tl_watched", None)
    if before is None:
        return
    touched = [rel for rel, stamp in _stat_watched().items() if stamp != before.get(rel)]
    if touched:
        terminalreporter.write_sep(
            "!",
            "AVISO: la suite modificó ficheros reales del laboratorio: "
            + ", ".join(touched)
            + " (docs/engineering/AUDIT_FINDINGS.md, F0-08)",
            yellow=True,
        )


@pytest.fixture(autouse=True)
def _allow_unapproved_performance(monkeypatch):
    """Los tests calculan rendimiento con datos sintéticos por diseño."""

    from tradinglab.discovery import guard

    monkeypatch.setenv("TRADINGLAB_ALLOW_UNAPPROVED", "1")
    monkeypatch.setattr(guard, "ALLOW_UNAPPROVED", True)

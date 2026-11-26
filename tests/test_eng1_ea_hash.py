"""ENG-1 F0-09: el hash del forward del EA no depende de los finales de línea.

Antes el hash se calculaba sobre los bytes crudos: en la copia de Windows del
operador cuatro ficheros tenían CRLF y daban ``f490642ba7a1f71b``, y en git
(LF), en CI o en un checkout limpio daba ``71ee2cabe6aa9aef``. Ahora se
normaliza a LF y el hash antiguo se acepta como alias del MISMO contenido.
"""

from __future__ import annotations

import hashlib

import pytest

from tradinglab import ea_forward as ef
from tradinglab.db import connect, init_db
from tradinglab.lifecycle import LifecycleError, criteria_hash

LEGACY = "f490642ba7a1f71b"
CURRENT = "71ee2cabe6aa9aef"
# Ficheros que tenían CRLF en la copia del operador cuando se congeló el hash.
CRLF_FILES = {"US100_EA.mq5", "US100_ExitManager.mqh", "US100_RiskManager.mqh", "ea_us100_engine.py"}


def _operator_bytes(path):
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return data.replace(b"\n", b"\r\n") if path.name in CRLF_FILES else data


def _old_raw_hash() -> str:
    """El cálculo anterior (bytes crudos) sobre la copia del operador reconstruida."""

    crit = dict(ef.EA_CRITERIA)
    crit["setfile_sha256"] = hashlib.sha256(
        _operator_bytes(ef.EA_DIR / "US100_FTMO_v3_challenge.set")
    ).hexdigest()
    digest = hashlib.sha256()
    for path in sorted(ef.EA_CODE):
        digest.update(path.name.encode("utf-8"))
        digest.update(_operator_bytes(path))
    crit["code_sha256"] = digest.hexdigest()
    crit["replica_sha256"] = hashlib.sha256(
        _operator_bytes(ef.ROOT / "src" / "tradinglab" / "ea_us100_engine.py")
    ).hexdigest()
    crit["calendar_sha256"] = hashlib.sha256(
        _operator_bytes(ef.ROOT / "src" / "tradinglab" / "nyse_calendar.py")
    ).hexdigest()
    return criteria_hash(crit)


def test_hash_normalizado_no_depende_de_crlf(tmp_path):
    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    lf.write_bytes(b"a\nb\n")
    crlf.write_bytes(b"a\r\nb\r\n")
    assert ef._sha256(lf) == ef._sha256(crlf)
    assert criteria_hash(ef.EA_CRITERIA) == CURRENT


def test_el_hash_antiguo_es_el_mismo_contenido_con_crlf():
    # Regresión: el cálculo anterior sobre la copia del operador da el hash guardado,
    # y el nuevo sobre el mismo contenido da el actual. Por eso el alias es válido.
    assert _old_raw_hash() == LEGACY
    assert LEGACY in ef.LEGACY_CRITERIA_HASHES[CURRENT]


def _forward_row(db, stored_hash):
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO lifecycle_bots (bot, state, asset, criteria, criteria_hash, frozen_at,"
            " start_date, created_at, updated_at, note) VALUES (?, 'incubando', 'US100.cash',"
            " '{}', ?, '2026-11-01T00:00:00+00:00', '2026-11-02', '2026-11-01T00:00:00+00:00',"
            " '2026-11-02T00:00:00+00:00', 'test')",
            (ef.DEFAULT_BOT, stored_hash),
        )


def test_el_forward_acepta_el_hash_antiguo(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    _forward_row(db, LEGACY)
    monkeypatch.setattr(ef, "_first_fill_date", lambda *a, **k: None)
    row = ef.ensure_forward(db)
    assert row["criteria_hash"] == LEGACY  # no se reescribe: el forward sigue igual


def test_el_forward_sigue_rechazando_otro_hash(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    _forward_row(db, "0000000000000000")
    monkeypatch.setattr(ef, "_first_fill_date", lambda *a, **k: None)
    with pytest.raises(LifecycleError, match="congelados"):
        ef.ensure_forward(db)

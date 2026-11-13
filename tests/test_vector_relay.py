from __future__ import annotations

import json
from types import SimpleNamespace

from tradinglab.db import connect, init_db
from tradinglab.vector_relay import last_relay, relay


class Sender:
    def __init__(self, ok: bool = True, skipped: bool = False) -> None:
        self.ok = ok
        self.skipped = skipped
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            ok=self.ok,
            skipped=self.skipped,
            channel="test",
        )


def _line(*, severity="critical", pattern="traceback", source="ai_trader", ts="2026-11-13T15:00:00+00:00"):
    return json.dumps(
        {
            "severity": severity,
            "pattern": pattern,
            "source": source,
            "message": f"{pattern} de prueba",
            "timestamp": ts,
            "task": "",
            "symbol": "",
        },
        ensure_ascii=False,
    ) + "\n"


def _write(path, *lines):
    path.write_text("".join(lines), encoding="utf-8")


def test_relay_sin_archivo_no_hace_nada(tmp_path):
    db = tmp_path / "lab.db"
    result = relay(db, path=tmp_path / "no-existe.jsonl")
    assert result["ok"] is True
    assert result["skipped"] is True
    assert "sin archivo" in result["reason"]


def test_relay_lee_solo_lineas_nuevas_y_deduplica(tmp_path):
    db = tmp_path / "lab.db"
    path = tmp_path / "alerts.jsonl"
    _write(path, _line(), _line())
    sender = Sender()

    first = relay(db, path=path, sender=sender)
    assert first["sent"] == 1
    assert first["skipped_dedupe"] == 1
    assert first["offset_end"] == path.stat().st_size

    second = relay(db, path=path, sender=sender)
    assert second["processed"] == 0
    assert second["sent"] == 0

    with path.open("a", encoding="utf-8") as handle:
        handle.write(_line(pattern="autotrading_disabled"))
    third = relay(db, path=path, sender=sender)
    assert third["sent"] == 1
    assert len(sender.calls) == 2
    assert last_relay(db)["sent"] == 2


def test_relay_no_envia_warn_pero_cuenta(tmp_path):
    db = tmp_path / "lab.db"
    path = tmp_path / "alerts.jsonl"
    _write(path, _line(severity="warn", pattern="requote"))
    sender = Sender()

    result = relay(db, path=path, sender=sender)

    assert result["warned"] == 1
    assert result["sent"] == 0
    assert sender.calls == []
    init_db(db)
    with connect(db) as con:
        row = con.execute("SELECT warn FROM vector_daily").fetchone()
        assert row["warn"] == 1


def test_relay_escala_segunda_desconexion(tmp_path):
    db = tmp_path / "lab.db"
    path = tmp_path / "alerts.jsonl"
    _write(path, _line(severity="warn", pattern="mt5_connection"))
    sender = Sender()

    first = relay(db, path=path, sender=sender)
    assert first["warned"] == 1
    assert sender.calls == []

    with path.open("a", encoding="utf-8") as handle:
        handle.write(_line(severity="warn", pattern="mt5_connection"))
    second = relay(db, path=path, sender=sender)

    assert second["sent"] == 1
    assert len(sender.calls) == 1
    assert sender.calls[0]["severity"] == "critical"


def test_relay_respeta_presupuesto(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    path = tmp_path / "alerts.jsonl"
    _write(path, _line())
    sender = Sender()
    monkeypatch.setattr(
        "tradinglab.vector_relay.weekly_budget",
        lambda *args, **kwargs: {"remaining": 0},
    )

    result = relay(db, path=path, sender=sender)

    assert result["sent"] == 0
    assert result["skipped_budget"] == 1
    assert sender.calls == []


def test_relay_ignora_linea_incompleta(tmp_path):
    db = tmp_path / "lab.db"
    path = tmp_path / "alerts.jsonl"
    path.write_text(_line().rstrip("\n"), encoding="utf-8")
    sender = Sender()

    result = relay(db, path=path, sender=sender)

    assert result["processed"] == 0
    assert result["offset_end"] == 0
    assert sender.calls == []

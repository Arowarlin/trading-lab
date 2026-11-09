from __future__ import annotations

import sqlite3

import pytest

from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.llm import (
    LLMClient,
    LLMSchemaError,
    _strip_fences,
    schema_summary,
    validate_schema,
)


def test_plain_json_untouched():
    assert _strip_fences('{"ok": true}') == '{"ok": true}'


def test_strips_json_fence():
    raw = '```json\n{"ok": true}\n```'
    assert _strip_fences(raw) == '{"ok": true}'


def test_strips_plain_fence():
    raw = '```\n{"ok": true}\n```'
    assert _strip_fences(raw) == '{"ok": true}'


def test_validate_schema_objeto_enum_y_requeridos():
    schema = {
        "type": "object",
        "properties": {
            "rating": {"type": "string", "enum": ["Buy", "Hold"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["rating"],
        "additionalProperties": False,
    }
    validate_schema({"rating": "Buy", "confidence": 0.5}, schema)
    with pytest.raises(LLMSchemaError, match="enum"):
        validate_schema({"rating": "Sell"}, schema)
    with pytest.raises(LLMSchemaError, match="máximo"):
        validate_schema({"rating": "Buy", "confidence": 1.2}, schema)
    with pytest.raises(LLMSchemaError, match="falta"):
        validate_schema({}, schema)
    with pytest.raises(LLMSchemaError, match="no permitidos"):
        validate_schema({"rating": "Buy", "otra": 1}, schema)


def test_chat_json_cuenta_fallos_de_esquema(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    schema = {
        "type": "object",
        "properties": {"rating": {"type": "string", "enum": ["Buy", "Hold"]}},
        "required": ["rating"],
        "additionalProperties": False,
    }
    content = {"value": '{"rating":"Buy"}'}

    class Response:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": content["value"]}}],
                "usage": {},
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr("tradinglab.llm.httpx.Client", FakeClient)
    client = LLMClient(Settings().llm, db)
    assert client.chat_json([{"role": "user", "content": "x"}], schema=schema) == {
        "rating": "Buy"
    }
    ok_summary = schema_summary(db)
    assert ok_summary["checked"] == 1
    assert ok_summary["ok"] == 1
    assert ok_summary["failed"] == 0

    content["value"] = '{"rating":"Sell"}'
    with pytest.raises(LLMSchemaError):
        client.chat_json([{"role": "user", "content": "x"}], schema=schema)
    summary = schema_summary(db)
    assert summary["checked"] == 2
    assert summary["failed"] == 1
    assert summary["recent_failures"][0]["purpose"] == "json"
    with connect(db) as con:
        rows = con.execute(
            "SELECT schema_ok, schema_error FROM llm_calls ORDER BY id"
        ).fetchall()
    assert rows[0]["schema_ok"] == 1
    assert rows[1]["schema_ok"] == 0
    assert "enum" in rows[1]["schema_error"]


def test_migracion_llm_calls_conserva_historial(tmp_path):
    db = tmp_path / "lab.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE llm_calls ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, model TEXT, "
            "purpose TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, "
            "latency_ms INTEGER, ok INTEGER NOT NULL, error TEXT)"
        )
        con.execute(
            "INSERT INTO llm_calls(ts, model, purpose, ok) VALUES(?,?,?,?)",
            ("2026-11-09T00:00:00+00:00", "qwen", "test", 1),
        )
    init_db(db)
    with connect(db) as con:
        columns = {
            row["name"] for row in con.execute("PRAGMA table_info(llm_calls)")
        }
        row = con.execute("SELECT * FROM llm_calls").fetchone()
    assert {"schema_ok", "schema_error"} <= columns
    assert row["model"] == "qwen"
    assert row["schema_ok"] is None

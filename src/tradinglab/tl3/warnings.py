"""E3 · Avisos que viajan: tabla append-only y render."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import registry
from .registry import DB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cifras(value: Any) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def add_warning(
    subject: str,
    fecha: str,
    etapa: str,
    texto: str,
    cifras: Any = None,
    source_path: str = "",
    *,
    db_path: str | Path = DB,
) -> int | None:
    """Añade un aviso; no duplica una fila idéntica. Solo inserta."""

    registry.init_db(db_path)
    payload = _cifras(cifras)
    with registry.connect(db_path) as con:
        existing = con.execute(
            "SELECT id FROM warnings WHERE subject=? AND fecha=? AND etapa=?"
            " AND texto=? AND cifras=? AND source_path=?",
            (str(subject), str(fecha), str(etapa), str(texto), payload, str(source_path)),
        ).fetchone()
        if existing is not None:
            return None
        cursor = con.execute(
            "INSERT INTO warnings(subject,fecha,etapa,texto,cifras,source_path,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                str(subject),
                str(fecha),
                str(etapa),
                str(texto),
                payload,
                str(source_path),
                _now(),
            ),
        )
        con.commit()
        return int(cursor.lastrowid)


def _parse(row: dict) -> dict:
    item = dict(row)
    raw = item.get("cifras")
    if isinstance(raw, str):
        try:
            item["cifras"] = json.loads(raw)
        except ValueError:
            item["cifras"] = raw
    return item


def warnings_for(subject: str, *, db_path: str | Path = DB) -> list[dict]:
    """Avisos de un subject, en orden de inserción."""

    registry.init_db(db_path)
    with registry.connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM warnings WHERE subject=? ORDER BY id", (str(subject),)
        ).fetchall()
    return [_parse(dict(row)) for row in rows]


def all_warnings(*, db_path: str | Path = DB) -> list[dict]:
    """Todos los avisos, en orden de inserción (para el estado global)."""

    registry.init_db(db_path)
    with registry.connect(db_path) as con:
        rows = con.execute("SELECT * FROM warnings ORDER BY id").fetchall()
    return [_parse(dict(row)) for row in rows]


def render(subject: str, *, db_path: str | Path = DB) -> str:
    """Markdown de todos los avisos de un subject; ``Ninguno`` si no hay."""

    items = warnings_for(subject, db_path=db_path)
    if not items:
        return "Ninguno"
    lines = [f"### Avisos · {subject}", ""]
    for item in items:
        cifras = item.get("cifras")
        suffix = ""
        if cifras:
            text = json.dumps(cifras, ensure_ascii=False, sort_keys=True)
            suffix = f" (cifras: `{text}`)"
        lines.append(
            f"- **{item['fecha']} · {item['etapa']}** — {item['texto']}{suffix}. "
            f"Fuente: `{item['source_path']}`."
        )
    return "\n".join(lines)


__all__ = ["add_warning", "all_warnings", "render", "warnings_for"]

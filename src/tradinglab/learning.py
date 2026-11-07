"""Aprendizaje controlado: lecciones, holdout sellado y contador DSR.

Qwen solo redacta propuestas (`proposed`); humano aprueba/rechaza. Ninguna
lección activa bots. La auto-aplicación se limita a reducciones de riesgo y
siempre guarda el estado anterior para reversión.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .accounts import load_accounts, own_limits, set_limits
from .config import Settings
from .db import connect, init_db, utcnow
from .runtime import record_console_action

AUTHORS = {"qwen", "humano"}
STATUSES = {"proposed", "approved", "rejected"}


class LearningError(ValueError):
    pass


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise LearningError(f"fecha inválida: {value}") from exc


def _holdout_hash(start: str, end: str) -> str:
    return hashlib.sha256(f"{start}|{end}".encode("utf-8")).hexdigest()[:16]


def init_learning(db_path: str | Path, settings: Settings | None = None) -> None:
    settings = settings or Settings()
    init_db(db_path)
    holdout = settings.learning
    with connect(db_path) as con:
        con.execute(
            "INSERT OR IGNORE INTO learning_holdout"
            "(id, start_date, end_date, hash, sealed_at) VALUES(1,?,?,?,?)",
            (
                holdout.holdout_start,
                holdout.holdout_end,
                _holdout_hash(holdout.holdout_start, holdout.holdout_end),
                utcnow(),
            ),
        )


def holdout_info(
    db_path: str | Path, settings: Settings | None = None
) -> dict:
    init_learning(db_path, settings)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM learning_holdout WHERE id = 1").fetchone()
    return dict(row) if row else {}


def _row_to_lesson(row) -> dict:
    item = dict(row)
    for key in ("action", "applied_action", "reversal"):
        if item.get(key):
            try:
                item[key] = json.loads(item[key])
            except (TypeError, ValueError):
                pass
    return item


def create_lesson(
    db_path: str | Path,
    *,
    hypothesis: str,
    evidence: str = "",
    author: str = "humano",
    kind: str = "lesson",
    champion: str | None = None,
    challenger: str | None = None,
    action: dict | None = None,
    settings: Settings | None = None,
) -> dict:
    if author not in AUTHORS:
        raise LearningError("author debe ser qwen o humano")
    if not str(hypothesis or "").strip():
        raise LearningError("hypothesis no puede estar vacía")
    if kind not in {"lesson", "challenger"}:
        raise LearningError("kind debe ser lesson o challenger")
    if kind == "challenger" and (not champion or not challenger):
        raise LearningError("challenger requiere champion y challenger")
    init_learning(db_path, settings)
    with connect(db_path) as con:
        cursor = con.execute(
            "INSERT INTO lessons"
            "(ts, kind, hypothesis, evidence, author, status, champion, challenger, action) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                kind,
                str(hypothesis).strip()[:2000],
                str(evidence or "")[:4000],
                author,
                "proposed",
                champion,
                challenger,
                json.dumps(action, ensure_ascii=False) if action else None,
            ),
        )
        lesson_id = int(cursor.lastrowid)
    return get_lesson(db_path, lesson_id)


def get_lesson(
    db_path: str | Path, lesson_id: int, settings: Settings | None = None
) -> dict:
    init_learning(db_path, settings)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM lessons WHERE id = ?", (int(lesson_id),)
        ).fetchone()
    if row is None:
        raise LearningError(f"lección no encontrada: {lesson_id}")
    return _row_to_lesson(row)


def list_lessons(
    db_path: str | Path,
    *,
    status: str | None = None,
    settings: Settings | None = None,
) -> list[dict]:
    init_learning(db_path, settings)
    with connect(db_path) as con:
        if status:
            if status not in STATUSES:
                raise LearningError(f"status inválido: {status}")
            rows = con.execute(
                "SELECT * FROM lessons WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM lessons ORDER BY id DESC"
            ).fetchall()
        counts = {
            row["lesson_id"]: int(row["n"])
            for row in con.execute(
                "SELECT lesson_id, COUNT(*) AS n FROM lesson_tests GROUP BY lesson_id"
            ).fetchall()
        }
    out = []
    for row in rows:
        item = _row_to_lesson(row)
        item["tests"] = counts.get(item["id"], 0)
        out.append(item)
    return out


def count_tests(db_path: str | Path, settings: Settings | None = None) -> int:
    init_learning(db_path, settings)
    with connect(db_path) as con:
        row = con.execute("SELECT COUNT(*) AS n FROM lesson_tests").fetchone()
    return int(row["n"])


def record_test(
    db_path: str | Path,
    lesson_id: int,
    *,
    period_start: str,
    period_end: str,
    metric: str = "",
    value: float | None = None,
    passed: bool | None = None,
    notes: str = "",
    settings: Settings | None = None,
) -> dict:
    """Registra una prueba y rechaza cualquier ventana que pise el holdout."""
    get_lesson(db_path, lesson_id, settings)
    start = _parse_day(period_start)
    end = _parse_day(period_end)
    if end < start:
        raise LearningError("period_end no puede ser anterior a period_start")
    sealed = holdout_info(db_path, settings)
    sealed_start = _parse_day(sealed["start_date"])
    sealed_end = _parse_day(sealed["end_date"])
    if start <= sealed_end and end >= sealed_start:
        raise LearningError(
            "ventana prohibida: pisa el holdout sellado "
            f"{sealed['start_date']}…{sealed['end_date']}"
        )
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO lesson_tests"
            "(ts, lesson_id, period_start, period_end, metric, value, passed, notes) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                int(lesson_id),
                start.isoformat(),
                end.isoformat(),
                metric[:100],
                value,
                None if passed is None else int(bool(passed)),
                notes[:1000],
            ),
        )
    return {
        "lesson_id": int(lesson_id),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "metric": metric,
        "value": value,
        "passed": passed,
        "global_trials": count_tests(db_path, settings),
    }


def approve(
    db_path: str | Path,
    lesson_id: int,
    *,
    by: str = "humano",
    settings: Settings | None = None,
) -> dict:
    lesson = get_lesson(db_path, lesson_id, settings)
    if lesson["status"] == "rejected":
        raise LearningError("una lección rechazada no se aprueba")
    with connect(db_path) as con:
        con.execute(
            "UPDATE lessons SET status='approved', approved_at=?, approved_by=? WHERE id=?",
            (utcnow(), by[:100], int(lesson_id)),
        )
    return get_lesson(db_path, lesson_id, settings)


def reject(
    db_path: str | Path,
    lesson_id: int,
    *,
    by: str = "humano",
    reason: str = "",
    settings: Settings | None = None,
) -> dict:
    get_lesson(db_path, lesson_id, settings)
    with connect(db_path) as con:
        con.execute(
            "UPDATE lessons SET status='rejected', rejected_at=?, rejected_by=?, "
            "reject_reason=? WHERE id=?",
            (utcnow(), by[:100], reason[:500], int(lesson_id)),
        )
    return get_lesson(db_path, lesson_id, settings)


def apply_lesson(
    db_path: str | Path,
    lesson_id: int,
    *,
    actor: str = "humano",
    auto: bool = False,
    settings: Settings | None = None,
) -> dict:
    """Aplica una lección aprobada. Auto solo si reduce riesgo."""
    settings = settings or Settings()
    lesson = get_lesson(db_path, lesson_id, settings)
    action = lesson.get("action") or {}
    if auto:
        actor = "auto"
    if action.get("kind") != "reduce_risk":
        raise LearningError(
            "solo se aplican acciones reduce_risk; el resto requiere revisión manual"
        )
    if lesson["status"] == "rejected":
        raise LearningError("una lección rechazada no se aplica")
    if lesson.get("applied_at") and not lesson.get("reverted_at"):
        raise LearningError("la lección ya está aplicada")
    if auto:
        if not settings.learning.auto_apply_reduce_risk:
            raise LearningError("auto_apply_reduce_risk está desactivado")
    elif lesson["status"] != "approved":
        raise LearningError("la lección necesita aprobación humana antes de aplicarse")
    account_id = str(action.get("account_id") or "")
    accounts = load_accounts()
    if account_id not in accounts:
        raise LearningError(f"cuenta desconocida: {account_id}")
    changes = action.get("changes") or {}
    if not isinstance(changes, dict) or not changes:
        raise LearningError("action.changes no puede estar vacío")
    account = accounts[account_id]
    old = asdict(own_limits(db_path, account))
    for field, raw in changes.items():
        if field not in old:
            raise LearningError(f"campo desconocido: {field}")
        value = float(raw)
        if value > float(old[field]) + 1e-12:
            raise LearningError(
                f"{field}: la lección intenta aflojar ({value} > {old[field]}); "
                "solo se permite reducir riesgo"
            )
    result = set_limits(
        db_path,
        account_id=account_id,
        changes={key: float(value) for key, value in changes.items()},
        origin="lesson",
        confirm=False,
        accounts=accounts,
    )
    if not result["ok"]:
        raise LearningError("; ".join(result["errors"]))
    reversal = {
        key: float(old[key])
        for key in changes
        if key in old
    }
    with connect(db_path) as con:
        con.execute(
            "UPDATE lessons SET applied_at=?, applied_by=?, applied_action=?, "
            "reversal=?, approved_at=COALESCE(approved_at,?), "
            "approved_by=COALESCE(approved_by,?), status='approved' WHERE id=?",
            (
                utcnow(),
                actor[:100],
                json.dumps(action, ensure_ascii=False),
                json.dumps(reversal, ensure_ascii=False),
                utcnow() if auto else None,
                "auto-reduce-risk" if auto else None,
                int(lesson_id),
            ),
        )
    try:
        record_console_action(
            db_path,
            action="lesson_apply",
            params={"lesson_id": lesson_id, "account": account_id, "changes": changes},
            result="aplicado",
            ok=True,
            actor=actor,
        )
    except Exception:
        pass
    return get_lesson(db_path, lesson_id, settings)


def revert_lesson(
    db_path: str | Path,
    lesson_id: int,
    *,
    actor: str = "humano",
    confirm: bool = False,
    settings: Settings | None = None,
) -> dict:
    if not confirm:
        raise LearningError("revertir exige confirmación explícita")
    settings = settings or Settings()
    lesson = get_lesson(db_path, lesson_id, settings)
    if not lesson.get("applied_at"):
        raise LearningError("la lección no está aplicada")
    if lesson.get("reverted_at"):
        raise LearningError("la lección ya está revertida")
    reversal = lesson.get("reversal") or {}
    if not isinstance(reversal, dict) or not reversal:
        raise LearningError("sin estado anterior para revertir")
    account_id = (lesson.get("action") or {}).get("account_id")
    account = load_accounts().get(str(account_id))
    if account is None:
        raise LearningError(f"cuenta desconocida: {account_id}")
    result = set_limits(
        db_path,
        account_id=account.id,
        changes={key: float(value) for key, value in reversal.items()},
        origin="lesson-revert",
        confirm=True,
        accounts=load_accounts(),
    )
    if not result["ok"]:
        raise LearningError("; ".join(result["errors"]))
    with connect(db_path) as con:
        con.execute(
            "UPDATE lessons SET reverted_at=?, reverted_by=? WHERE id=?",
            (utcnow(), actor[:100], int(lesson_id)),
        )
    try:
        record_console_action(
            db_path,
            action="lesson_revert",
            params={"lesson_id": lesson_id, "account": account_id},
            result="revertido",
            ok=True,
            actor=actor,
        )
    except Exception:
        pass
    return get_lesson(db_path, lesson_id, settings)


def research_trials(db_path: str | Path, settings: Settings | None = None) -> int:
    """Contador global que el DSR debe sumar a los trials del barrido."""
    return count_tests(db_path, settings)


__all__ = [
    "AUTHORS",
    "STATUSES",
    "LearningError",
    "apply_lesson",
    "approve",
    "count_tests",
    "create_lesson",
    "get_lesson",
    "holdout_info",
    "init_learning",
    "list_lessons",
    "record_test",
    "reject",
    "research_trials",
    "revert_lesson",
]

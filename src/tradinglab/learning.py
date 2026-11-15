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
from .trials import count_incubated

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
    """Contador único de pruebas del DSR.

    Suman las lecciones, los trials de Optuna, las lecturas del holdout, cada
    intento registrado en `strategy_trials` (también los fallidos) y los bots
    incubados.

    Las campañas registradas suman su `N_total` **completo** desde el momento
    del registro, antes de correr nada: el denominador del DSR no puede crecer
    mientras se mira el resultado. Sus celdas entran en `strategy_trials` con
    `counted = 0` justo para no contarse dos veces.
    """
    init_learning(db_path, settings)
    with connect(db_path) as con:
        lessons = con.execute("SELECT COUNT(*) AS n FROM lesson_tests").fetchone()["n"]
        trials = con.execute(
            "SELECT COUNT(*) AS n FROM optimization_trials"
        ).fetchone()["n"]
        holdout = con.execute(
            "SELECT COUNT(*) AS n FROM holdout_reads"
        ).fetchone()["n"]
        strategies = con.execute(
            "SELECT COUNT(*) AS n FROM strategy_trials WHERE counted = 1"
        ).fetchone()["n"]
        has_campaigns = con.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'campaign_registry'"
        ).fetchone()
        campaigns = 0
        if has_campaigns is not None:
            campaigns = con.execute(
                "SELECT COALESCE(SUM(n_total), 0) AS n FROM campaign_registry"
            ).fetchone()["n"]
    return (
        int(lessons)
        + int(trials)
        + int(holdout)
        + int(strategies)
        + int(campaigns)
        + count_incubated(db_path)
    )


def holdout_usage(
    db_path: str | Path, settings: Settings | None = None
) -> dict:
    """Lecturas del holdout sellado y configuraciones evaluadas."""
    init_learning(db_path, settings)
    with connect(db_path) as con:
        reads = int(
            con.execute("SELECT COUNT(*) AS n FROM holdout_reads").fetchone()["n"]
        )
        configs = int(
            con.execute(
                "SELECT COUNT(*) AS n FROM holdout_evaluations"
            ).fetchone()["n"]
        )
        last = con.execute(
            "SELECT * FROM holdout_reads ORDER BY id DESC LIMIT 1"
        ).fetchone()
        top = con.execute(
            "SELECT config_hash, symbol, strategy, reads, last_read_at "
            "FROM holdout_evaluations ORDER BY reads DESC, last_read_at DESC LIMIT 10"
        ).fetchall()
    return {
        "reads": reads,
        "configs": configs,
        "last": dict(last) if last else None,
        "top": [dict(row) for row in top],
    }


def _holdout_config_hash(symbol: str, strategy: str, params: dict | None) -> str:
    payload = json.dumps(
        {
            "symbol": symbol.upper(),
            "strategy": strategy,
            "params": params or {},
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_holdout_once(
    db_path: str | Path,
    *,
    symbol: str,
    strategy: str,
    params: dict | None,
    evaluator,
    settings: Settings | None = None,
    notes: str = "",
) -> dict:
    """Evalúa el holdout una vez por hash y reutiliza el resultado.

    Cada lectura (calculada o cacheada) se registra en `holdout_reads` y suma
    una prueba extra al contador DSR. `evaluator` no recibe argumentos y debe
    devolver un dict serializable.
    """
    init_learning(db_path, settings)
    config_hash = _holdout_config_hash(symbol, strategy, params)
    now = utcnow()
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM holdout_evaluations WHERE config_hash = ?",
            (config_hash,),
        ).fetchone()
        if row is not None:
            payload = json.loads(row["result"])
            reads = int(row["reads"]) + 1
            con.execute(
                "UPDATE holdout_evaluations SET reads=?, last_read_at=? "
                "WHERE config_hash=?",
                (reads, now, config_hash),
            )
            con.execute(
                "INSERT INTO holdout_reads"
                "(ts, config_hash, symbol, strategy, params, cached, notes) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    now,
                    config_hash,
                    symbol.upper(),
                    strategy,
                    json.dumps(params or {}, ensure_ascii=False, sort_keys=True),
                    1,
                    notes[:1000],
                ),
            )
            return {
                **payload,
                "cached": True,
                "reads": reads,
                "config_hash": config_hash,
                "first_read_at": row["first_read_at"],
                "last_read_at": now,
            }

        result = evaluator()
        if not isinstance(result, dict):
            result = {"result": result}
        con.execute(
            "INSERT INTO holdout_evaluations"
            "(config_hash, symbol, strategy, params, result, "
            "first_read_at, last_read_at, reads) VALUES(?,?,?,?,?,?,?,1)",
            (
                config_hash,
                symbol.upper(),
                strategy,
                json.dumps(params or {}, ensure_ascii=False, sort_keys=True),
                json.dumps(result, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
        con.execute(
            "INSERT INTO holdout_reads"
            "(ts, config_hash, symbol, strategy, params, cached, notes) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                now,
                config_hash,
                symbol.upper(),
                strategy,
                json.dumps(params or {}, ensure_ascii=False, sort_keys=True),
                0,
                notes[:1000],
            ),
        )
    return {
        **result,
        "cached": False,
        "reads": 1,
        "config_hash": config_hash,
        "first_read_at": now,
        "last_read_at": now,
    }


def record_optimization_trial(
    db_path: str | Path,
    *,
    study: str,
    trial: int,
    symbol: str = "",
    strategy: str = "",
    params: dict | None = None,
    value: float | None = None,
    period_start: str,
    period_end: str,
    notes: str = "",
    settings: Settings | None = None,
    sr_period: float | None = None,
    periods_per_year: float | None = None,
) -> dict:
    """Suma un trial de Optuna al contador DSR, sin pisar el holdout sellado."""
    init_learning(db_path, settings)
    start = _parse_day(period_start)
    end = _parse_day(period_end)
    if end < start:
        raise LearningError("period_end no puede ser anterior a period_start")
    sealed = holdout_info(db_path, settings)
    sealed_start = _parse_day(sealed["start_date"])
    sealed_end = _parse_day(sealed["end_date"])
    if start <= sealed_end and end >= sealed_start:
        raise LearningError(
            "el trial pisa el holdout sellado "
            f"{sealed_start.isoformat()}..{sealed_end.isoformat()}"
        )
    with connect(db_path) as con:
        cursor = con.execute(
            "INSERT INTO optimization_trials"
            "(ts, study, trial, symbol, strategy, params, value, "
            "period_start, period_end, notes, sr_period, periods_per_year) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                study[:100],
                int(trial),
                symbol.upper()[:30],
                strategy[:50],
                json.dumps(params or {}, ensure_ascii=False, sort_keys=True)[:4000],
                value,
                start.isoformat(),
                end.isoformat(),
                notes[:1000],
                sr_period,
                periods_per_year,
            ),
        )
        row_id = int(cursor.lastrowid)
    return {
        "id": row_id,
        "study": study,
        "trial": int(trial),
        "symbol": symbol.upper(),
        "strategy": strategy,
        "params": params or {},
        "value": value,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
    }


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


def _default_draft(settings: Settings, db_path: str | Path, evidence: str) -> str:
    from .llm import LLMClient

    client = LLMClient(settings.llm, db_path)
    return client.chat(
        [
            {
                "role": "system",
                "content": (
                    "Eres un analista cuantitativo. Redacta una hipótesis breve "
                    "y falsable usando SOLO la evidencia numérica. No inventes "
                    "datos, no prometas rentabilidad y no propongas activar bots. "
                    "Máximo 400 caracteres."
                ),
            },
            {"role": "user", "content": evidence},
        ],
        purpose="lesson_weekly",
        temperature=0.2,
        max_tokens=220,
    ).strip()


def weekly_lessons(
    db_path: str | Path,
    settings: Settings | None = None,
    *,
    min_sample: int = 30,
    limit: int = 3,
    draft_fn=None,
) -> dict:
    """Genera propuestas semanales desde decision_outcomes; no aprueba nada.

    Qwen solo redacta. Si el LLM falla o no hay muestra suficiente, no se crea
    ninguna lección y se devuelve el motivo (Sin datos).
    """
    from .decisions import report as decisions_report

    settings = settings or Settings()
    reports = [
        row
        for row in decisions_report(db_path, min_sample=min_sample)
        if not row.get("insufficient") and row.get("mean_20d") is not None
    ]
    if not reports:
        return {
            "ok": True,
            "created": [],
            "reason": f"Sin datos: ninguna calificación alcanza n>={min_sample}",
        }
    reports.sort(key=lambda row: row["mean_20d"], reverse=True)
    existing = {row["hypothesis"] for row in list_lessons(db_path, settings=settings)}
    created = []
    skipped = []
    for row in reports[: max(1, int(limit))]:
        evidence = (
            f"rating={row['rating']} n={row['n']} "
            f"mean_20d={row['mean_20d']:.4%} hit_20d={row.get('hit_rate_20d'):.2%} "
            f"mean_5d={row.get('mean_5d')} hit_5d={row.get('hit_rate_5d')} "
            f"p_value={row.get('p_value')}"
        )
        try:
            draft = (draft_fn or (lambda text: _default_draft(settings, db_path, text)))(evidence)
        except Exception as exc:
            skipped.append({"rating": row["rating"], "reason": f"Sin datos: LLM {exc}"})
            continue
        hypothesis = str(draft or "").strip()[:2000]
        if not hypothesis:
            skipped.append({"rating": row["rating"], "reason": "Sin datos: draft vacío"})
            continue
        if hypothesis in existing:
            skipped.append({"rating": row["rating"], "reason": "duplicada"})
            continue
        lesson = create_lesson(
            db_path,
            hypothesis=hypothesis,
            evidence=evidence,
            author="qwen",
            kind="lesson",
            settings=settings,
        )
        created.append(lesson)
        existing.add(hypothesis)
    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "reason": None if created else "Sin datos: no se crearon propuestas",
        "min_sample": min_sample,
    }


__all__ = [
    "AUTHORS",
    "STATUSES",
    "LearningError",
    "apply_lesson",
    "approve",
    "count_tests",
    "create_lesson",
    "evaluate_holdout_once",
    "get_lesson",
    "holdout_info",
    "holdout_usage",
    "init_learning",
    "list_lessons",
    "record_optimization_trial",
    "record_test",
    "reject",
    "research_trials",
    "revert_lesson",
    "weekly_lessons",
]

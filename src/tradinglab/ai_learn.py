"""Aprendizaje diario del carril IA: solo cambios que reducen riesgo.

Aplica como máximo dos cambios por semana (pausa, exclusión horaria/día/
condición o mitad de riesgo por símbolo), sube `playbook_version`, actualiza
el YAML y los dos skills y notifica. Lo que sube riesgo queda como lección
`proposed` para el operador.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .ai_trader import (
    NEW_YORK,
    _as_utc,
    _audit,
    _bootstrap_ci,
    _cell_status,
    _snapshot_condition,
    load_config,
)
from .alerts import send as send_alert
from .config import DEFAULT_DB, ROOT
from .db import connect, init_db
from .learning import create_lesson

CONFIG_PATH = ROOT / "config" / "ai_trader.yaml"
DOCS_PATH = ROOT / "docs" / "ai_trader_skill.md"
SKILL_PATH = (
    Path.home() / ".config" / "opencode" / "skills" /
    "trading-lab-operador" / "SKILL.md"
)
WEEKLY_LIMIT = 2
SNAPSHOT_FIELDS = (
    "session", "is_index", "trend_d1", "trend_h4", "bb_squeeze",
    "sweep_high", "sweep_low", "inside_bar", "rsi2_lt10",
)


class LearnError(ValueError):
    pass


def _stamp(value) -> datetime:
    if isinstance(value, datetime):
        stamp = value
    else:
        stamp = datetime.fromisoformat(str(value))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _cell_key(row: dict) -> tuple[str, str, str, str]:
    return (
        str(row.get("style") or ""),
        str(row.get("symbol") or ""),
        str(row.get("strategy") or ""),
        str(row.get("timeframe") or ""),
    )


def _evidence(values: list[float], seed: int) -> dict:
    mean = sum(values) / len(values)
    ci = _bootstrap_ci(values, seed=seed)
    return {
        "n": len(values),
        "mean_r": round(mean, 4),
        "ci90": ci,
    }


def _score(evidence: dict) -> float:
    return abs(float(evidence["mean_r"])) * math.sqrt(int(evidence["n"]))


def _load_rows(db_path: str | Path, version: int) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(row) for row in con.execute(
            "SELECT t.proposal_id, t.ts, t.style, t.symbol, t.setup AS strategy, "
            "t.timeframe, t.result_r, t.playbook_version, d.snapshot "
            "FROM ai_trades t "
            "LEFT JOIN ai_decisions d ON d.plan_id=t.proposal_id "
            " AND d.source='forward' AND d.decision='take' "
            "WHERE t.source='forward' AND t.status='closed' "
            " AND t.result_r IS NOT NULL AND t.playbook_version=? "
            "ORDER BY t.ts",
            (int(version),),
        ).fetchall()]
    out = []
    for row in rows:
        try:
            row["ts"] = _stamp(row["ts"])
        except Exception:
            continue
        try:
            row["result_r"] = float(row["result_r"])
        except (TypeError, ValueError):
            continue
        snapshot = row.get("snapshot")
        if isinstance(snapshot, str):
            try:
                row["snapshot"] = json.loads(snapshot)
            except json.JSONDecodeError:
                row["snapshot"] = None
        out.append(row)
    return out


def _candidate(kind: str, row: dict, evidence: dict, detail: str,
               **extra) -> dict:
    item = {
        "kind": kind,
        "style": str(row.get("style") or ""),
        "symbol": str(row.get("symbol") or ""),
        "strategy": str(row.get("strategy") or ""),
        "timeframe": str(row.get("timeframe") or ""),
        "evidence": evidence,
        "detail": detail,
        "score": round(_score(evidence), 4),
    }
    item.update(extra)
    return item


def _candidates(rows: list[dict], config: dict) -> list[dict]:
    candidates: list[dict] = []
    by_cell: dict[tuple, list[dict]] = {}
    for row in rows:
        by_cell.setdefault(_cell_key(row), []).append(row)

    for cell, items in by_cell.items():
        style, symbol, strategy, timeframe = cell
        values = [float(item["result_r"]) for item in items]
        if not values:
            continue
        seed = int.from_bytes(
            f"{style}|{symbol}|{strategy}|{timeframe}".encode()[:8], "little"
        )
        evidence = _evidence(values, seed)
        if evidence["n"] >= 30 and evidence["ci90"] and evidence["ci90"][1] < 0:
            candidates.append(_candidate(
                "pause", items[0], evidence,
                f"celda perdedora {strategy}/{symbol}/{timeframe}",
            ))
        # Exclusión por hora NY.
        by_hour: dict[int, list[float]] = {}
        by_weekday: dict[int, list[float]] = {}
        by_condition: dict[tuple[str, str], list[float]] = {}
        for item in items:
            local = item["ts"].astimezone(NEW_YORK)
            by_hour.setdefault(local.hour, []).append(float(item["result_r"]))
            by_weekday.setdefault(local.weekday(), []).append(float(item["result_r"]))
            snapshot = item.get("snapshot")
            if isinstance(snapshot, dict):
                for field in SNAPSHOT_FIELDS:
                    try:
                        value = _snapshot_condition(snapshot, field, timeframe)
                    except Exception:
                        value = None
                    if value is None:
                        continue
                    by_condition.setdefault((field, value), []).append(
                        float(item["result_r"])
                    )
        for hour, vals in by_hour.items():
            if len(vals) < 15:
                continue
            ev = _evidence(vals, seed + hour)
            if ev["ci90"] and ev["ci90"][1] < 0:
                candidates.append(_candidate(
                    "exclude_hour", items[0], ev,
                    f"{strategy}/{symbol}/{timeframe}: hora {hour} NY",
                    value=hour,
                ))
        for weekday, vals in by_weekday.items():
            if len(vals) < 15:
                continue
            ev = _evidence(vals, seed + 100 + weekday)
            if ev["ci90"] and ev["ci90"][1] < 0:
                candidates.append(_candidate(
                    "exclude_weekday", items[0], ev,
                    f"{strategy}/{symbol}/{timeframe}: día {weekday}",
                    value=weekday,
                ))
        for (field, value), vals in by_condition.items():
            if len(vals) < 15:
                continue
            ev = _evidence(vals, seed + 200 + SNAPSHOT_FIELDS.index(field))
            if ev["ci90"] and ev["ci90"][1] < 0:
                candidates.append(_candidate(
                    "exclude_snapshot", items[0], ev,
                    f"{strategy}/{symbol}/{timeframe}: {field}={value}",
                    field=field, value=value,
                ))

    # Mitad de riesgo por símbolo dentro del estilo.
    by_style_symbol: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        key = (str(row.get("style") or ""), str(row.get("symbol") or ""))
        by_style_symbol.setdefault(key, []).append(float(row["result_r"]))
    for (style, symbol), vals in by_style_symbol.items():
        if len(vals) < 30:
            continue
        ev = _evidence(vals, 500 + len(vals))
        if ev["mean_r"] >= 0:
            continue
        item_style = config["styles"].get(style)
        if item_style is None:
            continue
        base = float(item_style["risk_per_trade"])
        current = float(
            (item_style.get("risk_overrides") or {}).get(symbol.upper(), base)
        )
        if current <= base / 2 + 1e-12:
            continue
        candidates.append({
            "kind": "half_risk", "style": style, "symbol": symbol,
            "strategy": "", "timeframe": "",
            "evidence": ev, "detail": f"{symbol} en {style}: mitad de riesgo",
            "score": round(_score(ev), 4), "base_risk": base,
        })
    return sorted(
        candidates,
        key=lambda item: (item["score"], item["evidence"]["n"]),
        reverse=True,
    )


def _weekly_used(db_path: str | Path, now: datetime) -> int:
    init_db(db_path)
    since = (now - timedelta(days=7)).isoformat()
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM ai_learn_changes WHERE ts >= ?",
            (since,),
        ).fetchone()
    return int(row["n"])


def _load_raw_config(path: str | Path) -> dict:
    target = Path(path)
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise LearnError("config inválida")
    return data


def _write_config(path: str | Path, version: int, learned: dict) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    replaced, count = re.subn(
        r"(?m)^  playbook_version:\s*\d+",
        f"  playbook_version: {int(version)}",
        text,
        count=1,
    )
    if count != 1:
        raise LearnError("no se encontró global.playbook_version en el YAML")
    text = re.sub(r"(?ms)^learned:\s*$.*\Z", "", replaced).rstrip()
    clean = {
        key: value for key, value in learned.items()
        if value not in (None, [], {})
    }
    if clean:
        text += "\n\n" + yaml.safe_dump(
            {"learned": clean}, sort_keys=False, allow_unicode=True
        )
    target.write_text(text.rstrip() + "\n", encoding="utf-8")


def _write_docs_skill(path: Path, version: int, applied: list[dict],
                      learned: dict) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    lines = [f"## Cambios automáticos aprendidos (playbook v{version})",
             "<!-- learn:start -->"]
    if applied:
        for item in applied:
            ev = item.get("evidence") or {}
            lines.append(
                f"- {item['kind']}: {item.get('detail', '')} · "
                f"n={ev.get('n')} R={ev.get('mean_r')} IC90={ev.get('ci90')}"
            )
    else:
        lines.append("- Sin cambios aplicados en esta pasada.")
    exclusions = learned.get("exclusions") or []
    if exclusions:
        lines.append("")
        lines.append("Exclusiones vigentes:")
        for item in exclusions:
            lines.append(
                f"- {item.get('style')}/{item.get('symbol')}/"
                f"{item.get('strategy')}/{item.get('timeframe')}: "
                f"{item.get('kind')} {item.get('field') or ''}"
                f"={item.get('value')}"
            )
    overrides = learned.get("risk_overrides") or {}
    if overrides:
        lines.append("")
        lines.append("Riesgo por símbolo:")
        for style, mapping in overrides.items():
            for symbol, risk in mapping.items():
                lines.append(f"- {style}/{symbol}: {risk:.4%}")
    lines.append("<!-- learn:end -->")
    block = "\n".join(lines)
    if "<!-- learn:start -->" in text:
        text = re.sub(
            r"(?ms)^## Cambios automáticos aprendidos.*?<!-- learn:end -->",
            block,
            text,
            count=1,
        )
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")


def _proposed_lessons(db_path: str | Path, rows: list[dict],
                      config: dict, now: datetime) -> list[dict]:
    proposed: list[dict] = []
    by_cell: dict[tuple, list[float]] = {}
    for row in rows:
        by_cell.setdefault(_cell_key(row), []).append(float(row["result_r"]))
    for (style, symbol, strategy, timeframe), values in by_cell.items():
        if len(values) < 30:
            continue
        ev = _evidence(values, 700 + len(values))
        if not ev["ci90"] or ev["ci90"][0] <= 0:
            continue
        if _cell_status(
            db_path, strategy, symbol, timeframe
        ) != "paused":
            continue
        hypothesis = (
            f"Reactivar celda pausada {strategy}/{symbol}/{timeframe} "
            f"({style})"
        )
        evidence = (
            f"n={ev['n']} R medio={ev['mean_r']} IC90={ev['ci90']}"
        )
        if _lesson_exists(db_path, hypothesis):
            continue
        lesson = create_lesson(
            db_path, hypothesis=hypothesis, evidence=evidence,
            author="humano",
            action={"type": "resume_cell", "style": style, "symbol": symbol,
                    "strategy": strategy, "timeframe": timeframe},
        )
        proposed.append(lesson)
    # Riesgo que estaba a la mitad y ahora tiene evidencia positiva.
    by_style_symbol: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        by_style_symbol.setdefault(
            (str(row.get("style") or ""), str(row.get("symbol") or "")), []
        ).append(float(row["result_r"]))
    for (style, symbol), values in by_style_symbol.items():
        if len(values) < 30:
            continue
        ev = _evidence(values, 900 + len(values))
        if not ev["ci90"] or ev["ci90"][0] <= 0:
            continue
        item_style = config["styles"].get(style)
        if item_style is None:
            continue
        base = float(item_style["risk_per_trade"])
        current = float(
            (item_style.get("risk_overrides") or {}).get(symbol.upper(), base)
        )
        if current >= base - 1e-12:
            continue
        hypothesis = (
            f"Subir riesgo de {symbol} en {style} de {current:.4%} a {base:.4%}"
        )
        if _lesson_exists(db_path, hypothesis):
            continue
        lesson = create_lesson(
            db_path, hypothesis=hypothesis,
            evidence=f"n={ev['n']} R medio={ev['mean_r']} IC90={ev['ci90']}",
            author="humano",
            action={"type": "raise_risk", "style": style, "symbol": symbol,
                    "risk": base},
        )
        proposed.append(lesson)

    # Ampliación (estrategias, activos o estilos): solo propuesta.
    best = None
    for (style, symbol, strategy, timeframe), values in by_cell.items():
        if len(values) < 30:
            continue
        ev = _evidence(values, 1100 + len(values))
        if not ev["ci90"] or ev["ci90"][0] <= 0:
            continue
        score = _score(ev)
        if best is None or score > best[0]:
            best = (score, style, symbol, strategy, timeframe, ev)
    if best is not None:
        _, style, symbol, strategy, timeframe, ev = best
        hypothesis = (
            f"Revisar ampliación de {strategy} ({style}) a otros "
            f"activos/estilos desde {symbol}/{timeframe}"
        )
        if not _lesson_exists(db_path, hypothesis):
            lesson = create_lesson(
                db_path, hypothesis=hypothesis,
                evidence=(
                    f"n={ev['n']} R medio={ev['mean_r']} IC90={ev['ci90']}"
                ),
                author="humano",
                action={"type": "review_expansion", "style": style,
                        "symbol": symbol, "strategy": strategy,
                        "timeframe": timeframe},
            )
            proposed.append(lesson)
    return proposed


def _lesson_exists(db_path: str | Path, hypothesis: str) -> bool:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT 1 FROM lessons WHERE status='proposed' AND hypothesis=? "
            "LIMIT 1",
            (hypothesis,),
        ).fetchone()
    return row is not None


def learn(*, db_path: str | Path = DEFAULT_DB,
          config_path: str | Path = CONFIG_PATH,
          docs_path: str | Path = DOCS_PATH,
          skill_path: str | Path = SKILL_PATH,
          now: datetime | None = None,
          apply: bool = True) -> dict:
    moment = _as_utc(now)
    cfg = load_config(config_path)
    version = int(cfg["playbook_version"])
    rows = _load_rows(db_path, version)
    candidates = _candidates(rows, cfg)
    used = _weekly_used(db_path, moment)
    slots = max(0, WEEKLY_LIMIT - used)
    applied: list[dict] = []
    skipped: list[dict] = []
    raw = _load_raw_config(config_path)
    learned = dict(raw.get("learned") or {})
    if not isinstance(learned, dict):
        learned = {}
    learned.setdefault("exclusions", [])
    learned.setdefault("risk_overrides", {})
    current_version = version
    for candidate in candidates:
        kind = candidate["kind"]
        # Evitar duplicados ya vigentes.
        if kind == "pause" and _cell_status(
            db_path, candidate["strategy"], candidate["symbol"],
            candidate["timeframe"],
        ) == "paused":
            continue
        if kind in {"exclude_hour", "exclude_weekday", "exclude_snapshot"}:
            if any(
                item.get("style") == candidate["style"]
                and item.get("symbol") == candidate["symbol"]
                and item.get("strategy") == candidate["strategy"]
                and item.get("timeframe") == candidate["timeframe"]
                and item.get("kind") == kind.replace("exclude_", "")
                and item.get("field") == candidate.get("field")
                and str(item.get("value")) == str(candidate.get("value"))
                for item in learned["exclusions"]
            ):
                continue
        if kind == "half_risk":
            style = candidate["style"]
            symbol = candidate["symbol"]
            base = float(
                candidate.get("base_risk")
                or cfg["styles"][style]["risk_per_trade"]
            )
            existing = learned["risk_overrides"].get(style, {}).get(symbol)
            if existing is not None and float(existing) <= base / 2 + 1e-12:
                continue
        if not apply:
            skipped.append({**candidate, "reason": "dry-run"})
            continue
        if len(applied) >= slots:
            skipped.append({**candidate, "reason": "límite semanal de 2"})
            continue
        current_version += 1
        if kind == "pause":
            with connect(db_path) as con:
                con.execute(
                    "INSERT INTO ai_cell_state(strategy, symbol, timeframe, "
                    "status, reason, updated_at) VALUES(?,?,?,'paused',?,?) "
                    "ON CONFLICT(strategy,symbol,timeframe) DO UPDATE SET "
                    "status='paused', reason=excluded.reason, "
                    "updated_at=excluded.updated_at",
                    (
                        candidate["strategy"], candidate["symbol"],
                        candidate["timeframe"],
                        f"learn v{current_version}: {candidate['detail']}",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        elif kind == "half_risk":
            style = candidate["style"]
            symbol = candidate["symbol"]
            base = float(candidate.get("base_risk") or cfg["styles"][style]["risk_per_trade"])
            learned["risk_overrides"].setdefault(style, {})[symbol] = (
                round(base / 2, 6)
            )
        else:
            learned["exclusions"].append({
                "style": candidate["style"],
                "symbol": candidate["symbol"],
                "strategy": candidate["strategy"],
                "timeframe": candidate["timeframe"],
                "kind": kind.replace("exclude_", ""),
                "field": candidate.get("field"),
                "value": candidate.get("value"),
                "reason": candidate["detail"][:200],
            })
        applied.append({**candidate, "playbook_version": current_version})
        with connect(db_path) as con:
            con.execute(
                "INSERT INTO ai_learn_changes(ts, kind, style, symbol, strategy, "
                "timeframe, detail, evidence, playbook_version) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    moment.isoformat(), kind, candidate["style"],
                    candidate["symbol"], candidate["strategy"],
                    candidate["timeframe"], candidate["detail"],
                    json.dumps(candidate["evidence"], ensure_ascii=False),
                    current_version,
                ),
            )
        _audit(
            db_path, "ai_trader_learn",
            {
                "kind": kind, "style": candidate["style"],
                "symbol": candidate["symbol"],
                "strategy": candidate["strategy"],
                "timeframe": candidate["timeframe"],
                "evidence": candidate["evidence"],
                "playbook_version": current_version,
            },
            "applied", detail=candidate["detail"],
        )
    proposed = _proposed_lessons(db_path, rows, cfg, moment) if apply else []
    if apply and applied:
        _write_config(config_path, current_version, learned)
        for target in (Path(docs_path), Path(skill_path)):
            try:
                _write_docs_skill(target, current_version, applied, learned)
            except Exception:
                pass
        lines = [
            f"IA learn · playbook v{current_version} · "
            f"{len(applied)} cambio(s) aplicado(s)",
        ]
        for item in applied:
            ev = item["evidence"]
            lines.append(
                f"- {item['kind']} · {item['detail']} · n={ev['n']} "
                f"R={ev['mean_r']} IC90={ev['ci90']}"
            )
        if proposed:
            lines.append(f"Lecciones proposed: {len(proposed)}")
        try:
            send_alert(
                "ai_trader_learn", "\n".join(lines),
                severity="info", db_path=db_path,
            )
        except Exception:
            pass
    return {
        "version_before": version,
        "version_after": current_version,
        "candidates": len(candidates),
        "applied": applied,
        "skipped": skipped,
        "proposed": proposed,
        "weekly_used_before": used,
        "weekly_slots": slots,
        "trades": len(rows),
    }

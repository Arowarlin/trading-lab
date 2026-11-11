"""F13: pilot operativo de paper trading.

La decisión de F13 es deliberadamente conservadora: 4-8 semanas con una
estrategia diaria de ~2 trades/año no alcanzan para demostrar edge. Por eso
F13 mide sobre todo **operativa** (ciclos, guard, reconciliación, slippage,
fidelidad de señal) y solo extiende la evaluación de edge a 6 meses o >=20
trades. Nada se activa solo.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

import yaml

from .config import DEFAULT_DB, ROOT, Settings, get_settings
from .db import connect, init_db, utcnow

DEFAULT_CRITERIA: dict = {
    "window_weeks": 8,
    "min_cycles_pct": 0.95,
    "min_reconciliation_ok_pct": 0.95,
    "max_slippage_bps_p50": 10,
    "max_slippage_bps_p95": 25,
    "max_size_error_shares": 1,
    "expected_trades_8w_low": 0,
    "expected_trades_8w_high": 3,
    "edge_extension": "6 meses o >=20 trades",
    "hard_stops": [
        "cualquier breach de guard o kill-switch",
        "cualquier orden no autorizada o intento de live",
        "reconciliación con diferencia no explicada",
        "hash de configuración distinto al congelado",
        "dos ciclos diarios consecutivos perdidos",
    ],
}


def config_files(root: Path = ROOT) -> list[Path]:
    return [
        root / "config" / "lab.yaml",
        root / "config" / "bots.yaml",
        root / "config" / "prop.yaml",
        root / "config" / "f13.yaml",
    ]


def config_hash(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in config_files(root):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes() if path.exists() else b"")
    return digest.hexdigest()


def _normalised(blob: bytes) -> bytes:
    """Compara contenido ignorando CRLF/LF: el repo y Windows no coinciden."""
    return blob.replace(b"\r\n", b"\n")


def file_digests(root: Path = ROOT) -> dict[str, str]:
    """sha256 por archivo (normalizado a LF) para comparar el freeze."""
    return {
        path.name: hashlib.sha256(
            _normalised(path.read_bytes() if path.exists() else b"")
        ).hexdigest()
        for path in config_files(root)
    }


def _bot_block(bots_bytes: bytes, bot: str) -> dict | None:
    try:
        data = yaml.safe_load(bots_bytes.decode("utf-8")) or {}
    except Exception:
        return None
    for item in data.get("bots") or []:
        if str(item.get("id")) == str(bot):
            return item
    return None


def _baseline_from_git(
    root: Path, frozen_hash: str
) -> tuple[str, dict[str, str], dict[str, bytes]] | None:
    """Busca el commit cuyo hash combinado coincide con el congelado.

    Devuelve (commit, huellas por archivo, contenido por archivo) o None. El
    hash se calculó sobre los bytes del árbol de trabajo, así que se prueban
    las combinaciones CRLF/LF por archivo hasta reproducirlo.
    """
    import itertools
    import subprocess

    names = [path.name for path in config_files(root)]

    def git(*args: str) -> bytes:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
        ).stdout

    try:
        log = git("log", "--format=%H", "--", *[f"config/{name}" for name in names])
    except Exception:
        return None
    for sha in log.decode("utf-8", errors="replace").split():
        blobs: list[bytes] = []
        for name in names:
            try:
                blobs.append(git("show", f"{sha}:config/{name}"))
            except Exception:
                blobs.append(b"")
        for flags in itertools.product([False, True], repeat=len(names)):
            digest = hashlib.sha256()
            for name, blob, crlf in zip(names, blobs, flags):
                data = (
                    blob.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                    if crlf
                    else blob
                )
                digest.update(name.encode("utf-8"))
                digest.update(data)
            if digest.hexdigest() == frozen_hash:
                digests = {
                    name: hashlib.sha256(_normalised(blob)).hexdigest()
                    for name, blob in zip(names, blobs)
                }
                return (
                    sha,
                    digests,
                    {name: blob for name, blob in zip(names, blobs)},
                )
    return None


def load_criteria(root: Path = ROOT) -> dict:
    path = root / "config" / "f13.yaml"
    if not path.exists():
        return dict(DEFAULT_CRITERIA)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    criteria = dict(DEFAULT_CRITERIA)
    criteria.update(data.get("criteria") or {})
    return criteria


def freeze(
    db_path: str | Path,
    *,
    bot: str,
    symbol: str,
    start_date: str,
    root: Path = ROOT,
) -> dict:
    """Congela configuración y criterios. No activa el bot."""
    init_db(db_path)
    criteria = load_criteria(root)
    digest = config_hash(root)
    digests = json.dumps(file_digests(root), sort_keys=True, ensure_ascii=False)
    with connect(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO f13_config"
            "(id, bot, symbol, start_date, config_hash, criteria, frozen_at, "
            "file_hashes) VALUES(1, ?, ?, ?, ?, ?, ?, ?)",
            (
                bot,
                symbol,
                start_date,
                digest,
                json.dumps(criteria, ensure_ascii=False),
                utcnow(),
                digests,
            ),
        )
    return status(db_path) or {}


PROTECTED_FILES = ("bots.yaml", "prop.yaml", "f13.yaml")


def refreeze(
    db_path: str | Path,
    *,
    reason: str,
    root: Path = ROOT,
    bot: str | None = None,
    baseline: dict[str, str] | None = None,
) -> dict:
    """Re-congela el hash **solo** si lo protegido no cambió.

    - Protegidos: `bots.yaml`, `prop.yaml`, `f13.yaml` y el bloque del bot
      F13 dentro de `bots.yaml`. Deben ser idénticos al freeze.
    - `lab.yaml` sí puede cambiar (p. ej. un bloque ajeno al bot).
    - Guarda el hash anterior, el nuevo, el motivo y la fecha en
      `f13_config`, el historial en `f13_refreezes` y audita
      `f13_refreeze` en `console_actions`.
    """
    init_db(db_path)
    frozen = status(db_path)
    if not frozen:
        raise ValueError("F13 no está congelado; usa `lab f13 freeze`.")
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("El re-congelado exige un motivo (--reason).")
    bot_id = str(bot or frozen.get("bot") or "")

    baseline_digests: dict[str, str] | None = None
    baseline_blobs: dict[str, bytes] | None = None
    source = ""
    if baseline is not None:
        baseline_digests = {str(key): str(value) for key, value in dict(baseline).items()}
        source = "explicito"
    if baseline_digests is None:
        raw = str(frozen.get("file_hashes") or "").strip()
        if raw:
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                data = None
            if isinstance(data, dict):
                baseline_digests = {
                    str(key): str(value) for key, value in data.items()
                }
                source = "f13_config"
    if baseline_digests is None:
        found = _baseline_from_git(root, str(frozen.get("config_hash") or ""))
        if found is not None:
            commit, baseline_digests, baseline_blobs = found
            source = f"git:{commit[:7]}"
    if baseline_digests is None:
        raise ValueError(
            "Sin huellas por archivo del freeze y sin historial git que las "
            "reconstruya: no se re-congela a ciegas."
        )

    current = file_digests(root)
    changed = [
        path.name
        for path in config_files(root)
        if current.get(path.name) != baseline_digests.get(path.name)
    ]
    protected_changed = [name for name in PROTECTED_FILES if name in changed]
    if protected_changed:
        raise ValueError(
            "Cambiaron archivos protegidos por F13: "
            f"{', '.join(protected_changed)}. No se re-congela."
        )
    if baseline_blobs is not None:
        before = _bot_block(baseline_blobs.get("bots.yaml", b""), bot_id)
        after = _bot_block(
            (root / "config" / "bots.yaml").read_bytes()
            if (root / "config" / "bots.yaml").exists()
            else b"",
            bot_id,
        )
        if before != after:
            raise ValueError(
                f"El bot {bot_id} cambió en bots.yaml; no se re-congela."
            )

    previous = str(frozen.get("config_hash") or "")
    new_hash = config_hash(root)
    if new_hash == previous:
        raise ValueError(
            "El hash no cambió respecto al congelado; no hay nada que re-congelar."
        )
    now = utcnow()
    payload = json.dumps(current, sort_keys=True, ensure_ascii=False)
    with connect(db_path) as con:
        con.execute(
            "UPDATE f13_config SET config_hash=?, frozen_at=?, file_hashes=?, "
            "previous_hash=?, refreeze_reason=?, refrozen_at=? WHERE id=1",
            (new_hash, now, payload, previous, reason, now),
        )
        con.execute(
            "INSERT INTO f13_refreezes"
            "(ts, bot, previous_hash, new_hash, reason, changed_files, "
            "file_hashes, actor) VALUES(?,?,?,?,?,?,?,?)",
            (
                now,
                bot_id,
                previous,
                new_hash,
                reason,
                json.dumps(changed, ensure_ascii=False),
                payload,
                "cli",
            ),
        )
    try:
        from .runtime import record_console_action

        record_console_action(
            db_path,
            action="f13_refreeze",
            params={
                "bot": bot_id,
                "previous_hash": previous,
                "new_hash": new_hash,
                "reason": reason,
            },
            result="re-congelado",
            ok=True,
            actor="cli",
            detail=json.dumps(
                {"source": source, "changed_files": changed},
                ensure_ascii=False,
            )[:900],
        )
    except Exception:
        pass
    return {
        "bot": bot_id,
        "previous_hash": previous,
        "new_hash": new_hash,
        "reason": reason,
        "changed_files": changed,
        "source": source,
        "frozen_at": now,
    }


def refreeze_history(db_path: str | Path, limit: int = 20) -> list[dict]:
    """Historial de re-congelados, el más reciente primero."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM f13_refreezes ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


def _set_bot_enabled(root: Path, bot: str, enabled: bool) -> None:
    """Edita solo la línea enabled del bot, preservando el resto del YAML."""
    path = root / "config" / "bots.yaml"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^\s*-\s+id:\s*['\"]?{re.escape(bot)}['\"]?\s*$", line):
            start = index
            break
    if start is None:
        raise ValueError(f"Bot no encontrado en bots.yaml: {bot}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^[^\s#]", lines[index]):
            end = index
            break
        if re.match(r"^\s*-\s+id:\s*", lines[index]):
            end = index
            break
    changed = False
    for index in range(start, end):
        match = re.match(
            r"^(\s*)enabled:\s*(true|false)\s*(#.*)?$",
            lines[index],
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        indent = match.group(1)
        comment = match.group(3)
        newline = "\n" if lines[index].endswith("\n") else ""
        suffix = f" {comment.strip()}" if comment else ""
        lines[index] = (
            f"{indent}enabled: {'true' if enabled else 'false'}{suffix}{newline}"
        )
        changed = True
        break
    if not changed:
        raise ValueError(f"No encuentro enabled: en el bloque de {bot}")
    new_text = "".join(lines)
    old_data = yaml.safe_load(text) or {}
    new_data = yaml.safe_load(new_text) or {}
    expected = copy.deepcopy(old_data)
    for item in expected.get("bots", []):
        if item.get("id") == bot:
            item["enabled"] = bool(enabled)
    if new_data != expected:
        raise ValueError("La edición de bots.yaml cambió más de lo previsto.")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)


def activate(
    db_path: str | Path,
    *,
    bot: str,
    root: Path = ROOT,
    settings: Settings | None = None,
) -> dict:
    """Activa el bot F13 en paper y re-congela el hash. No live, no órdenes."""
    init_db(db_path)
    frozen = status(db_path)
    if not frozen:
        raise ValueError("F13 no está congelado.")
    if str(frozen.get("bot")) != bot:
        raise ValueError(
            f"F13 está congelado para {frozen.get('bot')}, no para {bot}."
        )
    mode = (settings or get_settings()).mode
    if mode != "paper":
        raise ValueError("F13 solo se activa en paper; mode=live está bloqueado.")
    check = config_check(db_path, root)
    if not check["ok"]:
        raise ValueError("El hash congelado no coincide con la configuración actual.")
    bots_path = root / "config" / "bots.yaml"
    if not bots_path.exists():
        raise ValueError("No existe config/bots.yaml.")
    original = bots_path.read_text(encoding="utf-8")
    data = yaml.safe_load(original) or {}
    spec = next(
        (item for item in data.get("bots", []) if item.get("id") == bot),
        None,
    )
    if spec is None:
        raise ValueError(f"Bot no encontrado: {bot}")
    if bool(spec.get("enabled")):
        raise ValueError(f"{bot} ya está enabled:true.")

    _set_bot_enabled(root, bot, True)
    try:
        row = freeze(
            db_path,
            bot=bot,
            symbol=str(frozen.get("symbol") or "QQQ"),
            start_date=str(frozen.get("start_date")),
            root=root,
        )
    except Exception:
        bots_path.write_text(original, encoding="utf-8")
        raise

    try:
        from .runtime import set_bot_enabled

        set_bot_enabled(
            db_path,
            bot=bot,
            enabled=True,
            yaml_enabled=True,
            actor="f13-activate",
            reason="activación F13 en paper",
        )
    except Exception:
        pass
    try:
        from .runtime import record_console_action

        record_console_action(
            db_path,
            action="f13_activate",
            params={"bot": bot, "start_date": row.get("start_date")},
            result="activado",
            ok=True,
            actor="cli",
            detail="re-congelado con enabled:true; paper",
        )
    except Exception:
        pass
    return row


def status(db_path: str | Path) -> dict | None:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM f13_config WHERE id = 1").fetchone()
    return dict(row) if row else None


def config_check(db_path: str | Path, root: Path = ROOT) -> dict:
    frozen = status(db_path)
    if not frozen:
        return {"ok": True, "status": "not_started", "current": config_hash(root)}
    current = config_hash(root)
    return {
        "ok": current == frozen["config_hash"],
        "status": "ok" if current == frozen["config_hash"] else "changed",
        "frozen": frozen["config_hash"],
        "current": current,
    }


def record_snapshot(
    db_path: str | Path,
    broker,
    *,
    bot: str,
    spy_close: float | None = None,
) -> dict:
    init_db(db_path)
    snap = broker.snapshot({})
    equity = float(snap.get("equity") or 0.0)
    with connect(db_path) as con:
        last = con.execute("SELECT equity FROM f13_metrics ORDER BY id DESC LIMIT 1").fetchone()
        prev = float(last["equity"]) if last else equity
        daily = equity / prev - 1.0 if prev > 0 else 0.0
        peak_row = con.execute("SELECT MAX(equity) AS peak FROM f13_metrics").fetchone()
        peak = max(equity, float(peak_row["peak"] or equity))
        drawdown = equity / peak - 1.0 if peak > 0 else 0.0
        spy_row = con.execute(
            "SELECT spy_close FROM f13_metrics WHERE spy_close IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_spy = float(spy_row["spy_close"]) if spy_row and spy_row["spy_close"] else None
        spy_return = (
            spy_close / last_spy - 1.0 if spy_close is not None and last_spy and last_spy > 0 else None
        )
        con.execute(
            "INSERT INTO f13_metrics"
            "(ts, trade_date, equity, cash, positions_value, daily_return, drawdown, "
            "spy_close, spy_return, open_positions, trades, notes) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                utcnow()[:10],
                equity,
                float(snap.get("cash") or 0.0),
                float(snap.get("positions_value") or 0.0),
                daily,
                drawdown,
                spy_close,
                spy_return,
                len(snap.get("positions") or []),
                0,
                bot,
            ),
        )
    return {"equity": equity, "daily_return": daily, "drawdown": drawdown, "spy_return": spy_return}


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def execution_metrics(
    db_path: str | Path,
    *,
    bot: str,
    start_date: str,
) -> dict:
    """Slippage real vs señal y error de tamaño vs orden."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT o.id, o.ts, o.ticker, o.side, o.qty, o.bot, f.price AS fill_price, f.qty AS fill_qty "
            "FROM orders o JOIN fills f ON f.order_id = o.id "
            "WHERE o.bot = ? AND o.ts >= ? ORDER BY o.id",
            (bot, start_date),
        ).fetchall()
        metrics = []
        for row in rows:
            signal = con.execute(
                "SELECT price FROM signals WHERE ticker = ? AND bot = ? AND ts <= ? "
                "ORDER BY id DESC LIMIT 1",
                (row["ticker"], bot, row["ts"]),
            ).fetchone()
            if not signal or not signal["price"] or not row["fill_price"]:
                continue
            sign = 1.0 if row["side"].lower() == "buy" else -1.0
            slippage = (float(row["fill_price"]) / float(signal["price"]) - 1.0) * 10_000 * sign
            metrics.append(
                {
                    "ticker": row["ticker"],
                    "slippage_bps": slippage,
                    "size_error": abs(float(row["fill_qty"]) - float(row["qty"])),
                }
            )
    values = [m["slippage_bps"] for m in metrics]
    return {
        "fills": len(metrics),
        "slippage_p50_bps": _percentile(values, 0.50),
        "slippage_p95_bps": _percentile(values, 0.95),
        "size_error_max": max((m["size_error"] for m in metrics), default=0.0),
    }


def _business_days(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _dryrun_cycles(root: Path, start: date, end: date) -> dict[date, str]:
    """Un ciclo por fecha con dry-run registrado (UTC, nombre del archivo)."""
    folder = root / "data" / "dryrun"
    if not folder.exists():
        return {}
    cycles: dict[date, str] = {}
    for path in sorted(folder.glob("dryrun_*.json")):
        match = re.match(
            r"dryrun_(\d{4})(\d{2})(\d{2})_(\d{6})\.json$", path.name
        )
        if not match:
            continue
        try:
            day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
        if start <= day <= end:
            cycles[day] = path.name
    return cycles


def _previous_monday(day: date) -> date:
    offset = day.weekday() if day.weekday() > 0 else 7
    return day - timedelta(days=offset)


def _frozen_criteria(frozen: dict, root: Path) -> dict:
    raw = frozen.get("criteria")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                merged = dict(DEFAULT_CRITERIA)
                merged.update(data)
                return merged
        except (TypeError, ValueError):
            pass
    return load_criteria(root)


def _pct_or_dash(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _num_or_dash(value: float | None) -> str:
    return "—" if value is None else f"{value:g}"


def _render_daily_report(payload: dict) -> str:
    criteria = payload.get("criteria") or {}
    cycles = payload.get("cycles") or {}
    recs = payload.get("reconciliations") or {}
    slip = payload.get("slippage") or {}
    size = payload.get("size") or {}
    config = payload.get("config") or {}
    lines = [
        f"# F13 · reporte diario {payload.get('report_date')}",
        "",
        f"Generado: {payload.get('generated_at')} · solo lectura",
    ]
    if payload.get("status") == "not_started":
        lines += [
            "",
            "F13 no iniciado. Criterios congelados/configurados:",
            "",
            "```json",
            json.dumps(criteria, indent=2, ensure_ascii=False, sort_keys=True),
            "```",
            "",
        ]
        return "\n".join(lines)

    monday = cycles.get("monday") or {}
    missing = cycles.get("missing") or []
    lines += [
        "",
        f"- Bot: `{payload.get('bot')}` · símbolo `{payload.get('symbol')}`",
        f"- Inicio: {payload.get('start_date')}",
        (
            f"- Hash: `{config.get('short')}…` · "
            f"{'OK' if config.get('ok') else 'CAMBIADO'}"
        ),
        "",
        "## Criterios",
        "",
        "| Criterio | Valor |",
        "|---|---|",
        f"| Ciclos mínimos | {_pct_or_dash(criteria.get('min_cycles_pct'))} |",
        (
            "| Reconciliaciones OK | "
            f"{_pct_or_dash(criteria.get('min_reconciliation_ok_pct'))} |"
        ),
        (
            "| Slippage p50 / p95 | "
            f"{_num_or_dash(criteria.get('max_slippage_bps_p50'))} / "
            f"{_num_or_dash(criteria.get('max_slippage_bps_p95'))} bps |"
        ),
        (
            "| Error de tamaño máx. | "
            f"{_num_or_dash(criteria.get('max_size_error_shares'))} acciones |"
        ),
        "",
        "## Ciclos",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Esperados (hasta ayer) | {cycles.get('expected', 0)} |",
        f"| Ejecutados | {cycles.get('executed', 0)} |",
        (
            "| Cumplimiento | "
            f"{_pct_or_dash(cycles.get('pct'))} · "
            f"{'OK' if cycles.get('ok') else 'FALLO'} |"
        ),
        f"| Último ciclo | {cycles.get('last_cycle_at') or '—'} |",
        f"| Ciclo de hoy | {'sí' if cycles.get('today') else 'no'} |",
        (
            "| Lunes | "
            f"{monday.get('date') or '—'} · "
            f"{'OK' if monday.get('ok') else 'FALTA'} |"
        ),
        f"| Fechas sin ciclo | {', '.join(missing) if missing else '—'} |",
        "",
        "## Reconciliaciones",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Total | {recs.get('count', 0)} |",
        (
            "| OK | "
            f"{recs.get('ok_count', 0)} "
            f"({_pct_or_dash(recs.get('ok_pct'))}) · "
            f"{'OK' if recs.get('ok') else 'FALLO'} |"
        ),
    ]
    last = recs.get("last") or {}
    if last:
        lines.append(
            f"| Última | {last.get('ts')} · {last.get('status')} · "
            f"{last.get('details') or 'sin diferencias'} |"
        )
    lines += [
        "",
        "## Slippage y tamaño",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Fills | {slip.get('fills', 0)} |",
        (
            "| Slippage p50 | "
            f"{_num_or_dash(slip.get('p50_bps'))} bps · "
            f"{'OK' if slip.get('ok') else 'FALLO'} |"
        ),
        f"| Slippage p95 | {_num_or_dash(slip.get('p95_bps'))} bps |",
        (
            "| Error tamaño máx. | "
            f"{_num_or_dash(size.get('max_error_shares'))} · "
            f"{'OK' if size.get('ok') else 'FALLO'} |"
        ),
        "",
    ]
    refreezes = payload.get("refreezes") or []
    lines += [
        "## Re-congelados",
        "",
        f"- Total: {len(refreezes)}",
        "",
    ]
    if refreezes:
        lines += [
            "| Fecha | Anterior | Nuevo | Motivo |",
            "|---|---|---|---|",
        ]
        for item in refreezes:
            lines.append(
                f"| {str(item.get('ts') or '')[:19]} | "
                f"`{str(item.get('previous_hash') or '')[:12]}…` | "
                f"`{str(item.get('new_hash') or '')[:12]}…` | "
                f"{item.get('reason') or '—'} |"
            )
    else:
        lines.append("Sin re-congelados.")
    lines += [
        "",
        "## Alertas",
        "",
    ]
    alerts = payload.get("alerts") or []
    if alerts:
        lines += [
            f"- `{alert.get('id')}`: {alert.get('message')}" for alert in alerts
        ]
    else:
        lines.append("Sin alertas.")
    lines += [
        "",
        "> Reporte de solo lectura: no envía órdenes, no activa bots y no "
        "modifica el estado operativo.",
        "",
    ]
    return "\n".join(lines)


def _write_daily_report(out_dir: Path, payload: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    day = str(payload["report_date"])
    json_path = out_dir / f"{day}.json"
    md_path = out_dir / f"{day}.md"
    data = dict(payload)
    data["files"] = {"json": str(json_path), "markdown": str(md_path)}
    text = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    for path in (json_path, out_dir / "latest.json"):
        path.write_text(text, encoding="utf-8")
    markdown = _render_daily_report(data)
    for path in (md_path, out_dir / "latest.md"):
        path.write_text(markdown, encoding="utf-8")
    return data


def daily_report(
    db_path: str | Path,
    *,
    root: Path = ROOT,
    out_dir: str | Path | None = None,
    today: date | None = None,
) -> dict:
    """Genera el reporte diario F13 en reports/f13/ sin operar.

    Cuenta ciclos por dry-run, reconciliaciones, slippage, tamaño y hash.
    Marca `monday_missing` si el último lunes esperado no tiene ciclo.
    """
    init_db(db_path)
    report_day = today or date.today()
    frozen = status(db_path)
    out = Path(out_dir) if out_dir is not None else root / "reports" / "f13"
    criteria = load_criteria(root)

    if not frozen:
        payload = {
            "generated_at": utcnow(),
            "report_date": report_day.isoformat(),
            "status": "not_started",
            "read_only": True,
            "criteria": criteria,
            "alerts": [],
        }
        return _write_daily_report(out, payload)

    bot = str(frozen.get("bot") or "")
    start = date.fromisoformat(str(frozen.get("start_date")))
    criteria = _frozen_criteria(frozen, root)
    check = config_check(db_path, root)
    refreezes = refreeze_history(db_path)
    cycle_map = _dryrun_cycles(root, start, report_day)
    expected_days = _business_days(start, report_day - timedelta(days=1))
    executed_days = [day for day in expected_days if day in cycle_map]
    missing_days = [day for day in expected_days if day not in cycle_map]
    cycles_pct = len(executed_days) / len(expected_days) if expected_days else None
    min_cycles_pct = float(criteria.get("min_cycles_pct", 0.95))
    cycles_ok = cycles_pct is None or cycles_pct >= min_cycles_pct

    last_file = max(cycle_map.values()) if cycle_map else None
    last_cycle_at = None
    if last_file:
        match = re.match(
            r"dryrun_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json$",
            last_file,
        )
        if match:
            last_cycle_at = (
                f"{match.group(1)}-{match.group(2)}-{match.group(3)}T"
                f"{match.group(4)}:{match.group(5)}:{match.group(6)}Z"
            )

    monday = _previous_monday(report_day)
    monday_expected = monday.isoformat() if monday >= start else None
    monday_ok = monday_expected is None or monday in cycle_map

    with connect(db_path) as con:
        rec_rows = con.execute(
            "SELECT * FROM reconciliation WHERE ts >= ? ORDER BY id",
            (f"{start.isoformat()}T00:00:00",),
        ).fetchall()
    rec_count = len(rec_rows)
    rec_ok_count = sum(1 for row in rec_rows if row["status"] == "ok")
    rec_pct = rec_ok_count / rec_count if rec_count else None
    min_rec_pct = float(criteria.get("min_reconciliation_ok_pct", 0.95))
    rec_ok = rec_pct is None or rec_pct >= min_rec_pct
    rec_last = dict(rec_rows[-1]) if rec_rows else None

    execution = execution_metrics(db_path, bot=bot, start_date=start.isoformat())
    max_slippage_p50 = float(criteria.get("max_slippage_bps_p50", 10))
    max_slippage_p95 = float(criteria.get("max_slippage_bps_p95", 25))
    p50 = execution["slippage_p50_bps"]
    p95 = execution["slippage_p95_bps"]
    slippage_ok = execution["fills"] == 0 or (
        (p50 if p50 is not None else 0.0) <= max_slippage_p50
        and (p95 if p95 is not None else 0.0) <= max_slippage_p95
    )
    max_size_error = float(criteria.get("max_size_error_shares", 1))
    size_error = float(execution["size_error_max"])
    size_ok = size_error <= max_size_error

    alerts: list[dict] = []
    if not check["ok"]:
        alerts.append(
            {
                "id": "f13_hash_changed",
                "severity": "critical",
                "message": "El hash actual no coincide con el congelado.",
            }
        )
    if not cycles_ok:
        alerts.append(
            {
                "id": "f13_cycles_low",
                "severity": "warning",
                "message": (
                    f"Ciclos {len(executed_days)}/{len(expected_days)} "
                    f"({_pct_or_dash(cycles_pct)}); mínimo {min_cycles_pct:.0%}."
                ),
            }
        )
    if not rec_ok:
        alerts.append(
            {
                "id": "f13_reconciliation_low",
                "severity": "error",
                "message": (
                    f"Reconciliaciones OK {rec_ok_count}/{rec_count} "
                    f"({_pct_or_dash(rec_pct)}); mínimo {min_rec_pct:.0%}."
                ),
            }
        )
    if not slippage_ok:
        alerts.append(
            {
                "id": "f13_slippage_high",
                "severity": "warning",
                "message": (
                    f"Slippage p50={_num_or_dash(p50)} bps "
                    f"p95={_num_or_dash(p95)} bps."
                ),
            }
        )
    if not size_ok:
        alerts.append(
            {
                "id": "f13_size_error",
                "severity": "error",
                "message": (
                    f"Error de tamaño {size_error:g} > {max_size_error:g}."
                ),
            }
        )
    if monday_expected is not None and not monday_ok:
        alerts.append(
            {
                "id": "f13_monday_missed",
                "severity": "error",
                "message": f"Falta el ciclo del lunes {monday_expected}.",
                "date": monday_expected,
            }
        )

    payload = {
        "generated_at": utcnow(),
        "report_date": report_day.isoformat(),
        "status": "ok" if not alerts else "warn",
        "read_only": True,
        "bot": bot,
        "symbol": str(frozen.get("symbol") or ""),
        "start_date": start.isoformat(),
        "config": {
            "hash": str(frozen.get("config_hash") or ""),
            "frozen_hash": check.get("frozen"),
            "current_hash": check.get("current"),
            "short": str(check.get("frozen") or frozen.get("config_hash") or "")[:16],
            "ok": bool(check["ok"]),
        },
        "criteria": criteria,
        "refreezes": refreezes,
        "cycles": {
            "expected": len(expected_days),
            "executed": len(executed_days),
            "pct": cycles_pct,
            "ok": cycles_ok,
            "missing": [day.isoformat() for day in missing_days],
            "last_cycle_at": last_cycle_at,
            "today": report_day in cycle_map,
            "monday": {"date": monday_expected, "ok": monday_ok},
        },
        "reconciliations": {
            "count": rec_count,
            "ok_count": rec_ok_count,
            "ok_pct": rec_pct,
            "ok": rec_ok,
            "last": rec_last,
        },
        "slippage": {
            "fills": execution["fills"],
            "p50_bps": p50,
            "p95_bps": p95,
            "ok": slippage_ok,
        },
        "size": {
            "max_error_shares": size_error,
            "ok": size_ok,
        },
        "alerts": alerts,
    }
    return _write_daily_report(out, payload)


def signal_check(
    settings: Settings,
    spec,
    db_path: str | Path = DEFAULT_DB,
) -> dict:
    """Recalcula la señal de hoy y la compara con la última señal registrada."""
    from . import data as data_mod
    from .indicators import atr
    from .strategies import STRATEGIES

    df = data_mod.fetch(
        spec.universe[0],
        (date.today() - timedelta(days=365 * 8)).isoformat(),
        date.today().isoformat(),
        settings.data.cache_dir,
    )
    strategy = STRATEGIES.get(spec.strategy)
    if strategy is None:
        return {"ok": False, "error": f"estrategia desconocida: {spec.strategy}"}
    result = strategy(df, **spec.params)
    target = float(result.target.iloc[-1])
    price = float(df["close"].iloc[-1])

    last_signal = None
    try:
        with connect(db_path) as con:
            row = con.execute(
                "SELECT ts, side, strength FROM signals WHERE bot = ? ORDER BY id DESC LIMIT 1",
                (spec.id,),
            ).fetchone()
        last_signal = dict(row) if row else None
    except Exception:
        last_signal = None

    match = None
    if last_signal and last_signal.get("strength") is not None:
        match = abs(float(last_signal["strength"]) - target) < 1e-6

    return {
        "ok": True,
        "ticker": spec.universe[0],
        "strategy": spec.strategy,
        "target": target,
        "price": price,
        "atr": float(atr(df).iloc[-1]),
        "last_signal": last_signal,
        "match": match,
    }


__all__ = [
    "DEFAULT_CRITERIA",
    "activate",
    "config_check",
    "config_hash",
    "daily_report",
    "execution_metrics",
    "freeze",
    "load_criteria",
    "record_snapshot",
    "signal_check",
    "status",
]

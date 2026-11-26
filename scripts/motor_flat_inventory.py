"""Inventario de campañas afectadas por ``flat_at`` con ``legacy``.

Solo lectura de ``discovery.db``. Escribe el informe y un aviso por plantilla
afectada en ``tl3_research.db``. No modifica campañas, estrategias ni plantillas.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tradinglab.config import ROOT
from tradinglab.discovery.timeframes import flat_at_fires
from tradinglab.tl3 import warnings

DISCOVERY_DB = ROOT / "data" / "discovery.db"
REPORT = ROOT / "TL3_REPORTS" / "motor_flat_inventario.md"
EXPORTS = ROOT / "exports" / "edge1"
FECHA = "2026-11-26"
ETAPA = "motor-flat"


def _campaigns(db_path: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, instrument, timeframe, template, status, config_json,"
            " created_at FROM disc_campaigns ORDER BY created_at"
        ).fetchall()
    finally:
        con.close()
    result: list[dict[str, Any]] = []
    for row in rows:
        config = json.loads(row["config_json"] or "{}")
        session = config.get("session") or {}
        item = {
            "id": row["id"],
            "instrument": row["instrument"],
            "timeframe": row["timeframe"],
            "template": row["template"] or "",
            "status": row["status"],
            "start": str(session.get("start") or "09:35"),
            "end": str(session.get("end") or "11:30"),
            "flat_at": str(session.get("flat_at") or "15:45"),
            "created_at": row["created_at"],
        }
        item["affected"] = not flat_at_fires(
            item["timeframe"], item["start"], item["end"], item["flat_at"]
        )
        item["kind"] = (
            "24 h" if item["start"] == "00:00" and item["end"] == "23:59" else "intradía"
        )
        result.append(item)
    return result


def _finalists(db_path: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT s.id, s.campaign_id, s.instrument, s.timeframe, s.verdict,"
            " c.template, c.config_json FROM disc_strategies s"
            " JOIN disc_campaigns c ON c.id = s.campaign_id"
            " WHERE s.status = 'finalist' AND s.campaign_id LIKE 'edge1-%'"
            " ORDER BY s.campaign_id, s.id"
        ).fetchall()
    finally:
        con.close()
    result: list[dict[str, Any]] = []
    for row in rows:
        config = json.loads(row["config_json"] or "{}")
        session = config.get("session") or {}
        item = {
            "id": int(row["id"]),
            "campaign_id": row["campaign_id"],
            "instrument": row["instrument"],
            "timeframe": row["timeframe"],
            "template": row["template"] or "",
            "verdict": row["verdict"] or "SIN VEREDICTO",
            "start": str(session.get("start") or "09:35"),
            "end": str(session.get("end") or "11:30"),
            "flat_at": str(session.get("flat_at") or "15:45"),
        }
        item["affected"] = not flat_at_fires(
            item["timeframe"], item["start"], item["end"], item["flat_at"]
        )
        item["label"] = (
            "mantiene varios días (swap; revisar las reglas de fin de semana)"
            if item["affected"]
            else "intradía correcto"
        )
        result.append(item)
    return result


def _eas() -> list[Path]:
    if not EXPORTS.exists():
        return []
    return sorted(path for path in EXPORTS.rglob("*") if path.is_file())


def build(db_path: Path = DISCOVERY_DB) -> dict[str, Any]:
    campaigns = _campaigns(db_path)
    affected = [item for item in campaigns if item["affected"]]
    by_template: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_pair: Counter[tuple[str, str]] = Counter()
    for item in affected:
        by_template[item["template"]].append(item)
        by_pair[(item["template"], item["timeframe"])] += 1
    finalists = _finalists(db_path)
    return {
        "campaigns": campaigns,
        "affected": affected,
        "by_template": dict(by_template),
        "by_pair": by_pair,
        "finalists": finalists,
        "eas": _eas(),
    }


def _table(rows: list[list[Any]], header: list[str]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def render(data: dict[str, Any]) -> str:
    campaigns = data["campaigns"]
    affected = data["affected"]
    finalists = data["finalists"]
    eas = data["eas"]
    n_intraday = sum(1 for item in affected if item["kind"] == "intradía")
    n_24h = len(affected) - n_intraday
    pair_rows = [
        [template, timeframe, count]
        for (template, timeframe), count in sorted(data["by_pair"].items())
    ]
    campaign_rows = [
        [
            item["id"],
            item["instrument"],
            item["timeframe"],
            item["template"],
            item["status"],
            f"{item['start']}-{item['end']}",
            item["flat_at"],
            item["kind"],
        ]
        for item in affected
    ]
    finalist_rows = [
        [
            item["campaign_id"],
            item["id"],
            item["instrument"],
            item["timeframe"],
            item["template"],
            item["verdict"],
            item["label"],
        ]
        for item in finalists
    ]
    lines = [
        "# Motor flat_mode · inventario de campañas afectadas",
        "",
        f"- Fecha: {FECHA}.",
        f"- Base: `{DISCOVERY_DB}` (solo lectura).",
        f"- Campañas totales: **{len(campaigns)}**; afectadas con `legacy`: **{len(affected)}**.",
        f"- De las afectadas: **{n_24h}** son de 24 h (varios días por diseño) y "
        f"**{n_intraday}** son intradía con TF no alineado (fallo real).",
        "- No se ha modificado ninguna campaña, estrategia ni plantilla.",
        "",
        "## Por plantilla y TF",
        "",
        _table(pair_rows, ["Plantilla", "TF", "Campañas"]),
        "",
        "## Campañas afectadas",
        "",
        _table(
            campaign_rows,
            ["Campaña", "Activo", "TF", "Plantilla", "Estado", "Sesión", "flat_at", "Tipo"],
        ),
        "",
        "## EDGE-1 · finalistas",
        "",
        f"Finalistas EDGE-1: **{len(finalists)}**. "
        f"Con `legacy`: **{sum(1 for item in finalists if item['affected'])}** mantienen "
        "varios días y "
        f"**{sum(1 for item in finalists if not item['affected'])}** son intradía correctos.",
        "",
        _table(
            finalist_rows,
            ["Campaña", "ID", "Activo", "TF", "Plantilla", "Veredicto", "Lectura"],
        ),
        "",
        "## EDGE-1 · EAs exportados",
        "",
    ]
    if eas:
        lines.append(_table([[path.relative_to(ROOT)] for path in eas], ["Fichero"]))
    else:
        lines.append("**Sin datos**: `exports/edge1/` no contiene EAs exportados.")
    lines.extend(
        [
            "",
            "## Lectura",
            "",
            "- Las plantillas de 24 h (`trend_pullback_mtf`, `vol_squeeze_breakout`, "
            "`donchian_vol_h4`, `fix_reversal`, `turn_of_month`, "
            "`d1_extension_reversion`) conservan `legacy`: su `flat_at` no dispara en "
            "TF ≥ M15 y por diseño mantienen posiciones varios días (con swap).",
            "- `st_reversal_idx` en M15/M30/H1 es un fallo real de sesión intradía: la "
            "posición puede dormir. La plantilla nueva `_v3` usa `no_overnight`; las "
            "campañas ya registradas no se tocan.",
            "- EDGE-1 no dejó EAs en `exports/edge1/`; no se inventan ficheros.",
            "",
        ]
    )
    return "\n".join(lines)


def write_warnings(data: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    for template, items in sorted(data["by_template"].items()):
        timeframes = sorted({item["timeframe"] for item in items})
        kinds = sorted({item["kind"] for item in items})
        if kinds == ["24 h"]:
            text = (
                f"flat_at no dispara con legacy en {'/'.join(timeframes)}: "
                "estrategia de varios días por diseño (swap)"
            )
        else:
            text = (
                f"flat_at no dispara con legacy en {'/'.join(timeframes)}: "
                "la posición puede dormir"
            )
        warning_id = warnings.add_warning(
            f"discovery:{template}",
            FECHA,
            ETAPA,
            text,
            cifras={
                "campaigns": len(items),
                "timeframes": timeframes,
                "kind": kinds,
            },
            source_path=str(REPORT.relative_to(ROOT)).replace("\\", "/"),
        )
        if warning_id is not None:
            ids.append(warning_id)
    return ids


def main() -> int:
    data = build()
    text = render(data)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    ids = write_warnings(data)
    print(f"campañas {len(data['campaigns'])} · afectadas {len(data['affected'])}")
    print(f"finalistas EDGE-1 {len(data['finalists'])} · EAs {len(data['eas'])}")
    print(f"avisos nuevos {len(ids)} · informe {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

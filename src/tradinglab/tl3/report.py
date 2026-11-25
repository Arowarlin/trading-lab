"""T4 · Escalera bruto → neto por componente."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

MDE_RULE = 2.49
STEPS = ("gross", "spread", "commission", "slippage", "swap")


def _summary(values: np.ndarray, *, n_boot: int, seed: int) -> dict[str, Any]:
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"n": 0, "mean": None, "ci95": None, "mde": None}
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(n_boot, values.size), replace=True).mean(axis=1)
    return {
        "n": int(values.size),
        "mean": float(values.mean()),
        "ci95": (
            float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)),
        ),
        "mde": MDE_RULE * float(values.std(ddof=1)) / np.sqrt(values.size)
        if values.size > 1
        else None,
    }


def ladder(
    trades: Iterable[dict[str, Any]] | pd.DataFrame,
    *,
    n_boot: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    frame = pd.DataFrame(list(trades)) if not isinstance(trades, pd.DataFrame) else trades.copy()
    missing = [column for column in STEPS if column not in frame.columns]
    if missing:
        raise ValueError("faltan columnas: " + ", ".join(missing))
    net = frame["gross"].astype(float)
    rows = [{"step": "gross", **_summary(net.to_numpy(float), n_boot=n_boot, seed=seed)}]
    for step in STEPS[1:]:
        net = net - frame[step].astype(float)
        rows.append(
            {
                "step": f"-{step}",
                **_summary(net.to_numpy(float), n_boot=n_boot, seed=seed),
            }
        )
    return {"steps": rows, "net": rows[-1]}


def status_table(db_path=None) -> str:
    """Último estado por hipótesis, en Markdown (append-only por rowid)."""

    from . import warnings as warnings_mod
    from .registry import DB, connect

    with connect(db_path or DB) as con:
        rows = con.execute(
            "SELECT h.hypothesis_id, h.parent_id, h.status, h.rejection_reason, h.created_at"
            " FROM hypotheses h"
            " JOIN (SELECT hypothesis_id, MAX(rowid) AS last FROM hypotheses GROUP BY hypothesis_id) x"
            " ON h.rowid = x.last"
            " ORDER BY h.rowid"
        ).fetchall()
    items = (
        warnings_mod.all_warnings(db_path=db_path)
        if db_path is not None
        else warnings_mod.all_warnings()
    )
    by_subject: dict[str, list[dict]] = {}
    for item in items:
        by_subject.setdefault(str(item["subject"]), []).append(item)
    subject_by_hypothesis = {
        "H-2026-008": "ea:us100-ftmo1",
        "H-2026-008b": "ea:us100-ftmo1",
        "H-2026-012": "ai_trader",
    }
    lines = [
        "| ID | Padre | Estado | Motivo | Creado | Avisos |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        subject = subject_by_hypothesis.get(str(row["hypothesis_id"]))
        related = by_subject.get(subject, []) if subject else []
        if related:
            last = related[-1]
            warning_cell = f"{len(related)} · {last['fecha']} {last['etapa']}"
        else:
            warning_cell = "—"
        lines.append(
            f"| {row['hypothesis_id']} | {row['parent_id'] or ''} | "
            f"{row['status']} | {row['rejection_reason'] or ''} | {row['created_at']} | "
            f"{warning_cell} |"
        )
    if items:
        last = items[-1]
        lines += [
            "",
            f"Avisos globales: **{len(items)}**. Último: {last['fecha']} · "
            f"{last['etapa']} ({last['subject']}).",
        ]
    else:
        lines += ["", "Avisos globales: **0**."]
    return "\n".join(lines)


__all__ = ["STEPS", "ladder", "status_table"]

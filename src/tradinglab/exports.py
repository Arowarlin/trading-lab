"""Exportaciones CSV/HTML con validación y vista previa.

No usa CDNs ni frameworks. Los archivos viven en `reports/exports` y nunca
incluyen secretos, PIN, tokens ni contenido de `.env`.
"""
from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ROOT, Settings
from .drift import build_drift
from .journal import build_journal
from .learning import list_lessons

EXPORT_DIR = ROOT / "reports" / "exports"
FORMATS = {"csv", "html"}
MAX_ROWS = 5_000


class ExportError(ValueError):
    pass


def _safe_out_dir(out_dir: str | Path | None) -> Path:
    path = Path(out_dir) if out_dir else EXPORT_DIR
    path = path.resolve()
    allowed = (ROOT / "reports").resolve()
    if path != allowed and allowed not in path.parents:
        raise ExportError("out_dir debe quedar dentro de reports/")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _filename(kind: str, fmt: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{kind}_{stamp}.{fmt}"


def _json_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["status"])
        writer.writeheader()
        if rows:
            for row in rows:
                writer.writerow({key: _json_cell(value) for key, value in row.items()})
        else:
            writer.writerow({"status": "Sin datos"})


def _write_html(path: Path, title: str, rows: list[dict], meta: dict) -> None:
    headers = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    head = "".join(f"<th>{html.escape(str(item))}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(
            f"<td>{html.escape(_json_cell(row.get(item)))}</td>" for item in headers
        ) + "</tr>"
        for row in rows[:MAX_ROWS]
    )
    if not rows:
        body = f'<tr><td colspan="{max(1, len(headers))}">Sin datos</td></tr>'
    meta_text = " · ".join(f"{key}: {value}" for key, value in meta.items())
    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body {{ margin: 24px; background: #0d1117; color: #e6edf3; font: 14px/1.5 "Segoe UI", Arial, sans-serif; }}
h1 {{ font-size: 20px; }} .muted {{ color: #8b949e; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
th, td {{ border: 1px solid #30363d; padding: 6px 8px; text-align: left; vertical-align: top; }}
th {{ background: #161b22; }} tr:nth-child(even) td {{ background: #11161d; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="muted">{html.escape(meta_text)}</p>
<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
</body></html>"""
    path.write_text(doc, encoding="utf-8")


def _export(
    kind: str,
    title: str,
    rows: list[dict],
    *,
    fmt: str,
    out_dir: str | Path | None,
    meta: dict,
) -> dict:
    if fmt not in FORMATS:
        raise ExportError("formato inválido: usa csv o html")
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS]
    directory = _safe_out_dir(out_dir)
    path = directory / _filename(kind, fmt)
    if fmt == "csv":
        _write_csv(path, rows)
    else:
        _write_html(path, title, rows, meta)
    return {
        "ok": True,
        "path": str(path),
        "format": fmt,
        "rows": len(rows),
        "preview": rows[:10],
        "preview_note": "Sin datos" if not rows else f"{min(10, len(rows))} filas",
        "meta": meta,
    }


def export_journal(
    db_path: str | Path,
    settings: Settings | None = None,
    *,
    fmt: str = "csv",
    out_dir: str | Path | None = None,
    limit: int = 500,
) -> dict:
    settings = settings or Settings()
    payload = build_journal(
        db_path, tz=settings.timezone, limit=min(MAX_ROWS, int(limit))
    )
    rows = [dict(item) for item in payload.get("trades") or []]
    return _export(
        "journal",
        "Diario de operaciones cerradas",
        rows,
        fmt=fmt,
        out_dir=out_dir,
        meta={
            "generated_at": payload.get("generated_at"),
            "total_trades": payload.get("total_trades", 0),
            "source": payload.get("source"),
        },
    )


def export_drift(
    db_path: str | Path,
    settings: Settings | None = None,
    *,
    fmt: str = "csv",
    out_dir: str | Path | None = None,
    min_trades: int = 20,
) -> dict:
    settings = settings or Settings()
    payload = build_drift(db_path, settings, min_trades=min_trades)
    rows = []
    for row in payload.get("bots") or []:
        rows.append(
            {
                "bot": row.get("bot"),
                "account": row.get("account"),
                "status": row.get("status"),
                "edge_status": row.get("edge_status"),
                "slippage_status": row.get("slippage_status"),
                "live_n": (row.get("live") or {}).get("n"),
                "live_sharpe": (row.get("live") or {}).get("sharpe"),
                "backtest_sharpe": (row.get("backtest") or {}).get("sharpe"),
                "live_expectancy": (row.get("live") or {}).get("expectancy"),
                "backtest_expectancy": (row.get("backtest") or {}).get("expectancy"),
                "slippage_p50_bps": (row.get("slippage") or {}).get("p50_bps"),
                "slippage_p95_bps": (row.get("slippage") or {}).get("p95_bps"),
                "reasons": row.get("reasons"),
            }
        )
    return _export(
        "drift",
        "Deriva live vs backtest",
        rows,
        fmt=fmt,
        out_dir=out_dir,
        meta={
            "generated_at": payload.get("generated_at"),
            "min_trades": payload.get("min_trades"),
            "seed": payload.get("seed"),
            "summary": payload.get("summary"),
        },
    )


def export_learning(
    db_path: str | Path,
    settings: Settings | None = None,
    *,
    fmt: str = "csv",
    out_dir: str | Path | None = None,
) -> dict:
    rows = list_lessons(db_path, settings=settings)
    safe_rows = [
        {
            "id": row.get("id"),
            "ts": row.get("ts"),
            "kind": row.get("kind"),
            "author": row.get("author"),
            "status": row.get("status"),
            "hypothesis": row.get("hypothesis"),
            "evidence": row.get("evidence"),
            "action": row.get("action"),
            "tests": row.get("tests"),
            "applied_at": row.get("applied_at"),
            "reverted_at": row.get("reverted_at"),
        }
        for row in rows
    ]
    return _export(
        "learning",
        "Lecciones y aprendizaje",
        safe_rows,
        fmt=fmt,
        out_dir=out_dir,
        meta={"lessons": len(safe_rows)},
    )


def list_exports(out_dir: str | Path | None = None) -> list[dict]:
    directory = _safe_out_dir(out_dir)
    rows = []
    for path in sorted(directory.glob("*"), reverse=True):
        if path.suffix.lower() not in {".csv", ".html"} or not path.is_file():
            continue
        stat = path.stat()
        rows.append(
            {
                "name": path.name,
                "path": str(path),
                "format": path.suffix.lower().lstrip("."),
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds"),
            }
        )
    return rows


def preview_file(path: str | Path, *, rows: int = 10) -> dict:
    target = Path(path).resolve()
    allowed = (ROOT / "reports").resolve()
    if allowed not in target.parents or not target.is_file():
        raise ExportError("archivo fuera de reports/ o inexistente")
    if target.suffix.lower() == ".csv":
        with target.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            data = [dict(row) for _, row in zip(range(max(1, rows)), reader)]
        return {"path": str(target), "format": "csv", "rows": data}
    if target.suffix.lower() == ".html":
        text = target.read_text(encoding="utf-8")
        return {
            "path": str(target),
            "format": "html",
            "rows": [],
            "html": text[:20_000],
            "truncated": len(text) > 20_000,
        }
    raise ExportError("solo se previsualizan CSV o HTML")


__all__ = [
    "EXPORT_DIR",
    "ExportError",
    "export_drift",
    "export_journal",
    "export_learning",
    "list_exports",
    "preview_file",
]
